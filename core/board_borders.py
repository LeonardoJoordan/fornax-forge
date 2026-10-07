"""Bordas dos cartões e dos conjuntos, compartilhadas por edição e saída."""
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from core.model_document import ModelValidationError
from core.object_style import rounded_rect_path, paint_shape_path

UNITS_PER_MM = 300 / 25.4
DEFAULT_BORDER = {
    "cards": False, "group": False, "color": "#333333", "width_mm": 0.3,
    "opacity": 1.0, "radius_mm": 0.0, "padding_mm": 2.0,
    "cards_position": "inside", "group_position": "outside", "join": "miter",
}
APPEARANCE_KEYS = (
    "color", "width_mm", "opacity", "radius_mm", "join",
    "corner_radii_mm", "corner_radii_linked",
)


def border_style(group, target=None):
    """Resolve cada contorno; arquivos antigos conservam sua aparência comum."""
    style = {**DEFAULT_BORDER, **group.get("border", {})}
    if 'target' not in style:
        style['target'] = 'both' if style['cards'] and style['group'] else 'group' if style['group'] else 'cards'
    target = target or style['target']
    # Na edição conjunta, os controles partem do cartão e aplicam a ambos.
    key = 'group_style' if target == 'group' else 'cards_style'
    if key in style:
        appearance = style[key]
        for name in APPEARANCE_KEYS:
            style.pop(name, None)
        style.update({name: value for name, value in DEFAULT_BORDER.items() if name in APPEARANCE_KEYS})
        style.update(appearance)
    return style


def validate_border_style(style):
    if not isinstance(style, dict):
        raise ModelValidationError("A aparência da borda deve ser um objeto.")
    for key in ('cards_style', 'group_style'):
        appearance = style.get(key, {})
        if not isinstance(appearance, dict) or any(name not in APPEARANCE_KEYS for name in appearance):
            raise ModelValidationError("A aparência individual do contorno é inválida.")
        validate_border_appearance(appearance)
    for key in ("cards", "group"):
        if type(style.get(key, DEFAULT_BORDER[key])) is not bool:
            raise ModelValidationError("Opção de borda inválida.")
    for key in ("cards_position", "group_position"):
        if style.get(key, DEFAULT_BORDER[key]) not in ("inside", "center", "outside"):
            raise ModelValidationError("Posição da borda inválida.")
    if style.get('target', 'cards') not in ('cards', 'group', 'both'):
        raise ModelValidationError("Aplicação do contorno inválida.")
    validate_border_appearance(style)
    value = style.get('padding_mm', DEFAULT_BORDER['padding_mm'])
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 1000):
        raise ModelValidationError("Folga do contorno inválida.")


def validate_border_appearance(style):
    if style.get("join", "miter") not in ("miter", "round"):
        raise ModelValidationError("Cantos do contorno inválidos.")
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
                           ("radius_mm", 0, 1000)):
        value = style.get(key, DEFAULT_BORDER[key])
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ModelValidationError("Espessura, transparência, raio ou folga de borda inválidos.")


def group_border_rect(group):
    from core.organogram import group_rect
    style = border_style(group, 'group')
    # A folga define o retângulo de referência; a posição define onde cresce o traço.
    padding = style["padding_mm"] * UNITS_PER_MM
    return group_rect(group).adjusted(-padding, -padding, padding, padding)


def bordered_group_bounds(group):
    from core.organogram import group_rect
    bounds = group_rect(group)
    card = border_style(group, 'cards')
    frame = border_style(group, 'group')
    if card["cards"] and card["opacity"] > 0:
        bounds = bounds.united(bordered_card_bounds(group, bounds))
    if frame["group"] and frame["opacity"] > 0:
        margin = _outer_margin(frame, "group_position")
        bounds = bounds.united(group_border_rect(group).adjusted(-margin, -margin, margin, margin))
    return bounds


def _outer_margin(style, position_key):
    fraction = {"inside": 0, "center": 0.5, "outside": 1}[style[position_key]]
    return style["width_mm"] * UNITS_PER_MM * fraction


def bordered_card_bounds(group, rect):
    style = border_style(group, 'cards')
    margin = _outer_margin(style, "cards_position") if style["cards"] and style["opacity"] > 0 else 0
    return rect.adjusted(-margin, -margin, margin, margin)


def card_clip_path(group, rect):
    """O cartão e seu contorno compartilham a silhueta, como nas formas."""
    style = border_style(group, 'cards')
    radii = _corner_radii(style) if style['cards'] else {}
    return rounded_rect_path(rect, radii)


def _corner_radii(style):
    return {key: style.get('corner_radii_mm', {}).get(key, style['radius_mm']) * UNITS_PER_MM
            for key in ('top_left', 'top_right', 'bottom_left', 'bottom_right')}


def group_border_path(group):
    """Limita os cantos pela folga restante até o contorno dos cartões."""
    style = border_style(group, 'group')
    width = style['width_mm'] * UNITS_PER_MM
    inward = width - _outer_margin(style, 'group_position')
    card = border_style(group, 'cards')
    card_outward = (_outer_margin(card, 'cards_position')
                    if card['cards'] and card['opacity'] > 0 else 0)
    clearance = max(0, style['padding_mm'] * UNITS_PER_MM - inward - card_outward)
    safe_radius = inward + (2 + math.sqrt(2)) * clearance
    radii = {key: min(radius, safe_radius) for key, radius in _corner_radii(style).items()}
    return rounded_rect_path(group_border_rect(group), radii)


def paint_group_borders(painter, group, card_rects):
    """Contornos independentes; o conjunto não pinta sobre os cartões."""
    card = border_style(group, 'cards')
    frame = border_style(group, 'group')
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        def draw(path, style, position):
            paint_shape_path(painter, path, {
                "fill_opacity": 0, "outline_enabled": True, "outline_color": style["color"],
                "outline_width": style['width_mm'] * UNITS_PER_MM, "outline_opacity": style["opacity"],
                "outline_position": position, "outline_join": style["join"],
            })
        if card["cards"] and card['opacity'] > 0:
            for rect in card_rects:
                draw(card_clip_path(group, rect), card, card["cards_position"])
        if frame["group"] and frame['opacity'] > 0:
            from core.organogram import group_rect
            # Uma espessura interna maior que a folga também não pode cobrir
            # o cartão. A proteção permanece vetorial na saída PDF.
            protected = bordered_card_bounds(group, group_rect(group))
            outer = QPainterPath()
            outer.addRect(bordered_group_bounds(group).adjusted(-1, -1, 1, 1))
            inner = QPainterPath()
            inner.addRect(protected)
            painter.setClipPath(outer.subtracted(inner), Qt.ClipOperation.IntersectClip)
            draw(group_border_path(group), frame, frame["group_position"])
    finally:
        painter.restore()
