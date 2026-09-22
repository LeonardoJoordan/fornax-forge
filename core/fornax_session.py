"""Ciclo de vida de acesso aos modelos ``.fornax``.

A sessão centraliza autorização, expiração e snapshots de jobs. Não possui UI,
não grava senha e não materializa assets em disco.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
import time
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4

from core.fornax_container import (
    FULL_MODE,
    MAX_PACKAGE_BYTES,
    PUBLIC_MODE,
    SIGNATURES_MODE,
    FornaxAssetError,
    FornaxDescriptor,
    FornaxError,
    FornaxFormatError,
    FornaxPasswordError,
    OpenedFornax,
    _unlock_fornax_with_key,
    _unlock_fornax_with_retained_kek,
    inspect_fornax,
    open_public_fornax,
    save_protected_fornax_with_key,
    save_public_fornax,
)


DEFAULT_GRACE_SECONDS = 300.0
SIGNATURE_FREE_LABEL = "Cópia sem assinaturas — o original está preservado"


class FornaxExternalChangeError(FornaxError):
    """O arquivo mudou enquanto havia trabalho aberto no editor."""


class AccessState(str, Enum):
    LOCKED = "locked"
    PUBLIC_ACTIVE = "public_active"
    AUTHORIZED_ACTIVE = "authorized_active"
    GRACE = "grace"
    SIGNATURE_FREE_COPY = "signature_free_copy"
    EXPIRED = "expired"
    EXTERNAL_CHANGED = "external_changed"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class SessionToken:
    model_id: str
    revision_id: str
    generation: int
    nonce: str


@dataclass(frozen=True, slots=True)
class SessionStatus:
    descriptor: FornaxDescriptor
    state: AccessState
    temporary: bool
    active: bool
    grace_remaining: float | None
    requires_password: bool
    can_open_without_signatures: bool
    save_as_required: bool
    notice: str | None
    public_changed: bool


class AuthorizedJobSnapshot:
    """Conteúdo imutável que um job já autorizado pode terminar de usar."""

    __slots__ = ("model_id", "revision_id", "authorization_id", "_document", "_assets", "_closed")

    def __init__(self, opened: OpenedFornax):
        self.model_id = opened.descriptor.model_id
        self.revision_id = opened.descriptor.revision_id
        self.authorization_id = str(uuid4())
        self._document = opened.document()
        self._assets = MappingProxyType({
            reference: bytes(opened.asset(reference))
            for reference in opened.asset_references
        })
        self._closed = False

    def document(self) -> dict:
        self._ensure_open()
        return deepcopy(self._document)

    def asset(self, reference: str) -> bytes:
        self._ensure_open()
        try:
            return self._assets[reference]
        except KeyError as exc:
            raise FornaxAssetError(f"Asset inexistente no snapshot: {reference!r}.") from exc

    @property
    def asset_references(self) -> tuple[str, ...]:
        self._ensure_open()
        return tuple(sorted(self._assets))

    def close(self) -> None:
        self._document = {}
        self._assets = MappingProxyType({})
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise FornaxFormatError("O snapshot autorizado já foi encerrado.")


class _ModelSession:
    __slots__ = (
        "descriptor", "fingerprint", "state", "temporary", "opened", "kek",
        "grace_deadline", "generation", "notice", "save_as_required",
    )

    def __init__(self, descriptor: FornaxDescriptor, fingerprint: str, *, temporary: bool):
        self.descriptor = descriptor
        self.fingerprint = fingerprint
        self.state = AccessState.LOCKED
        self.temporary = temporary
        self.opened: OpenedFornax | None = None
        self.kek: bytearray | None = None
        self.grace_deadline: float | None = None
        self.generation = 0
        self.notice: str | None = None
        self.save_as_required = False

    def discard_authorization(self, state: AccessState) -> None:
        if self.kek is not None:
            for index in range(len(self.kek)):
                self.kek[index] = 0
        self.kek = None
        self.opened = None
        self.grace_deadline = None
        self.state = state
        self.generation += 1
        self.notice = None
        self.save_as_required = False


class FornaxSessionManager:
    """Gerencia acessos por path e mantém apenas um modelo ativo na UI."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
    ):
        if grace_seconds <= 0:
            raise ValueError("grace_seconds deve ser positivo.")
        self._clock = clock
        self._grace_seconds = float(grace_seconds)
        self._sessions: dict[Path, _ModelSession] = {}
        self._active_path: Path | None = None
        self._closed = False

    def select(self, path: str | Path, *, temporary: bool = False) -> SessionStatus:
        self._ensure_open()
        selected = Path(path).resolve()
        if self._active_path is not None and self._active_path != selected:
            self._leave_active()
        session = self._session(selected, temporary=temporary)
        if self._changed_on_disk(session):
            session.discard_authorization(AccessState.EXTERNAL_CHANGED)
            self._active_path = selected
            return self._status(session)
        self._expire_session_if_due(session)
        self._active_path = selected
        if session.state == AccessState.GRACE:
            # A tolerância conserva a chave, não todos os assets do modelo anterior.
            session.opened = _unlock_fornax_with_retained_kek(session.descriptor, bytes(session.kek))
            session.state = AccessState.AUTHORIZED_ACTIVE
            session.grace_deadline = None
            session.generation += 1
        elif session.state == AccessState.PUBLIC_ACTIVE:
            if session.opened is None:
                session.opened = open_public_fornax(session.descriptor)
        elif session.state == AccessState.SIGNATURE_FREE_COPY:
            if session.opened is None:
                session.opened = open_public_fornax(session.descriptor)
        elif session.descriptor.mode == PUBLIC_MODE and session.opened is None:
            session.opened = open_public_fornax(session.descriptor)
            session.state = AccessState.PUBLIC_ACTIVE
            session.generation += 1
        return self._status(session)

    def unlock(
        self, path: str | Path, password: str, *, temporary: bool = False,
        cancel_check: Callable[[], bool] | None = None,
    ) -> SessionStatus:
        status = self.select(path, temporary=temporary)
        session = self._sessions[status.descriptor.path]
        if session.state == AccessState.EXTERNAL_CHANGED:
            raise FornaxFormatError("O arquivo mudou; recarregue antes de desbloquear.")
        if session.descriptor.mode == PUBLIC_MODE:
            return self._status(session)
        opened, kek = _unlock_fornax_with_key(
            session.descriptor, password, cancel_check=cancel_check,
        )
        session.opened = opened
        session.kek = bytearray(kek) if kek is not None else None
        session.state = AccessState.AUTHORIZED_ACTIVE
        session.grace_deadline = None
        session.notice = None
        session.save_as_required = False
        session.generation += 1
        return self._status(session)

    def open_without_signatures(
        self, path: str | Path, *, temporary: bool = False,
    ) -> SessionStatus:
        status = self.select(path, temporary=temporary)
        session = self._sessions[status.descriptor.path]
        if session.state == AccessState.EXTERNAL_CHANGED:
            raise FornaxFormatError("O arquivo mudou; recarregue antes de abrir a cópia.")
        if session.descriptor.mode != SIGNATURES_MODE:
            if session.descriptor.mode == FULL_MODE:
                raise FornaxPasswordError("O modelo integral não pode ser aberto sem senha.")
            raise FornaxFormatError("Este modelo não possui assinaturas protegidas.")
        session.discard_authorization(AccessState.SIGNATURE_FREE_COPY)
        session.opened = open_public_fornax(session.descriptor)
        session.notice = SIGNATURE_FREE_LABEL
        session.save_as_required = True
        session.generation += 1
        return self._status(session)

    def leave_active(self) -> None:
        self._ensure_open()
        self._leave_active()

    def forget(self, path: str | Path) -> None:
        """Descarta uma sessão cujo arquivo saiu da biblioteca."""
        self._ensure_open()
        selected = Path(path).resolve()
        session = self._sessions.pop(selected, None)
        if self._active_path == selected:
            self._active_path = None
        if session is not None:
            session.discard_authorization(AccessState.CLOSED)

    def _leave_active(self) -> None:
        if self._active_path is None:
            return
        session = self._sessions.get(self._active_path)
        self._active_path = None
        if session is None:
            return
        if session.state == AccessState.AUTHORIZED_ACTIVE:
            session.state = AccessState.GRACE
            session.grace_deadline = self._clock() + self._grace_seconds
            session.generation += 1
        session.opened = None

    def expire_due(self) -> tuple[FornaxDescriptor, ...]:
        self._ensure_open()
        expired = []
        for path, session in self._sessions.items():
            if path == self._active_path:
                continue
            if self._expire_session_if_due(session):
                expired.append(session.descriptor)
        return tuple(expired)

    def suspend(self) -> None:
        """Invalida tolerâncias fora do modelo quando o SO é suspenso."""
        self._ensure_open()
        for path, session in self._sessions.items():
            if path != self._active_path and session.state == AccessState.GRACE:
                session.discard_authorization(AccessState.EXPIRED)

    def check_external_change(self, path: str | Path) -> bool:
        self._ensure_open()
        selected = Path(path).resolve()
        session = self._sessions.get(selected)
        if session is None:
            return False
        if not self._changed_on_disk(session):
            return False
        session.discard_authorization(AccessState.EXTERNAL_CHANGED)
        return True

    def reload(self, path: str | Path, *, temporary: bool | None = None) -> SessionStatus:
        self._ensure_open()
        selected = Path(path).resolve()
        previous = self._sessions.get(selected)
        if previous is not None:
            previous.discard_authorization(AccessState.CLOSED)
        descriptor = inspect_fornax(selected)
        session = _ModelSession(
            descriptor, _fingerprint(selected),
            temporary=previous.temporary if temporary is None and previous else bool(temporary),
        )
        self._sessions[selected] = session
        self._active_path = selected
        if descriptor.mode == PUBLIC_MODE:
            session.opened = open_public_fornax(descriptor)
            session.state = AccessState.PUBLIC_ACTIVE
            session.generation += 1
        return self._status(session)

    def document(self, path: str | Path | None = None) -> dict:
        session = self._accessible_session(path)
        return session.opened.document()

    def asset(self, reference: str, path: str | Path | None = None) -> bytes:
        session = self._accessible_session(path)
        return session.opened.asset(reference)

    def borrow_job(self, path: str | Path | None = None) -> AuthorizedJobSnapshot:
        session = self._accessible_session(path)
        return AuthorizedJobSnapshot(session.opened)

    def save(
        self, document: dict, *, path: str | Path | None = None,
        destination: str | Path | None = None, mode: str | None = None,
        asset_provider=None, new_identity: bool = False,
    ) -> SessionStatus:
        """Publica a revisão usando a autorização atualmente ativa."""
        session = self._accessible_session(path)
        if self._changed_on_disk(session):
            session.discard_authorization(AccessState.EXTERNAL_CHANGED)
            raise FornaxExternalChangeError(
                "O arquivo foi alterado externamente durante a edição."
            )
        previous_key = session.kek
        target = Path(destination or session.descriptor.path).resolve()
        selected_mode = mode or session.descriptor.mode
        provider = asset_provider or session.opened.asset
        model_id = None if new_identity else session.descriptor.model_id
        if selected_mode == PUBLIC_MODE:
            descriptor = save_public_fornax(
                document, target, asset_provider=provider, model_id=model_id,
            )
            opened = open_public_fornax(descriptor)
            new_state = AccessState.PUBLIC_ACTIVE
            retained_key = None
        else:
            if session.state != AccessState.AUTHORIZED_ACTIVE or session.kek is None:
                raise FornaxPasswordError("O modelo protegido não possui autorização ativa para salvar.")
            descriptor = save_protected_fornax_with_key(
                document, target, bytes(session.kek), session.descriptor.salt,
                mode=selected_mode, asset_provider=provider,
                model_id=model_id or session.descriptor.model_id,
            )
            opened = _unlock_fornax_with_retained_kek(descriptor, bytes(session.kek))
            new_state = AccessState.AUTHORIZED_ACTIVE
            retained_key = session.kek

        old_path = session.descriptor.path
        if target != old_path:
            self._sessions.pop(old_path, None)
        session.descriptor = descriptor
        session.fingerprint = _fingerprint(target)
        session.opened = opened
        session.state = new_state
        session.grace_deadline = None
        session.notice = None
        session.save_as_required = False
        session.generation += 1
        if retained_key is None and previous_key is not None:
            for index in range(len(previous_key)):
                previous_key[index] = 0
        session.kek = retained_key
        self._sessions[target] = session
        self._active_path = target
        return self._status(session)

    def write_recovery(
        self, document: dict, destination: str | Path, *,
        path: str | Path | None = None, asset_provider=None,
    ) -> FornaxDescriptor:
        """Grava um snapshot lateral no mesmo nível de proteção da sessão."""
        session = self._accessible_session(path)
        provider = asset_provider or session.opened.asset
        if session.descriptor.mode == PUBLIC_MODE:
            return save_public_fornax(
                document, destination, asset_provider=provider,
                model_id=session.descriptor.model_id,
            )
        if session.state != AccessState.AUTHORIZED_ACTIVE or session.kek is None:
            raise FornaxPasswordError("O modelo protegido não possui autorização ativa para recuperar.")
        return save_protected_fornax_with_key(
            document, destination, bytes(session.kek), session.descriptor.salt,
            mode=session.descriptor.mode, asset_provider=provider,
            model_id=session.descriptor.model_id,
        )

    def read_recovery(
        self, recovery_path: str | Path, *, path: str | Path | None = None,
    ) -> OpenedFornax:
        """Lê um snapshot lateral somente com a autorização do original ativo."""
        session = self._accessible_session(path)
        descriptor = inspect_fornax(recovery_path)
        if (
            descriptor.model_id != session.descriptor.model_id
            or descriptor.mode != session.descriptor.mode
        ):
            raise FornaxFormatError("O arquivo de recuperação não pertence a este modelo.")
        if descriptor.mode == PUBLIC_MODE:
            return open_public_fornax(descriptor)
        if session.kek is None:
            raise FornaxPasswordError("A recuperação protegida exige uma sessão autorizada.")
        return _unlock_fornax_with_retained_kek(descriptor, bytes(session.kek))

    def issue_token(self, path: str | Path | None = None) -> SessionToken:
        session = self._accessible_session(path)
        return SessionToken(
            session.descriptor.model_id, session.descriptor.revision_id,
            session.generation, str(uuid4()),
        )

    def token_is_current(self, token: SessionToken) -> bool:
        if self._closed or self._active_path is None:
            return False
        session = self._sessions.get(self._active_path)
        return bool(
            session
            and session.opened is not None
            and session.state in {
                AccessState.PUBLIC_ACTIVE,
                AccessState.AUTHORIZED_ACTIVE,
                AccessState.SIGNATURE_FREE_COPY,
            }
            and session.descriptor.model_id == token.model_id
            and session.descriptor.revision_id == token.revision_id
            and session.generation == token.generation
        )

    def status(self, path: str | Path | None = None) -> SessionStatus:
        self._ensure_open()
        selected = self._resolve_requested_path(path)
        session = self._sessions[selected]
        self._expire_session_if_due(session)
        return self._status(session)

    def close(self) -> None:
        if self._closed:
            return
        for session in self._sessions.values():
            session.discard_authorization(AccessState.CLOSED)
        self._sessions.clear()
        self._active_path = None
        self._closed = True

    def _session(self, path: Path, *, temporary: bool) -> _ModelSession:
        session = self._sessions.get(path)
        if session is None:
            descriptor = inspect_fornax(path)
            session = _ModelSession(descriptor, _fingerprint(path), temporary=temporary)
            self._sessions[path] = session
        return session

    def _accessible_session(self, path: str | Path | None) -> _ModelSession:
        self._ensure_open()
        selected = self._resolve_requested_path(path)
        session = self._sessions[selected]
        if selected != self._active_path or session.opened is None or session.state not in {
            AccessState.PUBLIC_ACTIVE,
            AccessState.AUTHORIZED_ACTIVE,
            AccessState.SIGNATURE_FREE_COPY,
        }:
            raise FornaxPasswordError("O modelo não possui acesso ativo autorizado.")
        return session

    def _resolve_requested_path(self, path: str | Path | None) -> Path:
        if path is None:
            if self._active_path is None:
                raise FornaxFormatError("Nenhum modelo está ativo.")
            return self._active_path
        selected = Path(path).resolve()
        if selected not in self._sessions:
            raise FornaxFormatError("O modelo ainda não possui sessão.")
        return selected

    def _changed_on_disk(self, session: _ModelSession) -> bool:
        try:
            return _fingerprint(session.descriptor.path) != session.fingerprint
        except FornaxError:
            return True

    def _expire_session_if_due(self, session: _ModelSession) -> bool:
        if (
            session.state == AccessState.GRACE
            and session.grace_deadline is not None
            and self._clock() >= session.grace_deadline
        ):
            session.discard_authorization(AccessState.EXPIRED)
            return True
        return False

    def _status(self, session: _ModelSession) -> SessionStatus:
        remaining = None
        if session.state == AccessState.GRACE and session.grace_deadline is not None:
            remaining = max(0.0, session.grace_deadline - self._clock())
        return SessionStatus(
            descriptor=session.descriptor,
            state=session.state,
            temporary=session.temporary,
            active=session.descriptor.path == self._active_path,
            grace_remaining=remaining,
            requires_password=(
                session.descriptor.mode != PUBLIC_MODE
                and session.state in {
                    AccessState.LOCKED, AccessState.EXPIRED, AccessState.EXTERNAL_CHANGED,
                }
            ),
            can_open_without_signatures=(
                session.descriptor.mode == SIGNATURES_MODE
                and session.state in {
                    AccessState.LOCKED, AccessState.EXPIRED, AccessState.EXTERNAL_CHANGED,
                }
            ),
            save_as_required=session.save_as_required,
            notice=session.notice,
            public_changed=bool(session.opened and session.opened.public_changed),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise FornaxFormatError("O gerenciador de sessões já foi encerrado.")


def _fingerprint(path: Path) -> str:
    try:
        size = path.stat().st_size
        if size > MAX_PACKAGE_BYTES:
            raise FornaxFormatError("O arquivo .fornax excede 512 MiB.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise FornaxFormatError(f"Não foi possível verificar a revisão do modelo: {exc}.") from exc
