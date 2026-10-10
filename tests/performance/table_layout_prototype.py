"""Prova técnica isolada da etapa 01; não é o schema nem o renderer do produto.

Geometria nas unidades atuais (300 unidades/polegada). O QTextDocument tem
dispositivo lógico fixo, independente do monitor e do destino de pintura.
Nenhum módulo de produção importa este protótipo.
"""
from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass
from itertools import accumulate
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPen, QTextBlockFormat, QTextCursor,
    QTextLength, QTextOption, QTextTableCellFormat, QTextTableFormat,
)
from PySide6.QtWidgets import QGraphicsItem

from core.html_utils import TextOnlyDocument, sanitize_text_html
from core.organogram import UNITS_PER_MM
from core.text_layout import build_document
from core.ui_font import UI_FONT_FAMILY
from table_fixtures import table_spec, cell


LOGICAL_DPI = 300


def specimen():
    data = table_spec('prototipo', 4, 4, merged=((0, 0, 1, 4), (2, 2, 2, 2)))
    data['column_widths_mm'] = [40] * 4
    data['row_heights_mm'] = [14, 22, 22, 22]
    cell(data, 0, 0, '<p><b>FORNAX · QUADRO DE INFORMAÇÕES</b></p>',
         fill='#203746', color='#ffffff', align='center', vertical_align='center')
    cell(data, 1, 0, '<p><b>{nome}</b></p><p><i>Participante</i></p>', fill='#edf2f5')
    cell(data, 1, 1, '<p>Primeira linha<br>Segunda linha</p>', vertical_align='center')
    cell(data, 1, 2, '<p><b>Centralizado</b></p>', align='center', vertical_align='center')
    cell(data, 1, 3, '<p><u>À direita / base</u></p>', align='right', vertical_align='bottom')
    cell(data, 2, 0, '<p>Quebra automática: informação detalhada sobre a atividade.</p>')
    cell(data, 2, 1, '<p>SEM_QUEBRA_' + 'X' * 50 + '</p>', wrap=False, color='#a13c32')
    cell(data, 2, 2, '<p><b>Área mesclada 2 × 2</b></p><p>Textos, cores e contornos próprios.</p>',
         fill='#e1ecf1', align='center', vertical_align='center')
    cell(data, 3, 0, '<p>' + '<br>'.join(f'Linha {i}' for i in range(1, 9)) + '</p>',
         fill='#fff1dc', color='#805b29')
    cell(data, 3, 1, '<p><b>Ênfase</b> e <i>itálico</i><br>Ação, ç, Ω, 𝄞</p>')
    return data


def logical_device():
    device = QImage(1, 1, QImage.Format.Format_ARGB32)
    device.setDotsPerMeterX(round(LOGICAL_DPI / .0254))
    device.setDotsPerMeterY(round(LOGICAL_DPI / .0254))
    return device


def _zero_paragraph_margins(document):
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = QTextBlockFormat()
    fmt.setTopMargin(0)
    fmt.setBottomMargin(0)
    cursor.mergeBlockFormat(fmt)


@dataclass
class CellLayout:
    spec: dict
    rect: QRectF
    inner: QRectF
    document: TextOnlyDocument
    offset_y: float
    text_height: float
    overflow_x: bool
    overflow_y: bool
    lines: tuple


class FixedTableLayout:
    """Dados de teste -> medidas fixas e fronteiras únicas -> pintura comum."""

    def __init__(self, data):
        self.data = deepcopy(data)
        self.device = logical_device()  # Precisa viver tanto quanto os documentos.
        self.x = [0, *accumulate(w * UNITS_PER_MM for w in data['column_widths_mm'])]
        self.y = [0, *accumulate(h * UNITS_PER_MM for h in data['row_heights_mm'])]
        if any(not math.isfinite(v) or v <= 0 for v in
               data['column_widths_mm'] + data['row_heights_mm']):
            raise ValueError('Medidas inválidas no protótipo')
        self.width, self.height = self.x[-1], self.y[-1]
        self.anchors = {}
        self.cells = []
        self.build_count = 0
        self.edge_width = data['outline']['width_mm'] * UNITS_PER_MM
        self.padding = data['padding_mm'] * UNITS_PER_MM + self.edge_width / 2
        for spec in self.data['cells']:
            r, c = spec['row'], spec['column']
            rs, cs = spec['row_span'], spec['column_span']
            if not (0 <= r < r + rs <= data['rows'] and 0 <= c < c + cs <= data['columns']):
                raise ValueError('Mesclagem fora da grade')
            for row in range(r, r + rs):
                for column in range(c, c + cs):
                    if (row, column) in self.anchors:
                        raise ValueError('Sobreposição no protótipo')
                    self.anchors[row, column] = (r, c)
            rect = QRectF(self.x[c], self.y[r], self.x[c+cs]-self.x[c], self.y[r+rs]-self.y[r])
            inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
            if inner.width() <= 0 or inner.height() <= 0:
                raise ValueError('Contorno/espaçamento não cabe na célula')
            document = build_document({
                'w': inner.width(), 'font_family': UI_FONT_FAMILY,
                'font_size': data['default_font_size_pt'], 'rich_text_version': 1,
                'font_color': spec.get('color', '#17242d'), 'align': spec['align'],
            }, '<html><body style="color:' + spec.get('color', '#17242d') + ';">'
                                  + spec['html'] + '</body></html>')
            document.documentLayout().setPaintDevice(self.device)
            _zero_paragraph_margins(document)
            cursor = QTextCursor(document)
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            block_format.setAlignment({'left': Qt.AlignmentFlag.AlignLeft,
                                       'center': Qt.AlignmentFlag.AlignHCenter,
                                       'right': Qt.AlignmentFlag.AlignRight}[spec['align']])
            cursor.mergeBlockFormat(block_format)
            options = document.defaultTextOption()
            options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
                                if spec['wrap'] else QTextOption.WrapMode.NoWrap)
            document.setDefaultTextOption(options)
            document.setTextWidth(inner.width())
            height = document.documentLayout().documentSize().height()
            # Excesso começa pelo topo para não perder o início da informação.
            available = max(0, inner.height() - height)
            offset = available * {'top': 0, 'center': .5, 'bottom': 1}[spec['vertical_align']]
            lines = []
            block = document.begin()
            while block.isValid():
                text_layout = block.layout()
                for index in range(text_layout.lineCount()):
                    line = text_layout.lineAt(index)
                    # Guardar offsets UTF-16 do Qt, não fatiar strings Python com eles.
                    lines.append((block.position() + line.textStart(), line.textLength(),
                                  line.naturalTextRect().x(), line.y(), line.naturalTextWidth(), line.height()))
                block = block.next()
            self.cells.append(CellLayout(spec, rect, inner, document, offset, height,
                                         any(line[4] > inner.width() + .01 for line in lines),
                                         height > inner.height() + .01, tuple(lines)))
            self.build_count += 1
        if len(self.anchors) != data['rows'] * data['columns']:
            raise ValueError('Grade incompleta')
        # Todas as divisas têm uma identidade canônica, inclusive as ocultas.
        self.edges = {}
        for row in range(data['rows'] + 1):
            for col in range(data['columns']):
                self.edges['h', row, col] = (QPointF(self.x[col], self.y[row]),
                                           QPointF(self.x[col+1], self.y[row]))
        for row in range(data['rows']):
            for col in range(data['columns'] + 1):
                self.edges['v', row, col] = (QPointF(self.x[col], self.y[row]),
                                           QPointF(self.x[col], self.y[row+1]))
        self.visible_edges = {key: segment for key, segment in self.edges.items()
                              if self._edge_visible(key)}

    def _edge_visible(self, key):
        orientation, row, col = key
        if orientation == 'h':
            return row in (0, self.data['rows']) or self.anchors[row-1, col] != self.anchors[row, col]
        return col in (0, self.data['columns']) or self.anchors[row, col-1] != self.anchors[row, col]

    def hit(self, point):
        # Intervalos semiabertos: direita/base externas não pertencem à grade.
        if not (0 <= point.x() < self.width and 0 <= point.y() < self.height):
            return None
        row, col = bisect_right(self.y, point.y())-1, bisect_right(self.x, point.x())-1
        return self.anchors[row, col]

    def selection(self, first, last):
        top, bottom = sorted((first[0], last[0]))
        left, right = sorted((first[1], last[1]))
        # Fecho retangular: expandir até conter mesclagens inteiras.
        while True:
            old = top, left, bottom, right
            for entry in self.cells:
                spec = entry.spec
                r, c, rs, cs = spec['row'], spec['column'], spec['row_span'], spec['column_span']
                if r <= bottom and r+rs-1 >= top and c <= right and c+cs-1 >= left:
                    top, left = min(top, r), min(left, c)
                    bottom, right = max(bottom, r+rs-1), max(right, c+cs-1)
            if old == (top, left, bottom, right):
                return QRectF(self.x[left], self.y[top], self.x[right+1]-self.x[left],
                              self.y[bottom+1]-self.y[top])

    def paint(self, painter):
        painter.save()
        try:
            # Fundos adjacentes não devem misturar cores conforme a ordem de
            # pintura nas coordenadas fracionárias. Texto/contorno têm AA.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for entry in self.cells:
                painter.fillRect(entry.rect, QColor(entry.spec['fill']))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for entry in self.cells:
                painter.save()
                try:
                    painter.setClipRect(entry.inner, Qt.ClipOperation.IntersectClip)
                    painter.translate(entry.inner.left(), entry.inner.top() + entry.offset_y)
                    entry.document.drawContents(painter)
                finally:
                    painter.restore()
            pen = QPen(QColor(self.data['outline']['color']))
            pen.setWidthF(self.edge_width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            for start, end in self.visible_edges.values():
                painter.drawLine(start, end)
        finally:
            painter.restore()

    def measurements(self):
        return {'width': self.width, 'height': self.height, 'documents': self.build_count,
                'logical_dpi': self.device.logicalDpiX(), 'grid_edges': len(self.edges),
                'visible_edges': len(self.visible_edges),
                'cells': [{'anchor': [e.spec['row'], e.spec['column']],
                           'rect': [e.rect.x(), e.rect.y(), e.rect.width(), e.rect.height()],
                           'text': e.document.toPlainText(), 'text_height': e.text_height,
                           'offset_y': e.offset_y, 'lines': e.lines,
                           'overflow_x': e.overflow_x, 'overflow_y': e.overflow_y}
                          for e in self.cells]}


class PrototypeTableItem(QGraphicsItem):
    """Uma raiz gráfica; sem widgets por célula, edição ou histórico do produto."""

    def __init__(self, layout):
        super().__init__()
        self.layout = layout
        self.active = None
        self.drag_anchor = None
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def boundingRect(self):  # noqa: N802
        half = self.layout.edge_width / 2
        return QRectF(0, 0, self.layout.width, self.layout.height).adjusted(-half, -half, half, half)

    def paint(self, painter, option, widget=None):
        self.layout.paint(painter)
        if self.active is not None:
            painter.fillRect(self.active, QColor(40, 130, 210, 50))

    def mousePressEvent(self, event):  # noqa: N802
        anchor = self.layout.hit(event.pos())
        if anchor is None:
            event.ignore()
            return
        self.drag_anchor = anchor
        self.active = self.layout.selection(anchor, anchor)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        anchor = self.layout.hit(event.pos())
        if self.drag_anchor is not None and anchor is not None:
            self.active = self.layout.selection(self.drag_anchor, anchor)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self.mouseMoveEvent(event)
        self.drag_anchor = None
        event.accept()

    def ungrabMouseEvent(self, event):  # noqa: N802
        self.drag_anchor = None
        super().ungrabMouseEvent(event)


def render_image(layout, scale=1, margin=24):
    image = QImage(math.ceil((layout.width + 2*margin)*scale),
                   math.ceil((layout.height + 2*margin)*scale), QImage.Format.Format_ARGB32)
    image.setDotsPerMeterX(round(LOGICAL_DPI * scale / .0254))
    image.setDotsPerMeterY(round(LOGICAL_DPI * scale / .0254))
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.scale(scale, scale)
        painter.translate(margin, margin)
        layout.paint(painter)
    finally:
        painter.end()
    return image


def native_qtexttable(data, *, fixed_height=True):
    """Candidato nativo, com largura e altura totais declaradas fixas."""
    device = logical_device()
    doc = TextOnlyDocument()
    doc.documentLayout().setPaintDevice(device)
    doc.setDocumentMargin(0)
    from PySide6.QtGui import QFont
    font = QFont(UI_FONT_FAMILY)
    font.setPointSizeF(data['default_font_size_pt'])
    doc.setDefaultFont(font)
    width = sum(data['column_widths_mm']) * UNITS_PER_MM
    height = sum(data['row_heights_mm']) * UNITS_PER_MM
    doc.setTextWidth(width)
    fmt = QTextTableFormat()
    # Comprimentos do formato de tabela são escalados pelo Qt a partir de 96
    # DPI; textWidth/rects de layout já estão em unidades do paint device.
    factor = device.logicalDpiX() / 96
    fmt.setMargin(0)
    fmt.setWidth(QTextLength(QTextLength.Type.FixedLength, width / factor))
    if fixed_height:
        fmt.setHeight(QTextLength(QTextLength.Type.FixedLength, height))
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.FixedLength, w*UNITS_PER_MM / factor)
                                   for w in data['column_widths_mm']])
    fmt.setCellPadding(data['padding_mm'] * UNITS_PER_MM / factor)
    fmt.setCellSpacing(0)
    fmt.setBorder(data['outline']['width_mm'] * UNITS_PER_MM / factor)
    table = QTextCursor(doc).insertTable(data['rows'], data['columns'], fmt)
    for spec in data['cells']:
        r, c, rs, cs = spec['row'], spec['column'], spec['row_span'], spec['column_span']
        if rs > 1 or cs > 1:
            table.mergeCells(r, c, rs, cs)
        target = table.cellAt(r, c)
        cell_fmt = QTextTableCellFormat()
        cell_fmt.setBackground(QColor(spec['fill']))
        cell_fmt.setVerticalAlignment({
            'top': QTextTableCellFormat.VerticalAlignment.AlignTop,
            'center': QTextTableCellFormat.VerticalAlignment.AlignMiddle,
            'bottom': QTextTableCellFormat.VerticalAlignment.AlignBottom,
        }[spec['vertical_align']])
        target.setFormat(cell_fmt)
        cursor = target.firstCursorPosition()
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment({'left': Qt.AlignmentFlag.AlignLeft,
                               'center': Qt.AlignmentFlag.AlignHCenter,
                               'right': Qt.AlignmentFlag.AlignRight}[spec['align']])
        cursor.setBlockFormat(block_fmt)
        cursor.insertHtml('<html><body style="color:' + spec.get('color', '#17242d') + ';">'
                          + sanitize_text_html(spec['html']) + '</body></html>')
    _zero_paragraph_margins(doc)
    # O ciclo de vida do dispositivo é explícito no retorno.
    return doc, table, device
