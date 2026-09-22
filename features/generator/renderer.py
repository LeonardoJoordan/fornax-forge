from PySide6.QtGui import QPainter, QImage, QPixmap, QFont, QImageReader
from PySide6.QtCore import Qt, QPointF, QRectF, QBuffer, QByteArray, QIODevice
from html import unescape
import re
from pathlib import Path
from core.render_cache import get_background_proxy_path, infer_model_dir
from core.model_document import (
    adapt_model_page, normalize_model_document, validate_raster_dimensions,
)
from core.document_layers import layer_entries
from core.object_style import draw_shape, outline_margin, rounded_rect_path
from core.text_layout import PLACEHOLDER_PATTERN, build_document, text_geometry, resolve_rich_text
from core.dynamic_images import resolve_dynamic_image
from core.image_memory_cache import ImageMemoryCache


def signature_is_visible(signature: dict, row_data: dict | None) -> bool:
    """Resolve a visibilidade sem misturar as assinaturas de uma linha.

    O mapa por ``signature_id`` é o formato atual. O campo booleano antigo
    continua aceito somente quando esse mapa não existe, preservando modelos e
    chamadas de geração anteriores à separação das colunas.
    """
    values = row_data or {}
    visibility = values.get("__signature_visibility__")
    if isinstance(visibility, dict):
        signature_id = signature.get("signature_id")
        if signature_id in visibility:
            return bool(visibility[signature_id])
        return bool(signature.get("visible", True))

    legacy_visibility = values.get("__use_signature__")
    if legacy_visibility is not None:
        return bool(legacy_visibility)
    return bool(signature.get("visible", True))


def renderers_for_document(
    document: dict, dynamic_image_dir=None, asset_provider=None,
) -> list["NativeRenderer"]:
    """Cria o mesmo renderizador de prancheta para cada página do documento."""
    normalized = normalize_model_document(document)
    renderers = [
        NativeRenderer(
            adapt_model_page(normalized, page["page_id"]),
            asset_provider=asset_provider,
        )
        for page in normalized["pages"]
    ]
    directory = dynamic_image_dir or document.get("__dynamic_image_dir")
    image_cache = ImageMemoryCache()
    for renderer in renderers:
        renderer._image_cache = image_cache.fork()
        renderer.set_dynamic_image_directory(directory)
    return renderers

class NativeRenderer:
    def __init__(self, template_data: dict, asset_provider=None):
        if template_data.get("schema_version") == 4 and isinstance(template_data.get("pages"), list):
            raise ValueError(
                "NativeRenderer recebe uma única página. Use renderers_for_document()."
            )
        self.tpl = template_data
        canvas = self.tpl.get("canvas_size", {})
        validate_raster_dimensions(canvas.get("w"), canvas.get("h"), label="canvas")
        self.page_id = self.tpl.get("__page_id", "front")
        self.model_dir = infer_model_dir(self.tpl)
        self._image_cache = ImageMemoryCache()
        self._static_base_cache = None
        self._pixmap_cache = {}
        self.dynamic_image_dir = self.tpl.get("__dynamic_image_dir")
        self.asset_provider = asset_provider

    def set_dynamic_image_directory(self, directory):
        self.dynamic_image_dir = str(directory) if directory else None
        self._static_base_cache = None
        return self

    def fork(self):
        """Isola estado de pintura e compartilha o cache LRU protegido por lock."""
        renderer = NativeRenderer(self.tpl, asset_provider=self.asset_provider)
        renderer.model_dir = self.model_dir
        renderer.dynamic_image_dir = self.dynamic_image_dir
        renderer._image_cache = self._image_cache.fork()
        if self._static_base_cache is not None:
            renderer._static_base_cache = QImage(self._static_base_cache)
        return renderer

    def _get_image(self, path, *, external=False) -> QImage:
        path_str = str(path)
        cache_key = f"external:{path_str}" if external else path_str
        cached = self._image_cache.get(cache_key)
        if cached is not None:
            return cached

        img = QImage()
        if self.asset_provider is not None and not external:
            try:
                encoded = QByteArray(self.asset_provider(path_str))
                buffer = QBuffer(encoded)
                if buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                    reader = QImageReader(buffer)
                    reader.setAutoTransform(True)
                    img = reader.read()
            except Exception:
                img = QImage()
        else:
            reader = QImageReader(path_str)
            reader.setAutoTransform(True)
            img = reader.read()
            if img.isNull():
                img = QImage(path_str)
            
        self._image_cache[cache_key] = img
        return img

    def _draw_image_item(self, painter: QPainter, img: QImage, x, y, w, h, rotation=0, opacity=1.0) -> QRectF:
        painter.save()
        try:
            painter.setOpacity(opacity)
            if rotation:
                center_x = float(x) + (w / 2)
                center_y = float(y) + (h / 2)
                painter.translate(center_x, center_y)
                painter.rotate(rotation)
                target_rect = QRectF(-w / 2, -h / 2, w, h)
                painter.drawImage(target_rect, img, QRectF(img.rect()))
                return painter.transform().mapRect(target_rect)

            target_rect = QRectF(float(x), float(y), w, h)
            painter.drawImage(target_rect, img, QRectF(img.rect()))
            return target_rect
        finally:
            painter.restore()

    def pre_render_static_base(self):
        w, h = validate_raster_dimensions(
            self.tpl["canvas_size"]["w"], self.tpl["canvas_size"]["h"], label="canvas"
        )
        
        self._static_base_cache = QImage(w, h, QImage.Format_ARGB32)
        self._static_base_cache.setDotsPerMeterX(3780)
        self._static_base_cache.setDotsPerMeterY(3780)
        self._static_base_cache.fill(Qt.GlobalColor.white)

        painter = QPainter(self._static_base_cache)
        try:
            self._paint_card(painter, {}, out_links=None, static_only=True)
        finally:
            painter.end()

    def render_row(self, row_plain: dict, row_rich: dict, out_path: Path, out_links: list = None,
                   target_w_mm=None, target_h_mm=None):
        image = self.render_to_qimage(row_plain, row_rich, out_links=out_links)
        # Metadados físicos somente depois da pintura: o layout de texto usa 96 DPI.
        w_mm = target_w_mm or self.tpl.get("target_w_mm") or image.width() * 25.4 / 300
        h_mm = target_h_mm or self.tpl.get("target_h_mm") or image.height() * 25.4 / 300
        image.setDotsPerMeterX(round(image.width() * 1000 / w_mm))
        image.setDotsPerMeterY(round(image.height() * 1000 / h_mm))
        if not image.save(str(out_path), "PNG"):
            raise OSError(f"Não foi possível gravar {out_path}.")

    
    def render_to_pixmap(self, row_rich: dict = None, max_side: int = None, transparent=False) -> QPixmap:
        return QPixmap.fromImage(self.render_preview_image(row_rich, max_side, transparent))

    def render_preview_image(self, row_rich=None, max_side=None, transparent=False) -> QImage:
        """Prévia em QImage, utilizável em workers sem criar QPixmap."""
        w, h = validate_raster_dimensions(
            self.tpl["canvas_size"]["w"], self.tpl["canvas_size"]["h"], label="canvas"
        )

        scale = 1.0
        if max_side and max(w, h) > max_side:
            scale = max_side / max(w, h)
            render_w = max(1, int(round(w * scale)))
            render_h = max(1, int(round(h * scale)))
        else:
            render_w = w
            render_h = h
        
        image = QImage(render_w, render_h, QImage.Format_ARGB32)
        image.setDotsPerMeterX(3780) # Trava o Gerador em exatos 96 DPI
        image.setDotsPerMeterY(3780)
        image.fill(Qt.GlobalColor.transparent if transparent else Qt.GlobalColor.white)

        painter = QPainter(image)
        try:
            if scale != 1.0:
                painter.scale(scale, scale)
            if row_rich is None:
                placeholders = self.tpl.get("placeholders", [])
                row_rich = {p: f"{{{p}}}" for p in placeholders}
            self._paint_card(painter, row_rich)
        finally:
            painter.end()
        
        return image
    

    def render_to_qimage(self, row_plain: dict, row_rich: dict, out_links: list = None) -> QImage:
        if self._static_base_cache is not None:
            image = self._static_base_cache.copy()
        else:
            w, h = validate_raster_dimensions(
                self.tpl["canvas_size"]["w"], self.tpl["canvas_size"]["h"], label="canvas"
            )
            image = QImage(w, h, QImage.Format_ARGB32)
            image.setDotsPerMeterX(3780)
            image.setDotsPerMeterY(3780)
            image.fill(Qt.GlobalColor.white)

        painter = QPainter(image)
        try:
            is_dynamic = (self._static_base_cache is not None)
            self._paint_card(painter, row_rich, out_links, dynamic_only=is_dynamic, row_plain=row_plain)
        finally:
            painter.end()
        return image
    

    def resolve_html(self, html: str, row_rich: dict) -> str:
        def repl(match):
            key = match.group(1)
            return str(row_rich.get(key, ""))
        return re.sub(PLACEHOLDER_PATTERN, repl, html)
    

    @staticmethod
    def _normalize_link_url(raw_url) -> str:
        if raw_url is None:
            return ""

        url = re.sub(r"<[^>]+>", "", str(raw_url))
        url = unescape(url).strip()
        if url and not url.startswith(("http://", "https://", "mailto:", "tel:")):
            url = "https://" + url
        return url

    def _resolve_link_url(self, link_key: str, row_rich: dict, row_plain: dict = None) -> str:
        values = row_plain if row_plain is not None and link_key in row_plain else row_rich
        return self._normalize_link_url(values.get(link_key, ""))

    def _paint_card(self, painter, row_rich, out_links=None, static_only=False, dynamic_only=False, row_plain=None):
        if "layer_order" not in self.tpl and not self.tpl.get("shapes"):
            return self._paint_card_legacy(painter, row_rich, out_links, static_only, dynamic_only, row_plain)
        entries = layer_entries(self.tpl)
        masked_images = {
            image.get('object_id'): image
            for image in self.tpl.get('images', [])
            if image.get('mask_shape_id')
        }
        images_by_mask = {}
        for image in masked_images.values():
            images_by_mask.setdefault(image.get('mask_shape_id'), []).append(image)
        prefix = 0
        for _, kind, item in entries:
            if kind == "shape" and item.get("dynamic_image_field"):
                break
            if kind not in ("image", "shape") or (item.get("has_link") and item.get("link_key")):
                break
            prefix += 1
        for index, (_, kind, item) in enumerate(entries):
            if static_only and index >= prefix:
                break
            if dynamic_only and index < prefix:
                continue
            if kind == "shape":
                children = sorted(images_by_mask.get(item.get('object_id'), []),
                                  key=lambda value: value.get('mask_order', 0))
                rect = (
                    self._draw_dynamic_image_shape(
                        painter, item, row_rich, row_plain
                    )
                    if item.get("dynamic_image_field") else
                    self._draw_mask_group(
                        painter, item, children, row_rich, row_plain, out_links
                    )
                    if children else draw_shape(painter, item)
                )
                if rect is not None and item.get("has_link") and item.get("link_key") and out_links is not None:
                    url = self._resolve_link_url(item["link_key"], row_rich, row_plain)
                    if url:
                        out_links.append({"url": url, "rect": rect})
                continue
            if kind == 'image' and item.get('object_id') in masked_images:
                continue
            # A child view avoids mutating a renderer shared by batch workers.
            layer = {**self.tpl, "images": [], "boxes": [], "signatures": [], "background_path": None}
            layer.pop("layer_order", None)
            layer[{"image": "images", "text": "boxes", "signature": "signatures"}[kind]] = [item]
            child = NativeRenderer(layer, asset_provider=self.asset_provider)
            child.model_dir = self.model_dir
            child._image_cache = self._image_cache
            child._paint_card_legacy(painter, row_rich, out_links, row_plain=row_plain)

    def _draw_dynamic_image_shape(self, painter, shape, row_rich, row_plain):
        """Desenha a forma e, quando disponível, a imagem externa do registro."""
        if not shape.get("visible", True):
            return None
        rect = draw_shape(painter, shape)
        field = shape.get("dynamic_image_field")
        values = row_plain if row_plain is not None and field in row_plain else row_rich
        result = resolve_dynamic_image(self.dynamic_image_dir, (values or {}).get(field, ""))
        if result.path is None:
            return rect
        # Imagens dinâmicas vêm da pasta vinculada à planilha, fora do
        # pacote do modelo, e precisam continuar usando o sistema de arquivos.
        source = self._get_image(result.path, external=True)
        if source.isNull():
            return rect

        w = float(shape.get("width", 0))
        h = float(shape.get("height", 0))
        if w <= 0 or h <= 0:
            return rect
        sw, sh = float(source.width()), float(source.height())
        if sw <= 0 or sh <= 0:
            return rect

        painter.save()
        try:
            painter.translate(float(shape.get("x", 0)) + w / 2,
                              float(shape.get("y", 0)) + h / 2)
            painter.rotate(float(shape.get("rotation", 0)))
            painter.translate(-w / 2, -h / 2)
            painter.setClipPath(self._mask_local_path(shape), Qt.ClipOperation.IntersectClip)
            painter.setOpacity(float(shape.get("opacity", 1.0)))
            if shape.get("dynamic_image_fit", "cover") == "contain":
                scale = min(w / sw, h / sh)
                target_w, target_h = sw * scale, sh * scale
                target = QRectF((w - target_w) / 2, (h - target_h) / 2,
                                target_w, target_h)
                painter.drawImage(target, source, QRectF(source.rect()))
            else:
                scale = max(w / sw, h / sh)
                source_w, source_h = w / scale, h / scale
                source_rect = QRectF((sw - source_w) / 2, (sh - source_h) / 2,
                                     source_w, source_h)
                painter.drawImage(QRectF(0, 0, w, h), source, source_rect)
        finally:
            painter.restore()
        if shape.get("outline_enabled"):
            overlay = dict(shape)
            overlay["fill_opacity"] = 0.0
            draw_shape(painter, overlay)
        return rect

    def _resolve_asset_path(self, raw_path):
        path = Path(raw_path or '')
        if not path.is_absolute() and self.model_dir:
            path = self.model_dir / path
        if path.exists():
            return path
        try:
            from core.template_manager import slugify_model_name
            from core.paths import get_models_dir
            if 'name' in self.tpl:
                candidate = get_models_dir() / slugify_model_name(self.tpl['name']) / str(raw_path or '')
                if candidate.exists():
                    return candidate
        except ImportError:
            pass
        return path

    @staticmethod
    def _mask_local_path(shape):
        w = float(shape.get('width', 0))
        h = float(shape.get('height', 0))
        bounds = QRectF(0, 0, w, h)
        if shape.get('shape_type') in ('ellipse', 'circle'):
            from PySide6.QtGui import QPainterPath
            path = QPainterPath()
            path.addEllipse(bounds)
            return path
        radii = dict(shape.get('corner_radii') or {})
        radii.setdefault('all', max(0.0, float(shape.get('corner_radius', 0))))
        return rounded_rect_path(bounds, radii)

    def _draw_mask_group(self, painter, shape, images, row_rich, row_plain, out_links):
        if not shape.get('visible', True):
            return None
        rect = draw_shape(painter, shape)
        w = float(shape.get('width', 0))
        h = float(shape.get('height', 0))
        painter.save()
        try:
            painter.translate(float(shape.get('x', 0)) + w / 2,
                              float(shape.get('y', 0)) + h / 2)
            painter.rotate(float(shape.get('rotation', 0)))
            painter.translate(-w / 2, -h / 2)
            painter.setClipPath(self._mask_local_path(shape), Qt.ClipOperation.IntersectClip)
            for image in images:
                if not image.get('visible', True):
                    continue
                raw_path = image.get('path', '')
                path = raw_path if self.asset_provider is not None else self._resolve_asset_path(raw_path)
                if self.asset_provider is None and not path.exists():
                    continue
                source = self._get_image(path)
                iw = float(image.get('width', 0))
                ih = float(image.get('height', 0))
                if source.isNull() or iw <= 0 or ih <= 0:
                    continue
                image_rect = self._draw_image_item(
                    painter, source,
                    float(image.get('x', 0)), float(image.get('y', 0)),
                    iw, ih, image.get('rotation', 0),
                    float(image.get('opacity', 1.0)) * float(shape.get('opacity', 1.0)),
                )
        finally:
            painter.restore()
        if shape.get('outline_enabled'):
            overlay = dict(shape)
            overlay['fill_opacity'] = 0.0
            draw_shape(painter, overlay)
        return rect

    def _paint_card_legacy(self, painter: QPainter, row_rich: dict, out_links: list = None, static_only: bool = False, dynamic_only: bool = False, row_plain: dict = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Criamos uma fonte base com estratégia de outline para evitar o "hinting" (ajuste de pixel da tela)
        # Isso garante que o glifo seja desenhado exatamente onde as coordenadas flutuantes mandam.
        base_font = QFont()
        base_font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
        painter.setFont(base_font)

        if not dynamic_only and self.tpl.get("background_path"):
            bg_props = self.tpl.get("bg_props", {})
            if bg_props.get("visible", True):
                proxy_path = None if self.asset_provider is not None else get_background_proxy_path(self.model_dir, self.tpl)
                proxy_drawn = False
                if proxy_path:
                    bg = self._get_image(proxy_path)
                    if not bg.isNull():
                        painter.drawImage(
                            QRectF(0, 0, self.tpl["canvas_size"]["w"], self.tpl["canvas_size"]["h"]),
                            bg,
                            QRectF(bg.rect()),
                        )
                        proxy_drawn = True
                if not proxy_drawn:
                    bg_path = self.tpl["background_path"]
                    if self.asset_provider is None:
                        bg_path = Path(bg_path)
                        if not bg_path.is_absolute() and self.model_dir:
                            bg_path = self.model_dir / bg_path
                    bg = self._get_image(bg_path)
                    if not bg.isNull():
                        w = bg_props.get("w", self.tpl["canvas_size"]["w"])
                        h = bg_props.get("h", self.tpl["canvas_size"]["h"])
                        x = bg_props.get("x", 0)
                        y = bg_props.get("y", 0)
                        
                        painter.setOpacity(bg_props.get("opacity", 1.0))
                        painter.drawImage(QRectF(float(x), float(y), w, h), bg, QRectF(bg.rect()))
                        painter.setOpacity(1.0)

        for img in self.tpl.get("images", []):
            if not img.get("visible", True):
                continue

            is_linked = bool(img.get("has_link") and img.get("link_key"))
            if static_only and is_linked: continue
            if dynamic_only and not is_linked: continue
            
            raw_path = img.get("path", "")
            if self.asset_provider is not None:
                pix = self._get_image(raw_path)
                w, h = img.get("width", 0), img.get("height", 0)
                if not pix.isNull() and w > 0 and h > 0:
                    rect = self._draw_image_item(
                        painter, pix, float(img.get("x", 0)), float(img.get("y", 0)),
                        w, h, img.get("rotation", 0), img.get("opacity", 1.0),
                    )
                    if img.get("has_link") and img.get("link_key"):
                        url = self._resolve_link_url(img["link_key"], row_rich, row_plain)
                        if url and out_links is not None:
                            out_links.append({"url": url, "rect": rect})
                continue
            img_path = Path(raw_path)
            if not img_path.is_absolute() and self.model_dir:
                img_path = self.model_dir / img_path
            
            # Fallback de resolução de caminho (resolve assets relativos quando acionado via gerador)
            if not img_path.exists():
                # 1. Tenta achar matematicamente pelo nome do modelo (Pareto)
                try:
                    from core.template_manager import slugify_model_name
                    from core.paths import get_models_dir
                    if "name" in self.tpl:
                        alt_path = get_models_dir() / slugify_model_name(self.tpl["name"]) / raw_path
                        if alt_path.exists(): 
                            img_path = alt_path
                except ImportError:
                    pass
                
                # 2. Hack antigo via background (mantido como segurança extra)
                if not img_path.exists() and self.tpl.get("background_path"):
                    bg_path = Path(self.tpl["background_path"])
                    if bg_path.is_absolute():
                        alt_path = bg_path.parent.parent / raw_path
                        if alt_path.exists(): 
                            img_path = alt_path

            if img_path.exists():
                pix = self._get_image(img_path)
                w, h = img.get("width", 0), img.get("height", 0)
                
                # Blindagem contra corrompimento de QImage/QPixmap ou dimensões ausentes
                if not pix.isNull() and w > 0 and h > 0:
                    rect = self._draw_image_item(
                        painter,
                        pix,
                        float(img.get("x", 0)),
                        float(img.get("y", 0)),
                        w,
                        h,
                        img.get("rotation", 0),
                        img.get("opacity", 1.0),
                    )

                    if img.get("has_link") and img.get("link_key"):
                        url = self._resolve_link_url(img["link_key"], row_rich, row_plain)
                        if url and out_links is not None:
                            out_links.append({"url": url, "rect": rect})

        def _is_empty_placeholder_value(var_name: str) -> bool:
            """
            Retorna True quando o placeholder não tem conteúdo útil na linha atual.
            Remove tags HTML antes de testar, preservando a mesma lógica antiga.
            """
            val = row_rich.get(var_name, "")
            clean_val = re.sub(r"<[^>]+>", "", str(val)).strip()
            return not clean_val

        def _process_optional_blocks(html_text: str) -> str:
            """
            Processa blocos opcionais usando pipe, mas somente quando o conteúdo
            entre os pipes possui pelo menos um placeholder.

            Bloco opcional válido:
                |texto com {placeholder}|

            Trecho comum ignorado:
                | texto sem placeholder |
            """

            def replace_optional_block(match):
                block_content = match.group(1)
                vars_in_block = re.findall(PLACEHOLDER_PATTERN, block_content)

                for var in vars_in_block:
                    if _is_empty_placeholder_value(var):
                        return ""

                return block_content

            optional_block_pattern = r"\|([^|]*\{[\w]+\}[^|]*)\|"

            return re.sub(optional_block_pattern, replace_optional_block, html_text)
        
        if static_only:
            return  # Caixas de texto e assinaturas são exclusivamente dinâmicas

        for box in self.tpl.get("boxes", []):
            if not box.get("visible", True):
                continue

            html_original = box["html"]
            if box.get("rich_text_version") == 1:
                resolved = resolve_rich_text(box, row_rich)
                if resolved is not None:
                    painter.setOpacity(box.get("opacity", 1.0))
                    self._draw_html_box(painter, box, resolved, row_rich, out_links, row_plain)
                    painter.setOpacity(1.0)
                continue

            # 1. Primeiro resolve os blocos opcionais | ... |
            html_processado = _process_optional_blocks(html_original)

            # 2. Depois mantém a regra antiga:
            # se ainda sobrou placeholder vazio fora dos blocos opcionais,
            # a caixa inteira continua sumindo.
            needed_vars = re.findall(PLACEHOLDER_PATTERN, html_processado)
            should_skip = False

            for var in needed_vars:
                if _is_empty_placeholder_value(var):
                    should_skip = True
                    break
            
            if should_skip:
                continue

            try:
                html_resolved = self.resolve_html(html_processado, row_rich)
                painter.setOpacity(box.get("opacity", 1.0))
                self._draw_html_box(painter, box, html_resolved, row_rich, out_links, row_plain)
                painter.setOpacity(1.0)
            except Exception as e:
                print(f"[WARN] Erro ao desenhar caixa de texto: {e}")
                continue

        for sig in self.tpl.get("signatures", []):
            # Assinaturas dependem da linha e nunca podem ser incorporadas à
            # base estática, pois cada coluna pode ligá-las separadamente.
            if static_only or not signature_is_visible(sig, row_rich):
                continue

            raw_sig = sig["path"]
            if self.asset_provider is not None:
                pix = self._get_image(raw_sig)
                if not pix.isNull():
                    self._draw_image_item(
                        painter, pix, float(sig.get("x", 0)), float(sig.get("y", 0)),
                        sig["width"], sig["height"], sig.get("rotation", 0),
                        sig.get("opacity", 1.0),
                    )
                continue
            sig_path = Path(raw_sig)
            if not sig_path.is_absolute() and self.model_dir:
                sig_path = self.model_dir / sig_path

            if not sig_path.exists():
                try:
                    from core.template_manager import slugify_model_name
                    from core.paths import get_models_dir
                    if "name" in self.tpl:
                        alt_path = get_models_dir() / slugify_model_name(self.tpl["name"]) / raw_sig
                        if alt_path.exists():
                            sig_path = alt_path
                except ImportError:
                    pass

                if not sig_path.exists() and self.tpl.get("background_path"):
                    bg_path = Path(self.tpl["background_path"])
                    if bg_path.is_absolute():
                        alt_path = bg_path.parent.parent / raw_sig
                        if alt_path.exists():
                            sig_path = alt_path

            if sig_path.exists():
                pix = self._get_image(sig_path)
                if not pix.isNull():
                    self._draw_image_item(
                        painter,
                        pix,
                        float(sig.get("x", 0)),
                        float(sig.get("y", 0)),
                        sig["width"],
                        sig["height"],
                        sig.get("rotation", 0),
                        sig.get("opacity", 1.0),
                    )
    
    
    def _draw_html_box(self, painter, box_data, html_text, row_rich=None, out_links=None, row_plain=None):
        painter.save()
        try:
            doc = build_document(box_data, html_text)
            w, h = box_data.get("w", 300), box_data.get("h", 100)
            rotation = box_data.get("rotation", 0)
            align_str = box_data.get("align", "left")
            y_offset, real_top, content_h = text_geometry(doc, box_data)

            center_x = box_data.get("x", 0) + (w / 2)
            center_y = box_data.get("y", 0) + (h / 2)
            
            painter.translate(center_x, center_y)
            painter.rotate(rotation)
            painter.translate(-w / 2, -h / 2)
            
            margin = outline_margin(box_data)
            painter.setClipRect(QRectF(-margin, -10000, w+2*margin, 20000))
            painter.translate(0, y_offset)
            doc.drawContents(painter)
            
            # Mapeamento do Hiperlink isolado
            if box_data.get("has_link") and box_data.get("link_key") and out_links is not None:
                url = self._resolve_link_url(box_data["link_key"], row_rich or {}, row_plain)
                if url:
                    ideal_w = min(doc.idealWidth(), w)
                    # Calcula x_start baseado no alinhamento horizontal
                    if align_str == "center":
                        x_start = (w - ideal_w) / 2
                    elif align_str == "right":
                        x_start = w - ideal_w
                    else:
                        x_start = 0
                    # real_top é o topo da tinta no espaço local do doc (antes do y_offset)
                    # y_offset desloca o doc inteiro; o topo real no espaço da caixa é real_top + y_offset
                    local_rect = QRectF(x_start, real_top, ideal_w, content_h)
                    mapped_rect = painter.transform().mapRect(local_rect)
                    out_links.append({"url": url, "rect": mapped_rect})

        except Exception as e:
            print(f"[WARN] Falha interna no layout do texto: {e}")
        finally:
            # ESTA LINHA É A CURA DO EFEITO CASCATA. Sempre será executada!
            painter.restore()
