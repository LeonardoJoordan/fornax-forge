"""Prévia e exportação do quadro sem um bitmap gigante intermediário."""
from copy import deepcopy
import math
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QThread, Signal, QMarginsF
from PySide6.QtGui import QPainter, QImage, QPen, QColor, QPdfWriter, QPageLayout

from core.model_document import adapt_model_page, normalize_model_document, validate_raster_dimensions
from core.organogram import assignment_plan, assignment_issue_text, board_bounds, UNITS_PER_MM
from core.board_connectors import connector_style, connector_pen, connector_paths, text_cutouts, connector_clip
from core.board_borders import paint_group_borders
from core.i18n import tr
from core.naming_engine import confined_output_path
from .renderer import NativeRenderer
from .workers import physical_page, pdf_painter
from .pdf_links import inject_pdf_links


class OrganogramRenderer:
    def __init__(self, document, rows_plain, rows_rich=None, *, asset_provider=None, dynamic_image_dir=None):
        self.document = normalize_model_document(document)
        self.board = self.document["organogram"]
        self.paths = connector_paths(self.board)
        self.card = NativeRenderer(adapt_model_page(self.document), asset_provider=asset_provider)
        self.card.set_dynamic_image_directory(dynamic_image_dir)
        self.slots, self.assignment_issues = assignment_plan(self.document, rows_plain, rows_rich, dynamic_image_dir)
        self.group_slots = {}
        for slot in self.slots:
            self.group_slots.setdefault(slot[0], []).append(slot)
        self.bounds = board_bounds(self.board, visible_slots=self.slots)
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
            self.artwork_planes[True].paint_card(painter, {}, {}, out_links)
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
                        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
                        painter.translate(rect.topLeft())
                        painter.scale(rect.width() / canvas["w"], rect.height() / canvas["h"])
                        self.card.paint_card(painter, plain, rich, out_links)
                    finally:
                        painter.restore()
                # Vagas não ganham bordas; conjuntos totalmente vazios ficam ocultos.
                if slots:
                    paint_group_borders(painter, group, (slot[2] for slot in slots))
            self.artwork_planes[False].paint_card(painter, {}, {}, out_links)
        finally:
            painter.restore()

    def preview(self, max_side=1600):
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
            self.paint(painter)
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
            raise ValueError(tr("O quadro excede o tamanho seguro para PNG nessa resolução. Escolha PDF ou PDF em mosaico.")) from error
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
        width, height = ((dimension - 2 * margin_mm) * UNITS_PER_MM for dimension in paper)
        overlap = overlap_mm * UNITS_PER_MM
        step_x, step_y = width - overlap, height - overlap
        columns = max(1, math.ceil((self.bounds.width() - overlap) / step_x))
        rows = max(1, math.ceil((self.bounds.height() - overlap) / step_y))
        if columns * rows > 1000:
            raise ValueError(tr("O mosaico excede 1.000 folhas. Reduza o quadro antes de exportar."))
        return [(col, row, QRectF(self.bounds.left() + col * step_x,
                                 self.bounds.top() + row * step_y, width, height))
                for row in range(rows) for col in range(columns)]

    def export_pdf(self, path, *, paper=None, stop=None):
        w_mm, h_mm = self.bounds.width() / UNITS_PER_MM, self.bounds.height() / UNITS_PER_MM
        if paper is None and max(w_mm, h_mm) > 5000:
            raise ValueError(tr("Para quadros maiores que 5 m, use PDF em mosaico."))
        writer = QPdfWriter(str(path))
        # O layout de texto usa o mesmo DPI lógico do editor/prévia.
        writer.setResolution(96)
        writer.setTitle(tr("Quadro de pessoas — FORNAX Forge"))
        page_w, page_h = paper or (w_mm, h_mm)
        writer.setPageLayout(QPageLayout(physical_page(page_w, page_h),
                                        QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
        regions = self.mosaic_regions(paper) if paper else [(0, 0, self.bounds)]
        links_by_page = {}
        painter = pdf_painter(writer)
        try:
            for index, (column, row, region) in enumerate(regions):
                if stop and stop():
                    raise InterruptedError(tr("Geração cancelada."))
                if index and not writer.newPage():
                    raise OSError(tr("Não foi possível adicionar uma folha ao PDF."))
                painter.save()
                try:
                    painter.scale(96 / 300, 96 / 300)
                    margin = 10 * UNITS_PER_MM if paper else 0
                    painter.translate(margin - region.left(), margin - region.top())
                    links = []
                    self.paint(painter, region=region, stop=stop, out_links=links)
                    clip = painter.transform().mapRect(region)
                    links_by_page[index] = [
                        {**link, "rect": link["rect"].intersected(clip)} for link in links
                        if link["rect"].intersects(clip)
                    ]
                finally:
                    painter.restore()
                if paper:
                    painter.setPen(QColor("#555555"))
                    left, top = 10 * 96 / 25.4, 10 * 96 / 25.4
                    right, bottom = (page_w - 10) * 96 / 25.4, (page_h - 10) * 96 / 25.4
                    for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
                        painter.drawLine(round(x - 5), round(y), round(x + 5), round(y))
                        painter.drawLine(round(x), round(y - 5), round(x), round(y + 5))
                    # Rodapé fica na margem, fora da área de montagem do quadro.
                    painter.drawText(12, round(page_h * 96 / 25.4) - 10,
                                     tr("Linha {linha} · Coluna {coluna} · Sobreposição: 5 mm").format(linha=row + 1, coluna=column + 1))
        finally:
            painter.end()
        del writer
        inject_pdf_links(path, links_by_page, round(page_w * 96 / 25.4),
                         round(page_h * 96 / 25.4), memory_only=True)


class OrganogramWorker(QThread):
    progress_updated = Signal(int)
    log_updated = Signal(str)
    error_occurred = Signal(str)
    finished_process = Signal()

    def __init__(self, document, rows_plain, rows_rich, output_dir, mode, *, dpi=150,
                 asset_provider=None, dynamic_image_dir=None, authorized_snapshot=None, parent=None):
        super().__init__(parent)
        self.args = (deepcopy(document), deepcopy(rows_plain), deepcopy(rows_rich))
        self.output_dir = Path(output_dir)
        self.mode, self.dpi = mode, dpi
        self.asset_provider, self.dynamic_image_dir = asset_provider, dynamic_image_dir
        self.authorized_snapshot = authorized_snapshot
        self._is_running = True

    def stop(self):
        self.requestInterruption()
        self.wait()

    def run(self):
        extension = "png" if self.mode == "png" else "pdf"
        final = confined_output_path(self.output_dir, f"organograma.{extension}")
        temporary = confined_output_path(self.output_dir, f".organograma.partial.{extension}")
        try:
            renderer = OrganogramRenderer(*self.args, asset_provider=self.asset_provider,
                                         dynamic_image_dir=self.dynamic_image_dir)
            if renderer.assignment_issues:
                raise ValueError(tr("Corrija a distribuição dos registros antes de gerar:\n{pendencias}").format(
                    pendencias=assignment_issue_text(renderer.assignment_issues)))
            if not renderer.slots:
                raise ValueError(tr("Não há cartões com informações válidas nos blocos do quadro."))
            if self.mode == "png":
                renderer.export_png(temporary, self.dpi, self.isInterruptionRequested)
            else:
                paper = {"a4": (210, 297), "a3": (297, 420)}.get(self.mode)
                renderer.export_pdf(temporary, paper=paper, stop=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                raise InterruptedError(tr("Geração cancelada."))
            temporary.replace(final)
            self.progress_updated.emit(100)
            self.log_updated.emit(tr("Quadro gerado: {arquivo} ({quantidade} cartões)").format(
                arquivo=final.name, quantidade=len(renderer.slots)))
        except Exception as error:
            self.error_occurred.emit(str(error))
        finally:
            temporary.unlink(missing_ok=True)
            if self.authorized_snapshot is not None:
                self.authorized_snapshot.close()
            self._is_running = False
            self.finished_process.emit()
