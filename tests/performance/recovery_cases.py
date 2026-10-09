"""Recuperação em arquivos temporários: conteúdo, assets, foco e tempo da UI."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import time

from PySide6.QtCore import QTimer, QEvent, QEventLoop
from PySide6.QtTest import QTest
from core.fornax_container import PUBLIC_MODE, FULL_MODE, SIGNATURES_MODE, save_public_fornax, save_protected_fornax
from core.fornax_session import FornaxSessionManager
from core.model_document import iter_page_asset_paths
from features.editor.canvas_items import DesignerBox
from editor_scenarios import Scenario, make_document, fingerprint
from paint_cases import settle, close_window, screen_image, image_hash
from copy_cases import canonical_copy_document


@dataclass(frozen=True)
class RecoveryCase:
    id: str
    mode: str = PUBLIC_MODE
    large: bool = False
    repeats: int = 1
    continuous: bool = False


def cases():
    return (RecoveryCase('public-small'), RecoveryCase('signatures-small', SIGNATURES_MODE),
            RecoveryCase('full-small', FULL_MODE), RecoveryCase('public-large', large=True),
            RecoveryCase('full-large', FULL_MODE, True), RecoveryCase('repeated-public', repeats=3),
            RecoveryCase('repeated-full-large', FULL_MODE, True, 3),
            RecoveryCase('continuous-public', repeats=3, continuous=True))


def canonical_recovery(value, asset_hashes):
    """Package asset filenames are random UUIDs; compare the actual bytes.

    Preserve every document field, reference occurrence and asset multiplicity.
    Only known asset references receive content-based names for comparison.
    """
    if isinstance(value, str):
        return '<asset:' + asset_hashes[value] + '>' if value in asset_hashes else value
    if isinstance(value, list):
        return [canonical_recovery(item, asset_hashes) for item in value]
    if isinstance(value, dict):
        return {key: canonical_recovery(item, asset_hashes) for key, item in value.items()}
    return value


def wait_recovery(window, app, timeout=60):
    if getattr(window, '_recovery_worker', None) is not None:
        # QTest.qWait(1) polling competes for the GIL and distorts background
        # timings. Run the real Qt event loop while the independent probe ticks.
        loop = QEventLoop()
        check = QTimer()
        check.setInterval(2)
        deadline = time.monotonic() + timeout
        def finished():
            if getattr(window, '_recovery_worker', None) is None or time.monotonic() > deadline:
                loop.quit()
        check.timeout.connect(finished)
        check.start()
        loop.exec()
        check.stop()
        assert getattr(window, '_recovery_worker', None) is None, 'Recuperação não terminou em 60s'
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


class RecoverySession:
    def __init__(self, window, case, app, root):
        self.window, self.case, self.app = window, case, app
        self.document, self.provider = make_document(Scenario('recovery', 'autosave', 'mixed', 20, mode=case.mode, large=case.large))
        self.input_sha256 = fingerprint(self.document, self.provider)
        self.sessions = FornaxSessionManager()
        self.path = Path(root)/'synthetic.fornax'
        if case.mode == PUBLIC_MODE:
            save_public_fornax(self.document, self.path, asset_provider=self.provider)
            status = self.sessions.select(self.path)
        else:
            save_protected_fornax(self.document, self.path, 'synthetic-test-password', mode=case.mode, asset_provider=self.provider)
            status = self.sessions.unlock(self.path, 'synthetic-test-password')
        self.opened_document = self.sessions.document()
        self.source_asset_hashes = {
            reference: sha256(self.sessions.asset(reference)).hexdigest()
            for _page, _kind, reference in iter_page_asset_paths(self.opened_document)
        }
        window.load_from_fornax(self.opened_document, path=self.path, mode=case.mode,
                               model_id=status.descriptor.model_id, asset_provider=self.sessions.asset, session_manager=self.sessions)
        window._autosave_timer.stop()
        window.resize(1280,800); window.show(); settle(app)
        self.original = self.path.read_bytes()
        self.restore()

    def restore(self):
        w=self.window
        wait_recovery(w,self.app)
        w._remove_fornax_recovery()
        w._finish_page_interaction()
        w._load_document_into_scene(deepcopy(self.opened_document))
        self.box=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==6)
        self.box.state.html_content='<p>Recuperação sintética <b>{Nome}</b></p>'
        self.box.apply_state(); w.canvas_edit.begin(self.box); settle(self.app)
        self.saved=deepcopy(w._last_saved_document_state)
        self.history=deepcopy(w.history._undo_stack)
        self.cursor=(self.box.text_item.textCursor().position(),self.box.text_item.textCursor().anchor())

    def perform(self):
        from unittest.mock import patch
        import core.fornax_container as container
        writes=[]; gaps=[]; last=[time.perf_counter_ns()]
        timer=QTimer();timer.setInterval(2)
        def tick():
            now=time.perf_counter_ns();gaps.append((now-last[0])/1e6);last[0]=now
        timer.timeout.connect(tick); timer.start(); QTest.qWait(6)
        gaps.clear();last[0]=time.perf_counter_ns()
        publish=container._publish_package
        def observe(*args,**kwargs):
            writes.append(1);return publish(*args,**kwargs)
        calls=[]; started=time.perf_counter_ns()
        with patch.object(container,'_publish_package',side_effect=observe):
            for index in range(self.case.repeats):
                if self.case.continuous:
                    self.box.state.html_content=f'<p>Versão {index} <b>{{Nome}}</b></p>';self.box.apply_state()
                before=time.perf_counter_ns();self.window._write_fornax_recovery();calls.append((time.perf_counter_ns()-before)/1e6)
                wait_recovery(self.window,self.app)
            self.app.processEvents();tick()
        elapsed=(time.perf_counter_ns()-started)/1e6;timer.stop()
        return {'total_ms':elapsed,'call_ms':calls,'max_ui_gap_ms':max(gaps,default=0),'effective_writes':len(writes)}

    def verify(self):
        w=self.window
        recovery=w.fornax_recovery_path(self.path)
        opened=self.sessions.read_recovery(recovery,path=self.path)
        document=opened.document()
        self.expected_html=self.box.state.html_content
        self.assert_equal(next(box for box in document['pages'][0]['boxes'] if box['layer_id']==6)['html'],self.expected_html)
        self.assert_equal(w._last_saved_document_state,self.saved)
        self.assert_equal(w.history._undo_stack,self.history)
        assert w.canvas_edit.box is self.box and self.box.text_item.hasFocus()
        assert self.path.read_bytes()==self.original
        settle(self.app)
        hashes = {r:sha256(opened.asset(r)).hexdigest() for r in opened.asset_references}
        return {'document':canonical_recovery(canonical_copy_document(document), hashes),'mode':opened.descriptor.mode,
                'assets':sorted(hashes.values()),
                'saved':canonical_recovery(canonical_copy_document(w._last_saved_document_state), self.source_asset_hashes),
                'history':[canonical_recovery(canonical_copy_document(state), self.source_asset_hashes) for state in w.history._undo_stack],
                'cursor':[self.box.text_item.textCursor().position(),self.box.text_item.textCursor().anchor()],
                'source_unchanged':True,'focus':True,'pixels':image_hash(screen_image(w,workspace=True))}

    @staticmethod
    def assert_equal(a,b):
        assert a==b,(a,b)

    def close(self):
        close_window(self.window,self.app);wait_recovery(self.window,self.app);self.sessions.close()
