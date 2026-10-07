"""Prévia e exportação do quadro sem um bitmap gigante intermediário."""
from copy import deepcopy
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt, QRectF, QThread, Signal, QMarginsF, QPointF
from PySide6.QtGui import QPainter, QImage, QPen, QColor, QPdfWriter, QPageLayout, QFont

from core.model_document import adapt_model_page, normalize_model_document, validate_raster_dimensions
from core.organogram import assignment_plan, assignment_issue_text, board_bounds, slot_rect, UNITS_PER_MM
from core.text_layout import variables_in_html
from core.board_connectors import connector_style, connector_pen, connector_paths, text_cutouts, connector_clip
from core.board_borders import paint_group_borders, card_clip_path
from core.i18n import tr
from core.naming_engine import confined_output_path
from core.tiling import build_tile_plan, MARK_GAP_MM, MARK_LENGTH_MM
from .renderer import NativeRenderer
from .workers import physical_page, pdf_painter
from .pdf_links import inject_pdf_links


class OrganogramRenderer:
    def __init__(self, document, rows_plain, rows_rich=None, *, asset_provider=None, dynamic_image_dir=None,
                 layout_preview=False, fixed_layout=False):
        self.document = normalize_model_document(document)
        self.board = self.document["organogram"]
        self.paths = connector_paths(self.board)
        self.card = NativeRenderer(adapt_model_page(self.document), asset_provider=asset_provider)
        self.card.set_dynamic_image_directory(dynamic_image_dir)
        self.layout_preview = layout_preview
        self.layout_values = {name: f"{{{name}}}" for name in self.card.tpl.get("placeholders", [])}
        if layout_preview:
            # Mostra o desenho sem inventar registros nem alterar a distribuição da exportação.
            for box in self.board.get("boxes", []):
                for name in variables_in_html(box.get("html", "")):
                    self.layout_values[name] = f"{{{name}}}"
            self.slots = [(group["id"], index, slot_rect(group, index), self.layout_values, self.layout_values)
                          for group in self.board["groups"]
                          for index in range(group["rows"] * group["columns"])]
            self.assignment_issues = []
        else:
            self.slots, self.assignment_issues = assignment_plan(self.document, rows_plain, rows_rich, dynamic_image_dir)
        self.group_slots = {}
        for slot in self.slots:
            self.group_slots.setdefault(slot[0], []).append(slot)
        self.bounds = board_bounds(self.board, visible_slots=None if fixed_layout else self.slots)
        # O desenho complementar pode ultrapassar a página 1, mas não aloca raster.
        artwork = adapt_model_page(self.document)
        for key in ("boxes", "images", "shapes", "signatures", "layer_order", "background_path"):
            artwork[key] = deepcopy(self.board.get(key))
        # Máscara e imagens contidas nela pertencem ao mesmo plano.
        mask_positions = {entry.get("object_id"): entry.get("board_behind", False)
                          for entry in artwork.get("shapes", [])}
        self.artwork_planes = {}
        for behind in (True, False):
            plane = deepcopy(artwork)
            identifiers = set()
            for collection in ("boxes", "images", "shapes"):
                plane[collection] = [entry for entry in plane.get(collection, [])
                                     if mask_positions.get(entry.get("mask_shape_id"),
                                                           entry.get("board_behind", False)) == behind]
                identifiers.update(entry.get("object_id") for entry in plane[collection])
            plane["layer_order"] = [key for key in (plane.get("layer_order") or []) if key in identifiers]
            self.artwork_planes[behind] = NativeRenderer(plane, asset_provider=asset_provider)

    def paint(self, painter, *, region=None, stop=None, out_links=None):
        region = region or self.bounds
        painter.save()
        try:
            painter.setClipRect(region, Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            artwork_values = self.layout_values if self.layout_preview else {}
            self.artwork_planes[True].paint_card(painter, artwork_values, artwork_values, out_links)
            visible = {slot[0] for slot in self.slots}
            painter.save()
            try:
                foreground_text = [box for box in self.board.get("boxes", []) if not box.get("board_behind", False)]
                painter.setClipPath(connector_clip(region, text_cutouts(foreground_text)), Qt.ClipOperation.IntersectClip)
                for edge in self.board["connections"]:
                    if edge["source"] in visible and edge["target"] in visible:
                        style = connector_style(edge, self.board)
                        painter.setPen(connector_pen(style))
                        painter.drawPath(self.paths[(edge["source"], edge["target"])])
            finally:
                painter.restore()
            canvas = self.document["canvas_size"]
            # Mantém a mesma ordem de sobreposição dos conjuntos no editor.
            for group in self.board["groups"]:
                slots = self.group_slots.get(group["id"], [])
                for _group_id, _index, rect, plain, rich in slots:
                    if stop and stop():
                        raise InterruptedError(tr("Geração cancelada."))
                    if not region.intersects(rect):
                        continue
                    painter.save()
                    try:
                        painter.setClipPath(card_clip_path(group, rect), Qt.ClipOperation.IntersectClip)
                        painter.translate(rect.topLeft())
                        painter.scale(rect.width() / canvas["w"], rect.height() / canvas["h"])
                        self.card.paint_card(painter, plain, rich, out_links)
                    finally:
                        painter.restore()
                # Vagas não ganham bordas; conjuntos totalmente vazios ficam ocultos.
                if slots:
                    paint_group_borders(painter, group, (slot[2] for slot in slots))
            self.artwork_planes[False].paint_card(painter, artwork_values, artwork_values, out_links)
        finally:
            painter.restore()

    def preview(self, max_side=1600, stop=None):
        scale = max_side / max(self.bounds.width(), self.bounds.height())
        width = max(1, round(self.bounds.width() * scale))
        height = max(1, round(self.bounds.height() * scale))
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.setDotsPerMeterX(3780)
        image.setDotsPerMeterY(3780)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.scale(scale, scale)
            painter.translate(-self.bounds.left(), -self.bounds.top())
            self.paint(painter, stop=stop)
        finally:
            painter.end()
        return image

    def export_png(self, path, dpi=150, stop=None):
        scale = dpi / 300
        width = max(1, math.ceil(self.bounds.width() * scale))
        height = max(1, math.ceil(self.bounds.height() * scale))
        try:
            validate_raster_dimensions(width, height, label="quadro PNG")
        except ValueError as error:
            raise ValueError(tr("O quadro excede o tamanho seguro para PNG nessa resolução. Escolha PDF ou divida em ladrilhos.")) from error
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        if image.isNull():
            raise MemoryError(tr("Não foi possível reservar memória para o PNG."))
        image.setDotsPerMeterX(3780)
        image.setDotsPerMeterY(3780)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.scale(scale, scale)
            painter.translate(-self.bounds.left(), -self.bounds.top())
            self.paint(painter, stop=stop)
        finally:
            painter.end()
        image.setDotsPerMeterX(round(dpi * 1000 / 25.4))
        image.setDotsPerMeterY(round(dpi * 1000 / 25.4))
        if not image.save(str(path), "PNG"):
            raise OSError(tr("Não foi possível gravar o PNG."))

    def mosaic_regions(self, paper=(210, 297), *, margin_mm=10, overlap_mm=5):
        plan = build_tile_plan(self.bounds, paper, margin_mm=margin_mm, overlap_mm=overlap_mm)
        return [(tile.column, tile.row, tile.region) for tile in plan.tiles]

    def paint_tile(self, painter, plan, tile, *, stop=None):
        """Pinta no tamanho físico da folha; chamador define somente o DPI."""
        margin = plan.margin_mm * UNITS_PER_MM
        painter.save()
        try:
            painter.translate(margin - tile.region.left(), margin - tile.region.top())
            painter.translate(plan.drawing_bounds.topLeft())
            painter.scale(plan.scale, plan.scale)
            painter.translate(-plan.source_bounds.left(), -plan.source_bounds.top())
            source_region = QRectF(
                plan.source_bounds.left() + (tile.region.left() - plan.drawing_bounds.left()) / plan.scale,
                plan.source_bounds.top() + (tile.region.top() - plan.drawing_bounds.top()) / plan.scale,
                tile.region.width() / plan.scale, tile.region.height() / plan.scale)
            links = []
            painter.setClipRect(source_region, Qt.ClipOperation.IntersectClip)
            visible = source_region.intersected(self.bounds)
            if not visible.isEmpty():
                self.paint(painter, region=visible, stop=stop, out_links=links)
            clip = painter.transform().mapRect(source_region)
            links = [{**link, 'rect': link['rect'].intersected(clip)}
                     for link in links if link['rect'].intersects(clip)]
        finally:
            painter.restore()
        if plan.crop_marks:
            painter.save()
            try:
                painter.setPen(QPen(QColor('#000000'), 0.2 * UNITS_PER_MM))
                gap, length = MARK_GAP_MM * UNITS_PER_MM, MARK_LENGTH_MM * UNITS_PER_MM
                right = margin + tile.region.width()
                bottom = margin + tile.region.height()
                for x in (margin, margin + tile.trim.width()):
                    painter.drawLine(QPointF(x, margin - gap), QPointF(x, margin - gap - length))
                    painter.drawLine(QPointF(x, bottom + gap), QPointF(x, bottom + gap + length))
                for y in (margin, margin + tile.trim.height()):
                    painter.drawLine(QPointF(margin - gap, y), QPointF(margin - gap - length, y))
                    painter.drawLine(QPointF(right + gap, y), QPointF(right + gap + length, y))
                # Identificação acompanha as marcas, sempre na margem, fora da arte.
                font = QFont()
                font.setPixelSize(round(2.5 * UNITS_PER_MM))
                painter.setFont(font)
                label_rect = QRectF(margin, (plan.paper[1] - plan.margin_mm) * UNITS_PER_MM,
                                    (plan.paper[0] - 2 * plan.margin_mm) * UNITS_PER_MM, margin)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, tile.name)
            finally:
                painter.restore()
        return links

    def tile_image(self, plan, tile, *, scale, stop=None):
        width = max(1, math.ceil(plan.paper[0] * UNITS_PER_MM * scale))
        height = max(1, math.ceil(plan.paper[1] * UNITS_PER_MM * scale))
        validate_raster_dimensions(width, height, label='folha em ladrilhos')
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        if image.isNull():
            raise MemoryError(tr("Não foi possível reservar memória para a folha."))
        image.setDotsPerMeterX(3780)
        image.setDotsPerMeterY(3780)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.scale(scale, scale)
            self.paint_tile(painter, plan, tile, stop=stop)
        finally:
            painter.end()
        return image

    def export_tile_png(self, path, plan, tile, *, dpi=150, stop=None):
        image = self.tile_image(plan, tile, scale=dpi / 300, stop=stop)
        image.setDotsPerMeterX(round(dpi * 1000 / 25.4))
        image.setDotsPerMeterY(round(dpi * 1000 / 25.4))
        if not image.save(str(path), 'PNG'):
            raise OSError(tr("Não foi possível gravar o PNG."))

    def export_pdf(self, path, *, paper=None, plan=None, tiles=None, stop=None, progress=None):
        w_mm, h_mm = self.bounds.width() / UNITS_PER_MM, self.bounds.height() / UNITS_PER_MM
        if paper is None and plan is None and max(w_mm, h_mm) > 5000:
            raise ValueError(tr("Para quadros maiores que 5 m, divida o PDF em ladrilhos."))
        writer = QPdfWriter(str(path))
        # O layout de texto usa o mesmo DPI lógico do editor/prévia.
        writer.setResolution(96)
        writer.setTitle(tr("Quadro de pessoas — FORNAX Forge"))
        if plan is None and paper is not None:
            plan = build_tile_plan(self.bounds, paper, margin_mm=10, overlap_mm=5)
        page_w, page_h = plan.paper if plan is not None else (w_mm, h_mm)
        writer.setPageLayout(QPageLayout(physical_page(page_w, page_h),
                                        QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
        pages = tuple(tiles) if tiles is not None else plan.tiles if plan is not None else (None,)
        links_by_page = {}
        painter = pdf_painter(writer)
        try:
            for index, tile in enumerate(pages):
                if stop and stop():
                    raise InterruptedError(tr("Geração cancelada."))
                if index and not writer.newPage():
                    raise OSError(tr("Não foi possível adicionar uma folha ao PDF."))
                painter.save()
                try:
                    painter.scale(96 / 300, 96 / 300)
                    if tile is not None:
                        links_by_page[index] = self.paint_tile(painter, plan, tile, stop=stop)
                    else:
                        painter.translate(-self.bounds.left(), -self.bounds.top())
                        links = []
                        self.paint(painter, stop=stop, out_links=links)
                        clip = painter.transform().mapRect(self.bounds)
                        links_by_page[index] = [{**link, 'rect': link['rect'].intersected(clip)}
                                                for link in links if link['rect'].intersects(clip)]
                finally:
                    painter.restore()
                if progress:
                    progress(index + 1, len(pages))
        finally:
            painter.end()
        del writer
        inject_pdf_links(path, links_by_page, page_w * 96 / 25.4,
                         page_h * 96 / 25.4, memory_only=True, page_size_mm=(page_w, page_h),
                         page_labels=[tile.name for tile in pages] if plan is not None else None)


class OrganogramWorker(QThread):
    progress_updated = Signal(int)
    log_updated = Signal(str)
    error_occurred = Signal(str)
    finished_process = Signal()

    def __init__(self, document, rows_plain, rows_rich, output_dir, mode, *, dpi=150,
                 asset_provider=None, dynamic_image_dir=None, authorized_snapshot=None, parent=None,
                 tiling_options=None, separate_files=False):
        super().__init__(parent)
        self.args = (deepcopy(document), deepcopy(rows_plain), deepcopy(rows_rich))
        self.output_dir = Path(output_dir)
        self.mode, self.dpi = mode, dpi
        self.asset_provider, self.dynamic_image_dir = asset_provider, dynamic_image_dir
        self.tiling_options = deepcopy(tiling_options)
        self.separate_files = separate_files
        self.authorized_snapshot = authorized_snapshot
        self._is_running = True

    def stop(self):
        self.requestInterruption()
        self.wait()

    def run(self):
        extension = "png" if self.mode == "png" else "pdf"
        published = []
        try:
            renderer = OrganogramRenderer(*self.args, asset_provider=self.asset_provider,
                                         dynamic_image_dir=self.dynamic_image_dir,
                                         fixed_layout=self.tiling_options is not None or self.mode in ('a4', 'a3'))
            if renderer.assignment_issues:
                raise ValueError(tr("Corrija a distribuição dos registros antes de gerar:\n{pendencias}").format(
                    pendencias=assignment_issue_text(renderer.assignment_issues)))
            if not renderer.slots:
                raise ValueError(tr("Não há cartões com informações válidas nos blocos do quadro."))
            options = self.tiling_options
            if options is None and self.mode in ('a4', 'a3'):
                options = {'paper': (210, 297) if self.mode == 'a4' else (297, 420),
                           'margin_mm': 10, 'overlap_mm': 5, 'crop_marks': True}
            plan = build_tile_plan(renderer.bounds, **options) if options is not None else None
            separate = plan is not None and (self.separate_files or self.mode == 'png')
            filenames = ([f'organograma_{tile.name}.{extension}' for tile in plan.tiles] if separate
                         else [f'organograma.{extension}'])
            finals = [confined_output_path(self.output_dir, name) for name in filenames]
            if any(path.exists() for path in finals):
                raise FileExistsError(tr("Já existe um arquivo com o mesmo nome na pasta de saída."))
            with TemporaryDirectory(prefix='.organograma-', dir=self.output_dir) as staging:
                temporary = [confined_output_path(staging, name) for name in filenames]
                if separate:
                    for index, (tile, path) in enumerate(zip(plan.tiles, temporary)):
                        if self.isInterruptionRequested():
                            raise InterruptedError(tr("Geração cancelada."))
                        if self.mode == 'png':
                            renderer.export_tile_png(path, plan, tile, dpi=self.dpi, stop=self.isInterruptionRequested)
                        else:
                            renderer.export_pdf(path, plan=plan, tiles=(tile,), stop=self.isInterruptionRequested)
                        self.progress_updated.emit(round(95 * (index + 1) / len(plan.tiles)))
                elif self.mode == 'png':
                    renderer.export_png(temporary[0], self.dpi, self.isInterruptionRequested)
                else:
                    renderer.export_pdf(temporary[0], plan=plan, stop=self.isInterruptionRequested,
                                        progress=lambda done, total: self.progress_updated.emit(round(95 * done / total)))
                for source, target in zip(temporary, finals):
                    if self.isInterruptionRequested():
                        raise InterruptedError(tr("Geração cancelada."))
                    source.replace(target)
                    published.append(target)
            self.progress_updated.emit(100)
            self.log_updated.emit(tr("Quadro gerado: {arquivos} arquivo(s), {folhas} folha(s), {quantidade} cartões.").format(
                arquivos=len(finals), folhas=len(plan.tiles) if plan else 1, quantidade=len(renderer.slots)))
        except Exception as error:
            for path in published:
                path.unlink(missing_ok=True)
            self.error_occurred.emit(str(error))
        finally:
            if self.authorized_snapshot is not None:
                self.authorized_snapshot.close()
            self._is_running = False
            self.finished_process.emit()
