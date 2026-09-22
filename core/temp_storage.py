"""Áreas temporárias pertencentes ao FORNAX e limpeza após encerramento anormal."""

from pathlib import Path
import shutil

from core.paths import get_temp_dir


def cleanup_stale_workspaces() -> None:
    """Remove apenas conteúdo da área temporária exclusiva do aplicativo."""
    root = get_temp_dir().resolve()
    for entry in root.iterdir():
        try:
            if entry.is_symlink():
                entry.unlink(missing_ok=True)
                continue
            resolved = entry.resolve(strict=False)
            if not resolved.is_relative_to(root):
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
        except OSError:
            # Um arquivo bloqueado permanece para a próxima inicialização.
            continue
