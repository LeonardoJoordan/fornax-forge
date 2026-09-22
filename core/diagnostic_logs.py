"""Persistência limitada de diagnósticos sem conteúdo operacional sensível."""

from __future__ import annotations

from datetime import datetime
from html import unescape
from pathlib import Path
import re

from core.paths import get_logs_dir


MAX_LOG_BYTES = 1024 * 1024
LOG_BACKUPS = 3
_HTML_RE = re.compile(r"<[^>]+>")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<!\w)(?:[A-Za-z]:[\\/]|/)(?:[^\s<>\"']+)", re.UNICODE
)
_ITEM_RESULT_RE = re.compile(r"^(\[\d+/\d+\][^:\n]*:).*$")


def sanitize_log_message(message: str) -> str:
    """Mantém a categoria do evento e remove detalhes úteis apenas na tela."""
    first_line = str(message or "").splitlines()[0]
    plain = unescape(_HTML_RE.sub("", first_line)).strip()
    plain = _ABSOLUTE_PATH_RE.sub("[caminho omitido]", plain)
    match = _ITEM_RESULT_RE.match(plain)
    if match:
        plain = f"{match.group(1)} [detalhes omitidos]"
    return plain or "Evento sem descrição."


def _rotate(path: Path, incoming_size: int, *, max_bytes: int, backups: int) -> None:
    if not path.exists() or path.stat().st_size + incoming_size <= max_bytes:
        return
    oldest = path.with_name(f"{path.name}.{backups}")
    oldest.unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def append_diagnostic_log(
    filename: str,
    message: str,
    *,
    sanitize: bool = True,
    max_bytes: int = MAX_LOG_BYTES,
    backups: int = LOG_BACKUPS,
) -> Path:
    if Path(filename).name != filename or not filename:
        raise ValueError("Nome de log inválido.")
    path = get_logs_dir() / filename
    content = sanitize_log_message(message) if sanitize else str(message)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {content}\n"
    encoded = line.encode("utf-8")
    _rotate(path, len(encoded), max_bytes=max_bytes, backups=backups)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
    return path


def clear_diagnostic_log(filename: str, *, backups: int = LOG_BACKUPS) -> None:
    if Path(filename).name != filename or not filename:
        raise ValueError("Nome de log inválido.")
    root = get_logs_dir()
    for index in range(0, backups + 1):
        suffix = "" if index == 0 else f".{index}"
        (root / f"{filename}{suffix}").unlink(missing_ok=True)


def crash_summary(exc_type, exc_traceback) -> str:
    """Descreve a pilha sem caminhos absolutos, código-fonte ou valores."""
    lines = [f"Exceção não tratada: {getattr(exc_type, '__name__', 'Erro')}"]
    import traceback
    for frame in traceback.extract_tb(exc_traceback):
        lines.append(f"  {Path(frame.filename).name}:{frame.lineno} em {frame.name}")
    return "\n".join(lines)
