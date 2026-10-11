"""Divisão física compartilhada pela prévia e pelos arquivos para montagem."""
from dataclasses import dataclass
import math

from PySide6.QtCore import QRectF

from core.i18n import tr

UNITS_PER_MM = 300 / 25.4
MARK_GAP_MM = 2.0
MARK_LENGTH_MM = 3.0
BLEED_MARGIN_MM = 5.0
MAX_TILES = 1000


def sheet_margins(settings):
    """Sangria e reserva das marcas, separadas nas novas configurações.

    Configurações antigas guardavam a reserva total em margin_value; continuar
    lendo esse formato evita somar novamente as marcas em arquivos já salvos.
    """
    if settings.get('margin_policy') == 'separate' or settings.get('mode') in ('imposition', 'tiles'):
        return (BLEED_MARGIN_MM if settings.get('margin_enabled') else 0,
                MARK_GAP_MM + MARK_LENGTH_MM if settings.get('crop_marks') else 0)
    return (settings.get('margin_value', BLEED_MARGIN_MM) if settings.get('margin_enabled') else 0, 0)


def reserved_margin_mm(settings):
    return sum(sheet_margins(settings))


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


def tile_sheet_rect(plan, tile):
    """Folha completa nas coordenadas físicas do desenho, incluindo margens."""
    margin = plan.margin_mm * UNITS_PER_MM
    return QRectF(tile.region.left() - margin, tile.region.top() - margin,
                  plan.paper[0] * UNITS_PER_MM, plan.paper[1] * UNITS_PER_MM)


def tile_crop_mark_segments(plan, tile, *, drawing_bounds=None):
    """Marcas junto à arte visível; espaços vazios de posicionamento não são arte.

    No arraste, drawing_bounds muda enquanto as folhas permanecem fixas. As
    áreas úteis completas permitem que as marcas acompanhem esse movimento.
    A área repetida de configurações antigas continua fora do limite de corte.
    """
    if not plan.crop_marks:
        return []
    paper = tile_sheet_rect(plan, tile)
    margin = plan.margin_mm * UNITS_PER_MM
    usable = paper.adjusted(margin, margin, -margin, -margin)
    drawing = plan.drawing_bounds if drawing_bounds is None else drawing_bounds
    extent = usable.intersected(drawing)
    overlap = plan.overlap_mm * UNITS_PER_MM
    trim = usable.adjusted(0, 0, -overlap if tile.column + 1 < plan.columns else 0,
                           -overlap if tile.row + 1 < plan.rows else 0)
    grid = trim.intersected(drawing)
    if extent.isEmpty() or grid.isEmpty():
        return []
    return crop_mark_segments(grid, paper, gap=MARK_GAP_MM * UNITS_PER_MM,
                              length=MARK_LENGTH_MM * UNITS_PER_MM, extent=extent)


def crop_mark_segments(grid, paper, *, gap, length, columns=1, rows=1, extent=None):
    """Marcas externas quando há espaço; encostadas na folha quando não há.

    A ausência de margem não reduz a arte nem muda o tamanho da folha. Nesse
    caso, os traços junto à borda ficam dentro da área da página.
    """
    def interval(start, end, low, high):
        size = min(end - start, high - low)
        start = max(low, min(start, high - size))
        return start, start + size

    extent = extent if extent is not None else grid
    top = interval(extent.top() - gap - length, extent.top() - gap, paper.top(), paper.bottom())
    bottom = interval(extent.bottom() + gap, extent.bottom() + gap + length, paper.top(), paper.bottom())
    left = interval(extent.left() - gap - length, extent.left() - gap, paper.left(), paper.right())
    right = interval(extent.right() + gap, extent.right() + gap + length, paper.left(), paper.right())
    segments = []
    for column in range(columns + 1):
        x = grid.left() + grid.width() * column / columns
        segments.extend(((x, top[0], x, top[1]), (x, bottom[0], x, bottom[1])))
    for row in range(rows + 1):
        y = grid.top() + grid.height() * row / rows
        segments.extend(((left[0], y, left[1], y), (right[0], y, right[1], y)))
    return segments
