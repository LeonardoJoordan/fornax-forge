"""Primitivas locais de publicação: exclusão mútua e criação sem sobrescrita."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QLockFile


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path))
    # Não considerar uma operação longa como abandonada; Qt detecta processo morto.
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise OSError(f"Outra operação está usando este arquivo: {path.name}.")
    try:
        yield
    finally:
        lock.unlock()


def publish_new(staged: Path, destination: Path) -> None:
    """Publica bytes completos sem substituir um destino concorrente.

    Staging e destino pertencem ao mesmo filesystem. Sem suporte a hard links,
    falha preservando a origem; nunca recorre a uma cópia parcial no destino.
    """
    os.link(staged, destination)
    sync_directory(destination.parent)
    staged.unlink()
    sync_directory(staged.parent)


def sync_directory(directory: Path) -> None:
    # Nem todos os sistemas permitem fsync de diretório (notadamente Windows).
    import errno
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        if exc.errno in {errno.EINVAL, errno.ENOTSUP} or (
            os.name == "nt" and exc.errno in {errno.EACCES, errno.EPERM, errno.EISDIR}
        ):
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
                raise
    finally:
        os.close(descriptor)
