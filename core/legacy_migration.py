"""Conversão retomável de diretórios legados para contêineres ``.fornax``."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4
from uuid import UUID

from core.file_transactions import file_lock, publish_new, sync_directory

from core.fornax_container import (
    FULL_MODE,
    PUBLIC_MODE,
    SIGNATURES_MODE,
    inspect_fornax,
    save_protected_fornax,
    save_public_fornax,
)
from core.model_document import document_signatures, load_model_document


JOURNAL_VERSION = 1
MIGRATIONS_DIR = "migrations"
STATES = {"PREPARED", "VERIFIED", "PUBLISHED", "CLEANED"}


class LegacyMigrationError(RuntimeError):
    """A conversão não pôde prosseguir sem arriscar o modelo original."""


@dataclass(frozen=True, slots=True)
class LegacyMigrationResult:
    destination: Path
    cleanup_complete: bool
    remaining_paths: tuple[str, ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.pending-{uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_relative(raw: str) -> Path:
    if not isinstance(raw, str) or "\\" in raw or ":" in raw or any(ord(c) < 32 for c in raw):
        raise LegacyMigrationError("O diário de migração contém um caminho inválido.")
    pure = PurePosixPath(raw)
    if pure.as_posix() != raw or pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise LegacyMigrationError("O diário de migração contém um caminho inválido.")
    return Path(*pure.parts)


def _inventory(source: Path) -> list[dict]:
    if not source.is_dir() or source.is_symlink():
        raise LegacyMigrationError("A origem legada deve ser um diretório real.")
    entries = []
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        for name in directories:
            if (root_path / name).is_symlink():
                raise LegacyMigrationError("O modelo legado contém link simbólico.")
        for name in files:
            path = root_path / name
            if path.is_symlink():
                raise LegacyMigrationError("O modelo legado contém link simbólico.")
            if not path.is_file():
                raise LegacyMigrationError("O modelo legado contém entrada não regular.")
            relative = path.relative_to(source).as_posix()
            stat = path.stat()
            entries.append({
                "path": relative,
                "size": stat.st_size,
                "sha256": _sha256(path),
            })
    entries.sort(key=lambda item: item["path"])
    return entries


def _inventory_matches(source: Path, expected: list[dict]) -> bool:
    try:
        return _inventory(source) == expected
    except (OSError, LegacyMigrationError):
        return False


def _migration_dir(models_dir: Path) -> Path:
    return models_dir.parent / MIGRATIONS_DIR


def _destination_for(source: Path, models_dir: Path) -> Path:
    candidate = models_dir / f"{source.name}.fornax"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = models_dir / f"{source.name}-{counter}.fornax"
        if not candidate.exists():
            return candidate
        counter += 1


def _write_state(journal_path: Path, journal: dict, state: str) -> None:
    if state not in STATES:
        raise ValueError(state)
    journal["state"] = state
    _atomic_json(journal_path, journal)


def _validate_package(path: Path, expected_hash: str | None = None) -> str:
    inspect_fornax(path)
    digest = _sha256(path)
    if expected_hash is not None and digest != expected_hash:
        raise LegacyMigrationError("O pacote publicado mudou durante a migração.")
    return digest


def _cleanup_source(source: Path, inventory: list[dict]) -> tuple[str, ...]:
    if source.is_symlink():
        return ("<origem substituída por link>",)
    expected = {item["path"]: item for item in inventory}
    remaining = []
    for relative, item in expected.items():
        path = source / _safe_relative(relative)
        try:
            if any(parent.is_symlink() for parent in path.parents if parent != source.parent):
                remaining.append(relative)
                continue
            if (
                path.is_file() and not path.is_symlink()
                and path.stat().st_size == item["size"]
                and _sha256(path) == item["sha256"]
            ):
                path.unlink()
            elif path.exists() or path.is_symlink():
                remaining.append(relative)
        except OSError:
            remaining.append(relative)
    if source.exists():
        for root, directories, files in os.walk(source, topdown=False, followlinks=False):
            root_path = Path(root)
            if files:
                remaining.extend(
                    path.relative_to(source).as_posix()
                    for path in (root_path / name for name in files)
                    if path.relative_to(source).as_posix() not in remaining
                )
            for name in directories:
                directory = root_path / name
                if directory.is_symlink():
                    relative = directory.relative_to(source).as_posix()
                    if relative not in remaining:
                        remaining.append(relative)
                else:
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            sync_directory(root_path)
        try:
            source.rmdir()
        except OSError:
            pass
        sync_directory(source.parent)
    if source.exists():
        known = set(remaining)
        for path in source.rglob("*"):
            relative = path.relative_to(source).as_posix()
            if relative not in known:
                remaining.append(relative)
                known.add(relative)
        if not remaining:
            remaining.append("<diretório não removido>")
    return tuple(sorted(set(remaining)))


def migrate_legacy_model(
    source: str | Path,
    models_dir: str | Path,
    *,
    mode: str,
    password: str | None = None,
    public_signatures_acknowledged: bool = False,
) -> LegacyMigrationResult:
    models_dir = Path(models_dir).resolve()
    with file_lock(_migration_dir(models_dir) / ".migration.lock"):
        # Retomar antes de criar outra conversão da mesma pasta.
        _resume_legacy_migrations(models_dir)
        for journal_path in _migration_dir(models_dir).glob("*.json"):
            journal = _load_journal(journal_path)
            if journal["source"] == Path(source).name:
                raise LegacyMigrationError("Há uma migração pendente para este modelo.")
        result = _migrate_legacy_model(
            source, models_dir, mode=mode, password=password,
            public_signatures_acknowledged=public_signatures_acknowledged,
        )
    try:
        _migration_dir(models_dir).rmdir()
    except OSError:
        pass
    return result


def _migrate_legacy_model(
    source, models_dir, *, mode, password=None,
    public_signatures_acknowledged=False,
):
    """Converte uma pasta, publica o pacote validado e limpa somente a origem intacta."""
    source = Path(source).absolute()
    if source.is_symlink():
        raise LegacyMigrationError("A origem legada contém link simbólico.")
    models_dir = Path(models_dir).resolve()
    try:
        source.relative_to(models_dir)
    except ValueError as exc:
        raise LegacyMigrationError("A origem não pertence à biblioteca de modelos.") from exc
    if source.parent != models_dir:
        raise LegacyMigrationError("Somente modelos na raiz da biblioteca podem ser convertidos.")
    inventory = _inventory(source)
    document = load_model_document(source)
    has_signatures = bool(document_signatures(document))
    if has_signatures and mode == PUBLIC_MODE and not public_signatures_acknowledged:
        raise LegacyMigrationError(
            "A conversão pública de assinaturas exige aceite explícito."
        )
    if has_signatures and mode not in {PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE}:
        raise LegacyMigrationError("Modo de proteção inválido para assinaturas.")
    if not has_signatures and mode != PUBLIC_MODE:
        raise LegacyMigrationError("A migração pública esperava um modelo sem assinatura.")

    operation_id = str(uuid4())
    destination = _destination_for(source, models_dir)
    staging = models_dir / f".{destination.name}.migration-{operation_id}.fornax"
    journal_path = _migration_dir(models_dir) / f"{operation_id}.json"
    journal = {
        "version": JOURNAL_VERSION,
        "operation_id": operation_id,
        "state": "PREPARED",
        "source": source.relative_to(models_dir).as_posix(),
        "destination": destination.relative_to(models_dir).as_posix(),
        "staging": staging.relative_to(models_dir).as_posix(),
        "mode": mode,
        "source_inventory": inventory,
        "package_sha256": None,
    }
    _atomic_json(journal_path, journal)
    try:
        if mode == PUBLIC_MODE:
            if has_signatures:
                document["protection_preferences"] = {
                    "public_signatures_acknowledged": True,
                }
            save_public_fornax(document, staging, source_dir=source)
        else:
            if password is None:
                raise LegacyMigrationError("A senha é obrigatória para proteger assinaturas.")
            save_protected_fornax(
                document, staging, password, mode=mode, source_dir=source,
            )
        if not _inventory_matches(source, inventory):
            raise LegacyMigrationError("O modelo legado mudou durante a conversão.")
        journal["package_sha256"] = _validate_package(staging)
        _write_state(journal_path, journal, "VERIFIED")
        if destination.exists():
            raise LegacyMigrationError("O destino da migração passou a existir durante a conversão.")
        publish_new(staging, destination)
        _validate_package(destination, journal["package_sha256"])
        _write_state(journal_path, journal, "PUBLISHED")
        try:
            remaining = _cleanup_source(source, inventory)
        except OSError:
            remaining = ("<limpeza pendente>",)
        if not remaining:
            _write_state(journal_path, journal, "CLEANED")
            journal_path.unlink(missing_ok=True)
            try:
                journal_path.parent.rmdir()
            except OSError:
                pass
        return LegacyMigrationResult(destination, not remaining, remaining)
    except Exception:
        if journal.get("state") == "PREPARED":
            staging.unlink(missing_ok=True)
            journal_path.unlink(missing_ok=True)
        raise


def _load_journal(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LegacyMigrationError(f"Diário de migração inválido: {path.name}.") from exc
    required = {
        "version", "operation_id", "state", "source", "destination", "staging",
        "mode", "source_inventory", "package_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise LegacyMigrationError(f"Diário de migração inválido: {path.name}.")
    if type(value["version"]) is not int or value["version"] != JOURNAL_VERSION or not isinstance(value["state"], str) or value["state"] not in STATES:
        raise LegacyMigrationError(f"Diário de migração incompatível: {path.name}.")
    try:
        operation = str(UUID(value["operation_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise LegacyMigrationError("Identidade do diário inválida.") from exc
    if path.name != f"{operation}.json" or not isinstance(value["mode"], str) or value["mode"] not in {PUBLIC_MODE, FULL_MODE, SIGNATURES_MODE}:
        raise LegacyMigrationError("Identidade do diário inválida.")
    for key in ("source", "destination", "staging"):
        if len(_safe_relative(value[key]).parts) != 1:
            raise LegacyMigrationError("O diário aponta para fora da raiz da biblioteca.")
    if (value["source"].startswith(".") or not value["destination"].endswith(".fornax")
            or value["destination"].startswith(".")
            or value["staging"] != f".{value['destination']}.migration-{operation}.fornax"
            or len({value[key] for key in ("source", "destination", "staging")}) != 3):
        raise LegacyMigrationError("Caminhos do diário inconsistentes.")
    digest = value["package_sha256"]
    if value["state"] != "PREPARED" and (
        not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise LegacyMigrationError("Hash do pacote ausente ou inválido.")
    if not isinstance(value["source_inventory"], list):
        raise LegacyMigrationError("Inventário inválido.")
    seen = set()
    for item in value["source_inventory"]:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise LegacyMigrationError("Entrada do inventário inválida.")
        relative = str(_safe_relative(item["path"]))
        if relative in seen or type(item["size"]) is not int or item["size"] < 0:
            raise LegacyMigrationError("Entrada do inventário inválida.")
        seen.add(relative)
        if not isinstance(item["sha256"], str) or len(item["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["sha256"]):
            raise LegacyMigrationError("Hash de asset inválido.")
    return value


def publish_legacy_replacement(source: Path, destination: Path, staged: Path, inventory: list[dict]):
    """Substituição autorizada na importação usa a mesma limpeza retomável."""
    models_dir = destination.parent.resolve()
    source = source.absolute()
    if source.parent != models_dir or source.is_symlink():
        raise LegacyMigrationError("Origem legada inválida para substituição.")
    with file_lock(_migration_dir(models_dir) / ".migration.lock"):
        if not _inventory_matches(source, inventory):
            raise LegacyMigrationError("O modelo legado mudou durante a importação.")
        if destination.exists() or destination.is_symlink():
            raise LegacyMigrationError("O destino da importação já existe.")
        operation = str(uuid4())
        pending = models_dir / f".{destination.name}.migration-{operation}.fornax"
        journal_path = _migration_dir(models_dir) / f"{operation}.json"
        descriptor = inspect_fornax(staged)
        journal = {
            "version": JOURNAL_VERSION, "operation_id": operation,
            "state": "PREPARED", "source": source.name,
            "destination": destination.name, "staging": pending.name,
            "mode": descriptor.mode, "source_inventory": inventory,
            "package_sha256": None,
        }
        _atomic_json(journal_path, journal)
        os.replace(staged, pending)
        journal["package_sha256"] = _validate_package(pending)
        _write_state(journal_path, journal, "VERIFIED")
        publish_new(pending, destination)
        _write_state(journal_path, journal, "PUBLISHED")
        remaining = _cleanup_source(source, inventory)
        if not remaining:
            _write_state(journal_path, journal, "CLEANED")
            journal_path.unlink(missing_ok=True)
        return LegacyMigrationResult(destination, not remaining, remaining)


def resume_legacy_migrations(models_dir: str | Path) -> tuple[Path, ...]:
    models_dir = Path(models_dir).resolve()
    directory = _migration_dir(models_dir)
    if not directory.is_dir():
        return ()
    with file_lock(directory / ".migration.lock"):
        result = _resume_legacy_migrations(models_dir)
    try:
        directory.rmdir()
    except OSError:
        pass
    return result


def _resume_legacy_migrations(models_dir: str | Path) -> tuple[Path, ...]:
    """Retoma publicação/limpeza e informa origens já substituídas a ocultar."""
    models_dir = Path(models_dir).resolve()
    directory = _migration_dir(models_dir)
    if not directory.is_dir():
        return ()
    suppressed = []
    for journal_path in sorted(directory.glob("*.json")):
        try:
            if journal_path.is_symlink():
                continue
            journal = _load_journal(journal_path)
            source = models_dir / _safe_relative(journal["source"])
            destination = models_dir / _safe_relative(journal["destination"])
            staging = models_dir / _safe_relative(journal["staging"])
            if any(path.is_symlink() for path in (source, destination, staging)):
                continue
            state = journal["state"]
            expected_hash = journal["package_sha256"]
            if state == "PREPARED":
                staging.unlink(missing_ok=True)
                journal_path.unlink(missing_ok=True)
                continue
            if state == "VERIFIED":
                if destination.is_file():
                    _validate_package(destination, expected_hash)
                else:
                    _validate_package(staging, expected_hash)
                    if not _inventory_matches(source, journal["source_inventory"]):
                        raise LegacyMigrationError("A origem mudou antes da publicação retomada.")
                    publish_new(staging, destination)
                staging.unlink(missing_ok=True)
                _write_state(journal_path, journal, "PUBLISHED")
                state = "PUBLISHED"
            if state == "PUBLISHED":
                _validate_package(destination, expected_hash)
                suppressed.append(source.resolve())
                remaining = _cleanup_source(source, journal["source_inventory"])
                if not remaining:
                    _write_state(journal_path, journal, "CLEANED")
                    journal_path.unlink(missing_ok=True)
            elif state == "CLEANED":
                _validate_package(destination, expected_hash)
                journal_path.unlink(missing_ok=True)
        except Exception:
            # Um diário problemático nunca autoriza apagar ou ocultar a origem.
            continue
    try:
        directory.rmdir()
    except OSError:
        pass
    return tuple(suppressed)
