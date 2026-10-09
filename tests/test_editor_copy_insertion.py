"""Cópias: conteúdo, máscaras, identidade, páginas, assets e história."""
import json
import os
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent, QRectF, QSignalBlocker
from PySide6.QtGui import QImage, QPainter
from shiboken6 import isValid
from features.editor.canvas_items import DesignerBox, ImageItem, RectangleItem, SignatureItem
from features.editor.organogram_editor import BoardGroupItem, BoardConnectorItem
from core.model_document import persistent_model_document
import test_editor_performance_contracts as contracts
from copy_cases import prepare_copy, perform_copy, verify_copy, canonical_copy_document


class CopyBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def document(self, w):
        return canonical_copy_document(persistent_model_document(w._document_with_active_page()))

    def settle(self):
        for _ in range(4):
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def record(self, w, key):
        self.settle()
        def identity(i):
            if isinstance(i, BoardGroupItem): return 'block:'+i.data['id']
            if isinstance(i, BoardConnectorItem): return 'edge:'+i.board_edge['source']+':'+i.board_edge['target']
            return type(i).__name__+':'+str(getattr(i,'layer_id',None))
        selected=sorted(identity(i) for i in w.scene.selectedItems())
        image=QImage(900,700,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try: w.scene.render(painter,QRectF(0,0,900,700),w._get_document_rect())
        finally: painter.end()
        state={'document':self.document(w), 'selected':selected,
               'pixels_sha256':sha256(bytes(image.constBits())).hexdigest(),
               'history_index':w.history._current_index,
               'clipboard':w._object_clipboard, 'source_page':w._clipboard_source_page,
               'board_clipboard':getattr(w,'_board_clipboard',None)}
        if output:=os.environ.get('FORNAX_COPY_EVIDENCE'):
            path=Path(output);values=json.loads(path.read_text()) if path.exists() else {}
            values[key]=state;path.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n')
            image.save(str(path.with_name(path.stem+'-'+key+'.png')))
        return state

    def operation(self, w, operation, key):
        count=prepare_copy(w,operation);w.save_snapshot()
        before=self.document(w);history=w.history._current_index
        clipboard=deepcopy(w._object_clipboard);board_clip=deepcopy(getattr(w,'_board_clipboard',None))
        perform_copy(w,operation);after=self.document(w)
        for original,current in zip(before['pages'],after['pages']):
            self.assertEqual(original.get('guidelines'),current.get('guidelines'))
        verify_copy(w,operation,before,after,count,history)
        self.assertEqual(w._object_clipboard,clipboard)
        self.assertEqual(getattr(w,'_board_clipboard',None),board_clip)
        self.record(w,key)
        if operation.startswith('copy_paste_'):
            self.assertEqual(len(w.scene.selectedItems()),count)
        w.undo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(before,history=True))
        w.redo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(after,history=True))
        self.record(w,key+'-redo')
        return before,after

    def test_paste_counts_content_names_and_selection(self):
        for count in (1,10,50):
            w=self.editor('simple',20)
            before,after=self.operation(w,f'copy_paste_{count}',f'paste-{count}')
            original={e['object_id']:e for e in before['pages'][0]['boxes']}
            copied=[e for e in after['pages'][0]['boxes'] if e['object_id'] not in original]
            self.assertEqual(len(copied),count)
            self.assertEqual(len({e['layer_id'] for e in after['pages'][0]['boxes']}),20+count)
            self.assertEqual(len({e['custom_name'].casefold() for e in after['pages'][0]['boxes']}),20+count)
            for _kind,entry in w._object_clipboard:
                found=next(e for e in copied if e['custom_name']==entry['custom_name'])
                for k in ('html','w','h','font_family','rotation','keep_proportion','has_link','link_key'):
                    self.assertEqual(found[k],entry[k])
                self.assertEqual((found['x'],found['y']),(entry['x']+12,entry['y']+12))

    def test_cross_page_paste_preserves_front_and_original_position(self):
        w=self.editor('duplex',60)
        before,after=self.operation(w,'copy_cross','cross-page')
        self.assertEqual(before['pages'][0],after['pages'][0])
        entry=w._object_clipboard[0][1]
        new=next(e for e in after['pages'][1]['boxes'] if e['custom_name']==entry['custom_name']+' 2')
        self.assertEqual((new['x'],new['y']),(entry['x'],entry['y']))

    def test_duplicate_mask_restores_children_and_keeps_clipboard(self):
        w=self.editor('mixed',60)
        before,after=self.operation(w,'copy_duplicate_mask','duplicate-mask')
        oldids={e['object_id'] for e in before['pages'][0]['shapes']}
        shape=next(e for e in after['pages'][0]['shapes'] if e['object_id'] not in oldids)
        children=[e for e in after['pages'][0]['images'] if e['mask_shape_id']==shape['object_id']]
        self.assertEqual(len(children),1)
        self.assertEqual((children[0]['x'],children[0]['y']),(0,0))
        self.assertTrue(any(isinstance(i,RectangleItem) and i.layer_id==shape['layer_id'] and i.masked_images() for i in w.scene.items()))

    def test_duplicate_group_gets_new_groups_masks_signatures_and_names(self):
        w=self.editor('mixed',60)
        before,after=self.operation(w,'copy_duplicate_group','duplicate-group')
        old={e['signature_id'] for e in before['pages'][0]['signatures']}
        signatures=after['pages'][0]['signatures']
        self.assertEqual(len(signatures),len({e['signature_id'] for e in signatures}))
        self.assertTrue(old < {e['signature_id'] for e in signatures})
        groups={e['group_id'] for e in after['pages'][0]['boxes'] if e['custom_name'].endswith(' 2')}
        self.assertEqual(len(groups),1);self.assertNotIn(1,groups)

    def test_plain_duplicate_preserves_current_no_offset_behavior(self):
        w=self.editor('mixed',60)
        before,after=self.operation(w,'copy_duplicate_plain','duplicate-plain')
        old=w._object_clipboard[0][1];new=next(e for e in after['pages'][0]['boxes'] if e['custom_name']==old['custom_name']+' 2')
        self.assertEqual((new['x'],new['y']),(old['x'],old['y']))

    def test_board_duplicate_keeps_internal_connections_and_unique_names(self):
        w=self.editor('connected',10)
        before,after=self.operation(w,'copy_duplicate_board','duplicate-board')
        names=[e['name'].casefold() for e in after['organogram']['groups']]
        self.assertEqual(len(names),len(set(names)))
        oldids={e['id'] for e in before['organogram']['groups']}
        newids={e['id'] for e in after['organogram']['groups']}-oldids
        newedges=[e for e in after['organogram']['connections'] if e['source'] in newids]
        self.assertTrue(newedges);self.assertTrue(all(e['target'] in newids for e in newedges))

    def test_paste_public_and_protected_assets_has_no_external_file_dependency(self):
        from core.fornax_container import save_public_fornax,save_protected_fornax
        from core.fornax_session import FornaxSessionManager
        from editor_scenarios import Scenario,make_document
        from uuid import UUID
        doc,provider=make_document(Scenario('assets','select_all','mixed',20))
        for mode in ('public','signatures','full'):
            path=self.root/(mode+'.fornax');session=FornaxSessionManager();self.addCleanup(session.close)
            identities=iter(range(20000,21000))
            with patch('core.fornax_container.uuid4',side_effect=lambda:UUID(int=next(identities),version=4)):
                if mode=='public':
                    save_public_fornax(doc,path,asset_provider=provider);status=session.select(path)
                else:
                    save_protected_fornax(doc,path,'synthetic-password',mode=mode,asset_provider=provider)
                    status=session.unlock(path,'synthetic-password')
            w=self.editor('simple',1)
            w.load_from_fornax(session.document(),path=path,mode=status.descriptor.mode,
                              model_id=status.descriptor.model_id,asset_provider=session.asset,session_manager=session)
            with w._selection_batch():
                for i in w.scene.items():
                    if isinstance(i,(ImageItem,SignatureItem)) and not isinstance(i,RectangleItem) and i.parentItem() is None:
                        i.setSelected(True)
            w.copy_selected_items();w.save_snapshot();before=self.document(w)
            perform_copy(w,'copy_paste_assets')
            self.record(w,'assets-'+mode)
            selected=w.scene.selectedItems();self.assertTrue(selected)
            self.assertTrue(all(not i.pixmap().isNull() for i in selected if isinstance(i,(ImageItem,SignatureItem)) and not isinstance(i,RectangleItem)))
            after=self.document(w);w.undo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(before,history=True))
            w.redo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(after,history=True))

    def test_hidden_locked_linked_clipboard_and_repeated_names(self):
        w=self.editor('simple',20);prepare_copy(w,'copy_paste_1')
        entry=w._object_clipboard[0][1]
        entry.update(locked=True,visible=False,opacity=.43,has_link=True,link_key='destino',rotation=17)
        for iteration in range(2):
            perform_copy(w,'copy_paste_1')
            copied=[i for i in w.scene.items() if isinstance(i,DesignerBox) and i.custom_name.startswith('Copiado')]
            self.assertEqual(len(copied),iteration+1)
            for item in copied:
                self.assertFalse(item.isVisible());self.assertEqual(item.opacity(),.43)
                self.assertTrue(item.state.has_link);self.assertEqual(item.state.link_key,'destino')
                self.assertEqual(item.rotation(),17)
            self.assertEqual(w.scene.selectedItems(),[])
        self.record(w,'hidden-linked-repeated')

    def test_front_mask_pasted_as_board_artwork_keeps_grid_and_connections(self):
        w=self.editor('connected',10)
        # Origem e destino pertencem ao mesmo documento e autorização de assets.
        source=self.editor('mixed',20)
        doc=w._document_with_active_page();doc['pages']=source._document_with_active_page()['pages']
        w.load_starter_document(doc,source._editor_asset_provider)
        prepare_copy(w,'copy_duplicate_mask')
        w.switch_model_page('organogram');w.save_snapshot()
        before=self.document(w);grid=w.scene._board_grid
        perform_copy(w,'copy_paste_board_artwork');after=self.document(w)
        self.assertEqual(before['organogram']['groups'],after['organogram']['groups'])
        self.assertEqual(before['organogram']['connections'],after['organogram']['connections'])
        self.assertEqual(w.scene._board_grid,grid)
        self.assertTrue(any(isinstance(i,RectangleItem) and i.masked_images() for i in w.scene.items()))
        self.record(w,'board-artwork')
        w.undo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(before,history=True))
        w.redo();self.assertEqual(canonical_copy_document(self.document(w),history=True),canonical_copy_document(after,history=True))


class CopyWorkTest(CopyBehaviorTest):
    # Evita repetir os contratos herdados ao descobrir este módulo.
    def test_insert_preserves_wrappers_rows_and_never_clears_scene(self):
        w=self.editor('mixed',60);prepare_copy(w,'copy_paste_10')
        originals=[i for i in w.scene.items() if isinstance(i,(DesignerBox,ImageItem,SignatureItem))]
        rows=[(w.layer_list.item(n),w.layer_list.itemWidget(w.layer_list.item(n))) for n in range(w.layer_list.count())]
        with patch.object(w,'apply_scene_state',wraps=w.apply_scene_state) as reload, \
             patch.object(w,'refresh_layer_list',wraps=w.refresh_layer_list) as layers:
            perform_copy(w,'copy_paste_10')
        self.assertEqual(reload.call_count,0);self.assertEqual(layers.call_count,1)
        self.assertTrue(all(isValid(i) and i.scene() is w.scene for i in originals))
        self.assertTrue(all(isValid(row) and isValid(widget) and w.layer_list.itemWidget(row) is widget for row,widget in rows))

    def test_board_duplicates_publish_only_one_selection(self):
        w=self.editor('connected',40);prepare_copy(w,'copy_duplicate_board')
        with patch.object(w,'on_selection_changed',wraps=w.on_selection_changed) as changed:
            perform_copy(w,'copy_duplicate_board')
        self.assertEqual(changed.call_count,1)

    def test_plain_duplicates_publish_only_one_selection(self):
        w=self.editor('simple',20);w.select_all_items()
        with patch.object(w,'on_selection_changed',wraps=w.on_selection_changed) as changed:
            perform_copy(w,'copy_duplicate_plain')
        self.assertEqual(changed.call_count,1)

    def test_wrappers_survive_collection_during_mask_parenting(self):
        import gc
        w=self.editor('mixed',60);prepare_copy(w,'copy_duplicate_group')
        original=RectangleItem.refresh_mask_structure
        def collecting(shape): gc.collect();return original(shape)
        with patch.object(RectangleItem,'refresh_mask_structure',collecting):
            perform_copy(w,'copy_duplicate_group')
        self.assertTrue(all(isValid(i) for i in w.scene.items()))

    def test_plain_asset_duplicates_reuse_authorized_pixels(self):
        w=self.editor('mixed',20)
        with w._selection_batch():
            for item in w.scene.items():
                if isinstance(item,(ImageItem,SignatureItem)) and not isinstance(item,RectangleItem) and item.parentItem() is None and getattr(item,'group_id',None) is None:
                    item.setSelected(True)
        sources=[i for i in w.scene.selectedItems() if isinstance(i,(ImageItem,SignatureItem))]
        self.assertTrue(sources)
        perform_copy(w,'copy_duplicate_plain')
        copies=w.scene.selectedItems();self.assertEqual(len(copies),len(sources))
        self.assertTrue(all(not i.pixmap().isNull() for i in copies))
        self.assertEqual(sorted(sha256(bytes(i.pixmap().toImage().constBits())).hexdigest() for i in copies),
                         sorted(sha256(bytes(i.pixmap().toImage().constBits())).hexdigest() for i in sources))

    def test_canvas_paper_is_tracked_during_clear_and_garbage_collection(self):
        import gc
        from shiboken6 import createdByPython
        w=self.editor('simple',20)
        paper=w.fallback_bg
        self.assertTrue(createdByPython(paper))
        w.scene.clear()
        self.assertFalse(isValid(paper))
        del paper
        w.bg_item=None
        w.fallback_bg=None
        gc.collect()
        self.assertEqual(self.errors,[])


# Somente os testes novos de trabalho, sem repetir os contratos herdados.
for _name in tuple(CopyBehaviorTest.__dict__):
    if _name.startswith('test_') and _name not in CopyWorkTest.__dict__:
        setattr(CopyWorkTest,_name,None)
