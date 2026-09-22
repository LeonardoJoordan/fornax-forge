import math

from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPageLayout, QTransform
from PySide6.QtCore import Qt, QPointF, QRectF
from core.model_document import ModelValidationError, validate_raster_dimensions

DPI = 300
EPS_MM = 1e-6

def mm_to_px_300(mm):
    return round((mm * DPI) / 25.4)

def _fit_count_mm(available_mm, item_mm):
    if available_mm <= 0 or item_mm <= 0:
        return 0
    return max(0, math.floor((available_mm + EPS_MM) / item_mm))

class SheetAssembler:
    def __init__(self, target_w_mm: float, target_h_mm: float, sheet_w_mm: float = 210.0, sheet_h_mm: float = 297.0, crop_marks: bool = True, bleed_margin: bool = False, auto_rotate: bool = True):
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

        self.card_w_px = mm_to_px_300(target_w_mm)
        self.card_h_px = mm_to_px_300(target_h_mm)
        self.mark_len = mm_to_px_300(self.mark_len_mm)
        self.mark_gap = mm_to_px_300(self.mark_gap_mm)

        usable_w_mm = sheet_w_mm - (self.edge_reserve_mm * 2)
        usable_h_mm = sheet_h_mm - (self.edge_reserve_mm * 2)

        cols_p = _fit_count_mm(usable_w_mm, target_w_mm)
        rows_p = _fit_count_mm(usable_h_mm, target_h_mm)
        cap_p = cols_p * rows_p
        
        cols_l = _fit_count_mm(usable_h_mm, target_w_mm)
        rows_l = _fit_count_mm(usable_w_mm, target_h_mm)
        cap_l = cols_l * rows_l
        
        if auto_rotate and cap_l > cap_p:
            self.sheet_w_mm = sheet_h_mm
            self.sheet_h_mm = sheet_w_mm
            self.cols = cols_l
            self.rows = rows_l
            self.capacity = cap_l
            self.orientation = QPageLayout.Orientation.Landscape
        else:
            self.sheet_w_mm = sheet_w_mm
            self.sheet_h_mm = sheet_h_mm
            self.cols = cols_p
            self.rows = rows_p
            self.capacity = cap_p
            self.orientation = QPageLayout.Orientation.Portrait

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
        self.margin_left = mm_to_px_300(self.margin_left_mm)
        self.margin_top = mm_to_px_300(self.margin_top_mm)

    def _grid_x(self, col: int):
        return mm_to_px_300(self.margin_left_mm + (col * self.target_w_mm))

    def _grid_y(self, row: int):
        return mm_to_px_300(self.margin_top_mm + (row * self.target_h_mm))

    def render_sheet(self, cards: list[QImage | None], *, preserve_slots=False,
                     card_links=None, canvas_size=None, out_links=None,
                     rotate_cards_180=False) -> QImage:
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

    def _draw_crop_marks(self, painter: QPainter, cols: int, rows: int):
        pen = QPen(Qt.GlobalColor.black)
        pen.setWidth(2) 
        painter.setPen(pen)

        grid_start_x = self.margin_left
        # Usa as colunas e linhas dinâmicas para travar o fim do bloco
        grid_end_x = self._grid_x(cols)
        grid_start_y = self.margin_top
        grid_end_y = self._grid_y(rows)

        for c in range(cols + 1):
            x = self._grid_x(c)
            p1_top = QPointF(x, grid_start_y - self.mark_gap)
            p2_top = QPointF(x, grid_start_y - self.mark_gap - self.mark_len)
            painter.drawLine(p1_top, p2_top)
            
            p1_btm = QPointF(x, grid_end_y + self.mark_gap)
            p2_btm = QPointF(x, grid_end_y + self.mark_gap + self.mark_len)
            painter.drawLine(p1_btm, p2_btm)

        for r in range(rows + 1):
            y = self._grid_y(r)
            p1_lft = QPointF(grid_start_x - self.mark_gap, y)
            p2_lft = QPointF(grid_start_x - self.mark_gap - self.mark_len, y)
            painter.drawLine(p1_lft, p2_lft)
            
            p1_rgt = QPointF(grid_end_x + self.mark_gap, y)
            p2_rgt = QPointF(grid_end_x + self.mark_gap + self.mark_len, y)
            painter.drawLine(p1_rgt, p2_rgt)
