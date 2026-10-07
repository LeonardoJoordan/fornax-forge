"""Bordas dos cartões e dos conjuntos, compartilhadas por edição e saída."""
import math

from PySide6.QtGui import QColor, QPainter

from core.model_document import ModelValidationError
from core.object_style import rounded_rect_path, paint_shape_path

UNITS_PER_MM = 300 / 25.4
DEFAULT_BORDER = {
    "cards": False, "group": False, "color": "#333333", "width_mm": 0.3,
    "opacity": 1.0, "radius_mm": 0.0, "padding_mm": 2.0,
    "cards_position": "inside", "group_position": "outside", "join": "miter",
}


def border_style(group):
    style = {**DEFAULT_BORDER, **group.get("border", {})}
    if 'target' not in style:
        style['target'] = 'both' if style['cards'] and style['group'] else 'group' if style['group'] else 'cards'
    return style


def validate_border_style(style):
    if not isinstance(style, dict):
        raise ModelValidationError("A aparência da borda deve ser um objeto.")
    for key in ("cards", "group"):
        if type(style.get(key, DEFAULT_BORDER[key])) is not bool:
            raise ModelValidationError("Opção de borda inválida.")
    for key in ("cards_position", "group_position"):
        if style.get(key, DEFAULT_BORDER[key]) not in ("inside", "center", "outside"):
            raise ModelValidationError("Posição da borda inválida.")
    if style.get("join", "miter") not in ("miter", "round"):
        raise ModelValidationError("Cantos do contorno inválidos.")
    if style.get('target', 'cards') not in ('cards', 'group', 'both'):
        raise ModelValidationError("Aplicação do contorno inválida.")
    if type(style.get('corner_radii_linked', True)) is not bool:
        raise ModelValidationError("Vínculo dos cantos inválido.")
    radii = style.get('corner_radii_mm', {})
    if not isinstance(radii, dict) or any(key not in ('top_left', 'top_right', 'bottom_left', 'bottom_right') for key in radii):
        raise ModelValidationError("Raios dos cantos inválidos.")
    for value in radii.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1000:
            raise ModelValidationError("Raio do canto inválido.")
    color = style.get("color", DEFAULT_BORDER["color"])
    if not isinstance(color, str) or not QColor(color).isValid():
        raise ModelValidationError("Cor de borda inválida.")
    for key, low, high in (("width_mm", 0.01, 1000), ("opacity", 0, 1),
                           ("radius_mm", 0, 1000), ("padding_mm", 0, 1000)):
        value = style.get(key, DEFAULT_BORDER[key])
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ModelValidationError("Espessura, transparência, raio ou folga de borda inválidos.")


def group_border_rect(group):
    from core.organogram import group_rect
    style = border_style(group)
    # A folga define o retângulo de referência; a posição define onde cresce o traço.
    padding = style["padding_mm"] * UNITS_PER_MM
    return group_rect(group).adjusted(-padding, -padding, padding, padding)


def bordered_group_bounds(group):
    from core.organogram import group_rect
    style = border_style(group)
    bounds = group_rect(group)
    if style["opacity"] == 0:
        return bounds
    if style["cards"]:
        bounds = bounds.united(bordered_card_bounds(group, bounds))
    if style["group"]:
        margin = _outer_margin(style, "group_position")
        bounds = bounds.united(group_border_rect(group).adjusted(-margin, -margin, margin, margin))
    return bounds


def _outer_margin(style, position_key):
    fraction = {"inside": 0, "center": 0.5, "outside": 1}[style[position_key]]
    return style["width_mm"] * UNITS_PER_MM * fraction


def bordered_card_bounds(group, rect):
    style = border_style(group)
    margin = _outer_margin(style, "cards_position") if style["cards"] and style["opacity"] > 0 else 0
    return rect.adjusted(-margin, -margin, margin, margin)


def paint_group_borders(painter, group, card_rects):
    """Usa a mesma geometria vetorial de contorno das formas, sem recortar cartões."""
    style = border_style(group)
    if not (style["cards"] or style["group"]) or style["opacity"] == 0:
        return
    width = style["width_mm"] * UNITS_PER_MM
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        def draw(rect, position, *, group_frame=False):
            radii = {key: style.get('corner_radii_mm', {}).get(key, style['radius_mm']) * UNITS_PER_MM
                     for key in ('top_left', 'top_right', 'bottom_left', 'bottom_right')}
            if group_frame:
                # Limita o arco pela folga livre. A parte interna do traço
                # continua crescendo para dentro quando essa posição é escolhida.
                inward = width - _outer_margin(style, "group_position")
                clearance = max(0, style["padding_mm"] * UNITS_PER_MM - inward)
                safe_radius = inward + (2 + math.sqrt(2)) * clearance
                radii = {key: min(radius, safe_radius) for key, radius in radii.items()}
            path = rounded_rect_path(rect, radii)
            paint_shape_path(painter, path, {
                "fill_opacity": 0, "outline_enabled": True, "outline_color": style["color"],
                "outline_width": width, "outline_opacity": style["opacity"],
                "outline_position": position, "outline_join": style["join"],
            })
        if style["cards"]:
            for rect in card_rects:
                draw(rect, style["cards_position"])
        if style["group"]:
            draw(group_border_rect(group), style["group_position"], group_frame=True)
    finally:
        painter.restore()
