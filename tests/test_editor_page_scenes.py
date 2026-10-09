"""Conteúdo, seleção e dependências entre cenas de páginas."""
from copy import deepcopy
import gc, os, unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMessageBox
from shiboken6 import isValid
import test_editor_performance_contracts as contracts
from features.editor.canvas_items import DesignerBox, RectangleItem, Guideline
from paint_cases import settle, image_hash, screen_image


class PageBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def box(self, w):
        return next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==6)

    def cycle(self, w, page='back'):
        w.switch_model_page(page); settle(self.app); w.switch_model_page('front'); settle(self.app)

    def test_selection_and_masks_belong_to_each_page(self):
        w=self.editor('duplex',60); box=self.box(w); box.setSelected(True); wanted=w._selection_keys()
        w.switch_model_page('back'); w.scene.clearSelection(); w.switch_model_page('front')
        self.assertEqual(w._selection_keys(),wanted)
        masks=[i for i in w.scene.items() if isinstance(i,RectangleItem) and i.masked_images()]
        self.assertEqual(len(masks),6); self.assertTrue(all(i.masked_images()[0].parentItem() is i for i in masks))

    def test_text_edit_finishes_before_switch_and_is_preserved(self):
        w=self.editor('duplex',60); w.canvas_edit.begin(self.box(w)); cursor=w.canvas_edit.box.text_item.textCursor(); cursor.insertText('Conteúdo novo ')
        self.cycle(w); self.assertIsNone(w.canvas_edit.box); self.assertIn('Conteúdo novo',self.box(w).text_item.toPlainText())
        self.assertTrue(w.shortcut_undo.isEnabled())

    def test_inactive_page_changed_directly_is_reloaded(self):
        w=self.editor('duplex',60); self.cycle(w)
        w._model_document['pages'][1]['boxes'][1]['html']='<p>Atualizado fora da cena</p>'
        w.switch_model_page('back'); self.assertTrue(any('Atualizado fora' in i.text_item.toPlainText() for i in w.scene.items() if isinstance(i,DesignerBox)))

    def test_shared_canvas_size_reaches_other_page(self):
        w=self.editor('duplex',60); self.cycle(w); w.spin_phys_w.setValue(150); w.save_snapshot(); w.switch_model_page('back')
        self.assertEqual(w.spin_phys_w.value(),150); self.assertAlmostEqual(w._get_document_rect().width(),150*300/25.4,delta=1)

    def test_guides_controls_and_wrappers_survive_gc(self):
        w=self.editor('duplex',60); w.btn_lock_guides.setChecked(True); w.btn_toggle_guides.setChecked(False)
        self.cycle(w); gc.collect(); settle(self.app)
        self.assertTrue(w.btn_lock_guides.isChecked()); self.assertFalse(w.btn_toggle_guides.isChecked())
        self.assertEqual(len([i for i in w.scene.items() if isinstance(i,Guideline)]),2)

    def test_history_restores_content_after_switches(self):
        w=self.editor('duplex',60); before=self.box(w).pos(); self.box(w).moveBy(80,0); w.save_snapshot(); self.cycle(w)
        w.undo(); self.assertEqual(self.box(w).pos(),before); w.redo(); self.assertEqual(self.box(w).pos().x(),before.x()+80)
        self.cycle(w); self.assertEqual(self.box(w).pos().x(),before.x()+80)

    def test_new_document_does_not_reuse_previous_page(self):
        w=self.editor('duplex',60); self.cycle(w); doc=deepcopy(w._model_document); doc['pages'][1]['boxes'][1]['html']='<p>Outro documento</p>'
        w._load_document_into_scene(doc); w.switch_model_page('back')
        self.assertTrue(any('Outro documento' in i.text_item.toPlainText() for i in w.scene.items() if isinstance(i,DesignerBox)))

    def test_legacy_background_keeps_working_when_switching_pages(self):
        from editor_scenarios import synthetic_assets
        w = self.editor('duplex', 60)
        document = deepcopy(w._model_document)
        document['pages'][0]['background_path'] = 'asset:photo.png'
        document['pages'][0].pop('bg_props', None)
        w.load_starter_document(document, synthetic_assets().__getitem__)
        for _ in range(3):
            self.cycle(w)
        self.assertTrue(any(getattr(i, '_original_path', None) == 'asset:photo.png'
                            for i in w.scene.items()))

    def test_card_changes_refresh_board_preview(self):
        w=self.editor('connected',5); old=image_hash(w._board_card_preview); w.switch_model_page('front')
        box=next(i for i in w.scene.items() if isinstance(i,DesignerBox)); box.state.html_content='<p>Cartão alterado</p>'; box.recalculate_text_position(); w.save_snapshot(); w.switch_model_page('organogram')
        self.assertNotEqual(image_hash(w._board_card_preview),old)

    def test_asset_bytes_changes_refresh_board(self):
        w=self.editor('connected',5); w.switch_model_page('front')
        from editor_scenarios import synthetic_assets
        from features.editor.canvas_items import ImageItem
        payloads=synthetic_assets(); w._fornax_asset_provider=payloads.__getitem__
        # Usa uma imagem válida diferente, sem alterar o identificador do asset.
        image=ImageItem(None,pixmap_data=payloads['asset:photo.png'],asset_reference='asset:photo.png'); image.layer_id=99
        w.scene.addItem(image)
        w.switch_model_page('organogram'); old=image_hash(w._board_card_preview); w.switch_model_page('front')
        payloads.update(synthetic_assets(large=True)); w.switch_model_page('organogram'); self.assertNotEqual(image_hash(w._board_card_preview),old)

    def test_add_remove_and_undo_use_current_document(self):
        w=self.editor('simple',20); w.add_model_page(); self.assertEqual(w._active_page_id,'back')
        with patch('features.editor.document_session.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes): w.remove_model_page('back')
        self.assertEqual(w._active_page_id,'front'); w.undo(); self.assertEqual(len(w._model_document['pages']),2)

    def test_return_pixels_identical_to_fresh_loading(self):
        from core.model_document import replace_model_page
        w=self.editor('duplex',60)
        # Documento com fundo já materializado, mas sem a marca gravada pelas
        # versões novas. O carregador também reconhece seu nome histórico.
        document=replace_model_page(w._model_document,w.get_current_scene_state(),'front')
        for shape in document['pages'][0]['shapes']:
            if shape.get('is_document_background'):
                shape.pop('is_document_background')
        w._load_document_into_scene(document)
        w.resize(1280,800); w.show(); self.cycle(w); w._zoom_to_fit(); settle(self.app)
        w._zoom_to_fit(); settle(self.app)
        from core.model_document import adapt_model_page
        from features.editor.model_adapter import prepare_scene_page
        before_image=screen_image(w); before=image_hash(before_image); state=prepare_scene_page(adapt_model_page(w._model_document,'front'))
        view_before=(w.view.transform(),w.view.horizontalScrollBar().value(),w.view.verticalScrollBar().value(),w.view.viewport().size())
        w.apply_scene_state(state); settle(self.app); w._zoom_to_fit(); settle(self.app); w._zoom_to_fit(); settle(self.app)
        after_image=screen_image(w)
        if image_hash(after_image)!=before:
            before_image.save('/tmp/fornax-page-before.png'); after_image.save('/tmp/fornax-page-after.png')
            print('VIEWS',view_before,(w.view.transform(),w.view.horizontalScrollBar().value(),w.view.verticalScrollBar().value(),w.view.viewport().size()))
        self.assertEqual(image_hash(after_image),before)

    def test_selection_after_many_cycles_updates_active_panel_only(self):
        w=self.editor('duplex',60)
        for _ in range(10): self.cycle(w)
        box=self.box(w); box.setSelected(True); settle(self.app)
        self.assertEqual(w._get_selected(),box); self.assertIs(w.canvas_edit.window.scene,w.scene)

    def test_external_image_with_same_path_size_and_date_is_refreshed(self):
        from PySide6.QtGui import QImage,QColor
        from features.editor.canvas_items import ImageItem
        w=self.editor('duplex',60); w.switch_model_page('back'); path=self.root/'external.bmp'
        def write(color):
            image=QImage(20,20,QImage.Format.Format_RGB32); image.fill(QColor(color)); self.assertTrue(image.save(str(path)))
        write('red'); item=ImageItem(str(path)); item.layer_id=99; w.scene.addItem(item)
        w.switch_model_page('front'); stamp=path.stat(); write('blue'); self.assertEqual(path.stat().st_size,stamp.st_size)
        os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns)); w.switch_model_page('back')
        item=next(i for i in w.scene.items() if type(i) is ImageItem and i.layer_id==99)
        self.assertEqual(item.pixmap().toImage().pixelColor(0,0),QColor('blue'))

    def test_clear_inactive_page_does_not_restore_old_content(self):
        w=self.editor('duplex',60); self.cycle(w)
        with patch('features.editor.document_session.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes): w.clear_model_page('back')
        w.switch_model_page('back'); self.assertEqual([i for i in w.scene.items() if isinstance(i,DesignerBox)],[])

    def test_zoom_and_view_center_do_not_jump_on_same_size_pages(self):
        from PySide6.QtCore import QPointF
        w=self.editor('duplex',60); w.resize(1280,800); w.show(); self.cycle(w); settle(self.app)
        w.view.scale(.5,.5); w.view.centerOn(QPointF(500,900)); settle(self.app)
        center=w.view.mapToScene(w.view.viewport().rect().center()); transform=w.view.transform()
        self.cycle(w); after=w.view.mapToScene(w.view.viewport().rect().center())
        self.assertEqual(w.view.transform(),transform); self.assertLess((after-center).manhattanLength()*transform.m11(),4)


class PageReuseTest(PageBehaviorTest):
    def test_edited_cached_page_keeps_loader_layer_values(self):
        from core.model_document import adapt_model_page
        from features.editor.model_adapter import prepare_scene_page
        w = self.editor('duplex', 60)
        w.resize(1280, 800); w.show(); settle(self.app)
        self.cycle(w)
        self.box(w).moveBy(1, 0)
        w.switch_model_page('back')
        source = prepare_scene_page(adapt_model_page(w._model_document, 'front'))
        w.switch_model_page('front')
        cached = w.get_current_scene_state()
        w._zoom_to_fit(); settle(self.app)
        cached_pixels = image_hash(screen_image(w, workspace=True))
        w.apply_scene_state(source)
        w._zoom_to_fit(); settle(self.app)
        self.assertEqual(w._normalize_state_for_compare(cached),
                         w._normalize_state_for_compare(w.get_current_scene_state()))
        self.assertEqual(cached_pixels, image_hash(screen_image(w, workspace=True)))

    # Não herdar os casos de comportamento ao contar esta classe no driver.
    def test_retains_scene_and_items_without_rebuilding(self):
        w=self.editor('duplex',60); scene=w.scene; box=self.box(w)
        w.switch_model_page('back')
        with patch.object(w,'_insert_scene_items',wraps=w._insert_scene_items) as insert:
            w.switch_model_page('front'); self.assertIs(w.scene,scene); self.assertIs(self.box(w),box); insert.assert_not_called()

    def test_inactive_scene_signals_do_not_update_active_page(self):
        w=self.editor('duplex',60); old=w.scene; box=self.box(w); w.switch_model_page('back')
        with patch.object(w.canvas_edit,'finish',wraps=w.canvas_edit.finish) as finish:
            old.selectionChanged.emit(); self.assertIsNone(w.canvas_edit.box); finish.assert_not_called()
        self.assertFalse(old.receivers('2changed(QList<QRectF>)'))

    def test_budget_falls_back_to_reconstruction(self):
        w=self.editor('duplex',60); w._page_scene_budget=1; scene=w.scene; w.switch_model_page('back'); w.switch_model_page('front')
        self.assertIsNot(w.scene,scene); self.assertIsNone(w._inactive_page_scene)

    def test_font_change_and_protection_discard_clear_inactive_scene(self):
        w=self.editor('duplex',60); w.switch_model_page('back'); cached=w._inactive_page_scene
        w._clear_visual_cache(); self.assertIsNone(w._inactive_page_scene); self.assertEqual(cached.scene.items(),[])
        w.switch_model_page('front'); w.switch_model_page('back'); cached=w._inactive_page_scene
        document=deepcopy(w._model_document)
        # Suprime deleteLater apenas para inspecionar o descarte imediato.
        with patch.object(w,'deleteLater'):
            w._discard_protected_editor_content()
        self.assertEqual(cached.scene.items(),[]); self.assertEqual(w.scene.items(),[]); self.assertIsNone(w._inactive_page_scene)
        # A fixture usa uma janela pública: restaura-a só para seu cleanup.
        w._load_document_into_scene(document)

    def test_close_releases_inactive_items(self):
        w=self.editor('duplex',60); w.switch_model_page('back'); cached=w._inactive_page_scene
        w._last_saved_state=w.get_current_scene_state(); w._last_saved_document_state=w._capture_document_history_state(); w.close()
        self.assertIsNone(w._inactive_page_scene); self.assertEqual(cached.scene.items(),[])

    def test_destroyed_inactive_wrappers_fall_back(self):
        w=self.editor('duplex',60); w.switch_model_page('back'); cached=w._inactive_page_scene
        cached.scene.clear(); w.switch_model_page('front'); self.assertIsNot(w.scene,cached.scene)
        self.assertEqual(len(w.get_current_scene_state()['boxes']),24)

    def test_current_selection_signals_are_connected_once(self):
        w=self.editor('duplex',60)
        initial=w.scene.receivers('2selectionChanged()')
        for _ in range(5): self.cycle(w)
        self.assertEqual(w.scene.receivers('2selectionChanged()'),initial)

    def test_real_protected_close_discards_both_scenes_and_asset_provider(self):
        from core.fornax_container import save_protected_fornax,FULL_MODE,PUBLIC_MODE
        from core.fornax_session import FornaxSessionManager
        w=self.editor('duplex',60); document=deepcopy(w._model_document); provider=w._fornax_asset_provider
        path=self.root/'protected.fornax'
        save_protected_fornax(document,path,'senha-teste',mode=FULL_MODE,asset_provider=provider)
        sessions=FornaxSessionManager(); self.addCleanup(sessions.close); status=sessions.unlock(path,'senha-teste')
        w.load_from_fornax(sessions.document(),path=path,mode=FULL_MODE,model_id=status.descriptor.model_id,asset_provider=sessions.asset,session_manager=sessions)
        w.switch_model_page('back'); cached=w._inactive_page_scene; self.assertIsNotNone(cached)
        w._last_saved_state=w.get_current_scene_state(); w._last_saved_document_state=w._capture_document_history_state()
        with patch.object(w,'deleteLater'): w.close()
        self.assertIsNone(w._inactive_page_scene); self.assertIsNone(w._fornax_asset_provider)
        self.assertIsNone(w._board_card_preview); self.assertEqual(cached.scene.items(),[]); self.assertEqual(w.scene.items(),[])
        # Apenas permite que a fixture pública conclua seu cleanup.
        w._fornax_mode=PUBLIC_MODE; w._fornax_path=None; w._fornax_session_manager=None
        w.load_starter_document(document,provider)

    def test_theme_change_rebuilds_adornments_without_changing_art(self):
        from core.themes import theme_manager
        manager=theme_manager(); original=manager.theme_id
        w=self.editor('duplex',60); self.cycle(w); scene=w.scene
        document=deepcopy(w._document_with_active_page())
        w.switch_model_page('back')
        try:
            manager.select('light' if original!='light' else 'dark'); w.switch_model_page('front')
            self.assertIsNot(w.scene,scene); self.assertEqual(w._document_with_active_page(),document)
        finally: manager.select(original)
