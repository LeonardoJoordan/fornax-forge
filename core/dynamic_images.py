"""Campos de imagem resolvidos por registro, sem incorporar arquivos ao modelo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


SUPPORTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
FIT_MODES = ("cover", "contain")


@dataclass(frozen=True)
class DynamicImageResult:
    path: Path | None
    status: str
    matches: tuple[Path, ...] = ()


def dynamic_image_fields(document: dict) -> list[str]:
    """Retorna os campos usados por formas dinâmicas nas duas páginas."""
    fields = []
    pages = document.get("pages")
    page_values = pages if isinstance(pages, list) else (document,)
    for page in page_values:
        for shape in page.get("shapes", []):
            field = str(shape.get("dynamic_image_field") or "").strip()
            if field and field not in fields:
                fields.append(field)
    return fields


def _plain_value(value) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def resolve_dynamic_image(directory, value) -> DynamicImageResult:
    """Resolve um nome dentro da pasta configurada e detecta ambiguidades."""
    raw = _plain_value(value)
    if not raw:
        return DynamicImageResult(None, "empty")
    if not directory:
        return DynamicImageResult(None, "directory_missing")

    root = Path(directory).expanduser()
    if not root.is_dir():
        return DynamicImageResult(None, "directory_missing")
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return DynamicImageResult(None, "directory_missing")

    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        return DynamicImageResult(None, "invalid")

    candidate = root / relative

    def confined_file(path: Path) -> tuple[Path | None, bool]:
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            return None, False
        except (OSError, RuntimeError):
            return None, True
        if not resolved.is_relative_to(root):
            return None, True
        if not resolved.is_file():
            return None, False
        return resolved, False

    if relative.suffix:
        resolved, escaped = confined_file(candidate)
        if escaped:
            return DynamicImageResult(None, "invalid")
        if resolved is not None and relative.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS:
            return DynamicImageResult(resolved, "ok", (resolved,))
        return DynamicImageResult(None, "not_found")

    extensions = (*SUPPORTED_IMAGE_EXTENSIONS, *(value.upper() for value in SUPPORTED_IMAGE_EXTENSIONS))
    matches_list = []
    escaped = False
    for extension in extensions:
        resolved, outside = confined_file(candidate.with_suffix(extension))
        escaped = escaped or outside
        if resolved is not None and resolved not in matches_list:
            matches_list.append(resolved)
    if escaped:
        return DynamicImageResult(None, "invalid")
    matches = tuple(matches_list)
    if len(matches) == 1:
        return DynamicImageResult(matches[0], "ok", matches)
    if len(matches) > 1:
        return DynamicImageResult(None, "ambiguous", matches)
    return DynamicImageResult(None, "not_found")
