"""Inventário misto da biblioteca durante a transição para ``.fornax``."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from uuid import uuid4

from core.fornax_container import FULL_MODE, PUBLIC_MODE, FornaxDescriptor, UnsupportedFornaxFeature, inspect_fornax, open_public_fornax
from core.file_transactions import file_lock, sync_directory
from core.model_document import load_model_document
from core.legacy_migration import resume_legacy_migrations


@dataclass(frozen=True, slots=True)
class LibraryModel:
    key: str
    display_name: str
    path: Path
    kind: str
    descriptor: FornaxDescriptor | None = None

    @property
    def is_fornax(self) -> bool:
        return self.kind == "fornax"


def _inspect_recoverable(path):
    descriptor = inspect_fornax(path)
    if descriptor.mode == PUBLIC_MODE:
        open_public_fornax(descriptor)
    return descriptor


def scan_model_library(
    models_dir: str | Path, *, legacy_loader=load_model_document,
) -> tuple[LibraryModel, ...]:
    """Lista pastas legadas e arquivos finais, ignorando resíduos transacionais."""
    directory = Path(models_dir)
    directory.mkdir(parents=True, exist_ok=True)
    suppressed_legacy = set(resume_legacy_migrations(directory))
    found = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if entry.name.startswith(".") or ".pending-" in entry.name or entry.name.endswith(".bak"):
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                if entry.resolve() in suppressed_legacy:
                    continue
                document = legacy_loader(entry)
                found.append(LibraryModel(
                    key=entry.name,
                    display_name=str(document.get("name") or entry.name),
                    path=entry.resolve(),
                    kind="legacy",
                ))
            elif entry.is_file() and not entry.is_symlink() and entry.suffix.lower() == ".fornax":
                try:
                    descriptor = _inspect_recoverable(entry)
                except UnsupportedFornaxFeature:
                    # Versão futura não significa corrupção: não fazer downgrade.
                    continue
                except Exception:
                    backup = entry.with_name(entry.name + ".bak")
                    if backup.is_symlink():
                        continue
                    descriptor = _inspect_recoverable(backup)
                    pending = entry.with_name(f".{entry.name}.recovery-{uuid4().hex}")
                    try:
                        with file_lock(entry.with_name(f".{entry.name}.write.lock")):
                            # Revalidar sob lock: outro escritor pode ter recuperado.
                            try:
                                _inspect_recoverable(entry)
                            except UnsupportedFornaxFeature:
                                continue
                            except Exception:
                                shutil.copyfile(backup, pending)
                                with pending.open("r+b") as stream:
                                    os.fsync(stream.fileno())
                                _inspect_recoverable(pending)
                                os.replace(pending, entry)
                                sync_directory(entry.parent)
                    finally:
                        pending.unlink(missing_ok=True)
                    descriptor = inspect_fornax(entry)
                if descriptor.mode == FULL_MODE:
                    display_name = entry.stem
                else:
                    public = open_public_fornax(descriptor).document()
                    display_name = str(public.get("name") or entry.stem)
                found.append(LibraryModel(
                    key=f"fornax:{descriptor.model_id}",
                    display_name=display_name,
                    path=entry.resolve(),
                    kind="fornax",
                    descriptor=descriptor,
                ))
        except Exception:
            # Uma entrada inválida não impede o acesso aos demais modelos.
            continue
    found.sort(key=lambda model: (model.display_name.casefold(), model.key))
    return tuple(found)
