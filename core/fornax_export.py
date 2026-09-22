"""Cópias de compartilhamento individuais e em lote do formato ``.fornax``."""

from __future__ import annotations

from dataclasses import dataclass
import os
import hashlib
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4
import zipfile

from core.fornax_container import (
    FULL_MODE,
    PUBLIC_MODE,
    FornaxDescriptor,
    FornaxFormatError,
    inspect_fornax,
    open_public_fornax,
    save_protected_fornax,
    save_public_fornax,
    save_signature_free_copy,
    unlock_fornax,
)
from core.template_manager import slugify_model_name
from core.paths import get_temp_dir
from core.file_transactions import file_sha256
from core.model_document import without_signatures


MAX_BATCH_MODELS = 1000
MAX_BATCH_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ExportRequest:
    source: Path
    display_name: str
    local_password: str | None = None
    include_signatures: bool | None = None
    opened: object | None = None
    approved_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ExportedModel:
    source: Path
    exported_name: str
    mode: str
    model_id: str


def _export_copy(
    request: ExportRequest,
    destination: Path,
    *,
    include_signatures: bool,
    transport_password: str | None,
) -> FornaxDescriptor:
    if request.approved_sha256 is not None and file_sha256(request.source) != request.approved_sha256:
        raise FornaxFormatError("O modelo mudou após a autorização para exportar.")
    descriptor = inspect_fornax(request.source)
    effective_include = (
        include_signatures if request.include_signatures is None
        else request.include_signatures
    )
    if descriptor.mode == PUBLIC_MODE:
        opened = open_public_fornax(descriptor)
        document = opened.document()
        if not effective_include:
            document = without_signatures(document)
        return save_public_fornax(
            document, destination, asset_provider=opened.asset,
        )
    if not effective_include:
        return save_signature_free_copy(
            descriptor, destination,
            password=request.local_password if descriptor.mode == FULL_MODE else None,
        )
    if request.local_password is None:
        raise FornaxFormatError(
            f"O modelo protegido {request.display_name!r} exige a senha local."
        )
    if transport_password is None:
        raise FornaxFormatError("A exportação com assinaturas exige uma senha de transporte.")
    opened = request.opened or unlock_fornax(descriptor, request.local_password)
    if opened.descriptor != descriptor:
        raise FornaxFormatError("O acesso autorizado pertence a outro modelo ou revisão.")
    return save_protected_fornax(
        opened.document(), destination, transport_password,
        mode=descriptor.mode, asset_provider=opened.asset,
    )


def _unique_export_name(display_name: str, used: set[str]) -> str:
    base = slugify_model_name(display_name) or "modelo"
    candidate = f"{base}.fornax"
    counter = 2
    while candidate.casefold() in used:
        candidate = f"{base}-{counter}.fornax"
        counter += 1
    used.add(candidate.casefold())
    return candidate


def export_models(
    requests: list[ExportRequest] | tuple[ExportRequest, ...],
    destination: str | Path,
    *,
    include_signatures: bool,
    transport_password: str | None = None,
) -> tuple[ExportedModel, ...]:
    """Exporta uma cópia `.fornax` ou um ZIP de cópias independentes."""
    requests = tuple(requests)
    if not requests:
        raise FornaxFormatError("Nenhum modelo foi informado para exportação.")
    if len(requests) > MAX_BATCH_MODELS:
        raise FornaxFormatError("O lote excede o limite de 1000 modelos.")
    destination = Path(destination)
    single = len(requests) == 1
    expected_suffix = ".fornax" if single else ".zip"
    if destination.suffix.lower() != expected_suffix:
        raise FornaxFormatError(f"A saída deve usar a extensão {expected_suffix}.")
    for request in requests:
        source = Path(request.source)
        if (destination.resolve() == source.resolve()
                or (destination.exists() and destination.samefile(source))):
            raise FornaxFormatError("A exportação não pode sobrescrever o original.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    original_bytes = {
        request.source.resolve(): digest(request.source) for request in requests
    }

    def assert_origins_unchanged():
        for source, before in original_bytes.items():
            if digest(source) != before:
                raise FornaxFormatError("Um modelo original mudou durante a exportação.")

    exported = []
    with tempfile.TemporaryDirectory(prefix="export-", dir=get_temp_dir()) as temporary_dir:
        temporary_root = Path(temporary_dir)
        used_names = set()
        for request in requests:
            name = destination.name if single else _unique_export_name(
                request.display_name, used_names,
            )
            staged = temporary_root / name
            descriptor = _export_copy(
                request, staged, include_signatures=include_signatures,
                transport_password=transport_password,
            )
            exported.append(ExportedModel(
                request.source.resolve(), name, descriptor.mode, descriptor.model_id,
            ))

        assert_origins_unchanged()
        if single:
            staged = temporary_root / destination.name
            pending = destination.with_name(f".{destination.name}.pending-{uuid4().hex}")
            try:
                shutil.copyfile(staged, pending)
                with pending.open("r+b") as stream:
                    os.fsync(stream.fileno())
                inspect_fornax(pending)
                os.replace(pending, destination)
            finally:
                pending.unlink(missing_ok=True)
        else:
            pending = destination.with_name(f".{destination.name}.pending-{uuid4().hex}")
            try:
                total = 0
                with zipfile.ZipFile(pending, "w", zipfile.ZIP_STORED) as archive:
                    for item in exported:
                        staged = temporary_root / item.exported_name
                        size = staged.stat().st_size
                        total += size
                        if total > MAX_BATCH_BYTES:
                            raise FornaxFormatError("O lote excede o limite de 2 GiB.")
                        archive.write(staged, item.exported_name)
                with pending.open("r+b") as stream:
                    os.fsync(stream.fileno())
                with zipfile.ZipFile(pending, "r") as archive:
                    infos = archive.infolist()
                    if len(infos) != len(exported):
                        raise FornaxFormatError("O lote exportado ficou incompleto.")
                    if any(info.file_size > MAX_BATCH_BYTES for info in infos):
                        raise FornaxFormatError("O lote exportado excede os limites.")
                os.replace(pending, destination)
            finally:
                pending.unlink(missing_ok=True)

    assert_origins_unchanged()
    return tuple(exported)
