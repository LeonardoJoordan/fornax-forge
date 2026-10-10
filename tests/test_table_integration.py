"""Etapa 06: objetos completos, camadas, grupos e histórico entre páginas."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsItem
from PySide6.QtTest import QTest
from shiboken6 import isValid
import test_table_canvas as canvas
from core.table_model import new_table, cell_at, format_cells, resize_table
from core.model_document import normalize_model_document, add_model_table, add_blank_back_page, adapt_model_page
from core.fornax_container import save_public_fornax, open_public_fornax
from features.editor.table_item import TableItem
from features.editor.canvas_items import DesignerBox
from features.editor.history_capture import history_inputs


class TableIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from core.themes import theme_manager
        canvas.TableCanvasTest.setUpClass.__func__(cls)
        theme_manager().select(os.environ.get('FORNAX_TEST_THEME','dark'))
    setUp = canvas.TableCanvasTest.setUp
    tearDown = canvas.TableCanvasTest.tearDown
    editor = canvas.TableCanvasTest.editor
    type = canvas.TableCanvasTest.type

    @classmethod
    def tearDownClass(cls):
        cls.app.clipboard().clear()
        canvas.TableCanvasTest.tearDownClass.__func__(cls)

    def tables(self, w): return [i for i in w.scene.items() if isinstance(i, TableItem)]
    def doc(self, w): return deepcopy(w._capture_document_history_state()['document'])
    def select_root(self, w, item):
        w.table_edit.finish();w.scene.clearSelection();item.setSelected(True);item.clear_cell_selection()
    def reset(self,w):
        w.history.clear();w._history_capture_cache=None;w.save_snapshot()
    def pixels(self, w):
        from features.generator.renderer import NativeRenderer
        return NativeRenderer(adapt_model_page(self.doc(w),w._active_page_id)).render_preview_image()
    def row(self,w,item):
        return next(w.layer_list.item(i) for i in range(w.layer_list.count())
                    if w.layer_list.item(i).data(Qt.ItemDataRole.UserRole) is item)

    def scene_pixels(self,w):
        w.table_edit.finish();w.scene.clearSelection()
        tables=self.tables(w)
        for item in tables:item.overlays_enabled=False
        rect=w._get_document_rect();image=QImage(int(rect.width()),int(rect.height()),QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white);painter=QPainter(image)
        try:w.scene.render(painter,QRectF(image.rect()),rect)
        finally:
            painter.end()
            for item in tables:item.overlays_enabled=True
        return image

    def test_invalid_duplicate_preserves_active_draft_and_selection(self):
        table=new_table(40,20,width=800,height=800)
        source=add_model_table(add_model_table(normalize_model_document({'canvas_size':{'w':1000,'h':1000}}),table),new_table(40,20,width=800,height=800))
        w,item=self.editor(source);self.type(w,item,text='Ainda digitando')
        temporary=w.table_edit.text;before=self.doc(w);count=len(w.history._undo_stack)
        w.duplicate_selected()
        self.assertIs(w.table_edit.text,temporary);self.assertEqual(w.table_edit.document.toPlainText(),'Ainda digitando')
        self.assertEqual(self.doc(w),before);self.assertEqual(len(w.history._undo_stack),count)
        self.assertTrue(item.isSelected())

    def test_invalid_group_resize_does_not_change_any_member(self):
        w,item=self.editor();w.add_new_box();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        with w._selection_batch():item.setSelected(True);box.setSelected(True)
        before=self.doc(w);count=len(w.history._undo_stack)
        self.assertTrue(w.begin_multi_selection_resize(QPointF(0,0),w._selection_frame.rect()))
        w.update_multi_selection_resize(.001);w.end_multi_selection_resize()
        self.assertEqual(self.doc(w),before);self.assertEqual(len(w.history._undo_stack),count)
        self.assertTrue(w.table_panel.message.text())

    def test_invalid_layer_name_refuses_before_mutating_scene_or_history(self):
        w,item=self.editor();self.select_root(w,item);before=self.doc(w);count=len(w.history._undo_stack)
        with patch('features.editor.editor_window.dialog_get_text',return_value=('x'*129,True)):
            w.rename_layer(self.row(w,item))
        self.assertEqual(self.doc(w),before);self.assertEqual(len(w.history._undo_stack),count)
        self.assertTrue(w.table_panel.message.text())

    def test_mixed_group_duplicate_keeps_order_and_separate_group_identity(self):
        w,item=self.editor();w.add_new_box();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        with w._selection_batch():item.setSelected(True);box.setSelected(True)
        w.group_selected_items();original_id=item.group_id;w.duplicate_selected()
        copied=set(w.scene.selectedItems());self.assertEqual(len(copied),2)
        self.assertTrue(copied.isdisjoint({item,box}))
        ids={i.group_id for i in copied};self.assertEqual(len(ids),1);self.assertNotIn(original_id,ids)
        table=next(i for i in copied if isinstance(i,TableItem));text=next(i for i in copied if isinstance(i,DesignerBox))
        self.assertEqual(table.zValue()<text.zValue(),item.zValue()<box.zValue())
        final=self.doc(w);w.undo();w.redo();self.assertEqual(self.doc(w),final)

    def test_duplicate_whole_object_renews_every_identity_and_is_independent(self):
        w,item=self.editor();self.select_root(w,item);before=self.doc(w);self.reset(w)
        w.duplicate_selected()
        self.assertEqual(len(self.tables(w)),2)
        other=next(i for i in self.tables(w) if i is not item)
        self.assertNotEqual(other.data['object_id'],item.data['object_id'])
        self.assertTrue({c['id'] for c in item.data['cells']}.isdisjoint(c['id'] for c in other.data['cells']))
        self.assertNotEqual(other.layer_id,item.layer_id);self.assertNotEqual(other.custom_name,item.custom_name)
        other.data['cells'][0]['style']['font_color']='#123456'
        self.assertNotEqual(other.data['cells'][0]['style'],item.data['cells'][0]['style'])
        w.undo();w.undo();self.assertEqual(self.doc(w),before)

    def test_duplicate_with_cell_selection_still_duplicates_object_not_interval(self):
        w,item=self.editor();item.select_cell(1,1);w.btn_dup_layer.click()
        self.assertEqual(len(self.tables(w)),2)
        item=w.table_controller.selected();item.select_cell(1,1);w.view.setFocus()
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_D,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.tables(w)),3)

    def test_whole_copy_paste_and_range_copy_remain_distinct(self):
        w,item=self.editor();self.select_root(w,item);w.copy_selected_items()
        self.assertEqual(w._object_clipboard[0][0],'table')
        w.paste_copied_items();self.assertEqual(len(self.tables(w)),2)
        other=w.table_controller.selected();other.select_cell(0,0)
        clipboard=deepcopy(w._object_clipboard);w.copy_selected_items()
        self.assertEqual(w._object_clipboard,clipboard)
        self.assertTrue(QApplication.clipboard().mimeData().hasFormat('application/x-fornax-table-range+json'))

    def test_copy_across_pages_promotes_target_and_preserves_source(self):
        w,item=self.editor(add_blank_back_page(canvas.sample()));self.select_root(w,item)
        original=deepcopy(self.doc(w)['pages'][0]['tables']);w.copy_selected_items()
        w.switch_model_page('back');w.paste_copied_items()
        result=self.doc(w);self.assertEqual(result['schema_version'],6)
        self.assertEqual(result['pages'][0]['tables'],original)
        self.assertEqual(len(result['pages'][1]['tables']),1)
        self.assertNotEqual(result['pages'][1]['tables'][0]['object_id'],original[0]['object_id'])

    def test_duplicate_limit_refuses_atomically(self):
        table=new_table(40,20,width=800,height=800)
        source=add_model_table(add_model_table(normalize_model_document({'canvas_size':{'w':1000,'h':1000}}),table),new_table(40,20,width=800,height=800))
        w,item=self.editor(source);self.select_root(w,item);self.reset(w)
        before=self.doc(w);index=w.history._current_index
        w.duplicate_selected()
        self.assertEqual(self.doc(w),before);self.assertEqual(w.history._current_index,index)
        self.assertEqual(len(self.tables(w)),2);self.assertTrue(w.table_panel.message.text())

    def test_rename_visibility_and_lock_layer_controls_roundtrip(self):
        w,item=self.editor();self.select_root(w,item);self.reset(w);initial=self.doc(w)
        with patch('features.editor.editor_window.dialog_get_text',return_value=('Notas',True)):
            w.rename_layer(self.row(w,item))
        self.assertEqual(item.custom_name,'Notas')
        row=self.row(w,item);widget=w.layer_list.itemWidget(row)
        _,eye,_,lock,_=widget._layer_controls
        eye.click();self.assertFalse(item.isVisible())
        lock.click();self.assertFalse(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.assertEqual(item.acceptedMouseButtons(),Qt.MouseButton.NoButton)
        final=self.doc(w)
        for _ in range(3):w.undo()
        self.assertEqual(self.doc(w),initial)
        for _ in range(3):w.redo()
        self.assertEqual(self.doc(w),final)

    def test_delete_object_and_delete_cells_differ_and_undo_restores(self):
        w,item=self.editor();self.select_root(w,item);self.reset(w);initial=self.doc(w)
        item.select_cell(0,0);w.delete_selected_items();self.assertEqual(len(self.tables(w)),1)
        w.undo();item=self.tables(w)[0];self.select_root(w,item)
        w.delete_selected_items();self.assertEqual(self.tables(w),[])
        w.undo();self.assertEqual(self.doc(w),initial)

    def test_mixed_group_expands_selection_but_layer_partial_selection_is_preserved(self):
        w,item=self.editor();w.add_new_box();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        with w._selection_batch():item.setSelected(True);box.setSelected(True)
        self.assertTrue(w.group_selected_items());self.assertEqual(item.group_id,box.group_id)
        with w._selection_batch():w.scene.clearSelection();item.setSelected(True)
        self.assertEqual(set(w.scene.selectedItems()),{item,box})
        with patch.object(w,'_selecting_from_layer_list',True):
            with w._selection_batch():w.scene.clearSelection();item.setSelected(True)
        self.assertEqual(w.scene.selectedItems(),[item])
        self.assertTrue(w.ungroup_selected_items());self.assertIsNone(item.group_id);self.assertIsNone(box.group_id)

    def test_multi_selection_transforms_include_table_and_resize_tracks(self):
        w,item=self.editor();w.add_new_box();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        with w._selection_batch():item.setSelected(True);box.setSelected(True)
        self.assertEqual(set(w._get_selected_items()),{item,box})
        w.update_opacity(.4);w.update_rotation(12)
        self.assertEqual(item.opacity(),.4);self.assertEqual(item.rotation(),12)
        widths=list(item.data['column_widths']);heights=list(item.data['row_heights'])
        self.type(w,item,text='Texto antes do gesto')
        self.assertTrue(w.begin_multi_selection_resize(QPointF(0,0),w._selection_frame.rect()))
        self.assertIsNone(w.table_edit.item)
        w.update_multi_selection_resize(1.5);w.end_multi_selection_resize()
        self.assertIn('Texto antes do gesto',cell_at(item.data,1,1)['html'])
        self.assertEqual(item.data['column_widths'],[v*1.5 for v in widths])
        self.assertEqual(item.data['row_heights'],[v*1.5 for v in heights])

    def test_table_geometry_panel_keeps_center_and_rejects_invalid_size(self):
        w,item=self.editor();self.select_root(w,item);center=item.mapToScene(item.rect().center())
        before_w=item.rect().width();w.update_width(before_w*1.2*25.4/300)
        self.assertAlmostEqual(item.rect().width(),before_w*1.2)
        self.assertEqual(item.mapToScene(item.rect().center()),center)
        before=deepcopy(item.data)
        w.update_width(.001)
        self.assertEqual(item.data,before);self.assertTrue(w.table_panel.message.text())

    def test_layer_order_includes_table_without_recreating_roots(self):
        w,item=self.editor();w.add_new_box();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        rows=[w.layer_list.item(i) for i in range(w.layer_list.count())]
        table_row=self.row(w,item);w._order_layer_rows([table_row]+[r for r in rows if r is not table_row])
        w._on_layer_reordered(None,0,0,None,0)
        self.assertGreater(item.zValue(),box.zValue());self.assertIn(item,self.tables(w))
        order=self.doc(w)['pages'][0]['layer_order'];self.assertEqual(order[-1],item.data['object_id'])

    def test_capture_reads_data_directly_and_skips_only_unchanged_snapshots(self):
        w,item=self.editor();self.reset(w)
        self.assertIsNotNone(history_inputs(w))
        with patch.object(w,'_capture_document_history_state',wraps=w._capture_document_history_state) as capture:
            w.save_snapshot();self.assertEqual(capture.call_count,0)
            item.data['cells'][0]['html']='<p>Mutação direta</p>';w.save_snapshot()
            self.assertGreater(capture.call_count,0)
        self.assertIn('Mutação direta',self.doc(w)['pages'][0]['tables'][0]['cells'][0]['html'])
        item.unrecognized_persistent_option=123
        self.assertIsNone(history_inputs(w))

    def test_active_cell_and_inactive_page_changes_cannot_be_skipped(self):
        w,item=self.editor(add_blank_back_page(canvas.sample()));self.reset(w)
        self.type(w,item,text='Rascunho aceito');w.save_snapshot()
        self.assertIn('Rascunho aceito',cell_at(self.doc(w)['pages'][0]['tables'][0],1,1)['html'])
        old=w.history._current_index;w._model_document['pages'][1]['tables']=[]
        w._model_document['pages'][1]['guidelines_locked']=False;w.save_snapshot()
        self.assertGreater(w.history._current_index,old)

    def test_retained_page_accounts_for_documents_and_cleans_temporary_editor(self):
        w,item=self.editor(add_blank_back_page(canvas.sample()));temporary=self.type(w,item,text='Persistido')
        w.switch_model_page('back');retained=w._inactive_page_scene
        self.assertIsNotNone(retained);self.assertGreaterEqual(retained.estimated_bytes,len(item.layout.cells)*16384)
        self.assertIsNone(w.table_edit.item)
        self.assertFalse(any(isinstance(i,canvas.CellTextItem) for i in retained.scene.items()))
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.assertFalse(isValid(temporary))
        w.switch_model_page('front');self.assertIn('Persistido',cell_at(self.doc(w)['pages'][0]['tables'][0],1,1)['html'])
        self.assertIs(w.table_controller.window.scene,w.scene)

    def test_budget_forces_reload_and_never_restores_stale_table_cache(self):
        w,item=self.editor(add_blank_back_page(canvas.sample()));w._page_scene_budget=1
        w.switch_model_page('back');self.assertIsNone(w._inactive_page_scene)
        w._model_document['pages'][0]['tables'][0]['cells'][0]['html']='<p>Nova versão</p>'
        w.switch_model_page('front');self.assertIn('Nova versão',self.tables(w)[0].layout.cells[0].document.toPlainText())

    def test_combined_edit_format_merge_column_duplicate_page_save_and_history(self):
        w,item=self.editor(add_blank_back_page(canvas.sample()));self.reset(w);initial=self.doc(w)
        self.type(w,item,text='Nota final');w.table_edit.finish()
        item.select_cell(1,0);item.select_cell(1,1,extend=True)
        w.table_controller.format_text('bold',True);w.table_controller.structure('merge')
        w.table_controller.structure('column_after');w.duplicate_selected()
        self.assertEqual(len(self.tables(w)),2);w.switch_model_page('back')
        final=self.doc(w);path=self.root/'synthetic.fornax';save_public_fornax(final,path)
        loaded=open_public_fornax(path).document();self.assertEqual(loaded,final)
        count=w.history._current_index
        for _ in range(count):w.undo()
        self.assertEqual(self.doc(w),initial)
        for _ in range(count):w.redo()
        self.assertEqual(self.doc(w),final)
        w.switch_model_page('front');expected=self.pixels(w)
        self.assertEqual(self.scene_pixels(w),expected)
        state=w.get_current_scene_state();w.apply_scene_state(state)
        self.assertEqual(self.pixels(w),expected)
        self.assertEqual(self.scene_pixels(w),expected)
