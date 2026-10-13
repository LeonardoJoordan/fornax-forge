"""Pintura comum do canvas, prévia e arquivo; sem overlays nem acesso à UI."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor,QPainter
from core.text_effects import paint_object_shadow, active_shadow


def paint_table_local(painter, layout, *, editing_cell=None, exposed_rect=None):
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing,False)
        base_opacity = painter.opacity()
        for entry in layout.cells:
            if exposed_rect is not None and not entry.rect.intersects(exposed_rect):
                continue
            painter.setOpacity(base_opacity*entry.style['fill_opacity'])
            painter.fillRect(entry.rect,QColor(entry.style['fill_color']))
        painter.setOpacity(base_opacity)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing,True)
        for entry in layout.cells:
            if entry.cell['id'] == editing_cell:
                continue
            if exposed_rect is not None and not entry.inner.intersects(exposed_rect):
                continue
            painter.save()
            try:
                painter.setClipRect(entry.inner,Qt.ClipOperation.IntersectClip)
                painter.translate(entry.inner.left(),entry.inner.top()+entry.offset_y)
                entry.document.drawContents(painter)
            finally:
                painter.restore()
        for color, opacity, path in layout.edge_paths:
            painter.setOpacity(base_opacity*opacity)
            painter.fillPath(path, QColor(color))
    finally:
        painter.restore()


def table_paint_bounds(layout):
    width = max([layout.table['border']['width'], *(e['style'].get('width', layout.table['border']['width'])
                                                  for e in layout.table['edges'])])
    return QRectF(0, 0, layout.width, layout.height).adjusted(-width/2, -width/2, width/2, width/2)


def paint_table_shadow(painter, layout, cache=None, source_key=None):
    if not active_shadow(layout.table):
        return
    if source_key is None:
        source_key = ('table', layout.table['column_widths'], layout.table['row_heights'],
                      layout.table['border'], layout.table['edges'],
                      tuple((entry.rect.getRect(), entry.inner.getRect(), entry.offset_y,
                             entry.style, entry.document.toHtml()) for entry in layout.cells))
    paint_object_shadow(painter, table_paint_bounds(layout), layout.table,
                        lambda target: paint_table_local(target, layout), source_key, cache)


def paint_table(painter, layout, shadow_cache=None):
    table = layout.table
    if not table.get('visible',True):
        return
    painter.save()
    try:
        painter.setOpacity(painter.opacity()*table.get('opacity',1))
        painter.translate(table.get('x',0)+layout.width/2,table.get('y',0)+layout.height/2)
        painter.rotate(table.get('rotation',0))
        painter.translate(-layout.width/2,-layout.height/2)
        paint_table_shadow(painter, layout, shadow_cache)
        paint_table_local(painter,layout)
    finally:
        painter.restore()
