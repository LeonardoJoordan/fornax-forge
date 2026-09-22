"""Metadados compactos usados pela tela de informações do modelo."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from core.font_utils import text_box_font_families


ORIGIN_INFO_KEY = "origin_info"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_model_snapshot(document: dict, *, source: str, captured_at: str | None = None) -> dict:
    text_boxes = []
    assets = []
    for page_number, page in enumerate(document.get("pages", []), 1):
        for index, box in enumerate(page.get("boxes", []), 1):
            text_boxes.append({
                "page": page_number,
                "name": str(box.get("custom_name") or box.get("id") or f"Texto {index}"),
                "fonts": text_box_font_families(box),
            })
        background = page.get("background_path")
        if background:
            assets.append({"page": page_number, "name": Path(background).name})
        for collection in ("images", "signatures"):
            for item in page.get(collection, []):
                path = item.get("path")
                if path:
                    assets.append({"page": page_number, "name": Path(path).name})
    return {
        "captured_at": captured_at or _timestamp(),
        "source": source,
        "name": str(document.get("name", "")),
        "width_mm": document.get("target_w_mm"),
        "height_mm": document.get("target_h_mm"),
        "page_count": len(document.get("pages", [])),
        "assets": assets,
        "text_boxes": text_boxes,
    }


def ensure_origin_info(document: dict, *, source: str = "created") -> dict:
    """Retorna uma cópia com o primeiro estado preservado, sem sobrescrevê-lo."""
    result = deepcopy(document)
    if not isinstance(result.get(ORIGIN_INFO_KEY), dict):
        result[ORIGIN_INFO_KEY] = build_model_snapshot(result, source=source)
    return result


def current_model_snapshot(document: dict, *, captured_at: str | None = None) -> dict:
    return build_model_snapshot(document, source="current", captured_at=captured_at)
