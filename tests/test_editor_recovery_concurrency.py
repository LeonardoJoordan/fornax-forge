"""Async-specific recovery contracts: lifecycle races and publication boundary."""
from contextlib import contextmanager
from copy import deepcopy
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from core.fornax_container import FULL_MODE, PUBLIC_MODE, save_public_fornax
from features.editor.recovery_worker import RecoveryWorker, _LIVE_WORKERS
from test_editor_recovery_updates import RecoveryBehaviorTest


class RecoveryConcurrencyTest(RecoveryBehaviorTest):
    def close_editor(self, window):
        from shiboken6 import isValid
        if isValid(window):
            super().close_editor(window)

    @contextmanager
    def staged(self):
        reached, release = threading.Event(), threading.Event()
        original = RecoveryWorker.dispatch_commit
        def pause(worker, action):
            reached.set()
            if not release.wait(10):
                raise AssertionError('Teste não liberou a publicação')
            return original(worker, action)
        with patch.object(RecoveryWorker, 'dispatch_commit', pause):
            try:
                yield reached, release
            finally:
                release.set()

    def wait_stage(self, reached):
        deadline = time.monotonic() + 10
        while not reached.is_set():
            if time.monotonic() > deadline:
                self.fail('A preparação não chegou à publicação')
            QTest.qWait(1)

    def assert_clean(self, w):
        self.wait_recovery(w)
        self.assertIsNone(w._recovery_pending)
        self.assertFalse(list(self.root.glob('*.pending-*')))
        self.assertFalse(list(self.root.glob('*.backup-*')))
        self.assertFalse(_LIVE_WORKERS)

    def test_ui_keeps_responding_and_stale_text_is_replaced(self):
        w, s, path = self.editor(); box = self.begin_typing(w)
        with self.staged() as (reached, release):
            w._write_fornax_recovery(); self.wait_stage(reached)
            task = w._recovery_task
            calls = []; timer = QTimer(); timer.setInterval(1); timer.timeout.connect(lambda: calls.append(1)); timer.start()
            QTest.qWait(25); timer.stop(); self.assertGreaterEqual(len(calls), 2)
            box.state.html_content = '<p>A versão mais nova</p>'; box.apply_state()
            release.set(); self.wait_recovery(w)
        recovered = s.read_recovery(w.fornax_recovery_path(path), path=path).document()
        self.assertEqual(recovered['pages'][0]['boxes'][0]['html'], box.state.html_content)
        self.assertEqual(task.document, {}); self.assertEqual(task.assets, {})
        self.assertIs(w.canvas_edit.box, box); self.assert_clean(w)

    def test_many_requests_keep_only_latest_pending_snapshot(self):
        w, s, path = self.editor(); box = self.begin_typing(w)
        with self.staged() as (reached, release):
            w._write_fornax_recovery(); self.wait_stage(reached); first = w._recovery_worker
            for index in range(8):
                box.state.html_content = f'<p>Atualização {index}</p>'; box.apply_state(); w._write_fornax_recovery()
                self.assertIs(w._recovery_worker, first); self.assertEqual(len(_LIVE_WORKERS), 1)
            self.assertEqual(w._recovery_pending.document['pages'][0]['boxes'][0]['html'], box.state.html_content)
            release.set(); self.wait_recovery(w)
        self.assertEqual(s.read_recovery(w.fornax_recovery_path(path), path=path).document()['pages'][0]['boxes'][0]['html'], box.state.html_content)
        self.assert_clean(w)

    def test_manual_save_cancels_job_before_original_write_and_recovery_removal(self):
        w, s, path = self.editor(); self.begin_typing(w)
        with self.staged() as (reached, release):
            w._write_fornax_recovery(); self.wait_stage(reached)
            with patch.object(w, '_show_save_success_dialog'):
                w.export_to_json(skip_close_dialog=True)
            saved = path.read_bytes(); release.set(); self.wait_recovery(w)
        self.assertEqual(path.read_bytes(), saved)
        self.assertFalse(w.fornax_recovery_path(path).exists()); self.assert_clean(w)

    def test_close_discards_pending_public_and_protected_jobs(self):
        for mode in (PUBLIC_MODE, FULL_MODE):
            with self.subTest(mode=mode):
                w, s, path = self.editor(mode); self.begin_typing(w)
                with self.staged() as (reached, release):
                    w._write_fornax_recovery(); self.wait_stage(reached); task = w._recovery_task
                    w._last_saved_state = w.get_current_scene_state(); w._last_saved_document_state = w._capture_document_history_state()
                    w.close(); release.set(); self.wait_recovery(w)
                self.assertFalse(w.fornax_recovery_path(path).exists()); self.assertEqual(task.document, {}); self.assert_clean(w)

    def test_document_switch_cannot_publish_previous_model(self):
        w, s, path = self.editor(); self.begin_typing(w)
        with self.staged() as (reached, release):
            w._write_fornax_recovery(); self.wait_stage(reached)
            other = self.root/'other.fornax'; document = s.document(); document['name'] = 'Outro modelo'
            save_public_fornax(document, other, asset_provider=s.asset)
            status = s.select(other)
            w.load_from_fornax(s.document(), path=other, mode=PUBLIC_MODE, model_id=status.descriptor.model_id, asset_provider=s.asset, session_manager=s)
            release.set(); self.wait_recovery(w)
        self.assertFalse(w.fornax_recovery_path(path).exists()); self.assertFalse(w.fornax_recovery_path(other).exists()); self.assert_clean(w)

    def test_expired_protected_authorization_removes_encrypted_staging_and_key(self):
        w, s, path = self.editor(FULL_MODE); self.begin_typing(w)
        with self.staged() as (reached, release):
            w._write_fornax_recovery(); self.wait_stage(reached); task = w._recovery_task
            staged = list(self.root.glob('*.pending-*')); self.assertEqual(len(staged), 1)
            with zipfile.ZipFile(staged[0]) as archive:
                self.assertEqual(set(archive.namelist()), {'manifest.json', 'protected.bin'})
            s.leave_active(); s._clock = lambda: float('inf'); s.expire_due()
            self.assertIsNone(task.authorization._key)
            release.set(); self.wait_recovery(w)
        self.assertFalse(w.fornax_recovery_path(path).exists()); self.assertEqual(task.assets, {}); self.assert_clean(w)

    def test_external_change_during_staging_cannot_publish(self):
        w, s, path = self.editor(); self.begin_typing(w)
        with self.staged() as (reached, release), patch('builtins.print'):
            w._write_fornax_recovery(); self.wait_stage(reached)
            changed = path.read_bytes() + b'external-change'; path.write_bytes(changed)
            release.set(); self.wait_recovery(w)
        self.assertEqual(path.read_bytes(), changed); self.assertFalse(w.fornax_recovery_path(path).exists()); self.assert_clean(w)

    def test_destination_change_before_ui_commit_is_preserved(self):
        w, s, path = self.editor(); self.begin_typing(w)
        recovery = w.fornax_recovery_path(path)
        with self.staged() as (reached, release), patch('builtins.print'):
            w._write_fornax_recovery(); self.wait_stage(reached)
            recovery.write_bytes(b'alteracao-externa')
            release.set(); self.wait_recovery(w)
        self.assertEqual(recovery.read_bytes(), b'alteracao-externa')
        self.assertIsNone(w._recovery_success); self.assert_clean(w)

    def test_failed_ui_publication_preserves_recovery_and_allows_retry(self):
        import core.fornax_container as container
        w, s, path = self.editor(); box = self.begin_typing(w); self.recover(w)
        recovery = w.fornax_recovery_path(path); old = recovery.read_bytes()
        box.state.html_content = '<p>Depois da falha</p>'; box.apply_state()
        replace = container.os.replace
        def deny(source, target):
            if target == recovery:
                raise PermissionError('Destino sem permissão')
            return replace(source, target)
        with patch.object(container.os, 'replace', side_effect=deny), patch('builtins.print'):
            self.recover(w)
        self.assertEqual(recovery.read_bytes(), old); self.assert_clean(w)
        self.recover(w)
        self.assertEqual(s.read_recovery(recovery, path=path).document()['pages'][0]['boxes'][0]['html'], box.state.html_content)
        self.assert_clean(w)

    def test_publication_itself_runs_on_ui_thread_without_native_item_access_in_worker(self):
        from PySide6.QtWidgets import QApplication
        import core.fornax_container as container
        w, s, path = self.editor(); self.begin_typing(w); threads = []
        original = container.publish_new
        def publish(*args):
            threads.append(threading.get_ident()); return original(*args)
        with patch.object(container, 'publish_new', publish):
            self.recover(w)
        self.assertEqual(threads, [threading.get_ident()]); self.assert_clean(w)

for name in list(RecoveryBehaviorTest.__dict__):
    if name.startswith('test_'): setattr(RecoveryConcurrencyTest, name, None)
