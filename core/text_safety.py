"""Regras de segurança do HTML textual, sem importar Qt."""
import re
import math

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


def validate_text_shadow(value):
    """Valida efeitos persistidos antes de alocar qualquer bitmap (sem Qt)."""
    if not isinstance(value, dict):
        raise ValueError('Sombra inválida.')
    if 'enabled' in value and type(value['enabled']) is not bool:
        raise ValueError('Ativação da sombra inválida.')
    if 'color' in value and (not isinstance(value['color'], str)
                            or not re.fullmatch(r'#[0-9a-fA-F]{6}', value['color'])):
        raise ValueError('Cor da sombra inválida.')
    for key, maximum in (('opacity', 1), ('angle', 360), ('distance', 240), ('blur', 120), ('spread', 120)):
        if key in value:
            number = value[key]
            if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= maximum:
                raise ValueError(f'Propriedade de sombra inválida: {key}.')
