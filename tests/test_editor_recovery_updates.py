"""Contrato da recuperação: estado salvo, assets, falhas e autorização."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtGui import QColor,QImage
import test_editor_autosave as original
from core.fornax_container import FULL_MODE
from features.editor.canvas_items import ImageItem


class RecoveryBehaviorTest(unittest.TestCase):
    setUpClass=classmethod(original.EditorAutosaveTest.setUpClass.__func__)
    setUp=original.EditorAutosaveTest.setUp
    editor=original.EditorAutosaveTest.editor
    close_editor=original.EditorAutosaveTest.close_editor
    wait_recovery=original.EditorAutosaveTest.wait_recovery
    begin_typing=original.EditorAutosaveTest.begin_typing

    def recover(self,w):
        w._write_fornax_recovery();self.wait_recovery(w)

    def test_recovery_is_separate_from_manual_save_and_history(self):
        w,s,path=self.editor();saved=deepcopy(w._last_saved_document_state);self.begin_typing(w)
        history=deepcopy(w.history._undo_stack);self.recover(w);self.recover(w)
        self.assertEqual(w._last_saved_document_state,saved);self.assertEqual(w.history._undo_stack,history)
        self.assertTrue(w.fornax_recovery_path(path).exists())

    def test_external_asset_bytes_are_refreshed_without_changing_the_reference(self):
        w,s,path=self.editor();self.begin_typing(w)
        image=QImage(12,12,QImage.Format.Format_ARGB32);image.fill(QColor('green'))
        external=self.root/'external.png';self.assertTrue(image.save(str(external)))
        item=ImageItem(str(external));item.layer_id=80;w.scene.addItem(item);w.refresh_layer_list()
        self.recover(w);opened=s.read_recovery(w.fornax_recovery_path(path),path=path)
        old={opened.asset(r) for r in opened.asset_references};self.assertIn(external.read_bytes(),old)
        image.fill(QColor('yellow'));self.assertTrue(image.save(str(external)));self.recover(w)
        opened=s.read_recovery(w.fornax_recovery_path(path),path=path)
        self.assertIn(external.read_bytes(),{opened.asset(r) for r in opened.asset_references})

    def test_external_image_symlink_is_supported_like_regular_save(self):
        w,s,path=self.editor();self.begin_typing(w)
        external=self.root/'linked-image.png';external.symlink_to(self.root/'image.png')
        item=ImageItem(str(external));item.layer_id=80;w.scene.addItem(item);w.refresh_layer_list()
        self.recover(w);opened=s.read_recovery(w.fornax_recovery_path(path),path=path)
        self.assertIn(external.read_bytes(),{opened.asset(r) for r in opened.asset_references})

    def test_failure_preserves_previous_recovery_and_a_retry_succeeds(self):
        w,s,path=self.editor();box=self.begin_typing(w);self.recover(w);recovery=w.fornax_recovery_path(path);old=recovery.read_bytes()
        box.state.html_content='<p>Outra versão</p>';box.apply_state()
        with patch('core.fornax_session.save_public_fornax',side_effect=OSError('Disco indisponível')),patch('builtins.print'):
            self.recover(w)
        self.assertEqual(recovery.read_bytes(),old);self.recover(w)
        opened=s.read_recovery(recovery,path=path);self.assertEqual(opened.document()['pages'][0]['boxes'][0]['html'],box.state.html_content)

    def test_corrupt_recovery_is_not_replaced_without_verifying_previous_package(self):
        w,s,path=self.editor();box=self.begin_typing(w);self.recover(w)
        recovery=w.fornax_recovery_path(path);recovery.write_bytes(b'pacote-corrompido')
        box.state.html_content='<p>Nova versão</p>';box.apply_state()
        with patch('builtins.print'):self.recover(w)
        self.assertEqual(recovery.read_bytes(),b'pacote-corrompido')
        self.assertFalse(list(self.root.glob('*.pending-*')))
        self.assertIs(w.canvas_edit.box,box)

    def test_lost_authorization_cannot_write_another_protected_recovery(self):
        w,s,path=self.editor(FULL_MODE);box=self.begin_typing(w);self.recover(w);recovery=w.fornax_recovery_path(path);old=recovery.read_bytes()
        s.leave_active();box.state.html_content='<p>Sem autorização</p>';box.apply_state()
        with patch('builtins.print'):self.recover(w)
        self.assertEqual(recovery.read_bytes(),old)

    def test_save_as_required_does_not_write_to_original_recovery(self):
        w,s,path=self.editor();self.begin_typing(w);w._fornax_save_as_required=True;self.recover(w)
        self.assertFalse(w.fornax_recovery_path(path).exists())

    def test_protected_recovery_reopens_as_unsaved_editor_document(self):
        from features.editor.editor_window import EditorWindow
        from features.editor.canvas_items import DesignerBox
        w,s,path=self.editor(FULL_MODE);box=self.begin_typing(w);self.recover(w)
        opened=s.read_recovery(w.fornax_recovery_path(path),path=path)
        restored=EditorWindow();self.addCleanup(self.close_editor,restored)
        restored.load_from_fornax(opened.document(),path=path,mode=FULL_MODE,
            model_id=opened.descriptor.model_id,asset_provider=opened.asset,
            session_manager=s,recovered=True)
        self.assertTrue(restored._recovered_unsaved)
        self.assertEqual(next(item for item in restored.scene.items() if isinstance(item,DesignerBox)).state.html_content,box.state.html_content)
        # Avoid the intentional unsaved-recovery question during test cleanup.
        restored._recovered_unsaved=False


class RecoveryWorkTest(RecoveryBehaviorTest):
    def test_repeated_requests_write_only_one_package(self):
        import core.fornax_container as container
        w,s,path=self.editor();self.begin_typing(w)
        with patch.object(container,'_publish_package',wraps=container._publish_package) as publish:
            self.recover(w);self.recover(w);self.recover(w);self.assertEqual(publish.call_count,1)

    def test_external_source_change_cannot_publish_recovery(self):
        w,s,path=self.editor();self.begin_typing(w)
        path.write_bytes(path.read_bytes()+b'external-change')
        with patch('builtins.print'):self.recover(w)
        self.assertFalse(w.fornax_recovery_path(path).exists())
for name in list(RecoveryBehaviorTest.__dict__):
    if name.startswith('test_'):setattr(RecoveryWorkTest,name,None)
