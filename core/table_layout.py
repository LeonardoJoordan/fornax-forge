"""Grade fixa e texto Qt com dispositivo lógico de 300 dpi por chamada."""
from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass
from itertools import accumulate
import re

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QFont, QImage, QPainterPath, QTextBlockFormat, QTextCursor, QTextOption

from core.html_utils import TextOnlyDocument, normalize_text_decoration, sanitize_text_html
from core.table_html import cell_html_has_unsupported_resources
from core.table_model import effective_cell_style, validate_table, visible_edge_keys
from core.table_text import resolve_cell_document
from core.ui_font import resolve_font_family
from core.font_utils import resolve_bundled_font_aliases

LOGICAL_DPI = 300
ALIGNMENTS = {'left':Qt.AlignmentFlag.AlignLeft, 'center':Qt.AlignmentFlag.AlignHCenter,
              'right':Qt.AlignmentFlag.AlignRight}


def logical_text_device():
    device = QImage(1,1,QImage.Format.Format_ARGB32)
    device.setDotsPerMeterX(round(LOGICAL_DPI / .0254))
    device.setDotsPerMeterY(round(LOGICAL_DPI / .0254))
    return device


def build_cell_document(cell, style, device, width, values=None, *, resolve_values=True):
    document = TextOnlyDocument()
    document.documentLayout().setPaintDevice(device)
    document.setUndoRedoEnabled(False)
    document.setDocumentMargin(0)
    font = QFont(resolve_font_family(style['font_family']))
    font.setPointSizeF(style['font_size'])
    font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    document.setDefaultFont(font)
    document.setDefaultStyleSheet('body { color: '+style['font_color']+'; }')
    content = cell['html']
    if cell_html_has_unsupported_resources(content):
        content = sanitize_text_html(content)
    content = normalize_text_decoration(content)
    content = re.sub(r'(?i)</?a\b[^>]*>', '', content)
    if not re.search(r'(?i)<(?:html|body)\b', content):
        content = '<html><body style="color:'+style['font_color']+';">'+content+'</body></html>'
    document.setHtml(content)
    resolve_bundled_font_aliases(document)
    if resolve_values:
        resolve_cell_document(document,values)
    options = document.defaultTextOption()
    options.setAlignment(ALIGNMENTS[style['align']])
    options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
                        if style['wrap'] else QTextOption.WrapMode.NoWrap)
    document.setDefaultTextOption(options)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    block = QTextBlockFormat()
    block.setTopMargin(0)
    block.setBottomMargin(0)
    block.setLeftMargin(0)
    block.setRightMargin(0)
    block.setTextIndent(0)
    block.setAlignment(ALIGNMENTS[style['align']])
    block.setLineHeight(style['line_height']*100,
                        QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor.mergeBlockFormat(block)
    document.setTextWidth(width)
    return document


@dataclass
class CellLayout:
    cell: dict
    style: dict
    rect: QRectF
    inner: QRectF
    document: TextOnlyDocument
    offset_y: float
    text_height: float
    overflow_x: bool
    overflow_y: bool
    lines: tuple


class TableLayout:
    """Uma grade imutável de pintura; documentos pertencem à thread criadora.

    O proprietário deve manter este layout/dispositivo vivos durante a pintura.
    Não guardar layouts nos snapshots nem compartilhar documentos entre workers.
    """
    def __init__(self, table, values=None):
        validate_table(table)  # Antes de criar documentos Qt.
        self.table = deepcopy(table)
        self.device = logical_text_device()
        self.x = [0, *accumulate(table['column_widths'])]
        self.y = [0, *accumulate(table['row_heights'])]
        self.width,self.height = self.x[-1],self.y[-1]
        self.edge_styles = {(e['orientation'],e['row'],e['column']):
                            {**table['border'],**e['style']} for e in table['edges']}
        self.anchors = {}
        self.cells = []
        self.warnings = []
        for cell in self.table['cells']:
            r,c,rs,cs = (cell[key] for key in ('row','column','row_span','column_span'))
            for row in range(r,r+rs):
                for column in range(c,c+cs):
                    self.anchors[row,column] = (r,c)
            rect = QRectF(self.x[c],self.y[r],self.x[c+cs]-self.x[c],self.y[r+rs]-self.y[r])
            style = effective_cell_style(table,cell)

            def inset(keys):
                strokes = [self.edge_style(key)['width']/2
                           for key in keys if self.edge_style(key)['visible']]
                return style['padding']+max(strokes,default=0)

            left = inset(('v',row,c) for row in range(r,r+rs))
            right = inset(('v',row,c+cs) for row in range(r,r+rs))
            top = inset(('h',r,col) for col in range(c,c+cs))
            bottom = inset(('h',r+rs,col) for col in range(c,c+cs))
            inner = rect.adjusted(left,top,-right,-bottom)
            document = build_cell_document(cell,style,self.device,inner.width(),values)
            layout = document.documentLayout()
            text_height = layout.documentSize().height()
            offset = max(0,inner.height()-text_height)*{'top':0,'center':.5,'bottom':1}[style['vertical_align']]
            lines = []
            block = document.begin()
            while block.isValid():
                block_rect = layout.blockBoundingRect(block)
                for index in range(block.layout().lineCount()):
                    line = block.layout().lineAt(index)
                    lines.append((block.position()+line.textStart(),line.textLength(),
                                  line.naturalTextRect().x(),block_rect.y()+line.y(),
                                  line.naturalTextWidth(),line.height()))
                block = block.next()
            overflow_x = any(line[4] > inner.width()+.01 for line in lines)
            overflow_y = text_height > inner.height()+.01
            self.cells.append(CellLayout(cell,style,rect,inner,document,offset,text_height,
                                         overflow_x,overflow_y,tuple(lines)))
            if (overflow_x or overflow_y) and document.toPlainText().strip():
                self.warnings.append(dict(table_id=table['object_id'],table_name=table['custom_name'],
                    cell_id=cell['id'],row=r+1,column=c+1,overflow_x=overflow_x,overflow_y=overflow_y))
        self.refresh_edges()

    def refresh_edges(self):
        """Reconstrói somente segmentos/estilos; conserva documentos e medidas."""
        self.visible_edges = tuple(visible_edge_keys(self.table))
        self.edge_segments = []
        for key in self.visible_edges:
            style = self.edge_style(key)
            if not style['visible'] or not style['width'] or not style['opacity']:
                continue
            orientation,r,c = key
            if orientation == 'h':
                start,end = QPointF(self.x[c],self.y[r]),QPointF(self.x[c+1],self.y[r])
            else:
                start,end = QPointF(self.x[c],self.y[r]),QPointF(self.x[c],self.y[r+1])
            self.edge_segments.append((style,start,end))
        # Completar os encontros com a meia espessura do contorno perpendicular.
        # Um caminho por cor/opacidade evita escurecer interseções translúcidas
        # de mesma aparência; os caminhos são retidos, sem reconstrução no paint.
        junctions = {}
        for style, start, end in self.edge_segments:
            horizontal = start.y() == end.y()
            for point in (start, end):
                key = (point.x(), point.y(), horizontal)
                junctions[key] = max(junctions.get(key, 0), style['width']/2)
        paths = {}
        for style, start, end in self.edge_segments:
            horizontal = start.y() == end.y()
            first = junctions.get((start.x(), start.y(), not horizontal), 0)
            last = junctions.get((end.x(), end.y(), not horizontal), 0)
            half = style['width']/2
            if horizontal:
                rect = QRectF(start.x()-first, start.y()-half, end.x()-start.x()+first+last, style['width'])
            else:
                rect = QRectF(start.x()-half, start.y()-first, style['width'], end.y()-start.y()+first+last)
            key = (style['color'], style['opacity'])
            if key not in paths:
                paths[key] = QPainterPath()
                paths[key].setFillRule(Qt.FillRule.WindingFill)
            paths[key].addRect(rect)
        self.edge_paths = tuple((color, opacity, path) for (color, opacity), path in paths.items())

    def edge_style(self, key):
        return self.edge_styles.get(key,self.table['border'])

    def hit(self, point):
        if not 0 <= point.x() < self.width or not 0 <= point.y() < self.height:
            return None
        return self.anchors[bisect_right(self.y,point.y())-1,bisect_right(self.x,point.x())-1]

    def paint(self, painter):
        """Pinta em coordenadas locais; posicionamento é responsabilidade do item."""
        from core.table_paint import paint_table_local
        paint_table_local(painter,self)
