"""Geometria e aparência compartilhadas pelo editor e pela saída do quadro."""
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath, QTransform, QPainterPathStroker

from core.model_document import ModelValidationError
from core.board_borders import bordered_group_bounds

UNITS_PER_MM = 300 / 25.4
MAX_CURVE_RADIUS_MM = 100000
DEFAULT_STYLE = {"color": "#333333", "width_mm": 0.3, "opacity": 1.0, "radius_mm": 0.0}
_LEGACY_RADII = {"square": 0.0, "rounded": 5.0, "curved": MAX_CURVE_RADIUS_MM}


def connector_style(edge=None, board=None):
    result = dict(DEFAULT_STYLE)
    for layer in ((board or {}).get("connector_style", {}), (edge or {}).get("style", {})):
        result.update({key: layer[key] for key in DEFAULT_STYLE if key in layer})
        if "radius_mm" not in layer and "mode" in layer:
            result["radius_mm"] = _LEGACY_RADII[layer["mode"]]
    return result


def validate_connector_style(style):
    if not isinstance(style, dict):
        raise ModelValidationError("A aparência do conector deve ser um objeto.")
    color = style.get("color", DEFAULT_STYLE["color"])
    if not isinstance(color, str) or not QColor(color).isValid():
        raise ModelValidationError("Cor de conector inválida.")
    if style.get("mode", "square") not in ("square", "rounded", "curved"):
        raise ModelValidationError("Formato de conector inválido.")
    for key, minimum, maximum in (("width_mm", 0.05, 20), ("opacity", 0, 1),
                                  ("radius_mm", 0, MAX_CURVE_RADIUS_MM)):
        value = style.get(key, DEFAULT_STYLE[key])
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not minimum <= value <= maximum):
            raise ModelValidationError("Espessura, transparência ou raio de conector inválido.")


def connector_pen(style):
    color = QColor(style["color"])
    color.setAlphaF(color.alphaF() * style["opacity"])
    pen = QPen(color, style["width_mm"] * UNITS_PER_MM)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin if style["radius_mm"] == 0 else Qt.PenJoinStyle.RoundJoin)
    return pen


def connector_path(source, target, style, *, points=None, obstacles=None):
    if points is None:
        from core.board_routing import board_routes
        board = {"groups": [source, target], "connections": [{"source": source["id"], "target": target["id"], "style": style}]}
        points = board_routes(board)[(source["id"], target["id"])][0]
    if obstacles is None:
        obstacles = [bordered_group_bounds(source), bordered_group_bounds(target)]
    first, last = points[0], points[-1]
    path = QPainterPath(first)
    requested_radius = style["radius_mm"] * UNITS_PER_MM
    if requested_radius > 0:
        stroker = QPainterPathStroker()
        stroker.setWidth(style["width_mm"] * UNITS_PER_MM)
        half_width = stroker.width() / 2
        # Arredonda cada quina sem ultrapassar metade dos segmentos vizinhos.
        for index in range(1, len(points) - 1):
            previous, corner, following = points[index - 1:index + 2]
            incoming, outgoing = corner - previous, following - corner
            before, after = math.hypot(incoming.x(), incoming.y()), math.hypot(outgoing.x(), outgoing.y())
            if (min(before, after) < 1e-6
                    or abs(incoming.x() * outgoing.y() - incoming.y() * outgoing.x()) < 1e-6):
                path.lineTo(corner)
                continue
            radius = min(requested_radius, before / 2, after / 2)
            # Curvas amplas precisam caber no mesmo corredor da rota ortogonal.
            # Reduz o raio quando o arredondamento invadir um bloco vizinho.
            for _ in range(12):
                entry = corner - incoming * (radius / before)
                exit = corner + outgoing * (radius / after)
                arc = QPainterPath(entry)
                # Aproximação circular de 90 graus: o valor indica o raio,
                # não apenas a distância arbitrária de uma curva quadrática.
                tangent = 4 * (math.sqrt(2) - 1) / 3 * radius
                control1 = entry + incoming * (tangent / before)
                control2 = exit - outgoing * (tangent / after)
                arc.cubicTo(control1, control2, exit)
                bounds = arc.boundingRect().adjusted(-half_width, -half_width, half_width, half_width)
                candidates = [rect for rect in obstacles if rect.intersects(bounds)]
                stroke = stroker.createStroke(arc) if candidates else None
                if not any(stroke.intersects(rect) for rect in candidates):
                    break
                radius /= 2
            else:
                path.lineTo(corner)
                continue
            path.lineTo(entry)
            path.cubicTo(control1, control2, exit)
        path.lineTo(last)
    else:
        for point in points[1:]:
            path.lineTo(point)
    return path


def connector_paths(board, *, routes=None):
    from core.board_routing import board_routes
    if routes is None:
        routes = board_routes(board)
    groups = {group["id"]: group for group in board["groups"]}
    obstacles = [bordered_group_bounds(group) for group in board["groups"]]
    return {(edge["source"], edge["target"]): connector_path(
        groups[edge["source"]], groups[edge["target"]], connector_style(edge, board),
        points=routes[(edge["source"], edge["target"])][0], obstacles=obstacles) for edge in board["connections"]}


def text_cutouts(boxes):
    """Recorta a caixa inteira, inclusive sua rotação, sem pintar um fundo."""
    cutouts = QPainterPath()
    cutouts.setFillRule(Qt.FillRule.WindingFill)
    for box in boxes:
        if not box.get("visible", True) or box.get("opacity", 1) <= 0:
            continue
        w, h = box.get("w", 0), box.get("h", 0)
        transform = QTransform()
        transform.translate(box.get("x", 0) + w / 2, box.get("y", 0) + h / 2)
        transform.rotate(box.get("rotation", 0))
        rectangle = QPainterPath()
        rectangle.addRect(QRectF(-w / 2, -h / 2, w, h))
        cutouts.addPath(transform.map(rectangle))
    return cutouts


def connector_clip(bounds, cutouts):
    clip = QPainterPath()
    clip.addRect(bounds)
    return clip.subtracted(cutouts)
