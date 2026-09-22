import os
import platform
import shutil
import json
import hashlib
import tempfile
from pathlib import Path


APP_ID = "com.leobelisario.FornaxForge"
LEGACY_APP_ID = "com.leobelisario.ProjetoComSoc"
WINDOWS_APP_DIR = "FornaxForge"
LEGACY_WINDOWS_APP_DIR = "ProjetoComSoc"


def _data_home() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("APPDATA") or Path.home())
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def get_legacy_app_data_dir() -> Path:
    """Retorna a antiga pasta de dados sem criá-la ou modificá-la."""
    name = LEGACY_WINDOWS_APP_DIR if platform.system() == "Windows" else LEGACY_APP_ID
    return _data_home() / name


MIGRATION_FILE = ".comsoc-migration.json"


def _verified_copy(source, target):
    shutil.copy2(source, target)
    def digest(path):
        with open(path, "rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()
    if digest(source) != digest(target):
        raise OSError(f"Falha ao verificar a cópia de {source}")
    return target


def _save_migration(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _migrate_data(source, destination):
    marker = destination / MIGRATION_FILE
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state["complete"]:
            return
    else:
        # Cada modelo é uma unidade: nunca misturar assets de versões distintas.
        entries = []
        if source.is_dir():
            for item in sorted(source.iterdir()):
                if item.name == "models" and item.is_dir():
                    entries.extend(str(child.relative_to(source)) for child in sorted(item.iterdir()))
                elif not item.name.startswith("."):
                    entries.append(item.name)
        state = {"complete": False, "pending": entries}
        _save_migration(marker, state)
    while state["pending"]:
        relative = state["pending"][0]
        original, target = source / relative, destination / relative
        if not target.exists() and not target.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            # Publicar somente a unidade completamente copiada e verificada.
            with tempfile.TemporaryDirectory(prefix=".migration-", dir=destination) as temporary:
                staged = Path(temporary) / "entry"
                if original.is_dir():
                    shutil.copytree(original, staged, copy_function=_verified_copy)
                else:
                    _verified_copy(original, staged)
                staged.rename(target)
        state["pending"].pop(0)
        _save_migration(marker, state)
    state["complete"] = True
    _save_migration(marker, state)


def get_app_data_dir() -> Path:
    """Migra uma vez; retomadas respeitam unidades concluídas e conflitos."""
    name = WINDOWS_APP_DIR if platform.system() == "Windows" else APP_ID
    app_dir = _data_home() / name
    app_dir.mkdir(parents=True, exist_ok=True)
    _migrate_data(get_legacy_app_data_dir(), app_dir)
    return app_dir

def get_logs_dir() -> Path:
    logs_dir = get_app_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir

def get_temp_dir() -> Path:
    temporary_dir = get_app_data_dir() / "temporary"
    try:
        temporary_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        user_token = getattr(os, "getuid", lambda: "user")()
        temporary_dir = Path(tempfile.gettempdir()) / f"{APP_ID}-{user_token}"
        temporary_dir.mkdir(parents=True, exist_ok=True)
    if platform.system() != "Windows":
        try:
            temporary_dir.chmod(0o700)
        except OSError:
            pass
    return temporary_dir

def get_models_dir() -> Path:
    models_dir = get_app_data_dir() / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir
