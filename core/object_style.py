"""Estilo vetorial compartilhado por formas e contorno de texto."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath, QPainter, QPainterPathStroker


def rounded_rect_path(bounds, radii):
    """Cria um retângulo com raio independente em cada canto."""
    if not isinstance(radii, dict):
        radii = {}
    fallback = max(0.0, float(radii.get('all', 0)))
    tl = max(0.0, float(radii.get('top_left', fallback)))
    tr = max(0.0, float(radii.get('top_right', fallback)))
    br = max(0.0, float(radii.get('bottom_right', fallback)))
    bl = max(0.0, float(radii.get('bottom_left', fallback)))
    width, height = max(0.0, bounds.width()), max(0.0, bounds.height())
    limits = [1.0]
    for available, used in ((width, tl + tr), (width, bl + br),
                            (height, tl + bl), (height, tr + br)):
        if used > 0:
            limits.append(available / used)
    scale = min(limits)
    tl, tr, br, bl = (value * scale for value in (tl, tr, br, bl))

    left, top, right, bottom = bounds.left(), bounds.top(), bounds.right(), bounds.bottom()
    path = QPainterPath()
    path.moveTo(left + tl, top)
    path.lineTo(right - tr, top)
    if tr:
        path.arcTo(QRectF(right - 2 * tr, top, 2 * tr, 2 * tr), 90, -90)
    path.lineTo(right, bottom - br)
    if br:
        path.arcTo(QRectF(right - 2 * br, bottom - 2 * br, 2 * br, 2 * br), 0, -90)
    path.lineTo(left + bl, bottom)
    if bl:
        path.arcTo(QRectF(left, bottom - 2 * bl, 2 * bl, 2 * bl), 270, -90)
    path.lineTo(left, top + tl)
    if tl:
        path.arcTo(QRectF(left, top, 2 * tl, 2 * tl), 180, -90)
    path.closeSubpath()
    return path


def style_color(item, part):
    color = QColor(item.get(part + '_color', '#ffffff' if part == 'fill' else '#000000'))
    color.setAlphaF(color.alphaF() * max(0, min(1, float(item.get(part + '_opacity', 1)))))
    return color


def outline_pen(item):
    if not item.get("outline_enabled", False):
        return QPen(Qt.NoPen)
    pen = QPen(style_color(item, 'outline'))
    pen.setWidthF(max(0.1, float(item.get("outline_width", 1))))
    pen.setJoinStyle(Qt.MiterJoin if item.get('outline_join') == 'miter' else Qt.RoundJoin)
    return pen


def outline_margin(item):
    if item.get('outline_enabled') and item.get('outline_position') == 'inside':
        return 1
    if item.get('outline_enabled') and item.get('outline_position') == 'outside':
        return max(0.1, float(item.get('outline_width', 1))) + 1
    return outline_pen(item).widthF()/2 + 1 if item.get("outline_enabled", False) else 0


def paint_shape_path(painter, path, item):
    """Posicionamento opt-in; documentos sem a opção mantêm o desenho antigo."""
    position = item.get('outline_position')
    if not item.get('outline_enabled') or position not in ('inside', 'outside', 'center'):
        painter.setPen(outline_pen(item))
        painter.setBrush(style_color(item, 'fill'))
        painter.drawPath(path)
        return
    painter.fillPath(path, style_color(item, 'fill'))
    stroker = QPainterPathStroker()
    width = max(0.1, float(item.get('outline_width', 1)))
    stroker.setWidth(width if position == 'center' else width * 2)
    stroker.setJoinStyle(Qt.MiterJoin if item.get('outline_join') == 'miter' else Qt.RoundJoin)
    stroke = stroker.createStroke(path)
    if position == 'inside':
        stroke = stroke.intersected(path)
    elif position == 'outside':
        stroke = stroke.subtracted(path)
    painter.fillPath(stroke, style_color(item, 'outline'))


def normalize_line_body(item):
    """Preserva o traço antigo ao convertê-lo em corpo com altura independente."""
    if item.get('shape_type') != 'line' or item.get('line_body', False):
        return item
    result = dict(item)
    height = max(0.1, float(item.get('outline_width', 1)))
    result.update(
        line_body=True, height=height,
        y=item.get('y', 0) + (item.get('height', 1) - height) / 2,
        fill_color=item.get('outline_color', '#000000'),
        fill_opacity=item.get('outline_opacity', 1), outline_enabled=False,
    )
    return result


def draw_shape(painter, item):
    item = normalize_line_body(item)
    if not item.get("visible", True):
        return
    w, h = item.get("width", 200), item.get("height", 120)
    if w <= 0 or h <= 0:
        return
    painter.save()
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(item.get("opacity", 1))
        painter.translate(item.get("x", 0)+w/2, item.get("y", 0)+h/2)
        painter.rotate(item.get("rotation", 0))
        path = QPainterPath()
        bounds = QRectF(-w/2, -h/2, w, h)
        if item.get('shape_type') == 'line':
            radius = min(max(0, item.get('corner_radius', 0)), w / 2, h / 2)
            path.addRoundedRect(bounds, radius, radius)
        elif item.get("shape_type", "rectangle") in ("ellipse", "circle"):
            path.addEllipse(bounds)
        else:
            fallback = max(0, float(item.get('corner_radius', 0)))
            radii = dict(item.get('corner_radii') or {})
            radii.setdefault('all', fallback)
            path = rounded_rect_path(bounds, radii)
        paint_shape_path(painter, path, item)
        return painter.transform().mapRect(bounds)
    finally:
        painter.restore()
