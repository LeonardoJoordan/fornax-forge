"""Pintura comum do canvas, prévia e arquivo; sem overlays nem acesso à UI."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter


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


def paint_table(painter, layout):
    table = layout.table
    if not table.get('visible',True):
        return
    painter.save()
    try:
        painter.setOpacity(painter.opacity()*table.get('opacity',1))
        painter.translate(table.get('x',0)+layout.width/2,table.get('y',0)+layout.height/2)
        painter.rotate(table.get('rotation',0))
        painter.translate(-layout.width/2,-layout.height/2)
        paint_table_local(painter,layout)
    finally:
        painter.restore()
