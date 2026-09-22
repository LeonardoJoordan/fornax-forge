from PySide6.QtGui import QFontDatabase
import re
from html import unescape

from core.ui_font import bundled_font_families


def _normalized_font_name(name: str) -> str:
    return " ".join(str(name or "").strip().casefold().split())


def system_font_families() -> set[str]:
    """Retorna nomes normalizados das fontes disponíveis para o Qt."""
    try:
        families = QFontDatabase.families()
    except TypeError:
        families = QFontDatabase().families()
    return {
        _normalized_font_name(family)
        for family in (*families, *bundled_font_families())
    }


def text_box_font_families(box: dict) -> list[str]:
    """Coleta todas as famílias de uma caixa, inclusive trechos de texto rico."""
    fonts = []
    seen = set()
    families = [str(box.get("font_family", "")).strip()]
    if box.get("rich_text_version") == 1:
        for match in re.findall(
            r'font-family\s*:\s*(.+?)(?=;|["\'](?:\s|>)|$)',
            unescape(box.get("html", "")), re.I,
        ):
            families.extend(part.strip(" '\"") for part in match.split(","))
    for family in families:
        normalized = _normalized_font_name(family)
        if normalized in ("serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"):
            continue
        if family and normalized not in seen:
            fonts.append(family)
            seen.add(normalized)
    return fonts


def template_font_families(template_data: dict) -> list[str]:
    """Coleta as famílias tipográficas declaradas nas caixas de texto do modelo."""
    fonts = []
    seen = set()

    if template_data.get("schema_version") == 4 and isinstance(template_data.get("pages"), list):
        boxes = [box for page in template_data["pages"] for box in page.get("boxes", [])]
    else:
        boxes = template_data.get("boxes", [])

    for box in boxes:
        for family in text_box_font_families(box):
            normalized = _normalized_font_name(family)
            if normalized in ("serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"):
                continue
            if family and normalized not in seen:
                fonts.append(family)
                seen.add(normalized)

    return fonts


def missing_template_fonts(template_data: dict) -> list[str]:
    available = system_font_families()
    missing = []

    for family in template_font_families(template_data):
        if _normalized_font_name(family) not in available:
            missing.append(family)

    return missing


def is_font_available(family: str, available: set[str] | None = None) -> bool:
    available = system_font_families() if available is None else available
    normalized = _normalized_font_name(family)
    if normalized in available:
        return True
    # Os arquivos incorporados são expostos pelo Qt como "Inter 18pt" em
    # algumas plataformas, embora documentos e HTML usem também "Inter".
    return normalized == "inter" and _normalized_font_name("Inter 18pt") in available


def format_font_list(fonts: list[str]) -> str:
    return ", ".join(fonts)
