"""Fonte incorporada usada exclusivamente pela interface do aplicativo."""

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from core.resources import PROJECT_ROOT


UI_FONT_FAMILY = "Inter 18pt"
DOCUMENT_FONT_FAMILY = UI_FONT_FAMILY


def bundled_font_families() -> set[str]:
    """Famílias disponibilizadas pelo próprio aplicativo, incluindo aliases legíveis."""
    return {UI_FONT_FAMILY, "Inter"}


def install_ui_font(app: QApplication) -> str:
    font_dir = PROJECT_ROOT / "assets" / "fonts" / "ui"
    # As fontes variáveis eram expostas pelo Qt somente como Regular e Italic
    # em algumas plataformas. As variantes estáticas garantem que pesos como
    # Bold e ExtraBold sejam resolvidos para os desenhos reais da família.
    files = tuple(sorted(font_dir.glob("Inter_18pt-*.ttf")))
    families = []
    for path in files:
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))

    family = UI_FONT_FAMILY if UI_FONT_FAMILY in families else (families[0] if families else "")
    if family:
        font = app.font()
        font.setFamily(family)
        app.setFont(font)
    return family
