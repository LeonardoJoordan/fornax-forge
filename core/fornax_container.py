"""Contêiner ``.fornax`` independente da interface."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import threading
from types import MappingProxyType
from typing import Any, Callable, Mapping
import unicodedata
from uuid import UUID, uuid4
import zipfile
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from core.file_transactions import file_lock, publish_new, sync_directory

from core.model_document import (
    UnsupportedSchemaError,
    document_signatures,
    normalize_model_document,
    persistent_model_document,
    without_signatures,
)


FORMAT_NAME = "fornax"
CONTAINER_VERSION = 1
PUBLIC_SIGNATURES_VERSION = 2
SUPPORTED_CONTAINER_VERSIONS = {CONTAINER_VERSION, PUBLIC_SIGNATURES_VERSION}
PUBLIC_MODE = "none"
SIGNATURES_MODE = "signatures"
FULL_MODE = "full"
PROTECTED_MODES = {SIGNATURES_MODE, FULL_MODE}
SUPPORTED_MODES = {PUBLIC_MODE, *PROTECTED_MODES}
CRYPTO_PROFILE = "a2id-64m-t3-p1-aes256gcm-v1"
MANIFEST_PATH = "manifest.json"
PUBLIC_DOCUMENT_PATH = "public/document.json"
PUBLIC_ASSET_PREFIX = "public/assets/"
PROTECTED_PATH = "protected.bin"
INNER_DOCUMENT_PATH = "document.json"
INNER_SIGNATURES_PATH = "signatures.json"
INNER_ASSET_PREFIX = "assets/"

MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_MANIFEST_BYTES = 16 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_ASSET_BYTES = 128 * 1024 * 1024
MAX_PROTECTED_BYTES = 256 * 1024 * 1024 + 16
MAX_INNER_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_OBJECTS = 100_000
MAX_IMAGE_DIMENSION = 32_768
MAX_IMAGE_PIXELS = 64_000_000
SUPPORTED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
_KDF_LOCK = threading.Lock()


class FornaxError(ValueError):
    """Base para erros seguros do contêiner."""


class FornaxFormatError(FornaxError):
    """O pacote não obedece à estrutura declarada."""


class FornaxLimitError(FornaxError):
    """O pacote excede um limite operacional."""


class UnsupportedFornaxFeature(FornaxError):
    """A versão ou o modo exige suporte ainda indisponível."""


class FornaxAssetError(FornaxError):
    """Um asset referenciado não pôde ser incorporado ou resolvido."""


class FornaxPasswordError(FornaxError):
    """Senha inválida ou conteúdo protegido adulterado."""


class FornaxOperationCancelled(FornaxError):
    """A operação foi cancelada antes de iniciar uma derivação cara."""


@dataclass(frozen=True, slots=True)
class FornaxDescriptor:
    path: Path
    mode: str
    model_id: str
    revision_id: str
    version: int = CONTAINER_VERSION
    crypto_profile: str | None = None
    salt: bytes | None = None
    wrap_nonce: bytes | None = None
    payload_nonce: bytes | None = None
    wrapped_key: bytes | None = None


@dataclass(frozen=True, slots=True)
class OpenedFornax:
    """Snapshot público desconectado do ZIP e seguro para repasse interno."""

    descriptor: FornaxDescriptor
    _document: dict
    _assets: Mapping[str, bytes]
    public_changed: bool = False

    def document(self) -> dict:
        return deepcopy(self._document)

    def asset(self, reference: str) -> bytes:
        try:
            return self._assets[reference]
        except KeyError as exc:
            raise FornaxAssetError(f"Asset inexistente no pacote: {reference!r}.") from exc

    @property
    def asset_references(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))


def _duplicate_key_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FornaxFormatError(f"Chave JSON repetida: {key!r}.")
        result[key] = value
    return result


def _strict_json(raw: bytes, *, label: str) -> Any:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_key_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                FornaxFormatError(f"Número JSON inválido em {label}: {token}.")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FornaxFormatError(f"JSON inválido em {label}: {exc}.") from exc
    _validate_json_complexity(value, label=label)
    return value


def _validate_json_complexity(root: Any, *, label: str) -> None:
    stack = [(root, 1)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > MAX_JSON_OBJECTS:
            raise FornaxLimitError(f"{label} excede o limite de elementos JSON.")
        if depth > MAX_JSON_DEPTH:
            raise FornaxLimitError(f"{label} excede a profundidade JSON permitida.")
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise FornaxFormatError(f"{label} possui chave JSON inválida.")
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise FornaxFormatError(f"{label} possui número não finito.")


def _json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FornaxFormatError(f"Conteúdo não serializável como JSON: {exc}.") from exc


def _canonical_uuid(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise FornaxFormatError(f"{field} deve ser UUIDv4 textual.")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise FornaxFormatError(f"{field} inválido.") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise FornaxFormatError(f"{field} deve ser UUIDv4 canônico em minúsculas.")
    return value


def _hex_bytes(value: Any, *, field: str, length: int) -> bytes:
    if not isinstance(value, str) or len(value) != length * 2 or value.lower() != value:
        raise FornaxFormatError(f"{field} deve conter {length} bytes em hexadecimal minúsculo.")
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise FornaxFormatError(f"{field} possui hexadecimal inválido.") from exc
    if len(result) != length:
        raise FornaxFormatError(f"{field} possui tamanho inválido.")
    return result


def _parse_manifest(raw: bytes, path: Path) -> FornaxDescriptor:
    manifest = _strict_json(raw, label=MANIFEST_PATH)
    if not isinstance(manifest, dict) or "header" not in manifest:
        raise FornaxFormatError("Manifesto deve conter 'header'.")
    header = manifest["header"]
    base_fields = {"format", "version", "mode", "model_id", "revision_id"}
    if not isinstance(header, dict) or not base_fields.issubset(header):
        raise FornaxFormatError("Cabeçalho possui campos obrigatórios ausentes.")
    if header["format"] != FORMAT_NAME:
        raise FornaxFormatError("O arquivo não declara o formato FORNAX.")
    version = header["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise FornaxFormatError("A versão do contêiner deve ser inteira.")
    if version not in SUPPORTED_CONTAINER_VERSIONS:
        raise UnsupportedFornaxFeature(f"Versão .fornax não suportada: {version!r}.")
    mode = header["mode"]
    if not isinstance(mode, str) or mode not in SUPPORTED_MODES:
        raise UnsupportedFornaxFeature(f"Modo .fornax não suportado: {mode!r}.")
    if version == PUBLIC_SIGNATURES_VERSION and mode != PUBLIC_MODE:
        raise UnsupportedFornaxFeature(
            "A versão 2 do contêiner é exclusiva para modelos públicos com assinaturas."
        )
    model_id = _canonical_uuid(header["model_id"], field="model_id")
    revision_id = _canonical_uuid(header["revision_id"], field="revision_id")
    if mode == PUBLIC_MODE:
        if set(manifest) != {"header"} or set(header) != base_fields:
            raise FornaxFormatError("Manifesto público possui campos desconhecidos.")
        return FornaxDescriptor(path.resolve(), mode, model_id, revision_id, version)
    crypto_fields = {
        "crypto_profile", "salt", "wrap_nonce", "payload_nonce",
    }
    if set(manifest) != {"header", "wrapped_key_hex"} or set(header) != base_fields | crypto_fields:
        raise FornaxFormatError("Manifesto protegido possui campos ausentes ou desconhecidos.")
    if header["crypto_profile"] != CRYPTO_PROFILE:
        raise UnsupportedFornaxFeature("Perfil criptográfico .fornax não suportado.")
    return FornaxDescriptor(
        path=path.resolve(),
        mode=mode,
        model_id=model_id,
        revision_id=revision_id,
        version=version,
        crypto_profile=header["crypto_profile"],
        salt=_hex_bytes(header["salt"], field="salt", length=16),
        wrap_nonce=_hex_bytes(header["wrap_nonce"], field="wrap_nonce", length=12),
        payload_nonce=_hex_bytes(header["payload_nonce"], field="payload_nonce", length=12),
        wrapped_key=_hex_bytes(manifest["wrapped_key_hex"], field="wrapped_key_hex", length=48),
    )


def _descriptor_header(descriptor: FornaxDescriptor) -> dict:
    header = {
        "format": FORMAT_NAME,
        "version": descriptor.version,
        "mode": descriptor.mode,
        "model_id": descriptor.model_id,
        "revision_id": descriptor.revision_id,
    }
    if descriptor.mode in PROTECTED_MODES:
        header.update({
            "crypto_profile": descriptor.crypto_profile,
            "salt": descriptor.salt.hex(),
            "wrap_nonce": descriptor.wrap_nonce.hex(),
            "payload_nonce": descriptor.payload_nonce.hex(),
        })
    return header


def _header_bytes(descriptor: FornaxDescriptor) -> bytes:
    return json.dumps(
        _descriptor_header(descriptor), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def _validate_entry_name(name: str) -> None:
    if not name or not name.isascii() or "\\" in name or name.endswith("/"):
        raise FornaxFormatError(f"Nome de entrada ZIP inválido: {name!r}.")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")) or ":" in name or any(ord(c) < 32 for c in name):
        raise FornaxFormatError(f"Caminho inseguro no ZIP: {name!r}.")


def _validated_inventory(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise FornaxLimitError("O pacote possui entradas demais.")
    inventory = {}
    folded = set()
    total = 0
    for info in entries:
        _validate_entry_name(info.filename)
        lowered = info.filename.casefold()
        if info.filename in inventory or lowered in folded:
            raise FornaxFormatError(f"Entrada ZIP duplicada ou ambígua: {info.filename!r}.")
        if info.flag_bits & 0x1:
            raise FornaxFormatError("Criptografia ZIP tradicional não é aceita.")
        if info.compress_type not in SUPPORTED_COMPRESSION:
            raise FornaxFormatError(f"Compressão ZIP não suportada em {info.filename!r}.")
        file_type = (info.external_attr >> 16) & 0o170000
        if file_type == stat.S_IFLNK:
            raise FornaxFormatError(f"Link simbólico não é permitido: {info.filename!r}.")
        if info.file_size < 0 or info.compress_size < 0:
            raise FornaxFormatError("Tamanho negativo no diretório ZIP.")
        entry_limit = (
            MAX_ASSET_BYTES
            if info.filename.startswith((PUBLIC_ASSET_PREFIX, INNER_ASSET_PREFIX))
            else MAX_JSON_BYTES
        )
        if info.filename == MANIFEST_PATH:
            entry_limit = MAX_MANIFEST_BYTES
        elif info.filename == PROTECTED_PATH:
            entry_limit = MAX_PROTECTED_BYTES
        if info.file_size > entry_limit:
            raise FornaxLimitError(f"Entrada excede o limite: {info.filename!r}.")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise FornaxLimitError("Conteúdo descompactado excede o limite do modelo.")
        inventory[info.filename] = info
        folded.add(lowered)
    return inventory


def _read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    try:
        with archive.open(info, "r") as stream:
            chunks = []
            size = 0
            while True:
                chunk = stream.read(min(1024 * 1024, limit + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise FornaxLimitError(f"Entrada excede o limite durante leitura: {info.filename!r}.")
                chunks.append(chunk)
            return b"".join(chunks)
    except (RuntimeError, zipfile.BadZipFile, EOFError, OSError) as exc:
        raise FornaxFormatError(f"Não foi possível validar {info.filename!r}: {exc}.") from exc


def _open_archive(path: Path):
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FornaxFormatError(f"Não foi possível acessar o pacote: {exc}.") from exc
    if size > MAX_PACKAGE_BYTES:
        raise FornaxLimitError("O arquivo .fornax excede 512 MiB.")
    try:
        return zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise FornaxFormatError(f"Contêiner ZIP inválido: {exc}.") from exc


def inspect_fornax(path: str | Path) -> FornaxDescriptor:
    """Lê inventário e manifesto limitados, sem carregar documento ou assets."""
    package_path = Path(path)
    with _open_archive(package_path) as archive:
        inventory = _validated_inventory(archive)
        if MANIFEST_PATH not in inventory:
            raise FornaxFormatError("O pacote não contém manifest.json.")
        raw = _read_entry(archive, inventory[MANIFEST_PATH], MAX_MANIFEST_BYTES)
        descriptor = _parse_manifest(raw, package_path)
        if descriptor.mode == PUBLIC_MODE:
            required = {MANIFEST_PATH, PUBLIC_DOCUMENT_PATH}
            allowed_prefix = PUBLIC_ASSET_PREFIX
        elif descriptor.mode == SIGNATURES_MODE:
            required = {MANIFEST_PATH, PUBLIC_DOCUMENT_PATH, PROTECTED_PATH}
            allowed_prefix = PUBLIC_ASSET_PREFIX
        else:
            required = {MANIFEST_PATH, PROTECTED_PATH}
            allowed_prefix = None
        missing = required - set(inventory)
        if missing:
            raise FornaxFormatError(f"Entrada obrigatória ausente: {sorted(missing)[0]!r}.")
        unexpected = [name for name in inventory if name not in required and not (
            allowed_prefix and name.startswith(allowed_prefix)
        )]
        if unexpected:
            raise FornaxFormatError(f"Entrada não permitida no modo {descriptor.mode}: {unexpected[0]!r}.")
        return descriptor


def _document_asset_references(document: dict) -> list[str]:
    references = []
    for page in document.get("pages", []):
        background = page.get("background_path")
        if isinstance(background, str) and background:
            references.append(background)
        for collection in ("images", "signatures"):
            for item in page.get(collection, []):
                path = item.get("path")
                if isinstance(path, str) and path:
                    references.append(path)
    return list(dict.fromkeys(references))


def _validate_public_reference(reference: str) -> None:
    _validate_entry_name(reference)
    if not reference.startswith(PUBLIC_ASSET_PREFIX):
        raise FornaxFormatError(f"Referência de asset fora do escopo público: {reference!r}.")
    tail = reference.removeprefix(PUBLIC_ASSET_PREFIX)
    if "/" in tail or not tail:
        raise FornaxFormatError(f"Referência de asset público inválida: {reference!r}.")
    asset_path = PurePosixPath(tail)
    if asset_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
        raise FornaxFormatError(f"Extensão de asset público inválida: {reference!r}.")
    _canonical_uuid(asset_path.stem, field="ID do asset")


def _validate_svg(data: bytes, *, reference: str) -> None:
    lowered = data.lower()
    # ``http://www.w3.org/2000/svg`` é o namespace normal do formato; URLs
    # externas são avaliadas somente nos atributos de referência abaixo.
    forbidden = (b"<!doctype", b"<!entity", b"<script", b"javascript:")
    if any(token in lowered for token in forbidden):
        raise FornaxFormatError(f"SVG contém conteúdo externo ou executável: {reference!r}.")
    try:
        root = ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise FornaxFormatError(f"SVG inválido em {reference!r}: {exc}.") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise FornaxFormatError(f"Asset com extensão SVG não contém um SVG: {reference!r}.")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject"}:
            raise FornaxFormatError(f"SVG contém conteúdo executável: {reference!r}.")
        # CSS pode buscar recursos por url()/@import, inclusive com escapes.
        # O formato aceita referências locais (#id), mas não CSS escapado.
        css_values = list(element.attrib.values())
        if tag == "style":
            css_values.append("".join(element.itertext()))
        for css in css_values:
            if "\\" in css or "@import" in css.lower():
                raise FornaxFormatError(f"SVG possui CSS externo ou escapado: {reference!r}.")
            for target in re.findall(r"url\s*\((.*?)\)", css, flags=re.I | re.S):
                if not target.strip().strip("'\"").startswith("#"):
                    raise FornaxFormatError(f"SVG possui referência externa: {reference!r}.")
        for key, value in element.attrib.items():
            local_key = key.rsplit("}", 1)[-1].lower()
            if local_key.startswith("on"):
                raise FornaxFormatError(f"SVG possui evento executável: {reference!r}.")
            if local_key in {"href", "src"}:
                normalized = value.strip().lower()
                if normalized and not normalized.startswith("#") and not normalized.startswith("data:"):
                    raise FornaxFormatError(f"SVG possui referência externa: {reference!r}.")


def _validate_image_asset(data: bytes, *, reference: str) -> None:
    suffix = PurePosixPath(reference).suffix.lower()
    if suffix == ".svg":
        _validate_svg(data, reference=reference)
    elif suffix not in {".png", ".jpg", ".jpeg"}:
        raise FornaxFormatError(f"Tipo de asset gráfico não permitido: {reference!r}.")
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise FornaxFormatError(f"Não foi possível examinar o asset: {reference!r}.")
    reader = QImageReader(buffer)
    size = reader.size()
    if not size.isValid() or size.width() <= 0 or size.height() <= 0:
        raise FornaxFormatError(f"Asset gráfico inválido: {reference!r}.")
    if (
        size.width() > MAX_IMAGE_DIMENSION
        or size.height() > MAX_IMAGE_DIMENSION
        or size.width() * size.height() > MAX_IMAGE_PIXELS
    ):
        raise FornaxLimitError(f"Dimensões do asset excedem o limite: {reference!r}.")


def open_public_fornax(path_or_descriptor: str | Path | FornaxDescriptor) -> OpenedFornax:
    """Abre o modo público em memória, validando todos os bytes referenciados."""
    if isinstance(path_or_descriptor, FornaxDescriptor):
        expected = path_or_descriptor
        package_path = expected.path
    else:
        expected = None
        package_path = Path(path_or_descriptor)
    with _open_archive(package_path) as archive:
        inventory = _validated_inventory(archive)
        if MANIFEST_PATH not in inventory:
            raise FornaxFormatError("O pacote não contém manifest.json.")
        descriptor = _parse_manifest(
            _read_entry(archive, inventory[MANIFEST_PATH], MAX_MANIFEST_BYTES), package_path
        )
        if expected is not None and descriptor != expected:
            raise FornaxFormatError("O pacote mudou depois de ser inspecionado.")
        if descriptor.mode == FULL_MODE:
            raise FornaxPasswordError("O modelo integralmente protegido exige senha.")
        allowed_fixed = {MANIFEST_PATH, PUBLIC_DOCUMENT_PATH}
        if descriptor.mode == SIGNATURES_MODE:
            allowed_fixed.add(PROTECTED_PATH)
        if PUBLIC_DOCUMENT_PATH not in inventory:
            raise FornaxFormatError("O pacote público não contém public/document.json.")
        unexpected = [
            name for name in inventory
            if name not in allowed_fixed and not name.startswith(PUBLIC_ASSET_PREFIX)
        ]
        if unexpected:
            raise FornaxFormatError(f"Entrada não permitida: {unexpected[0]!r}.")
        raw_document = _read_entry(archive, inventory[PUBLIC_DOCUMENT_PATH], MAX_JSON_BYTES)
        source = _strict_json(raw_document, label=PUBLIC_DOCUMENT_PATH)
        if not isinstance(source, dict):
            raise FornaxFormatError("O documento público deve ser um objeto JSON.")
        try:
            document = persistent_model_document(normalize_model_document(source))
        except UnsupportedSchemaError as exc:
            raise UnsupportedFornaxFeature(str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise FornaxFormatError(f"Documento gráfico inválido: {exc}.") from exc
        signatures = document_signatures(document)
        acknowledged = (
            document.get("protection_preferences", {})
            .get("public_signatures_acknowledged") is True
        )
        if descriptor.version == CONTAINER_VERSION and signatures:
            raise FornaxFormatError("A parte pública v1 não pode conter assinaturas.")
        if descriptor.version == PUBLIC_SIGNATURES_VERSION:
            if not signatures:
                raise FornaxFormatError("Um pacote público v2 deve conter assinaturas.")
            if not acknowledged:
                raise FornaxFormatError(
                    "Um pacote público com assinaturas exige aceite explícito."
                )
        references = _document_asset_references(document)
        for reference in references:
            _validate_public_reference(reference)
        asset_entries = {name for name in inventory if name.startswith(PUBLIC_ASSET_PREFIX)}
        if set(references) != asset_entries:
            missing = set(references) - asset_entries
            orphaned = asset_entries - set(references)
            if missing:
                raise FornaxAssetError(f"Asset referenciado está ausente: {sorted(missing)[0]!r}.")
            raise FornaxFormatError(f"Asset não referenciado no pacote: {sorted(orphaned)[0]!r}.")
        assets = {
            reference: _read_entry(archive, inventory[reference], MAX_ASSET_BYTES)
            for reference in references
        }
        for reference, data in assets.items():
            _validate_image_asset(data, reference=reference)
    return OpenedFornax(descriptor, document, MappingProxyType(assets))


def _source_asset_path(reference: str, source_dir: Path | None) -> Path:
    source = Path(reference)
    if not source.is_absolute():
        if source_dir is None:
            raise FornaxAssetError(
                f"É necessário informar source_dir para o asset relativo {reference!r}."
            )
        source = source_dir / source
    try:
        resolved = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FornaxAssetError(f"Asset não encontrado: {reference!r}.") from exc
    if not resolved.is_file():
        raise FornaxAssetError(f"Asset não é um arquivo regular: {reference!r}.")
    return resolved


def _load_source_asset(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_ASSET_BYTES:
            raise FornaxLimitError(f"Asset excede 128 MiB: {path.name!r}.")
        with path.open("rb") as stream:
            data = stream.read(MAX_ASSET_BYTES + 1)
    except OSError as exc:
        raise FornaxAssetError(f"Não foi possível ler o asset {path.name!r}: {exc}.") from exc
    if len(data) > MAX_ASSET_BYTES:
        raise FornaxLimitError(f"Asset excede 128 MiB: {path.name!r}.")
    return data


def _manifest(model_id: str, revision_id: str, *, version: int = CONTAINER_VERSION) -> dict:
    return {"header": {
        "format": FORMAT_NAME,
        "version": version,
        "mode": PUBLIC_MODE,
        "model_id": model_id,
        "revision_id": revision_id,
    }}


def _fsync_directory(directory: Path) -> None:
    sync_directory(directory)


def save_public_fornax(
    document: dict,
    destination: str | Path,
    *,
    source_dir: str | Path | None = None,
    asset_provider=None,
    model_id: str | None = None,
) -> FornaxDescriptor:
    """Publica atomicamente um modelo público em um único ``.fornax``."""
    destination = Path(destination)
    expected_stamp = _file_stamp(destination)
    if destination.suffix.lower() != ".fornax":
        raise FornaxFormatError("O destino deve usar a extensão .fornax.")
    if destination.exists() and not destination.is_file():
        raise FornaxFormatError("O destino .fornax não é um arquivo regular.")
    normalized = persistent_model_document(document)
    has_signatures = bool(document_signatures(normalized))
    preferences = normalized.get("protection_preferences")
    acknowledged = (
        isinstance(preferences, dict)
        and preferences.get("public_signatures_acknowledged") is True
    )
    if has_signatures and not acknowledged:
        raise FornaxFormatError(
            "Salvar assinaturas sem proteção exige aceite explícito do usuário."
        )
    if not has_signatures:
        normalized.pop("protection_preferences", None)
    version = PUBLIC_SIGNATURES_VERSION if has_signatures else CONTAINER_VERSION
    rewritten, assets = _rewrite_selected_assets(
        normalized, prefix=PUBLIC_ASSET_PREFIX,
        source_dir=Path(source_dir).resolve() if source_dir is not None else None,
        asset_provider=asset_provider,
    )
    rewritten = persistent_model_document(rewritten)
    selected_model_id = model_id or str(uuid4())
    _canonical_uuid(selected_model_id, field="model_id")
    revision_id = str(uuid4())
    manifest_bytes = _json_bytes(_manifest(selected_model_id, revision_id, version=version))
    document_bytes = _json_bytes(rewritten)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES or len(document_bytes) > MAX_JSON_BYTES:
        raise FornaxLimitError("Metadados do modelo excedem o limite do formato.")
    total = len(manifest_bytes) + len(document_bytes) + sum(map(len, assets.values()))
    if total > MAX_UNCOMPRESSED_BYTES:
        raise FornaxLimitError("Conteúdo do modelo excede 512 MiB.")

    def verify(path):
        verified = open_public_fornax(path)
        if verified.document() != rewritten:
            raise FornaxFormatError("A verificação lógica do pacote recém-gravado falhou.")
        if any(verified.asset(reference) != data for reference, data in assets.items()):
            raise FornaxFormatError("A verificação dos assets recém-gravados falhou.")

    entries = {MANIFEST_PATH: manifest_bytes, PUBLIC_DOCUMENT_PATH: document_bytes, **assets}
    _publish_package(destination, entries, verify, expected_stamp=expected_stamp)
    return FornaxDescriptor(
        destination.resolve(), PUBLIC_MODE, selected_model_id, revision_id, version
    )


def password_bytes(password: str) -> bytes:
    """Normaliza uma senha segundo o contrato interoperável do formato v1."""
    if not isinstance(password, str):
        raise FornaxPasswordError("A senha deve ser texto.")
    try:
        normalized = unicodedata.normalize("NFC", password)
        encoded = normalized.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise FornaxPasswordError("A senha contém Unicode inválido.") from exc
    if not 8 <= len(normalized) <= 64:
        raise FornaxPasswordError("A senha deve possuir entre 8 e 64 caracteres.")
    return encoded


def _derive_kek(
    password: str,
    salt: bytes,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> bytes:
    # Um único Argon2id por processo evita picos simultâneos de memória. A fila
    # de solicitações pertence à camada de sessão e pode ser cancelada antes de
    # adquirir este lock; uma derivação já iniciada não é interrompida.
    while not _KDF_LOCK.acquire(timeout=0.05):
        if cancel_check is not None and cancel_check():
            raise FornaxOperationCancelled("Desbloqueio cancelado antes da derivação da chave.")
    try:
        if cancel_check is not None and cancel_check():
            raise FornaxOperationCancelled("Desbloqueio cancelado antes da derivação da chave.")
        return Argon2id(
            salt=salt, length=32, iterations=3, lanes=1, memory_cost=65536,
        ).derive(password_bytes(password))
    finally:
        _KDF_LOCK.release()


def _asset_source(
    reference: str,
    *,
    source_dir: Path | None,
    asset_provider,
) -> tuple[object, bytes, str]:
    if asset_provider is not None:
        try:
            data = bytes(asset_provider(reference))
        except Exception as exc:
            raise FornaxAssetError(f"Não foi possível obter o asset {reference!r}.") from exc
        suffix = PurePosixPath(reference).suffix.lower()
        return ("provider", reference), data, suffix
    source = _source_asset_path(reference, source_dir)
    return source, _load_source_asset(source), source.suffix.lower()


def _rewrite_selected_assets(
    document: dict,
    *,
    prefix: str,
    source_dir: Path | None,
    asset_provider=None,
    include_signatures: bool = True,
) -> tuple[dict, dict[str, bytes]]:
    rewritten = deepcopy(document)
    by_source: dict[object, str] = {}
    assets: dict[str, bytes] = {}

    def replace(reference: str) -> str:
        key, data, suffix = _asset_source(
            reference, source_dir=source_dir, asset_provider=asset_provider,
        )
        if key in by_source:
            return by_source[key]
        if suffix not in {".png", ".jpg", ".jpeg", ".svg"}:
            raise FornaxFormatError(f"Tipo de asset gráfico não permitido: {reference!r}.")
        internal = f"{prefix}{uuid4()}{suffix}"
        if len(data) > MAX_ASSET_BYTES:
            raise FornaxLimitError(f"Asset excede 128 MiB: {reference!r}.")
        _validate_image_asset(data, reference=internal)
        by_source[key] = internal
        assets[internal] = data
        return internal

    for page in rewritten.get("pages", []):
        background = page.get("background_path")
        if isinstance(background, str) and background:
            page["background_path"] = replace(background)
        collections = ("images", "signatures") if include_signatures else ("images",)
        for collection in collections:
            for item in page.get(collection, []):
                reference = item.get("path")
                if isinstance(reference, str) and reference:
                    item["path"] = replace(reference)
    return rewritten, assets


def _inner_zip(entries: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            archive.writestr(name, entries[name])
    payload = output.getvalue()
    if len(payload) > MAX_INNER_BYTES:
        raise FornaxLimitError("O conteúdo protegido excede 256 MiB.")
    return payload


def _protected_descriptor(
    path: Path,
    mode: str,
    model_id: str,
    revision_id: str,
    *,
    salt: bytes,
    wrap_nonce: bytes,
    payload_nonce: bytes,
    wrapped_key: bytes,
) -> FornaxDescriptor:
    return FornaxDescriptor(
        path.resolve(), mode, model_id, revision_id, CONTAINER_VERSION,
        CRYPTO_PROFILE, salt, wrap_nonce, payload_nonce, wrapped_key,
    )


def _protected_manifest(descriptor: FornaxDescriptor) -> dict:
    return {
        "header": _descriptor_header(descriptor),
        "wrapped_key_hex": descriptor.wrapped_key.hex(),
    }


def _encrypt_payload(
    plaintext: bytes,
    password: str | None,
    *,
    path: Path,
    mode: str,
    model_id: str,
    revision_id: str,
    retained_kek: bytes | None = None,
    retained_salt: bytes | None = None,
) -> tuple[FornaxDescriptor, bytes]:
    if retained_kek is not None:
        if retained_salt is None or len(retained_salt) != 16 or len(retained_kek) != 32:
            raise FornaxFormatError("Material de sessão protegido inválido.")
        salt = bytes(retained_salt)
        kek = bytes(retained_kek)
    else:
        if password is None:
            raise FornaxPasswordError("A senha do modelo protegido está ausente.")
        salt = os.urandom(16)
        kek = _derive_kek(password, salt)
    wrap_nonce = os.urandom(12)
    payload_nonce = os.urandom(12)
    dek = os.urandom(32)
    provisional = _protected_descriptor(
        path, mode, model_id, revision_id, salt=salt,
        wrap_nonce=wrap_nonce, payload_nonce=payload_nonce,
        wrapped_key=b"\0" * 48,
    )
    header = _header_bytes(provisional)
    wrapped_key = AESGCM(kek).encrypt(
        wrap_nonce, dek, b"FORNAX/v1/wrap\0" + header,
    )
    descriptor = _protected_descriptor(
        path, mode, model_id, revision_id, salt=salt,
        wrap_nonce=wrap_nonce, payload_nonce=payload_nonce,
        wrapped_key=wrapped_key,
    )
    ciphertext = AESGCM(dek).encrypt(
        payload_nonce, plaintext, b"FORNAX/v1/payload\0" + header,
    )
    return descriptor, ciphertext


def _public_hashes(document_bytes: bytes, assets: Mapping[str, bytes]) -> list[dict]:
    entries = {PUBLIC_DOCUMENT_PATH: document_bytes, **assets}
    return [
        {"path": path, "sha256": hashlib.sha256(entries[path]).hexdigest()}
        for path in sorted(entries)
    ]


def _filter_origin_info(document: dict, signature_paths: set[str]) -> None:
    origin = document.get("origin_info")
    if not isinstance(origin, dict) or not isinstance(origin.get("assets"), list):
        return
    protected_names = {PurePosixPath(path).name for path in signature_paths}
    origin["assets"] = [
        item for item in origin["assets"]
        if not isinstance(item, dict) or item.get("name") not in protected_names
    ]


def _split_signatures(
    document: dict,
    *,
    source_dir: Path | None,
    asset_provider=None,
) -> tuple[dict, dict[str, bytes], dict, dict[str, bytes]]:
    original = deepcopy(document)
    signature_paths = {
        item.get("path")
        for page in original["pages"]
        for item in page.get("signatures", [])
        if isinstance(item.get("path"), str) and item.get("path")
    }
    public = deepcopy(original)
    protected_pages = []
    protected_assets: dict[str, bytes] = {}
    protected_by_reference: dict[str, str] = {}
    for original_page, public_page in zip(original["pages"], public["pages"]):
        signatures = deepcopy(original_page.get("signatures", []))
        for signature in signatures:
            reference = signature.get("path")
            if isinstance(reference, str) and reference:
                if reference not in protected_by_reference:
                    _, data, suffix = _asset_source(
                        reference, source_dir=source_dir, asset_provider=asset_provider,
                    )
                    if suffix not in {".png", ".jpg", ".jpeg", ".svg"}:
                        raise FornaxFormatError(f"Tipo de assinatura não permitido: {reference!r}.")
                    target = f"{INNER_ASSET_PREFIX}{uuid4()}{suffix}"
                    _validate_image_asset(data, reference=target)
                    protected_by_reference[reference] = target
                    protected_assets[target] = data
                signature["path"] = protected_by_reference[reference]
        signature_object_ids = {item["object_id"] for item in signatures}
        protected_pages.append({
            "page_id": original_page["page_id"],
            "signatures": signatures,
            "original_layer_order": deepcopy(original_page.get("layer_order", [])),
            "public_object_ids": [
                object_id for object_id in original_page.get("layer_order", [])
                if object_id not in signature_object_ids
            ],
        })
        public_page["signatures"] = []
        public_page["layer_order"] = [
            object_id for object_id in public_page.get("layer_order", [])
            if object_id not in signature_object_ids
        ]
    protected_origin = deepcopy(original.get("origin_info"))
    _filter_origin_info(public, signature_paths)
    public, public_assets = _rewrite_selected_assets(
        public, prefix=PUBLIC_ASSET_PREFIX, source_dir=source_dir,
        asset_provider=asset_provider, include_signatures=False,
    )
    public = persistent_model_document(public)
    protected = {
        "version": 1,
        "public_reference": [],
        "pages": protected_pages,
        "protected_origin_info": protected_origin,
    }
    return public, public_assets, protected, protected_assets


def _file_stamp(path):
    if path.is_symlink():
        raise FornaxFormatError("O destino não pode ser um link simbólico.")
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not path.is_file():
        raise FornaxFormatError("O destino não é um arquivo regular.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").digest()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, digest)


def _publish_package(destination: Path, entries: Mapping[str, bytes], verify, *, expected_stamp) -> None:
    with file_lock(destination.with_name(f".{destination.name}.write.lock")):
        if _file_stamp(destination) != expected_stamp:
            raise FornaxFormatError("O destino mudou durante o salvamento; nada foi substituído.")
        _publish_package_locked(destination, entries, verify, expected_stamp)


def _publish_package_locked(destination: Path, entries: Mapping[str, bytes], verify, expected_stamp) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    backup_temporary = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.pending-", suffix=".fornax", dir=destination.parent,
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        os.chmod(temporary_path, 0o600)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(entries):
                compression = zipfile.ZIP_STORED if name == PROTECTED_PATH else zipfile.ZIP_DEFLATED
                archive.writestr(name, entries[name], compress_type=compression)
        # Windows requires a writable descriptor for fsync; preserve the bytes.
        with temporary_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        verify(temporary_path)
        if _file_stamp(destination) != expected_stamp:
            raise FornaxFormatError("O destino mudou durante a gravação; nada foi substituído.")
        if destination.is_file():
            # Nunca substituir um backup válido por um original inválido.
            previous = inspect_fornax(destination)
            if previous.mode == PUBLIC_MODE:
                open_public_fornax(previous)
            following = inspect_fornax(temporary_path)
            # Aumentar proteção ou trocar credenciais não deixa um backup com
            # conteúdo aberto/senha antiga. Neste caso o backup é a nova revisão.
            backup_source = destination
            if following.mode != PUBLIC_MODE and (
                previous.mode != following.mode or previous.salt != following.salt
            ):
                backup_source = temporary_path
            fd, backup_name = tempfile.mkstemp(
                prefix=f".{destination.name}.backup-", suffix=".tmp",
                dir=destination.parent,
            )
            os.close(fd)
            backup_temporary = Path(backup_name)
            shutil.copyfile(backup_source, backup_temporary)
            with backup_temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            os.replace(backup_temporary, destination.with_name(destination.name + ".bak"))
            backup_temporary = None
            _fsync_directory(destination.parent)
        if expected_stamp is None:
            publish_new(temporary_path, destination)
        else:
            if _file_stamp(destination) != expected_stamp:
                raise FornaxFormatError("O destino mudou antes da publicação; nada foi substituído.")
            os.replace(temporary_path, destination)
        temporary_path = None
        _fsync_directory(destination.parent)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if backup_temporary is not None:
            try:
                backup_temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _save_protected_fornax(
    document: dict,
    destination: str | Path,
    password: str | None,
    *,
    mode: str = SIGNATURES_MODE,
    source_dir: str | Path | None = None,
    asset_provider=None,
    model_id: str | None = None,
    retained_kek: bytes | None = None,
    retained_salt: bytes | None = None,
) -> FornaxDescriptor:
    """Cria um pacote parcial ou integral com uma nova chave por revisão."""
    if mode not in PROTECTED_MODES:
        raise FornaxFormatError("O modo protegido deve ser 'signatures' ou 'full'.")
    if retained_kek is None:
        password_bytes(password)
    destination = Path(destination)
    expected_stamp = _file_stamp(destination)
    if destination.suffix.lower() != ".fornax":
        raise FornaxFormatError("O destino deve usar a extensão .fornax.")
    normalized = persistent_model_document(document)
    normalized.pop("protection_preferences", None)
    signatures = document_signatures(normalized)
    if mode == SIGNATURES_MODE and not signatures:
        raise FornaxFormatError("Proteção de assinaturas exige ao menos uma assinatura.")
    source_root = Path(source_dir).resolve() if source_dir is not None else None
    selected_model_id = model_id or str(uuid4())
    _canonical_uuid(selected_model_id, field="model_id")
    revision_id = str(uuid4())

    outer_entries: dict[str, bytes] = {}
    if mode == FULL_MODE:
        protected_document, protected_assets = _rewrite_selected_assets(
            normalized, prefix=INNER_ASSET_PREFIX, source_dir=source_root,
            asset_provider=asset_provider,
        )
        inner_entries = {INNER_DOCUMENT_PATH: _json_bytes(protected_document), **protected_assets}
        expected_document = protected_document
    else:
        public, public_assets, protected, protected_assets = _split_signatures(
            normalized, source_dir=source_root, asset_provider=asset_provider,
        )
        public_bytes = _json_bytes(public)
        protected["public_reference"] = _public_hashes(public_bytes, public_assets)
        inner_entries = {INNER_SIGNATURES_PATH: _json_bytes(protected), **protected_assets}
        outer_entries = {PUBLIC_DOCUMENT_PATH: public_bytes, **public_assets}
        expected_document = _merge_protected_signatures(public, protected)
    inner = _inner_zip(inner_entries)
    descriptor, ciphertext = _encrypt_payload(
        inner, password, path=destination, mode=mode,
        model_id=selected_model_id, revision_id=revision_id,
        retained_kek=retained_kek, retained_salt=retained_salt,
    )
    outer_entries[MANIFEST_PATH] = _json_bytes(_protected_manifest(descriptor))
    outer_entries[PROTECTED_PATH] = ciphertext
    total = sum(map(len, outer_entries.values()))
    if total > MAX_PACKAGE_BYTES:
        raise FornaxLimitError("O pacote protegido excede 512 MiB.")

    def verify(path: Path):
        opened = (
            _unlock_fornax_with_retained_kek(path, bytes(retained_kek))
            if retained_kek is not None else unlock_fornax(path, password)
        )
        if opened.document() != expected_document:
            raise FornaxFormatError("A verificação lógica do pacote protegido falhou.")

    _publish_package(destination, outer_entries, verify, expected_stamp=expected_stamp)
    return descriptor.__class__(
        destination.resolve(), descriptor.mode, descriptor.model_id,
        descriptor.revision_id, descriptor.version, descriptor.crypto_profile,
        descriptor.salt, descriptor.wrap_nonce, descriptor.payload_nonce,
        descriptor.wrapped_key,
    )


def save_protected_fornax(
    document: dict,
    destination: str | Path,
    password: str,
    *,
    mode: str = SIGNATURES_MODE,
    source_dir: str | Path | None = None,
    asset_provider=None,
    model_id: str | None = None,
) -> FornaxDescriptor:
    """Cria um pacote protegido a partir de uma senha fornecida pelo usuário."""
    return _save_protected_fornax(
        document, destination, password, mode=mode, source_dir=source_dir,
        asset_provider=asset_provider, model_id=model_id,
    )


def save_protected_fornax_with_key(
    document: dict,
    destination: str | Path,
    kek: bytes,
    salt: bytes,
    *,
    mode: str,
    asset_provider=None,
    model_id: str,
) -> FornaxDescriptor:
    """Publica nova revisão com a KEK da sessão, sem reter ou pedir senha."""
    return _save_protected_fornax(
        document, destination, None, mode=mode, asset_provider=asset_provider,
        model_id=model_id, retained_kek=kek, retained_salt=salt,
    )


def _read_inner_zip(payload: bytes, *, mode: str) -> tuple[dict[str, bytes], dict]:
    if len(payload) > MAX_INNER_BYTES:
        raise FornaxLimitError("O conteúdo protegido excede 256 MiB.")
    try:
        archive = zipfile.ZipFile(BytesIO(payload), "r")
    except zipfile.BadZipFile as exc:
        raise FornaxFormatError("O conteúdo protegido interno não é um ZIP válido.") from exc
    with archive:
        inventory = _validated_inventory(archive)
        required_json = INNER_DOCUMENT_PATH if mode == FULL_MODE else INNER_SIGNATURES_PATH
        if required_json not in inventory:
            raise FornaxFormatError(f"Conteúdo protegido sem {required_json!r}.")
        unexpected = [
            name for name in inventory
            if name != required_json and not name.startswith(INNER_ASSET_PREFIX)
        ]
        if unexpected:
            raise FornaxFormatError(f"Entrada interna não permitida: {unexpected[0]!r}.")
        raw_json = _read_entry(archive, inventory[required_json], MAX_JSON_BYTES)
        metadata = _strict_json(raw_json, label=required_json)
        assets = {
            name: _read_entry(archive, info, MAX_ASSET_BYTES)
            for name, info in inventory.items() if name.startswith(INNER_ASSET_PREFIX)
        }
        for reference, data in assets.items():
            _validate_inner_asset_reference(reference)
            _validate_image_asset(data, reference=reference)
    return assets, metadata


def _validate_inner_asset_reference(reference: str) -> None:
    _validate_entry_name(reference)
    if not reference.startswith(INNER_ASSET_PREFIX):
        raise FornaxFormatError(f"Referência interna inválida: {reference!r}.")
    tail = reference.removeprefix(INNER_ASSET_PREFIX)
    if "/" in tail:
        raise FornaxFormatError(f"Referência interna inválida: {reference!r}.")
    path = PurePosixPath(tail)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
        raise FornaxFormatError(f"Extensão interna inválida: {reference!r}.")
    _canonical_uuid(path.stem, field="ID do asset protegido")


def _outer_contents(path: Path, descriptor: FornaxDescriptor):
    with _open_archive(path) as archive:
        inventory = _validated_inventory(archive)
        current = _parse_manifest(
            _read_entry(archive, inventory[MANIFEST_PATH], MAX_MANIFEST_BYTES), path,
        )
        if current != descriptor:
            raise FornaxFormatError("O pacote mudou depois de ser inspecionado.")
        ciphertext = _read_entry(archive, inventory[PROTECTED_PATH], MAX_PROTECTED_BYTES)
        public_document_bytes = None
        public_assets = {}
        if descriptor.mode == SIGNATURES_MODE:
            public_document_bytes = _read_entry(
                archive, inventory[PUBLIC_DOCUMENT_PATH], MAX_JSON_BYTES,
            )
            public_assets = {
                name: _read_entry(archive, info, MAX_ASSET_BYTES)
                for name, info in inventory.items() if name.startswith(PUBLIC_ASSET_PREFIX)
            }
    return ciphertext, public_document_bytes, public_assets


def _decrypt_payload(
    descriptor: FornaxDescriptor, ciphertext: bytes, password: str,
    *, cancel_check: Callable[[], bool] | None = None,
) -> tuple[bytes, bytes]:
    header = _header_bytes(descriptor)
    try:
        kek = _derive_kek(password, descriptor.salt, cancel_check=cancel_check)
        dek = AESGCM(kek).decrypt(
            descriptor.wrap_nonce, descriptor.wrapped_key,
            b"FORNAX/v1/wrap\0" + header,
        )
        plaintext = AESGCM(dek).decrypt(
            descriptor.payload_nonce, ciphertext,
            b"FORNAX/v1/payload\0" + header,
        )
        return plaintext, kek
    except InvalidTag as exc:
        raise FornaxPasswordError(
            "Senha incorreta ou conteúdo protegido danificado/alterado."
        ) from exc


def _decrypt_payload_with_kek(
    descriptor: FornaxDescriptor, ciphertext: bytes, kek: bytes,
) -> bytes:
    """Autentica uma revisão usando somente o material da sessão ativa."""
    if len(kek) != 32:
        raise FornaxFormatError("Material de sessão protegido inválido.")
    header = _header_bytes(descriptor)
    try:
        dek = AESGCM(kek).decrypt(
            descriptor.wrap_nonce, descriptor.wrapped_key,
            b"FORNAX/v1/wrap\0" + header,
        )
        return AESGCM(dek).decrypt(
            descriptor.payload_nonce, ciphertext,
            b"FORNAX/v1/payload\0" + header,
        )
    except InvalidTag as exc:
        raise FornaxPasswordError("A autorização da sessão não corresponde ao modelo.") from exc


def _validated_full_document(metadata: Any, assets: Mapping[str, bytes]) -> dict:
    if not isinstance(metadata, dict):
        raise FornaxFormatError("document.json protegido deve ser um objeto.")
    try:
        document = persistent_model_document(normalize_model_document(metadata))
    except (TypeError, ValueError) as exc:
        raise FornaxFormatError(f"Documento protegido inválido: {exc}.") from exc
    references = set(_document_asset_references(document))
    for reference in references:
        _validate_inner_asset_reference(reference)
    if references != set(assets):
        raise FornaxAssetError("Os assets protegidos não correspondem ao documento.")
    return document


def _public_reference_changed(
    expected: Any, document_bytes: bytes, assets: Mapping[str, bytes],
) -> bool:
    if not isinstance(expected, list):
        raise FornaxFormatError("public_reference inválido.")
    actual = _public_hashes(document_bytes, assets)
    expected_paths = []
    for item in expected:
        if (
            not isinstance(item, dict) or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or not isinstance(item["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        ):
            raise FornaxFormatError("Entrada de public_reference inválida.")
        expected_paths.append(item["path"])
    if expected_paths != sorted(expected_paths) or len(expected_paths) != len(set(expected_paths)):
        raise FornaxFormatError("public_reference deve possuir paths únicos e ordenados.")
    return expected != actual


def _merge_protected_signatures(public: dict, protected: Any) -> dict:
    if not isinstance(protected, dict) or set(protected) != {
        "version", "public_reference", "pages", "protected_origin_info",
    } or protected["version"] != 1 or not isinstance(protected["pages"], list):
        raise FornaxFormatError("signatures.json possui estrutura inválida.")
    result = deepcopy(public)
    pages = {page["page_id"]: page for page in result["pages"]}
    seen_pages = set()
    for protected_page in protected["pages"]:
        if not isinstance(protected_page, dict) or set(protected_page) != {
            "page_id", "signatures", "original_layer_order", "public_object_ids",
        }:
            raise FornaxFormatError("Página protegida possui estrutura inválida.")
        page_id = protected_page["page_id"]
        if page_id in seen_pages or page_id not in pages:
            raise FornaxFormatError("Página protegida ausente, repetida ou incompatível.")
        seen_pages.add(page_id)
        page = pages[page_id]
        signatures = deepcopy(protected_page["signatures"])
        if not isinstance(signatures, list) or not all(isinstance(item, dict) for item in signatures):
            raise FornaxFormatError("Lista de assinaturas protegidas inválida.")
        occupied = {
            item["object_id"]
            for collection in ("boxes", "images", "shapes")
            for item in page.get(collection, [])
        }
        remapped = {}
        for signature in signatures:
            object_id = signature.get("object_id")
            if not isinstance(object_id, str) or not object_id:
                raise FornaxFormatError("Assinatura protegida sem object_id.")
            if object_id in occupied or object_id in remapped.values():
                new_id = f"signature:{uuid4()}"
                remapped[object_id] = new_id
                signature["object_id"] = new_id
            occupied.add(signature["object_id"])
        original_order = protected_page["original_layer_order"]
        public_ids = protected_page["public_object_ids"]
        if not isinstance(original_order, list) or not isinstance(public_ids, list):
            raise FornaxFormatError("Ordem protegida inválida.")
        original_order = [remapped.get(item, item) for item in original_order]
        signature_ids = {item["object_id"] for item in signatures}
        current_order = list(page["layer_order"])
        unchanged = current_order == public_ids
        if unchanged:
            merged_order = original_order
        else:
            merged_order = current_order[:]
            for index, object_id in enumerate(original_order):
                if object_id not in signature_ids:
                    continue
                next_public = next(
                    (candidate for candidate in original_order[index + 1:]
                     if candidate not in signature_ids and candidate in merged_order),
                    None,
                )
                position = merged_order.index(next_public) if next_public else len(merged_order)
                merged_order.insert(position, object_id)
        page["signatures"] = signatures
        page["layer_order"] = merged_order
    if seen_pages != set(pages):
        raise FornaxFormatError("signatures.json não descreve todas as páginas.")
    if protected["protected_origin_info"] is not None:
        result["origin_info"] = deepcopy(protected["protected_origin_info"])
    try:
        return persistent_model_document(normalize_model_document(result))
    except (TypeError, ValueError) as exc:
        raise FornaxFormatError(f"Não foi possível recombinar as assinaturas: {exc}.") from exc


def unlock_fornax(
    path_or_descriptor: str | Path | FornaxDescriptor,
    password: str,
) -> OpenedFornax:
    """Autentica todo o payload antes de disponibilizar documento ou assets."""
    opened, _kek = _unlock_fornax_with_key(path_or_descriptor, password)
    return opened


def _unlock_fornax_with_retained_kek(
    path_or_descriptor: str | Path | FornaxDescriptor, kek: bytes,
) -> OpenedFornax:
    descriptor = (
        path_or_descriptor if isinstance(path_or_descriptor, FornaxDescriptor)
        else inspect_fornax(path_or_descriptor)
    )
    if descriptor.mode == PUBLIC_MODE:
        return open_public_fornax(descriptor)
    ciphertext, public_bytes, public_assets = _outer_contents(descriptor.path, descriptor)
    plaintext = _decrypt_payload_with_kek(descriptor, ciphertext, kek)
    protected_assets, metadata = _read_inner_zip(plaintext, mode=descriptor.mode)
    if descriptor.mode == FULL_MODE:
        document = _validated_full_document(metadata, protected_assets)
        return OpenedFornax(
            descriptor, document, MappingProxyType(dict(protected_assets)), False,
        )
    public_opened = open_public_fornax(descriptor)
    changed = _public_reference_changed(
        metadata.get("public_reference") if isinstance(metadata, dict) else None,
        public_bytes, public_assets,
    )
    document = _merge_protected_signatures(public_opened.document(), metadata)
    assets = {**public_assets, **protected_assets}
    if set(_document_asset_references(document)) != set(assets):
        raise FornaxAssetError("Os assets recombinados não correspondem ao documento.")
    return OpenedFornax(descriptor, document, MappingProxyType(assets), changed)


def _unlock_fornax_with_key(
    path_or_descriptor: str | Path | FornaxDescriptor,
    password: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[OpenedFornax, bytes | None]:
    """Variante interna usada pela sessão para reter somente a KEK derivada."""
    if isinstance(path_or_descriptor, FornaxDescriptor):
        descriptor = path_or_descriptor
        if inspect_fornax(descriptor.path) != descriptor:
            raise FornaxFormatError("O pacote mudou depois de ser inspecionado.")
    else:
        descriptor = inspect_fornax(path_or_descriptor)
    if descriptor.mode == PUBLIC_MODE:
        return open_public_fornax(descriptor), None
    password_bytes(password)
    ciphertext, public_bytes, public_assets = _outer_contents(descriptor.path, descriptor)
    plaintext, kek = _decrypt_payload(
        descriptor, ciphertext, password, cancel_check=cancel_check,
    )
    protected_assets, metadata = _read_inner_zip(plaintext, mode=descriptor.mode)
    if descriptor.mode == FULL_MODE:
        document = _validated_full_document(metadata, protected_assets)
        return OpenedFornax(
            descriptor, document, MappingProxyType(dict(protected_assets)), False,
        ), kek
    public_opened = open_public_fornax(descriptor)
    changed = _public_reference_changed(
        metadata.get("public_reference") if isinstance(metadata, dict) else None,
        public_bytes, public_assets,
    )
    document = _merge_protected_signatures(public_opened.document(), metadata)
    references = set(_document_asset_references(document))
    assets = {**public_assets, **protected_assets}
    if references != set(assets):
        raise FornaxAssetError("Os assets recombinados não correspondem ao documento.")
    return OpenedFornax(descriptor, document, MappingProxyType(assets), changed), kek


def reencrypt_fornax(
    source: str | Path | FornaxDescriptor,
    current_password: str,
    destination: str | Path,
    new_password: str,
    *,
    mode: str | None = None,
    new_identity: bool = False,
) -> FornaxDescriptor:
    """Troca a senha ou cria cópia protegida com material criptográfico novo."""
    opened = unlock_fornax(source, current_password)
    if opened.descriptor.mode == PUBLIC_MODE:
        raise FornaxFormatError("Um modelo público não possui senha para trocar.")
    target_mode = mode or opened.descriptor.mode
    if target_mode not in PROTECTED_MODES:
        raise FornaxFormatError("A recriptografia exige modo protegido.")
    model_id = None if new_identity else opened.descriptor.model_id
    return save_protected_fornax(
        opened.document(), destination, new_password, mode=target_mode,
        asset_provider=opened.asset, model_id=model_id,
    )


def save_signature_free_copy(
    source: str | Path | FornaxDescriptor,
    destination: str | Path,
    *,
    password: str | None = None,
) -> FornaxDescriptor:
    """Cria uma nova identidade pública sem qualquer assinatura protegida."""
    descriptor = source if isinstance(source, FornaxDescriptor) else inspect_fornax(source)
    destination_path = Path(destination)
    if destination_path.resolve() == descriptor.path.resolve():
        raise FornaxFormatError("A cópia sem assinaturas não pode sobrescrever o original.")
    if descriptor.mode == FULL_MODE:
        if password is None:
            raise FornaxPasswordError("O modelo integral exige senha antes de criar a cópia.")
        opened = unlock_fornax(descriptor, password)
        document = opened.document()
        signature_paths = {
            item.get("path")
            for page in document["pages"]
            for item in page.get("signatures", [])
            if isinstance(item.get("path"), str)
        }
        document = without_signatures(document)
        _filter_origin_info(document, signature_paths)
        # No modo integral os paths já foram anonimizados antes da abertura e
        # não permitem relacionar com segurança os nomes do snapshot legado.
        # Uma cópia pública pode omitir esse inventário; nunca deve arriscar
        # revelar o nome original de um asset de assinatura.
        origin = document.get("origin_info")
        if isinstance(origin, dict) and isinstance(origin.get("assets"), list):
            origin["assets"] = []
    else:
        opened = open_public_fornax(descriptor)
        document = opened.document()
    document = without_signatures(document)
    return save_public_fornax(
        document, destination_path, asset_provider=opened.asset,
    )
