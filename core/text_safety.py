"""Regras de segurança do HTML textual, sem importar Qt."""
import re

_TEXT_DECORATION_RE = re.compile(
    r"(?i)(?<![-\w])text-decoration(?:-line)?\s*:\s*([^;\"']+)\s*;?"
)
_UNSUPPORTED_TEXT_RESOURCE_RE = re.compile(
    r"(?is)<\s*(?:img|object|embed|iframe|link|svg)\b|"
    r"(?:url\s*\(|@import\b|src\s*=)"
)


def text_html_has_unsupported_resources(html: str) -> bool:
    return bool(_UNSUPPORTED_TEXT_RESOURCE_RE.search(str(html or "")))


def sanitize_text_html(html: str) -> str:
    cleaned = str(html or "")
    cleaned = re.sub(r"(?is)<\s*(?:object|iframe|svg)\b[^>]*>.*?<\s*/\s*(?:object|iframe|svg)\s*>", "", cleaned)
    cleaned = re.sub(r"(?is)<\s*(?:img|embed|link)\b[^>]*>", "", cleaned)
    cleaned = re.sub(r"(?is)@import\s+[^;]+;?", "", cleaned)
    return re.sub(r"(?is)url\s*\([^)]*\)", "none", cleaned)


def normalize_text_decoration(html: str) -> str:
    def replace(match):
        if re.search(r"(?i)\bunderline\b", match.group(1)):
            return "text-decoration: underline;"
        if re.search(r"(?i)\bnone\b", match.group(1)):
            return "text-decoration: none;"
        return ""
    return _TEXT_DECORATION_RE.sub(replace, html)
