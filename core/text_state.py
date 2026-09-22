from dataclasses import dataclass

from core.ui_font import DOCUMENT_FONT_FAMILY

@dataclass
class TextState:
    """
    Fonte da Verdade para as propriedades de texto.
    Isola os metadados de formatação global do conteúdo HTML (limpo).
    """
    html_content: str = "Placeholder"
    font_family: str = DOCUMENT_FONT_FAMILY
    font_size: int = 16
    align: str = "left"
    vertical_align: str = "top"
    indent_px: float = 0.0
    line_height: float = 1.15
    font_color: str = "#000000"
    has_link: bool = False
    link_key: str = ""
