"""Tabelas em recuperação assíncrona: fixtures sintéticas, sem dados em logs."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import zipfile
from PySide6.QtCore import QCoreApplication, QEvent
from shiboken6 import isValid
import test_table_canvas as canvas
import test_editor_autosave as autosave
import test_editor_recovery_concurrency as races
from core.table_model import new_table, set_cell_html, cell_at
from core.model_document import add_model_table, normalize_model_document
from core.fornax_container import PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE, FornaxFormatError, unlock_fornax
from features.editor.table_item import TableItem
from features.editor.recovery_worker import _LIVE_WORKERS


class TableRecoveryProductTest(unittest.TestCase):
    setUpClass=classmethod(canvas.TableCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp=canvas.TableCanvasTest.setUp
    type=canvas.TableCanvasTest.type
    wait_recovery=autosave.EditorAutosaveTest.wait_recovery
    staged=races.RecoveryConcurrencyTest.staged
    wait_stage=races.RecoveryConcurrencyTest.wait_stage
    assert_clean=races.RecoveryConcurrencyTest.assert_clean

    def close_editor(self,w):
        if isValid(w):autosave.EditorAutosaveTest.close_editor(self,w)

    def tearDown(self):
        for window in self.windows:
            if isValid(window):
                window._recovered_unsaved=False
                self.close_editor(window)
                if isValid(window):window.deleteLater()
        self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(self.errors,[]);self.assertFalse(_LIVE_WORKERS)

    def editor(self,mode=PUBLIC_MODE):
        table=set_cell_html(new_table(2,2,width=600,height=300),0,0,'<p><b>{nota}</b></p>')
        table.update(x=100,y=100)
        def with_table(raw):return add_model_table(normalize_model_document(raw),table)
        with patch.object(autosave,'normalize_model_document',side_effect=with_table):
            w,s,path=autosave.EditorAutosaveTest.editor(self,mode)
        self.windows.append(w);w._autosave_timer.stop()
        item=next(i for i in w.scene.items() if isinstance(i,TableItem))
        self.type(w,item,anchor=(1,1),text='Conteúdo sintético em edição')
        return w,s,path,item

    def recover(self,w):w._write_fornax_recovery();self.wait_recovery(w)

    def test_live_cell_recovery_is_independent_in_all_protection_modes(self):
        for mode in (PUBLIC_MODE,SIGNATURES_MODE,FULL_MODE):
            with self.subTest(mode=mode):
                w,s,path,item=self.editor(mode);original=path.read_bytes()
                saved=deepcopy(w._last_saved_document_state);history=deepcopy(w.history._undo_stack)
                self.recover(w)
                recovered=s.read_recovery(w.fornax_recovery_path(path),path=path).document()
                self.assertTrue(recovered['pages'][0]['tables'][0]==item.to_data())
                self.assertTrue(path.read_bytes()==original)
                self.assertTrue(w._last_saved_document_state==saved);self.assertTrue(w.history._undo_stack==history)
                self.assertIs(w.table_edit.item,item);self.assert_clean(w)
                if mode==FULL_MODE:
                    with zipfile.ZipFile(w.fornax_recovery_path(path)) as archive:
                        self.assertEqual(set(archive.namelist()),{'manifest.json','protected.bin'})

    def test_close_cancels_pending_table_recovery_and_clears_snapshot(self):
        for mode in (PUBLIC_MODE,FULL_MODE):
            with self.subTest(mode=mode):
                w,s,path,item=self.editor(mode);original=path.read_bytes()
                with self.staged() as (reached,release):
                    w._write_fornax_recovery();self.wait_stage(reached);task=w._recovery_task
                    w.table_edit.finish();w._last_saved_state=w.get_current_scene_state()
                    w._last_saved_document_state=w._capture_document_history_state();w.close()
                    release.set();self.wait_recovery(w)
                self.assertFalse(w.fornax_recovery_path(path).exists())
                self.assertTrue(path.read_bytes()==original);self.assertEqual(task.document,{})
                self.assertEqual(task.assets,{});self.assert_clean(w)

    def test_manual_save_cancels_old_recovery_but_preserves_active_text(self):
        w,s,path,item=self.editor(FULL_MODE)
        expected=item.to_data()
        with self.staged() as (reached,release):
            w._write_fornax_recovery();self.wait_stage(reached)
            with patch.object(w,'_show_save_success_dialog'):w.export_to_json(skip_close_dialog=True)
            saved=path.read_bytes();release.set();self.wait_recovery(w)
        self.assertTrue(path.read_bytes()==saved)
        self.assertTrue(s.document()['pages'][0]['tables'][0]==expected)
        self.assertFalse(w.fornax_recovery_path(path).exists());self.assert_clean(w)

    def test_external_source_change_preserved_before_publication(self):
        w,s,path,item=self.editor(FULL_MODE)
        with self.staged() as (reached,release),patch('builtins.print'):
            w._write_fornax_recovery();self.wait_stage(reached)
            changed=path.read_bytes()+b'synthetic-external-change';path.write_bytes(changed)
            release.set();self.wait_recovery(w)
        self.assertTrue(path.read_bytes()==changed)
        self.assertFalse(w.fornax_recovery_path(path).exists());self.assert_clean(w)

    def test_expiry_removes_key_and_unpublished_table_snapshot(self):
        w,s,path,item=self.editor(FULL_MODE);original=path.read_bytes()
        with self.staged() as (reached,release):
            w._write_fornax_recovery();self.wait_stage(reached);task=w._recovery_task
            staged=list(self.root.glob('*.pending-*'));self.assertEqual(len(staged),1)
            with zipfile.ZipFile(staged[0]) as archive:self.assertEqual(set(archive.namelist()),{'manifest.json','protected.bin'})
            s.leave_active();s._clock=lambda:float('inf');s.expire_due()
            self.assertIsNone(task.authorization._key)
            release.set();self.wait_recovery(w)
        self.assertTrue(path.read_bytes()==original)
        self.assertFalse(w.fornax_recovery_path(path).exists())
        self.assertEqual(task.document,{});self.assertEqual(task.assets,{});self.assert_clean(w)

    def test_new_draft_replaces_stale_snapshot_without_ending_cell_edit(self):
        w,s,path,item=self.editor();temporary=w.table_edit.text
        with self.staged() as (reached,release):
            w._write_fornax_recovery();self.wait_stage(reached);first=w._recovery_task
            cursor=temporary.textCursor();cursor.insertText(' Atualização');temporary.setTextCursor(cursor)
            self.app.processEvents();latest=deepcopy(item.to_data())
            release.set();self.wait_recovery(w)
        self.assertTrue(s.read_recovery(w.fornax_recovery_path(path),path=path).document()['pages'][0]['tables'][0]==latest)
        self.assertIs(w.table_edit.text,temporary);self.assertEqual(first.document,{})
        self.assert_clean(w)

    def test_failed_publication_preserves_previous_recovery_then_retries(self):
        import core.fornax_container as container
        w,s,path,item=self.editor();self.recover(w);recovery=w.fornax_recovery_path(path);old=recovery.read_bytes()
        cursor=w.table_edit.text.textCursor();cursor.insertText(' Novo');w.table_edit.text.setTextCursor(cursor)
        replace=container.os.replace
        def deny(source,target):
            if target==recovery:raise PermissionError('Falha sintética de publicação')
            return replace(source,target)
        with patch.object(container.os,'replace',side_effect=deny),patch('builtins.print'):self.recover(w)
        self.assertTrue(recovery.read_bytes()==old);self.assert_clean(w)
        self.recover(w)
        self.assertTrue(s.read_recovery(recovery,path=path).document()['pages'][0]['tables'][0]==item.to_data())
        self.assert_clean(w)

    def test_authorized_job_keeps_independent_tables_after_session_expiry(self):
        from features.generator.renderer import renderers_for_document
        from features.generator.workers import DirectRenderWorker
        w,s,path,item=self.editor(FULL_MODE)
        job=s.borrow_job()
        try:
            expected=job.document();copy=job.document()
            copy['pages'][0]['tables'][0]['cells'][0]['html']='Alteração na cópia'
            self.assertTrue(job.document()==expected)
            s.leave_active();s._clock=lambda:float('inf');s.expire_due()
            renderers=renderers_for_document(job.document(),asset_provider=job.asset)
            out=self.root/'job';out.mkdir()
            task=(0,0,0,{'nota':'9'},{'nota':'9'},'sintetico')
            worker=DirectRenderWorker([task],renderers,out,'PNG',secure_output=True)
            errors=[];worker.error_occurred.connect(lambda *_:errors.append(True))
            worker.start();self.assertTrue(worker.wait(30000));self.app.processEvents()
            self.assertFalse(errors);self.assertEqual(len(list(out.glob('*.png'))),1)
            self.assertTrue(job.document()==expected)
        finally:job.close()
        self.assertEqual(job._document,{});self.assertEqual(dict(job._assets),{})
        with self.assertRaises(FornaxFormatError):job.document()

    def test_protected_transport_import_preserves_table_with_new_identity(self):
        from core.fornax_export import export_models,ExportRequest
        from core.fornax_import import open_import_package,import_candidate
        w,s,path,item=self.editor(FULL_MODE)
        expected=s.document();original=path.read_bytes();shared=self.root/'transport.fornax'
        export_models([ExportRequest(path,'Sintético',local_password='senha-de-teste')],shared,
                      include_signatures=True,transport_password='transporte-sintetico')
        with zipfile.ZipFile(shared) as archive:self.assertEqual(set(archive.namelist()),{'manifest.json','protected.bin'})
        target=self.root/'imported.fornax'
        with open_import_package(shared) as candidates:
            status=import_candidate(candidates[0],target,include_signatures=True,target_mode=FULL_MODE,
                                    transport_password='transporte-sintetico',local_password='nova-local-sintetica')
        self.assertEqual(status.mode,FULL_MODE)
        self.assertNotEqual(status.model_id,s.status(path).descriptor.model_id)
        reopened=unlock_fornax(status,'nova-local-sintetica').document()
        self.assertTrue(reopened['pages'][0]['tables']==expected['pages'][0]['tables'])
        self.assertEqual(reopened['schema_version'],6)
        self.assertEqual(len(reopened['pages'][0]['signatures']),len(expected['pages'][0]['signatures']))
        self.assertTrue(path.read_bytes()==original)


if __name__=='__main__':unittest.main()
