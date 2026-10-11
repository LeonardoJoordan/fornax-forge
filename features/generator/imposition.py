import math
from copy import copy

from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPageLayout, QTransform
from PySide6.QtCore import Qt, QPointF, QRectF
from core.model_document import ModelValidationError, validate_raster_dimensions
from core.tiling import crop_mark_segments

DPI = 300
EPS_MM = 1e-6

def mm_to_px_300(mm):
    return round((mm * DPI) / 25.4)

def _fit_count_mm(available_mm, item_mm):
    if available_mm <= 0 or item_mm <= 0:
        return 0
    return max(0, math.floor((available_mm + EPS_MM) / item_mm))

class SheetAssembler:
    @classmethod
    def from_settings(cls, settings):
        return cls(settings.get('target_w_mm', 100), settings.get('target_h_mm', 150),
                   settings.get('sheet_w_mm', 210), settings.get('sheet_h_mm', 297),
                   settings.get('crop_marks', True), settings.get('bleed_margin', False),
                   auto_rotate=settings.get('auto_rotate', True),
                   margin_mm=settings.get('margin_mm'), offset_mm=settings.get('offset_mm'))

    def __init__(self, target_w_mm: float, target_h_mm: float, sheet_w_mm: float = 210.0, sheet_h_mm: float = 297.0, crop_marks: bool = True, bleed_margin: bool = False, auto_rotate: bool = True, *, margin_mm=None, offset_mm=None):
        for label, value in (
            ("largura do item", target_w_mm), ("altura do item", target_h_mm),
            ("largura da folha", sheet_w_mm), ("altura da folha", sheet_h_mm),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ModelValidationError(f"A {label} deve ser um número positivo.")
        self.target_w_mm = target_w_mm
        self.target_h_mm = target_h_mm
        self.crop_marks = crop_marks
        self.bleed_margin = bleed_margin
        self.positioned = offset_mm is not None
        
        # Configuração das linhas de corte e seus tamanhos
        if self.crop_marks:
            self.mark_gap_mm = 2.0  
            self.mark_len_mm = 3.0  
        else:
            self.mark_gap_mm = 0.0
            self.mark_len_mm = 0.0

        # Cálculo cumulativo da reserva de borda (reduz a área útil da folha)
        self.edge_reserve_mm = 0.0
        
        if self.bleed_margin:
            self.edge_reserve_mm += 5.0 # Adiciona 5mm de proteção
            
        if self.crop_marks:
            self.edge_reserve_mm += (self.mark_gap_mm + self.mark_len_mm) # Adiciona 5mm para as marcas

        # A configuração unificada fornece uma margem explícita. Modelos antigos
        # conservam a reserva cumulativa original quando este campo está ausente.
        if margin_mm is not None:
            if isinstance(margin_mm, bool) or not isinstance(margin_mm, (int, float)) or not math.isfinite(margin_mm) or margin_mm < 0:
                raise ModelValidationError("A margem deve ser um número positivo ou zero.")
            self.edge_reserve_mm = margin_mm
        if offset_mm is not None and (len(offset_mm) != 2 or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in offset_mm)):
            raise ModelValidationError("A posição deve conter duas medidas positivas ou zero.")
        offset_x, offset_y = offset_mm or (0, 0)

        self.card_w_px = mm_to_px_300(target_w_mm)
        self.card_h_px = mm_to_px_300(target_h_mm)
        self.mark_len = mm_to_px_300(self.mark_len_mm)
        self.mark_gap = mm_to_px_300(self.mark_gap_mm)

        usable_w_mm = sheet_w_mm - (self.edge_reserve_mm * 2)
        usable_h_mm = sheet_h_mm - (self.edge_reserve_mm * 2)

        cols_p = _fit_count_mm(usable_w_mm - offset_x, target_w_mm)
        rows_p = _fit_count_mm(usable_h_mm - offset_y, target_h_mm)
        cap_p = cols_p * rows_p
        
        cols_l = _fit_count_mm(usable_h_mm - offset_x, target_w_mm)
        rows_l = _fit_count_mm(usable_w_mm - offset_y, target_h_mm)
        cap_l = cols_l * rows_l
        
        if auto_rotate and cap_l > cap_p:
            self.sheet_w_mm = sheet_h_mm
            self.sheet_h_mm = sheet_w_mm
            self.cols = cols_l
            self.rows = rows_l
            self.capacity = cap_l
        else:
            self.sheet_w_mm = sheet_w_mm
            self.sheet_h_mm = sheet_h_mm
            self.cols = cols_p
            self.rows = rows_p
            self.capacity = cap_p

        self.orientation = (QPageLayout.Orientation.Landscape if self.sheet_w_mm > self.sheet_h_mm
                            else QPageLayout.Orientation.Portrait)

        validate_raster_dimensions(
            mm_to_px_300(self.sheet_w_mm), mm_to_px_300(self.sheet_h_mm),
            label="folha de impressão",
        )

        self.sheet_w = mm_to_px_300(self.sheet_w_mm)
        self.sheet_h = mm_to_px_300(self.sheet_h_mm)

        total_grid_w_mm = self.cols * target_w_mm
        total_grid_h_mm = self.rows * target_h_mm
        
        self.margin_left_mm = (self.sheet_w_mm - total_grid_w_mm) / 2.0
        self.margin_top_mm = (self.sheet_h_mm - total_grid_h_mm) / 2.0
        if offset_mm is not None:
            self.margin_left_mm = self.edge_reserve_mm + offset_x
            self.margin_top_mm = self.edge_reserve_mm + offset_y
        self.margin_left = mm_to_px_300(self.margin_left_mm)
        self.margin_top = mm_to_px_300(self.margin_top_mm)

    def _grid_x(self, col: int):
        return mm_to_px_300(self.margin_left_mm + (col * self.target_w_mm))

    def _grid_y(self, row: int):
        return mm_to_px_300(self.margin_top_mm + (row * self.target_h_mm))

    def render_sheet(self, cards: list[QImage | None], *, preserve_slots=False,
                     card_links=None, canvas_size=None, out_links=None,
                     rotate_cards_180=False, back_face=False) -> QImage:
        if back_face and self.positioned:
            # Com posição livre, espelhar somente a ordem das células não basta:
            # o verso precisa espelhar também a margem da malha na folha física.
            back = copy(self)
            if self.orientation == QPageLayout.Orientation.Landscape:
                back.margin_top_mm = self.sheet_h_mm - self.rows * self.target_h_mm - self.margin_top_mm
            else:
                back.margin_left_mm = self.sheet_w_mm - self.cols * self.target_w_mm - self.margin_left_mm
            back.margin_left = mm_to_px_300(back.margin_left_mm)
            back.margin_top = mm_to_px_300(back.margin_top_mm)
            return back.render_sheet(cards, preserve_slots=preserve_slots, card_links=card_links,
                                     canvas_size=canvas_size, out_links=out_links,
                                     rotate_cards_180=rotate_cards_180)
        sheet = QImage(self.sheet_w, self.sheet_h, QImage.Format_ARGB32)
        sheet.setDotsPerMeterX(round(DPI / 0.0254))
        sheet.setDotsPerMeterY(round(DPI / 0.0254))
        sheet.fill(Qt.GlobalColor.white)
        
        painter = QPainter(sheet)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        idx = 0
        limit = len(cards)
        
        if limit == 0:
            painter.end()
            return sheet

        if self.cols <= 0 or self.rows <= 0:
            painter.end()
            return sheet

        # Calcula a malha efetivamente ocupada nesta folha
        actual_cols = self.cols if preserve_slots else min(self.cols, limit)
        actual_rows = self.rows if preserve_slots else (limit + self.cols - 1) // self.cols
        
        for r in range(self.rows):
            for c in range(self.cols):
                if idx >= limit:
                    break
                original_img = cards[idx]
                x = self._grid_x(c)
                y = self._grid_y(r)
                cell_w = max(1, self._grid_x(c + 1) - x)
                cell_h = max(1, self._grid_y(r + 1) - y)

                if original_img is not None:
                    scaled_image = original_img.scaled(
                        cell_w, cell_h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    if rotate_cards_180:
                        scaled_image = scaled_image.transformed(
                            QTransform().rotate(180),
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    painter.drawImage(x, y, scaled_image)
                    if out_links is not None and card_links and idx < len(card_links):
                        canvas_w, canvas_h = canvas_size or (original_img.width(), original_img.height())
                        scale_x = cell_w / max(1, canvas_w)
                        scale_y = cell_h / max(1, canvas_h)
                        for link in card_links[idx] or []:
                            rect = link.get("rect")
                            if rect is None:
                                continue
                            rect_x = rect.x()
                            rect_y = rect.y()
                            if rotate_cards_180:
                                rect_x = canvas_w - rect.x() - rect.width()
                                rect_y = canvas_h - rect.y() - rect.height()
                            out_links.append({
                                "url": link.get("url", ""),
                                "rect": QRectF(
                                    x + rect_x * scale_x,
                                    y + rect_y * scale_y,
                                    rect.width() * scale_x,
                                    rect.height() * scale_y,
                                ),
                            })
                idx += 1

        if self.crop_marks:
            self._draw_crop_marks(painter, actual_cols, actual_rows)
        painter.end()
        return sheet

    def _draw_crop_marks(self, painter: QPainter, cols: int, rows: int, *, preview=False):
        pen = QPen(Qt.GlobalColor.black)
        # No mapa reduzido, um pixel de tela mantém as marcas legíveis. A saída
        # final continua com a espessura original de dois pixels em 300 DPI.
        pen.setWidth(1 if preview else 2)
        pen.setCosmetic(preview)
        painter.setPen(pen)

        if cols <= 0 or rows <= 0:
            return
        grid = QRectF(self.margin_left, self.margin_top,
                      self._grid_x(cols) - self.margin_left, self._grid_y(rows) - self.margin_top)
        paper = QRectF(0, 0, self.sheet_w - 1, self.sheet_h - 1)
        # Mantém os limites individuais arredondados, iguais aos cartões.
        segments = crop_mark_segments(grid, paper, gap=self.mark_gap, length=self.mark_len,
                                      columns=cols, rows=rows)
        for index, (x1, y1, x2, y2) in enumerate(segments):
            if index < (cols + 1) * 2:
                x1 = x2 = min(paper.right(), self._grid_x(index // 2))
            else:
                y1 = y2 = min(paper.bottom(), self._grid_y((index - (cols + 1) * 2) // 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
