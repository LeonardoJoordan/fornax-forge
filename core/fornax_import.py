"""Recepção segura de modelos ``.fornax`` individuais e em lote."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from uuid import uuid4
import zipfile

from core.fornax_container import (
    MAX_PACKAGE_BYTES,
    FULL_MODE,
    PUBLIC_MODE,
    SIGNATURES_MODE,
    PROTECTED_MODES,
    FornaxDescriptor,
    FornaxFormatError,
    inspect_fornax,
    open_public_fornax,
    save_protected_fornax,
    save_public_fornax,
    unlock_fornax,
)
from core.model_info import build_model_snapshot
from core.model_document import document_signatures, without_signatures
from core.file_transactions import file_lock, publish_new, sync_directory, file_sha256
from core.paths import get_temp_dir


MAX_BATCH_MODELS = 1000
MAX_BATCH_BYTES = 2 * 1024 * 1024 * 1024
MAX_BATCH_UNCOMPRESSED = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    entry_name: str
    display_name: str
    path: Path
    descriptor: FornaxDescriptor
    source_path: Path | None = None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate(path: Path, entry_name: str) -> ImportCandidate:
    descriptor = inspect_fornax(path)
    if descriptor.mode == FULL_MODE:
        display_name = Path(entry_name).stem
    else:
        document = open_public_fornax(descriptor).document()
        display_name = str(document.get("name") or Path(entry_name).stem)
    return ImportCandidate(entry_name, display_name, path, descriptor)


def _validate_batch_member(info: zipfile.ZipInfo, seen: set[str]) -> None:
    name = info.filename
    path = PurePosixPath(name)
    if (
        not name or "/" in name or "\\" in name or ":" in name
        or any(ord(c) < 32 for c in name) or path.is_absolute() or len(path.parts) != 1
        or path.name in {".", ".."} or path.suffix.lower() != ".fornax"
    ):
        raise FornaxFormatError(f"Entrada de lote inválida: {name!r}.")
    folded = name.casefold()
    if folded in seen:
        raise FornaxFormatError(f"Entrada repetida ou ambígua no lote: {name!r}.")
    seen.add(folded)
    if info.flag_bits & 0x1:
        raise FornaxFormatError("ZIPs protegidos pelo mecanismo tradicional não são aceitos.")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise FornaxFormatError(f"Compressão não permitida em {name!r}.")
    unix_mode = (info.external_attr >> 16) & 0o170000
    if unix_mode == 0o120000:
        raise FornaxFormatError(f"Link simbólico não permitido em {name!r}.")


@contextmanager
def open_import_package(source: str | Path):
    """Materializa somente membros `.fornax` validados durante a operação."""
    source = Path(source).resolve()
    limit = MAX_PACKAGE_BYTES if source.suffix.lower() == ".fornax" else MAX_BATCH_BYTES
    if source.stat().st_size > limit:
        raise FornaxFormatError("O arquivo recebido excede o limite de tamanho.")
    before = _file_sha256(source)
    with tempfile.TemporaryDirectory(prefix="import-", dir=get_temp_dir()) as temporary_dir:
        temporary_root = Path(temporary_dir)
        if source.suffix.lower() == ".fornax":
            candidate_path = temporary_root / source.name
            shutil.copyfile(source, candidate_path)
            os.chmod(candidate_path, 0o600)
            candidates = (_candidate(candidate_path, source.name),)
        elif source.suffix.lower() == ".zip":
            if source.stat().st_size > MAX_BATCH_BYTES:
                raise FornaxFormatError("O lote excede o limite físico de 2 GiB.")
            candidates_list = []
            seen = set()
            with zipfile.ZipFile(source, "r") as archive:
                infos = archive.infolist()
                if not infos or len(infos) > MAX_BATCH_MODELS:
                    raise FornaxFormatError("O lote deve conter entre 1 e 1000 modelos.")
                total = 0
                for info in infos:
                    _validate_batch_member(info, seen)
                    if info.file_size > MAX_PACKAGE_BYTES:
                        raise FornaxFormatError("Um modelo do lote excede 512 MiB.")
                    total += info.file_size
                    if total > MAX_BATCH_UNCOMPRESSED:
                        raise FornaxFormatError("O lote excede o limite descompactado de 4 GiB.")
                for info in infos:
                    target = temporary_root / info.filename
                    with archive.open(info, "r") as incoming, target.open("xb") as outgoing:
                        copied = 0
                        while True:
                            chunk = incoming.read(min(1024 * 1024, info.file_size - copied + 1))
                            if not chunk:
                                break
                            copied += len(chunk)
                            if copied > info.file_size:
                                raise FornaxFormatError("Tamanho de entrada inconsistente no lote.")
                            outgoing.write(chunk)
                        outgoing.flush()
                        os.fsync(outgoing.fileno())
                    os.chmod(target, 0o600)
                    candidates_list.append(_candidate(target, info.filename))
            candidates = tuple(candidates_list)
        else:
            raise FornaxFormatError("Selecione um arquivo .fornax ou um lote .zip.")
        yield tuple(replace(candidate, source_path=source) for candidate in candidates)
    if _file_sha256(source) != before:
        raise FornaxFormatError("O arquivo recebido mudou durante a importação.")


def import_candidate(
    candidate: ImportCandidate,
    destination: str | Path,
    *,
    include_signatures: bool,
    target_mode: str | None = None,
    public_signatures_acknowledged: bool = False,
    transport_password: str | None = None,
    local_password: str | None = None,
    opened=None,
    model_name: str | None = None,
    replace_existing: bool = False,
    legacy_source: str | Path | None = None,
    approved_sha256: str | None = None,
) -> FornaxDescriptor:
    """Publica uma cópia local com identidade e credenciais novas."""
    destination = Path(destination)
    if approved_sha256 is not None and file_sha256(candidate.path) != approved_sha256:
        raise FornaxFormatError("O modelo recebido mudou após a autorização para importar.")
    from core.fornax_container import _file_stamp
    expected_stamp = _file_stamp(destination)
    for origin in (candidate.path, candidate.source_path):
        if origin is not None and (
            destination.resolve() == origin.resolve()
            or (destination.exists() and origin.exists() and os.path.samefile(destination, origin))
        ):
            raise FornaxFormatError("A importação não pode substituir o arquivo recebido.")
    if expected_stamp is not None and not replace_existing:
        raise FornaxFormatError("O destino já existe. Escolha outro nome ou autorize a substituição.")
    legacy_inventory = None
    if legacy_source is not None:
        from core.legacy_migration import _inventory
        legacy_source = Path(legacy_source).absolute()
        if not replace_existing or expected_stamp is not None or legacy_source.parent != destination.parent.resolve():
            raise FornaxFormatError("A substituição legada exige um destino novo e autorização explícita.")
        legacy_inventory = _inventory(legacy_source)
    descriptor = candidate.descriptor
    if descriptor.mode == PUBLIC_MODE:
        opened = open_public_fornax(descriptor)
        document = opened.document()
    elif descriptor.mode == FULL_MODE or include_signatures:
        if opened is None and transport_password is None:
            raise FornaxFormatError("O modelo protegido exige a senha de exportação.")
        opened = opened or unlock_fornax(descriptor, transport_password)
        if (
            opened.descriptor.model_id != descriptor.model_id
            or opened.descriptor.revision_id != descriptor.revision_id
        ):
            raise FornaxFormatError("O acesso autorizado pertence a outro modelo.")
        document = opened.document()
    else:
        opened = open_public_fornax(descriptor)
        document = opened.document()

    if model_name is not None:
        document["name"] = model_name

    # O aceite pertence à biblioteca de destino e nunca é herdado do remetente.
    document.pop("protection_preferences", None)
    if not include_signatures:
        document = without_signatures(document)
    has_signatures = bool(document_signatures(document))
    if target_mode is None:
        target_mode = (
            descriptor.mode
            if include_signatures and descriptor.mode in PROTECTED_MODES
            else PUBLIC_MODE
        )
    if target_mode not in {PUBLIC_MODE, *PROTECTED_MODES}:
        raise FornaxFormatError("Modo de destino inválido para importação.")
    if target_mode == SIGNATURES_MODE and not has_signatures:
        raise FornaxFormatError("Proteção de assinaturas exige ao menos uma assinatura.")
    if target_mode == PUBLIC_MODE and has_signatures:
        if not public_signatures_acknowledged:
            raise FornaxFormatError(
                "Importar assinaturas sem proteção exige aceite local explícito."
            )
        document["protection_preferences"] = {
            "public_signatures_acknowledged": True,
        }
    document["origin_info"] = build_model_snapshot(document, source="imported")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(f".{destination.name}.import-{uuid4().hex}.fornax")
    try:
        if target_mode in PROTECTED_MODES:
            if local_password is None:
                raise FornaxFormatError("Defina uma nova senha local para o modelo protegido.")
            saved = save_protected_fornax(
                document, staged, local_password, mode=target_mode,
                asset_provider=opened.asset,
            )
        else:
            saved = save_public_fornax(document, staged, asset_provider=opened.asset)
        with file_lock(destination.with_name(f".{destination.name}.write.lock")):
            if _file_stamp(destination) != expected_stamp:
                raise FornaxFormatError("O destino mudou durante a importação; nada foi substituído.")
            if legacy_source is not None:
                from core.legacy_migration import publish_legacy_replacement
                publish_legacy_replacement(legacy_source, destination, staged, legacy_inventory)
            elif expected_stamp is None:
                publish_new(staged, destination)
            else:
                previous = inspect_fornax(destination)
                if previous.mode == PUBLIC_MODE:
                    open_public_fornax(previous)
                following = inspect_fornax(staged)
                backup_source = destination
                if following.mode != PUBLIC_MODE and (
                    previous.mode != following.mode or previous.salt != following.salt
                ):
                    backup_source = staged
                backup = destination.with_name(destination.name + ".bak")
                pending_backup = destination.with_name(f".{destination.name}.backup-{uuid4().hex}")
                try:
                    shutil.copyfile(backup_source, pending_backup)
                    with pending_backup.open("r+b") as stream:
                        os.fsync(stream.fileno())
                    os.replace(pending_backup, backup)
                    sync_directory(destination.parent)
                    os.replace(staged, destination)
                    sync_directory(destination.parent)
                finally:
                    pending_backup.unlink(missing_ok=True)
        verified = inspect_fornax(destination)
        return FornaxDescriptor(
            verified.path, verified.mode, verified.model_id, verified.revision_id,
            verified.version, verified.crypto_profile, verified.salt,
            verified.wrap_nonce, verified.payload_nonce, verified.wrapped_key,
        )
    finally:
        staged.unlink(missing_ok=True)


def import_legacy_document(
    document, source_dir, destination, *, mode=PUBLIC_MODE,
    include_signatures: bool = True, public_signatures_acknowledged: bool = False,
    password=None, replace_existing=False, legacy_source=None,
):
    """Normaliza ZIPs antigos pelo mesmo fluxo transacional dos pacotes atuais."""
    from core.model_document import iter_page_asset_paths
    root = Path(source_dir).resolve()
    for _, _, reference in iter_page_asset_paths(document):
        path = Path(reference)
        resolved = (path if path.is_absolute() else root / path).resolve()
        if not resolved.is_relative_to(root):
            raise FornaxFormatError("O modelo recebido referencia um asset fora da pasta importada.")
    with tempfile.TemporaryDirectory(prefix="legacy-import-", dir=get_temp_dir()) as temporary:
        converted = Path(temporary) / "converted.fornax"
        source_document = document if include_signatures else without_signatures(document)
        if mode == PUBLIC_MODE:
            if document_signatures(source_document):
                if not public_signatures_acknowledged:
                    raise FornaxFormatError(
                        "Importar assinaturas sem proteção exige aceite local explícito."
                    )
                source_document = dict(source_document)
                source_document["protection_preferences"] = {
                    "public_signatures_acknowledged": True,
                }
            save_public_fornax(source_document, converted, source_dir=source_dir)
        else:
            save_protected_fornax(
                source_document, converted, password, mode=mode, source_dir=source_dir,
            )
        with open_import_package(converted) as candidates:
            return import_candidate(
                candidates[0], destination, include_signatures=include_signatures,
                target_mode=mode,
                public_signatures_acknowledged=public_signatures_acknowledged,
                transport_password=password, local_password=password,
                replace_existing=replace_existing, legacy_source=legacy_source,
            )
