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
LEGACY_LOGS_SUBDIR = Path("legacy_logs") / "ProjetoComSoc"


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


def _copy_migration_entry(original, target, destination):
    if target.exists() or target.is_symlink():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    # Publicar somente a unidade completamente copiada e verificada.
    with tempfile.TemporaryDirectory(prefix=".migration-", dir=destination) as temporary:
        staged = Path(temporary) / "entry"
        if original.is_dir():
            shutil.copytree(original, staged, copy_function=_verified_copy)
        else:
            _verified_copy(original, staged)
        staged.rename(target)


def _separate_legacy_logs(source, destination):
    """Arquiva o histórico antigo antes de retirar cópias dos logs ativos.

    Migrações anteriores copiaram logs para ``logs/``. Só retiramos bytes
    quando o arquivo ativo começa com o conteúdo exato do histórico arquivado;
    o restante, escrito pelo FORNAX, permanece no arquivo ativo.
    """
    original = source / "logs"
    archive = destination / LEGACY_LOGS_SUBDIR
    if original.is_dir():
        _copy_migration_entry(original, archive, destination)
    active_dir = destination / "logs"
    if not archive.is_dir() or archive.is_symlink() or active_dir.is_symlink():
        return
    for old_log in sorted(archive.iterdir()):
        active = active_dir / old_log.name
        if not old_log.is_file() or not active.is_file() or active.is_symlink():
            continue
        old_bytes = old_log.read_bytes()
        current_bytes = active.read_bytes()
        if not old_bytes or not current_bytes.startswith(old_bytes):
            continue
        remaining = current_bytes[len(old_bytes):]
        if not remaining:
            active.unlink()
            continue
        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".migration-log-", dir=active_dir, delete=False,
            ) as stream:
                staged = Path(stream.name)
                stream.write(remaining)
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copymode(active, staged)
            staged.replace(active)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)


def _migrate_data(source, destination):
    marker = destination / MIGRATION_FILE
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state["complete"] and state.get("legacy_logs_separated"):
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
        original = source / relative
        target = destination / (LEGACY_LOGS_SUBDIR if relative == "logs" else relative)
        _copy_migration_entry(original, target, destination)
        state["pending"].pop(0)
        _save_migration(marker, state)
    _separate_legacy_logs(source, destination)
    state["complete"] = True
    state["legacy_logs_separated"] = True
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

def get_fallback_logs_dir() -> Path:
    """Destino persistente de emergência, independente da migração de dados."""
    system = platform.system()
    if system == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        logs_dir = root / WINDOWS_APP_DIR / "diagnostics"
    elif system == "Darwin":
        logs_dir = Path.home() / "Library" / "Logs" / APP_ID
    else:
        root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        logs_dir = root / APP_ID / "logs"
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
