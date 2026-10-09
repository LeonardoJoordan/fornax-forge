"""Recovery file work owns plain snapshots; only the commit runs on the UI.

No scene, widget, QPixmap or editor/provider callback crosses the thread boundary.
One worker at a time stages/verifies a package. The UI validates its snapshot and
executes the short publication without processing intervening edit events.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat

from PySide6.QtCore import QCoreApplication, QThread, Signal
from core.fornax_container import (
    _file_stamp, _stat_stamp, _load_source_asset, FornaxAssetError, FornaxFormatError,
)
from core.fornax_session import RecoveryCancelled
from core.model_document import iter_page_asset_paths


# Workers have no window parent: closing a protected window may delete it while
# compression finishes. Keep each thread alive until its native finished signal.
_LIVE_WORKERS = set()
_SHUTDOWN_INSTALLED = False


def _shutdown_recovery_workers():
    # Qt threads must finish before QApplication and its native services die.
    # Cancellation releases jobs awaiting UI approval; no UI callback is needed
    # to finish staging/cleanup. Closing one editor never waits here.
    workers = tuple(_LIVE_WORKERS)
    for worker in workers:
        worker.task.authorization.cancel()
    for worker in workers:
        worker.wait()
        _LIVE_WORKERS.discard(worker)


def _asset_stamp(path):
    # Image sources may be symlinks, just as in the regular save provider.
    # Follow the target and detect replacement/content changes by its stat.
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise FornaxAssetError(f"Asset não é um arquivo regular: {path}")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@dataclass
class RecoveryTask:
    document: dict
    assets: dict
    external: dict
    authorization: object
    destination: Path
    epoch: int
    previous: object = None

    @classmethod
    def capture(cls, document, authorized_bytes, authorization, destination, epoch, previous):
        assets, external = {}, {}
        for _page, _kind, reference in iter_page_asset_paths(document):
            if reference in assets or reference in external:
                continue
            data = authorized_bytes(reference)
            if data is not None:
                assets[reference] = bytes(data)
            else:
                path = Path(reference)
                stamp = _asset_stamp(path)
                if stamp is None:
                    raise FornaxAssetError(f"Asset não encontrado: {reference}")
                external[reference] = stamp
        return cls(deepcopy(document), assets, external, authorization, Path(destination), epoch, previous)

    def read_assets(self):
        for reference, stamp in self.external.items():
            self.authorization.check()
            path = Path(reference)
            if _asset_stamp(path) != stamp:
                raise RecoveryCancelled("O asset mudou antes da captura de arquivo.")
            self.assets[reference] = _load_source_asset(path)
            if _asset_stamp(path) != stamp:
                raise RecoveryCancelled("O asset mudou durante a captura de arquivo.")

    def external_is_current(self):
        return all(_asset_stamp(Path(reference)) == stamp for reference, stamp in self.external.items())

    def content_key(self):
        descriptor = self.authorization.descriptor
        token = self.authorization.token
        payload = [self.document, descriptor.mode, descriptor.model_id, descriptor.revision_id,
                   token.generation, {ref: hashlib.sha256(data).hexdigest() for ref, data in self.assets.items()}]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).digest()

    def clear(self):
        self.authorization.cancel()
        self.document.clear()
        self.assets.clear()
        self.external.clear()
        self.previous = None


class RecoveryWorker(QThread):
    commit_requested = Signal(object)

    def __init__(self, task):
        super().__init__()  # Intentionally no QObject/window parent.
        global _SHUTDOWN_INSTALLED
        app = QCoreApplication.instance()
        if app is not None and not _SHUTDOWN_INSTALLED:
            app.aboutToQuit.connect(_shutdown_recovery_workers)
            _SHUTDOWN_INSTALLED = True
        self.task = task
        self.result = None
        self.error = None
        self.commit_error = None
        self.commit_action = None
        self.committed = False
        self.finished.connect(self._release_thread)
        _LIVE_WORKERS.add(self)

    def _release_thread(self):
        _LIVE_WORKERS.discard(self)
        self.deleteLater()

    def dispatch_commit(self, action):
        task = self.task
        task.authorization.check_source()  # Full hash outside the UI.
        if not task.external_is_current():
            raise RecoveryCancelled("O asset mudou durante a preparação.")
        self.commit_action = action
        self.commit_requested.emit(self)
        task.authorization.answer.wait()
        if self.commit_error is not None:
            raise self.commit_error
        task.authorization.check()
        if not self.committed:
            raise RecoveryCancelled("Publicação não autorizada.")
        self.commit_action = None

    def run(self):
        task = self.task
        try:
            task.authorization.check_source()
            task.read_assets()
            key = task.content_key()
            stamp = _file_stamp(task.destination)
            if task.previous == (key, stamp) and stamp is not None:
                # Even a no-op needs UI validation and source/asset checks.
                def unchanged(validate=None):
                    if validate is not None:
                        validate()
                    if _stat_stamp(task.destination) != stamp[:-1]:
                        raise FornaxFormatError("A recuperação mudou antes da confirmação.")
                self.dispatch_commit(unchanged)
            else:
                task.authorization.write(task.document, task.destination,
                                         task.assets.__getitem__, self.dispatch_commit)
                stamp = _file_stamp(task.destination)
            self.result = (key, stamp)
        except RecoveryCancelled:
            pass
        except Exception as error:
            # Keep no traceback: it would retain documents/assets/keys in frames.
            self.error = str(error)
        finally:
            self.commit_action = None
            self.commit_error = None
            task.clear()
