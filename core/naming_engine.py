import re
import unicodedata
from pathlib import Path
from typing import Dict, Set

_INVALID_WIN_CHARS = r'<>:"/\\|?*'
_INVALID_WIN_RE = re.compile(f"[{re.escape(_INVALID_WIN_CHARS)}\x00-\x1f]")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
MAX_OUTPUT_BASENAME = 180

def build_output_filename(pattern: str, row: Dict[str, str], used: Set[str]) -> str:
    raw = apply_pattern(pattern, row)
    base = sanitize_filename(raw)
    return unique_filename(base, used)

def apply_pattern(pattern: str, row: Dict[str, str]) -> str:
    """
    Substitui {coluna} pelos valores da linha.
    """
    def repl(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(row.get(key, "")).strip()

    return re.sub(r"\{([^{}]+)\}", repl, pattern)

def sanitize_filename(name: str, replacement: str = "_") -> str:
    """
    Remove caracteres inválidos (Windows) e normaliza espaços/pontos.
    """
    name = unicodedata.normalize("NFC", str(name)).strip()
    name = _INVALID_WIN_RE.sub(replacement, name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^\.+", replacement, name)
    name = name.rstrip(". ").strip()
    name = name or "arquivo"
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:MAX_OUTPUT_BASENAME].rstrip(". ") or "arquivo"

def unique_filename(base: str, used: Set[str]) -> str:
    """
    Se base já existe em used, adiciona sufixo _01, _02...
    """
    folded = {str(value).casefold() for value in used}
    if base.casefold() not in folded:
        used.add(base)
        return base

    i = 1
    while True:
        suffix = f"_{i:02d}"
        candidate = f"{base[:MAX_OUTPUT_BASENAME - len(suffix)]}{suffix}"
        if candidate.casefold() not in folded:
            used.add(candidate)
            return candidate
        i += 1


def confined_output_path(directory, filename: str) -> Path:
    """Retorna um destino simples dentro da pasta, recusando escapes e symlinks."""
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise ValueError("Nome de arquivo de saída inválido.")
    root = Path(directory).resolve()
    candidate = root / filename
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("O arquivo de saída está fora da pasta autorizada.")
    return resolved
