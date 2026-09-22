import hashlib
import json
from pathlib import Path
import tempfile
import threading

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from core.paths import get_models_dir
from core.template_manager import slugify_model_name


CACHE_DIR_NAME = ".render_cache"
MANIFEST_NAME = "manifest.json"
CACHE_VERSION = 2
_MANIFEST_LOCK = threading.RLock()


def page_cache_id(template_data: dict, page_id: str | None = None) -> str:
    value = page_id or template_data.get("__page_id") or "front"
    return value if value in {"front", "back"} else "front"


def thumbnail_cache_path(model_dir: Path, page_id: str = "front") -> Path:
    return _cache_dir(Path(model_dir)) / f"thumbnail_{page_id}.png"


def infer_model_dir(template_data: dict) -> Path | None:
    explicit = template_data.get("__model_dir")
    if explicit:
        return Path(explicit)

    bg_raw = template_data.get("background_path")
    if bg_raw:
        bg_path = Path(bg_raw)
        if bg_path.is_absolute():
            if bg_path.parent.name == "assets":
                return bg_path.parent.parent
            if any((bg_path.parent / filename).exists() for filename in ("template_v4.json", "template_v3.json")):
                return bg_path.parent

    name = template_data.get("name")
    if name:
        return get_models_dir() / slugify_model_name(name)

    return None


def _cache_dir(model_dir: Path) -> Path:
    return model_dir / CACHE_DIR_NAME


def _manifest_path(model_dir: Path) -> Path:
    return _cache_dir(model_dir) / MANIFEST_NAME


def _read_manifest(model_dir: Path) -> dict:
    path = _manifest_path(model_dir)
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_manifest(model_dir: Path, manifest: dict):
    cache_dir = _cache_dir(model_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".manifest-", suffix=".tmp", dir=cache_dir, delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
        temporary.replace(_manifest_path(model_dir))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def source_revision(source_path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    except OSError:
        return None


def get_thumbnail_cache_path(model_dir: Path, source_path: Path, page_id: str = "front") -> Path | None:
    model_dir = Path(model_dir)
    source_path = Path(source_path)
    page_id = page_cache_id({}, page_id)
    path = thumbnail_cache_path(model_dir, page_id)
    revision = source_revision(source_path)
    if revision is None or not path.is_file():
        return None
    with _MANIFEST_LOCK:
        entry = _read_manifest(model_dir).get("thumbnails", {}).get(page_id)
    expected = {
        "version": CACHE_VERSION,
        "page_id": page_id,
        "source": Path(source_path).name,
        "revision": revision,
        "path": str(path.relative_to(model_dir)),
    }
    return path if entry == expected else None


def publish_thumbnail_cache(
    model_dir: Path, source_path: Path, image: QImage, page_id: str = "front",
    expected_revision: str | None = None,
) -> Path | None:
    model_dir = Path(model_dir)
    source_path = Path(source_path)
    page_id = page_cache_id({}, page_id)
    revision = source_revision(source_path)
    if revision is None or expected_revision is not None and revision != expected_revision:
        return None
    path = thumbnail_cache_path(model_dir, page_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}-", suffix=".tmp.png", dir=path.parent, delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        if not image.save(str(temporary), "PNG"):
            return None
        if source_revision(source_path) != revision:
            return None
        entry = {
            "version": CACHE_VERSION,
            "page_id": page_id,
            "source": Path(source_path).name,
            "revision": revision,
            "path": str(path.relative_to(model_dir)),
        }
        with _MANIFEST_LOCK:
            if source_revision(source_path) != revision:
                return None
            temporary.replace(path)
            manifest = _read_manifest(model_dir)
            manifest.setdefault("thumbnails", {})[page_id] = entry
            _write_manifest(model_dir, manifest)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def _resolve_model_path(model_dir: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None

    path = Path(raw_path)
    if path.is_absolute():
        return path

    return model_dir / path


def _relative_to_model(model_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(model_dir))
    except ValueError:
        return str(path)


def _float_value(value, default=0.0, digits=3) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return round(float(default), digits)


def _background_spec(template_data: dict, source_path: Path, model_dir: Path) -> dict | None:
    canvas = template_data.get("canvas_size", {})
    canvas_w = int(canvas.get("w", 0) or 0)
    canvas_h = int(canvas.get("h", 0) or 0)
    if canvas_w <= 0 or canvas_h <= 0:
        return None

    bg_props = template_data.get("bg_props", {}) or {}
    if not bg_props.get("visible", True):
        return None

    if not source_path.exists():
        return None

    stat = source_path.stat()
    return {
        "version": CACHE_VERSION,
        "page_id": page_cache_id(template_data),
        "source": _relative_to_model(model_dir, source_path),
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "canvas_size": {"w": canvas_w, "h": canvas_h},
        "bg_props": {
            "x": _float_value(bg_props.get("x", 0), 0),
            "y": _float_value(bg_props.get("y", 0), 0),
            "w": _float_value(bg_props.get("w", canvas_w), canvas_w),
            "h": _float_value(bg_props.get("h", canvas_h), canvas_h),
            "opacity": _float_value(bg_props.get("opacity", 1.0), 1.0, digits=4),
            "visible": True,
        },
    }


def _spec_key(spec: dict) -> str:
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_entry(template_data: dict, model_dir: Path) -> tuple[dict, Path, Path] | None:
    source_path = _resolve_model_path(model_dir, template_data.get("background_path", ""))
    if not source_path:
        return None

    spec = _background_spec(template_data, source_path, model_dir)
    if not spec:
        return None

    key = _spec_key(spec)
    rel_proxy = f"{CACHE_DIR_NAME}/background_{key}.png"
    proxy_path = model_dir / rel_proxy
    entry = {
        "kind": "background",
        "key": key,
        "proxy": rel_proxy,
        "spec": spec,
    }
    return entry, source_path, proxy_path


def get_background_proxy_path(model_dir: Path | None, template_data: dict) -> Path | None:
    if model_dir is None:
        return None

    built = _build_entry(template_data, model_dir)
    if not built:
        _clear_background_proxy(model_dir, page_cache_id(template_data))
        return None

    expected_entry, _, proxy_path = built
    if not proxy_path.exists():
        return None

    with _MANIFEST_LOCK:
        manifest = _read_manifest(model_dir)
    if manifest.get("backgrounds", {}).get(page_cache_id(template_data)) != expected_entry:
        return None

    return proxy_path


def ensure_background_proxy(model_dir: Path | None, template_data: dict) -> Path | None:
    try:
        return _ensure_background_proxy(model_dir, template_data)
    except Exception:
        return None


def _ensure_background_proxy(model_dir: Path | None, template_data: dict) -> Path | None:
    if model_dir is None:
        return None

    built = _build_entry(template_data, model_dir)
    if not built:
        return None

    expected_entry, source_path, proxy_path = built
    current = get_background_proxy_path(model_dir, template_data)
    if current:
        return current

    proxy_path.parent.mkdir(parents=True, exist_ok=True)
    spec = expected_entry["spec"]
    canvas = spec["canvas_size"]
    props = spec["bg_props"]

    image = QImage(canvas["w"], canvas["h"], QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    target_w = max(1, int(round(abs(props["w"]))))
    target_h = max(1, int(round(abs(props["h"]))))

    reader = QImageReader(str(source_path))
    reader.setAutoTransform(True)
    reader.setScaledSize(QSize(target_w, target_h))
    bg = reader.read()

    if bg.isNull():
        reader = QImageReader(str(source_path))
        reader.setAutoTransform(True)
        bg = reader.read()

    if bg.isNull():
        return None

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(props["opacity"])
        painter.drawImage(
            QRectF(props["x"], props["y"], props["w"], props["h"]),
            bg,
            QRectF(bg.rect()),
        )
    finally:
        painter.end()

    with tempfile.NamedTemporaryFile(
        prefix=f".{proxy_path.stem}-", suffix=".tmp.png", dir=proxy_path.parent, delete=False,
    ) as stream:
        temporary_proxy = Path(stream.name)
    try:
        if not image.save(str(temporary_proxy), "PNG"):
            return None
        with _MANIFEST_LOCK:
            if not proxy_path.exists():
                temporary_proxy.replace(proxy_path)
            manifest = _read_manifest(model_dir)
            manifest.pop("background", None)
            manifest.setdefault("backgrounds", {})[page_cache_id(template_data)] = expected_entry
            _write_manifest(model_dir, manifest)
            _cleanup_old_background_proxies(model_dir, manifest)
    finally:
        temporary_proxy.unlink(missing_ok=True)
    return proxy_path


def _cleanup_old_background_proxies(model_dir: Path, manifest: dict):
    cache_dir = _cache_dir(model_dir)
    if not cache_dir.exists():
        return

    keep = {
        model_dir / entry["proxy"]
        for entry in manifest.get("backgrounds", {}).values()
        if isinstance(entry, dict) and entry.get("proxy")
    }

    for path in cache_dir.glob("background_*.png"):
        if path not in keep:
            try:
                path.unlink()
            except OSError:
                pass


def _clear_background_proxy(model_dir: Path, page_id: str):
    cache_dir = _cache_dir(model_dir)
    if not cache_dir.exists():
        return

    with _MANIFEST_LOCK:
        manifest = _read_manifest(model_dir)
        backgrounds = manifest.setdefault("backgrounds", {})
        backgrounds.pop(page_id, None)
        manifest.pop("background", None)
        _write_manifest(model_dir, manifest)
        _cleanup_old_background_proxies(model_dir, manifest)
