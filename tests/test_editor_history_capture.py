"""Captura: mutações síncronas, passos completos e retorno sem alterações."""
from copy import deepcopy
import json,os,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QGraphicsItem
from features.editor.canvas_items import DesignerBox,ImageItem,SignatureItem,RectangleItem,Guideline
from features.editor.organogram_editor import BoardConnectorItem
from core.history_manager import HistoryManager
from copy_cases import canonical_copy_document
from paint_cases import settle,screen_image,image_hash
import test_editor_performance_contracts as contracts

class HistoryBehaviorTest(unittest.TestCase):
    setUpClass=classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp=contracts.PerformanceContractsTest.setUp
    def editor(self,fixture='simple',size=20):
        w=contracts.PerformanceContractsTest.editor(self,fixture,size)
        w.resize(1280,800);w.show();settle(self.app)
        return w

    def reset(self,w):
        w.history.clear();w.save_snapshot();settle(self.app)
        return deepcopy(w.history._undo_stack[0]['document'])

    def record(self,w,key):
        settle(self.app)
        result={'document':canonical_copy_document(w._document_with_active_page()),
                'history':[canonical_copy_document(state) for state in w.history._undo_stack],
                'index':w.history._current_index,'sizes':w.history._state_sizes,
                'buttons':[w.btn_undo.isEnabled(),w.btn_redo.isEnabled()],
                'pixels':image_hash(screen_image(w,workspace=True))}
        if path:=os.environ.get('FORNAX_HISTORY_EVIDENCE'):
            p=Path(path);values=json.loads(p.read_text()) if p.exists() else {};values[key]=result;p.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n')
        return result

    def test_unchanged_selection_zoom_and_pan_keep_redo(self):
        w=self.editor('mixed',60);w.resize(1280,800);w.show();self.reset(w)
        box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        box.moveBy(60,0);w.save_snapshot();w.undo();before=deepcopy(w.history._undo_stack)
        w.scene.clearSelection();w.view.scale(1.1,1.1);w.view.centerOn(QPointF(300,400));w.save_snapshot();w.save_snapshot()
        self.assertEqual(w.history._undo_stack,before);self.assertEqual(w.history._current_index,0);self.assertTrue(w.history.can_redo());self.record(w,'unchanged-after-undo')

    def test_round_trip_motion_has_no_step(self):
        w=self.editor('mixed',60);self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox));origin=box.pos()
        box.moveBy(60,0);box.setPos(origin);w.save_snapshot();self.assertEqual(len(w.history._undo_stack),1)

    def test_plain_python_and_native_item_mutations_are_captured_immediately(self):
        mutations=(('name',lambda i:setattr(i,'custom_name','Renomeado')),('position',lambda i:i.moveBy(60,0)),
          ('rotation',lambda i:i.setRotation(19)),('opacity',lambda i:i.setOpacity(.4)),('visibility',lambda i:i.setVisible(False)),
          ('lock',lambda i:i.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,True)),('group',lambda i:setattr(i,'group_id',27)),
          ('layer',lambda i:i.setZValue(222)),('proportion',lambda i:setattr(i,'keep_proportion',False)),
          ('html',lambda i:setattr(i.state,'html_content','<p><b>{Novo}</b></p>')),('font',lambda i:setattr(i.state,'font_size',37)),
          ('align',lambda i:setattr(i.state,'vertical_align','bottom')),('link',lambda i:setattr(i.state,'link_key','destino')))
        for name,change in mutations:
            with self.subTest(name=name):
                w=self.editor('mixed',20);before=self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==1)
                change(box);w.save_snapshot();self.assertEqual(w.history._current_index,1)
                after=deepcopy(w.history._undo_stack[-1]['document']);self.assertNotEqual(before,after)
                w.undo();self.assertEqual(w.history._undo_stack[w.history._current_index]['document'],before)
                w.redo();self.assertEqual(w.history._undo_stack[w.history._current_index]['document'],after)

    def test_native_text_document_change_without_event_loop_is_not_skipped(self):
        w=self.editor('simple',20);self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        cursor=QTextCursor(box.text_item.document());cursor.insertText('Novo identificador ');w.save_snapshot()
        self.assertEqual(w.history._current_index,1)

    def test_image_signature_shape_and_guide_fields(self):
        w=self.editor('mixed',60);self.reset(w)
        mutations=[lambda:setattr(next(i for i in w.scene.items() if type(i) is ImageItem),'link_key','Novo link'),
          lambda:setattr(next(i for i in w.scene.items() if isinstance(i,SignatureItem)),'signature_id','signature-renamed'),
          lambda:setattr(next(i for i in w.scene.items() if isinstance(i,RectangleItem)),'outline_width',13),
          lambda:next(i for i in w.scene.items() if isinstance(i,Guideline)).moveBy(30,30)]
        for index,change in enumerate(mutations):
            change();w.save_snapshot();self.assertEqual(w.history._current_index,index+1)

    def test_global_controls_and_inactive_page_change(self):
        w=self.editor('duplex',60);self.reset(w)
        w._model_document['pages'][1]['boxes'][0]['html']='<p>Verso alterado</p>';w.save_snapshot();self.assertEqual(w.history._current_index,1)
        w.btn_toggle_guides.click();self.assertEqual(w.history._current_index,2)
        w.btn_lock_guides.click();self.assertEqual(w.history._current_index,3)
        self.record(w,'global-page-changes')

    def test_board_data_style_ports_and_relations_without_waiting_for_signals(self):
        w=self.editor('connected',10);w.switch_model_page('organogram');self.reset(w)
        group=w._board_items()[0];group.data['name']='Nome direto';w.save_snapshot();self.assertEqual(w.history._current_index,1)
        group.data.setdefault('border',{})['cards']=True;w.save_snapshot();self.assertEqual(w.history._current_index,2)
        edge=next(i for i in w.scene.items() if isinstance(i,BoardConnectorItem));edge.board_edge['style']={'color':'#13579b'};w.save_snapshot();self.assertEqual(w.history._current_index,3)
        w._board_connector_style['opacity']=.3;w.save_snapshot();self.assertEqual(w.history._current_index,4)
        self.record(w,'board-direct-changes')

    def test_pending_numeric_undo_and_new_edit_before_redo(self):
        w=self.editor('mixed',60);self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==6);box.setSelected(True)
        original=box.rect().width();w.caixa_texto_panel.spin_w.setValue(40);changed=box.rect().width();self.assertNotEqual(original,changed)
        w.undo();self.assertEqual(w.history._current_index,0);w.redo();self.assertEqual(w.history._current_index,1)
        w.undo();box=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==6);box.setSelected(True);w.caixa_texto_panel.spin_w.setValue(60)
        w.redo();self.assertFalse(w.history.can_redo());self.assertEqual(len(w.history._undo_stack),2);self.record(w,'numeric-branch')

    def test_text_edit_checkpoint_and_new_branch(self):
        w=self.editor('simple',20);self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox));w.canvas_edit.begin(box)
        cursor=box.text_item.textCursor();cursor.insertText('Texto novo ');w.canvas_edit.checkpoint();self.assertEqual(w.history._current_index,1)
        w.canvas_edit.finish();w.save_snapshot();self.assertEqual(w.history._current_index,1)
        w.undo();w.add_new_box();self.assertFalse(w.history.can_redo())

    def test_page_navigation_no_steps_and_new_structure_is_undoable(self):
        w=self.editor('duplex',20);self.reset(w);w.switch_model_page('back');w.switch_model_page('front');self.assertEqual(w.history._current_index,0)
        with patch('features.editor.document_session.QMessageBox.question',return_value=__import__('PySide6.QtWidgets',fromlist=['QMessageBox']).QMessageBox.StandardButton.Yes):w.remove_model_page('back')
        self.assertEqual(w.history._current_index,1);w.undo();self.assertEqual(len(w._model_document['pages']),2);w.redo();self.assertEqual(len(w._model_document['pages']),1)

    def test_unknown_text_subclass_uses_the_full_capture(self):
        class ExtendedText(DesignerBox):pass
        w=self.editor('simple',1);item=ExtendedText(text='Inicial');item.layer_id=99;w.scene.addItem(item);self.reset(w)
        with patch.object(w,'_capture_document_history_state',wraps=w._capture_document_history_state) as capture:w.save_snapshot();self.assertGreater(capture.call_count,0)
        item.state.html_content='Alterado';w.save_snapshot();self.assertEqual(w.history._current_index,1)

    def test_mask_edit_is_deferred_until_confirmed(self):
        w=self.editor('mixed',60);self.reset(w)
        shape=next(i for i in w.scene.items() if isinstance(i,RectangleItem) and i.masked_images())
        image=shape.masked_images()[0];self.assertTrue(w.begin_mask_edit(image));image.moveBy(12,5);w.save_snapshot()
        self.assertEqual(w.history._current_index,0);w.finish_mask_edit(True);self.assertEqual(w.history._current_index,1)
        w.undo();w.redo();self.assertEqual(w.history._current_index,1)

    def test_close_still_prompts_for_uncommitted_changes(self):
        w=self.editor('duplex',20);self.reset(w)
        w._last_saved_state=w.get_current_scene_state();w._last_saved_document_state=w._capture_document_history_state()
        box=next(i for i in w.scene.items() if isinstance(i,DesignerBox));box.state.html_content='Não salvo'
        with patch('features.editor.editor_window.QMessageBox.exec',return_value=0) as prompt:
            w.close();self.assertEqual(prompt.call_count,1);self.assertTrue(w.isVisible())

    def test_asset_path_rewrite_and_reload_do_not_reuse_old_capture(self):
        w=self.editor('mixed',60);self.reset(w)
        w._apply_saved_asset_paths({'asset:photo.png':'asset:signature.png'})
        w.save_snapshot();self.assertEqual(w.history._current_index,1)
        self.assertNotIn('asset:photo.png',[i.get('path') for i in w._model_document['pages'][0]['images']])
        document=w._document_with_active_page();w._load_document_into_scene(document);w.save_snapshot()
        self.assertEqual(w.history._current_index,0)

    def test_history_limits_and_json_equivalence(self):
        h=HistoryManager(max_steps=3,max_bytes=80)
        h.push({'value':'ação'});h.push({'value':'ação'});self.assertEqual(len(h._undo_stack),1)
        for n in range(5):h.push({'value':n})
        self.assertLessEqual(len(h._undo_stack),3);self.assertEqual(h._state_sizes,[len(json.dumps(s,sort_keys=True,ensure_ascii=False).encode()) for s in h._undo_stack])
        h.undo();old=len(h._undo_stack);h.push(deepcopy(h._undo_stack[h._current_index]));self.assertEqual(len(h._undo_stack),old);self.assertTrue(h.can_redo())
        h.push({'value':1.0});self.assertFalse(h.can_redo());h.clear();self.assertEqual(h._current_index,-1)

class HistoryWorkTest(HistoryBehaviorTest):
    def test_repeated_unchanged_snapshot_avoids_full_capture(self):
        w=self.editor('mixed',60);self.reset(w)
        with patch.object(w,'_capture_document_history_state',wraps=w._capture_document_history_state) as capture:
            w.save_snapshot();w.save_snapshot();self.assertEqual(capture.call_count,0)
    def test_unchanged_after_restore_avoids_full_capture(self):
        w=self.editor('simple',20);self.reset(w);box=next(i for i in w.scene.items() if isinstance(i,DesignerBox));box.moveBy(60,0);w.save_snapshot();w.undo()
        with patch.object(w,'_capture_document_history_state',wraps=w._capture_document_history_state) as capture:w.save_snapshot();self.assertEqual(capture.call_count,0)
for name in list(HistoryBehaviorTest.__dict__):
    if name.startswith('test_'):setattr(HistoryWorkTest,name,None)
