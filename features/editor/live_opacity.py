"""Prévia imediata de opacidade sem checkpoints intermediários no histórico."""


def preview_property(window, callback, *args):
    depth = getattr(window, '_live_property_preview_depth', 0)
    window._live_property_preview_depth = depth + 1
    try:
        return callback(*args)
    finally:
        window._live_property_preview_depth = depth


def connect_live_opacity(window, spin, callback, *, available=None):
    """Mantém a confirmação existente no editingFinished; apenas antecipa a pintura."""
    applying = False

    def preview(value):
        nonlocal applying
        if applying or available is not None and not available():
            return
        applying = True
        try:
            preview_property(window, callback, value)
        finally:
            applying = False

    spin.valueChanged.connect(preview)
