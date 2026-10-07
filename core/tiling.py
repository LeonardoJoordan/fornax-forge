"""Divisão física compartilhada pela prévia e pelos arquivos para montagem."""
from dataclasses import dataclass
import math

from PySide6.QtCore import QRectF

from core.i18n import tr

UNITS_PER_MM = 300 / 25.4
MARK_GAP_MM = 2.0
MARK_LENGTH_MM = 3.0
MAX_TILES = 1000


def spreadsheet_position(column, row):
    if type(column) is not int or type(row) is not int or column < 0 or row < 0:
        raise ValueError("A posição deve possuir linha e coluna inteiras não negativas.")
    letters, number = '', column + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return f'{letters}{row + 1}'


@dataclass(frozen=True)
class Tile:
    column: int
    row: int
    region: QRectF
    trim: QRectF

    @property
    def name(self):
        return spreadsheet_position(self.column, self.row)


@dataclass(frozen=True)
class TilePlan:
    paper: tuple[float, float]
    margin_mm: float
    overlap_mm: float
    crop_marks: bool
    columns: int
    rows: int
    tiles: tuple[Tile, ...]
    scale: float
    source_bounds: QRectF
    drawing_bounds: QRectF
    offset_mm: tuple[float, float]


def build_tile_plan(bounds, paper=(210, 297), *, margin_mm=0, overlap_mm=0, crop_marks=False,
                    target_size_mm=None, offset_mm=(0, 0), auto_orientation=False):
    if auto_orientation:
        candidates, errors = [], []
        for oriented in (tuple(sorted(paper)), tuple(sorted(paper, reverse=True))):
            try:
                candidates.append(build_tile_plan(bounds, oriented, margin_mm=margin_mm,
                    overlap_mm=overlap_mm, crop_marks=crop_marks, target_size_mm=target_size_mm,
                    offset_mm=offset_mm))
            except ValueError as error:
                errors.append(error)
        if not candidates:
            raise errors[0]
        return min(candidates, key=lambda plan: (len(plan.tiles), plan.columns + plan.rows,
                                                plan.paper[0] > plan.paper[1]))
    if len(paper) != 2:
        raise ValueError(tr("Informe a largura e a altura da folha."))
    values = (*paper, margin_mm, overlap_mm)
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) for value in values):
        raise ValueError(tr("As medidas de impressão devem ser números finitos."))
    paper_w, paper_h = paper
    if not (0 < paper_w <= 5000 and 0 < paper_h <= 5000):
        raise ValueError(tr("Cada dimensão da folha deve ser maior que zero e de até 5.000 mm."))
    if margin_mm < 0 or overlap_mm < 0:
        raise ValueError(tr("A margem e a sobreposição não podem ser negativas."))
    if crop_marks and margin_mm < MARK_GAP_MM + MARK_LENGTH_MM:
        raise ValueError(tr("As marcas de corte precisam de uma margem de pelo menos 5 mm na folha. Ajuste a margem ou desative as marcas."))
    width, height = paper_w - 2 * margin_mm, paper_h - 2 * margin_mm
    if min(width, height) <= 0:
        raise ValueError(tr("A margem ocupa toda a folha. Reduza a margem."))
    if overlap_mm >= min(width, height):
        raise ValueError(tr("A sobreposição deve ser menor que a área útil da folha."))
    if bounds.isEmpty() or any(not math.isfinite(value) for value in
                              (bounds.x(), bounds.y(), bounds.width(), bounds.height())):
        raise ValueError(tr("O desenho não possui dimensões válidas para impressão."))
    scale = 1.0
    if target_size_mm is not None:
        if len(target_size_mm) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0 for value in target_size_mm):
            raise ValueError(tr("Informe dimensões finais positivas para o desenho."))
        scale = target_size_mm[0] * UNITS_PER_MM / bounds.width()
        if not math.isclose(target_size_mm[1] * UNITS_PER_MM / bounds.height(), scale, rel_tol=0.002):
            raise ValueError(tr("As dimensões finais devem manter a proporção do desenho."))
    if len(offset_mm) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 for value in offset_mm):
        raise ValueError(tr("A posição do desenho deve usar medidas positivas ou zero."))
    step_x, step_y = width - overlap_mm, height - overlap_mm
    drawing = QRectF(bounds.topLeft(), bounds.size() * scale)
    columns = max(1, math.ceil((drawing.width() / UNITS_PER_MM + offset_mm[0] - overlap_mm) / step_x - 1e-9))
    rows = max(1, math.ceil((drawing.height() / UNITS_PER_MM + offset_mm[1] - overlap_mm) / step_y - 1e-9))
    if columns * rows > MAX_TILES:
        raise ValueError(tr("O ladrilhamento excede 1.000 folhas. Ajuste o papel ou a composição."))
    tiles = []
    for row in range(rows):
        for column in range(columns):
            x = drawing.left() + (column * step_x - offset_mm[0]) * UNITS_PER_MM
            y = drawing.top() + (row * step_y - offset_mm[1]) * UNITS_PER_MM
            region = QRectF(x, y, min(width * UNITS_PER_MM, drawing.right() - x),
                            min(height * UNITS_PER_MM, drawing.bottom() - y))
            # A faixa repetida fica à direita/abaixo. Ao recortar nestes limites,
            # as partes cobrem o desenho exatamente uma vez, sem espaços ou duplicação.
            trim = QRectF(x, y, step_x * UNITS_PER_MM if column + 1 < columns else region.width(),
                          step_y * UNITS_PER_MM if row + 1 < rows else region.height())
            tiles.append(Tile(column, row, region, trim))
    return TilePlan(tuple(paper), margin_mm, overlap_mm, crop_marks, columns, rows, tuple(tiles),
                    scale, QRectF(bounds), drawing, tuple(offset_mm))
