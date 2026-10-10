from PySide6.QtGui import QFontDatabase, QTextCharFormat, QTextCursor
import re
from html import unescape

from core.ui_font import resolve_font_family


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
        for family in families
    }


def resolve_bundled_font_aliases(document):
    """Corrige apenas os aliases de família, preservando texto e demais estilos."""
    updates = []
    block_updates = []
    block = document.begin()
    while block.isValid():
        families = block.charFormat().fontFamilies() or []
        resolved = [resolve_font_family(name) for name in families]
        if resolved != families:
            block_updates.append((block.position(), resolved))
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                families = fragment.charFormat().fontFamilies() or []
                resolved = [resolve_font_family(name) for name in families]
                if resolved != families:
                    updates.append((fragment.position(), fragment.length(), resolved))
            iterator += 1
        block = block.next()
    cursor = QTextCursor(document)
    for position, families in block_updates:
        cursor.setPosition(position)
        fmt = QTextCharFormat()
        fmt.setFontFamilies(families)
        cursor.mergeBlockCharFormat(fmt)
    for position, length, families in updates:
        cursor.setPosition(position)
        cursor.setPosition(position+length, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setFontFamilies(families)
        cursor.mergeCharFormat(fmt)


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
    """Coleta famílias de caixas e células, inclusive no verso e no quadro."""
    fonts = []
    seen = set()

    if isinstance(template_data.get("pages"), list):
        pages = [*template_data["pages"], *([template_data["organogram"]] if template_data.get("organogram") else [])]
        boxes = [box for page in pages for box in page.get("boxes", [])]
    else:
        pages = [template_data]
        boxes = template_data.get("boxes", [])

    for box in boxes:
        for family in text_box_font_families(box):
            normalized = _normalized_font_name(family)
            if normalized in ("serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"):
                continue
            if family and normalized not in seen:
                fonts.append(family)
                seen.add(normalized)

    for page in pages:
        for table in page.get('tables', []):
            for family in table_font_families(table):
                normalized = _normalized_font_name(family)
                if normalized not in seen:
                    fonts.append(family)
                    seen.add(normalized)

    return fonts


def table_font_families(table: dict) -> list[str]:
    from core.table_model import effective_cell_style
    fonts = []
    seen = set()
    for cell in table.get('cells', []):
        for family in text_box_font_families({**effective_cell_style(table,cell),
                                            'html':cell['html'], 'rich_text_version':1}):
            normalized = _normalized_font_name(family)
            if normalized not in seen:
                seen.add(normalized)
                fonts.append(family)
    return fonts


def missing_template_fonts(template_data: dict) -> list[str]:
    available = system_font_families()
    missing = []

    for family in template_font_families(template_data):
        if not is_font_available(family, available):
            missing.append(family)

    return missing


def is_font_available(family: str, available: set[str] | None = None) -> bool:
    available = system_font_families() if available is None else available
    return _normalized_font_name(resolve_font_family(family)) in available


def format_font_list(fonts: list[str]) -> str:
    return ", ".join(fonts)
