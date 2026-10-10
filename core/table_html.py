"""Distingue texto literal de recursos em marcação/CSS das células."""
from html import unescape
import re
from core.text_safety import text_html_has_unsupported_resources

_MARKUP = re.compile(r'''(?is)<(?:[^>"']|"[^"]*"|'[^']*')*(?:>|$)|<[^>]*$''')
_CSS_BLOCK = re.compile(r'(?is)<style\b[^>]*>.*?(?:</style\s*>|$)')


def cell_html_has_unsupported_resources(content):
    # Dados escapados ("&lt;img src=...&gt;", "url(...)" em texto) não
    # solicitam recursos. A inspeção continua estrita em tags e blocos CSS;
    # entidades em atributos não podem disfarçar url()/src/@import.
    markup = [match.group() for match in _MARKUP.finditer(content)]
    markup.extend(match.group() for match in _CSS_BLOCK.finditer(content))
    return any(text_html_has_unsupported_resources(unescape(part)) for part in markup)
