import re

from PySide6.QtGui import QTextDocument


_TEXT_DECORATION_RE = re.compile(
    r"(?i)(?<![-\w])text-decoration(?:-line)?\s*:\s*([^;\"']+)\s*;?"
)

_UNSUPPORTED_TEXT_RESOURCE_RE = re.compile(
    r"(?is)<\s*(?:img|object|embed|iframe|link|svg)\b|"
    r"(?:url\s*\(|@import\b|src\s*=)"
)


class TextOnlyDocument(QTextDocument):
    """Documento rico que nunca resolve recursos externos.

    As caixas do FORNAX guardam texto formatado. Elementos gráficos pertencem
    às camadas de imagem e, portanto, nenhum recurso solicitado pelo HTML deve
    chegar ao sistema de arquivos ou à rede.
    """

    def loadResource(self, resource_type, name):  # noqa: N802 - API do Qt
        return None


def text_html_has_unsupported_resources(html: str) -> bool:
    """Detecta construções capazes de solicitar ou incorporar recursos."""
    return bool(_UNSUPPORTED_TEXT_RESOURCE_RE.search(str(html or "")))


def sanitize_text_html(html: str) -> str:
    """Remove recursos gráficos/externos sem alterar a tipografia permitida."""
    cleaned = str(html or "")
    cleaned = re.sub(
        r"(?is)<\s*(?:object|iframe|svg)\b[^>]*>.*?<\s*/\s*(?:object|iframe|svg)\s*>",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?is)<\s*(?:img|embed|link)\b[^>]*>", "", cleaned)
    cleaned = re.sub(r"(?is)@import\s+[^;]+;?", "", cleaned)
    cleaned = re.sub(r"(?is)url\s*\([^)]*\)", "none", cleaned)
    return cleaned


def normalize_text_decoration(html: str) -> str:
    """Preserva somente o sublinhado entre as decorações visuais do HTML."""
    def replace_decoration(match: re.Match) -> str:
        value = match.group(1)
        if re.search(r"(?i)\bunderline\b", value):
            return "text-decoration: underline;"
        if re.search(r"(?i)\bnone\b", value):
            return "text-decoration: none;"
        return ""

    return _TEXT_DECORATION_RE.sub(replace_decoration, html)
