"""Localização centralizada dos recursos distribuídos com o aplicativo."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = PROJECT_ROOT / "assets" / "icons"
TRANSLATIONS_DIR = PROJECT_ROOT / "assets" / "translations"


def app_icon_path(size: int = 256) -> Path:
    """Retorna o PNG do aplicativo mais adequado ao tamanho solicitado."""
    available = (32, 48, 64, 128, 256, 512, 1024)
    selected = min(available, key=lambda candidate: (abs(candidate - size), candidate < size))
    return ICONS_DIR / f"fornax-forge_{selected}.png"


def windows_icon_path() -> Path:
    return ICONS_DIR / "fornax-forge.ico"


def object_icon_path(name: str) -> Path:
    return ICONS_DIR / "ui" / "objects" / f"{name}.svg"


def state_icon_path(name: str) -> Path:
    return ICONS_DIR / "ui" / "state" / f"{name}.svg"


def action_icon_path(name: str) -> Path:
    return ICONS_DIR / "ui" / "actions" / f"{name}.svg"


def align_icon_path(name: str) -> Path:
    return ICONS_DIR / "ui" / "align" / f"{name}.svg"


def navigation_icon_path(name: str) -> Path:
    return ICONS_DIR / "ui" / "navigation" / f"{name}.svg"


def translation_path(locale: str) -> Path:
    return TRANSLATIONS_DIR / f"fornax_{locale}.qm"
