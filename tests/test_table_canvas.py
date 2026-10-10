"""Etapa 04: gestos, foco, texto, histórico e recuperação da célula ativa."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt,QPointF,QRectF,QEvent,QCoreApplication
from PySide6.QtGui import QImage,QPainter,QTextCursor,QInputMethodEvent,QMouseEvent
from PySide6.QtWidgets import QApplication,QGraphicsTextItem,QLineEdit,QStyleOptionGraphicsItem
from PySide6.QtTest import QTest
from shiboken6 import isValid
from core.ui_font import install_ui_font
from core.table_model import new_table,set_cell_html,merge_cells,cell_at,MAX_CELL_HTML_BYTES
from core.model_document import normalize_model_document,add_model_table,add_blank_back_page,adapt_model_page
from core.fornax_container import save_public_fornax,save_protected_fornax,PUBLIC_MODE,FULL_MODE
from core.fornax_session import FornaxSessionManager
from features.editor.editor_window import EditorWindow
from features.editor.table_item import TableItem
from features.editor.table_edit import CellTextItem
from features.generator.renderer import NativeRenderer


def sample():
    table=new_table(3,3,width=660,height=420)
    table.update(x=80,y=80)
    table=merge_cells(table,0,0,0,1)
    table=set_cell_html(table,0,0,'<p><b>{nome}</b> |Detalhe: {detalhe}|</p>')
    table=set_cell_html(table,1,0,'<p>Texto fixo</p>')
    return add_model_table(normalize_model_document({'canvas_size':{'w':900,'h':650}}),table)


class TableCanvasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False);install_ui_font(cls.app)
        cls.errors=[];cls.previous_hook=sys.excepthook
        sys.excepthook=lambda typ,value,tb:cls.errors.append(str(value))

    @classmethod
    def tearDownClass(cls):
        sys.excepthook=cls.previous_hook

    def setUp(self):
        self.temp=TemporaryDirectory(prefix='fornax-table-canvas-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.enterContext(patch('core.paths._data_home',return_value=self.root/'data'))
        self.windows=[]

    def tearDown(self):
        for window in self.windows:
            if not isValid(window):continue
            window._finish_page_interaction()
            window._recovered_unsaved=False
            window._last_saved_state=window.get_current_scene_state()
            window._last_saved_document_state=window._capture_document_history_state()
            window.close();window.deleteLater()
        self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(self.errors,[])

    def editor(self,source=None):
        window=EditorWindow();self.windows.append(window)
        window._load_document_into_scene(source or sample())
        window.show();window.activateWindow();self.app.processEvents();window._zoom_to_fit()
        return window,next(i for i in window.scene.items() if isinstance(i,TableItem))

    def type(self,window,item,anchor=(1,1),text='Olá'):
        window.table_edit.begin(item,anchor)
        cursor=window.table_edit.text.textCursor();cursor.insertText(text);window.table_edit.text.setTextCursor(cursor)
        return window.table_edit.text

    def plain(self,window,anchor):
        data=window.get_current_scene_state()['tables'][0]
        from core.html_utils import TextOnlyDocument
        doc=TextOnlyDocument();doc.setHtml(cell_at(data,*anchor)['html']);return doc.toPlainText()

    def point(self,window,item,x,y):
        return window.view.mapFromScene(item.mapToScene(QPointF(x,y)))

    def test_one_root_no_editors_per_cell_and_shared_painter_matches_renderer(self):
        window,item=self.editor()
        self.assertEqual(sum(isinstance(i,TableItem) for i in window.scene.items()),1)
        self.assertFalse(any(isinstance(i,CellTextItem) for i in window.scene.items()))
        item.overlays_enabled=False
        image=QImage(900,650,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:window.scene.render(painter,QRectF(0,0,900,650),QRectF(0,0,900,650))
        finally:painter.end()
        expected=NativeRenderer(adapt_model_page(window._document_with_active_page())).render_preview_image()
        self.assertEqual(image,expected)

    def test_partial_paint_draws_only_affected_cell_with_identical_pixels(self):
        window,item=self.editor();item.overlays_enabled=False
        option=QStyleOptionGraphicsItem();option.exposedRect=item.layout.cells[1].rect
        image=QImage(660,420,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        calls=[]
        from core.html_utils import TextOnlyDocument
        draw=TextOnlyDocument.drawContents
        def tracked(document,*args):
            calls.append(document);return draw(document,*args)
        try:
            painter.setClipRect(option.exposedRect)
            with patch.object(TextOnlyDocument,'drawContents',tracked):item.paint(painter,option)
        finally:painter.end()
        self.assertEqual(calls,[item.layout.cells[1].document])
        complete=QImage(660,420,QImage.Format.Format_ARGB32);complete.fill(Qt.GlobalColor.white)
        painter=QPainter(complete)
        try:item.layout.paint(painter)
        finally:painter.end()
        area=option.exposedRect.toAlignedRect()
        self.assertEqual(image.copy(area),complete.copy(area))

    def test_double_click_edits_mapped_cell_at_zoom_and_rotation(self):
        window,item=self.editor();item.setRotation(8)
        point=self.point(window,item,330,210)
        QTest.mouseDClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertIs(window.table_edit.item,item)
        self.assertEqual(window.table_edit.anchor,(1,1))
        self.assertEqual(sum(isinstance(i,CellTextItem) for i in window.scene.items()),1)

    def test_native_typing_ime_and_manual_line_break_do_not_move_table(self):
        window,item=self.editor();item.select_cell(1,1)
        before=item.pos()
        QTest.keyClicks(window.view.viewport(),'Texto ')
        self.assertIs(window.table_edit.item,item)
        ime=QInputMethodEvent();ime.setCommitString('ação 😀𝄞')
        window.scene.sendEvent(window.table_edit.text,ime)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Return)
        QTest.keyClicks(window.view.viewport(),'linha 2')
        self.assertEqual(self.plain(window,(1,1)),'Texto ação 😀𝄞\nlinha 2')
        self.assertEqual(item.pos(),before)

    def test_ime_begins_editing_selected_cell_without_ascii_key(self):
        window,item=self.editor();item.select_cell(1,2)
        ime=QInputMethodEvent();ime.setCommitString('São José')
        QApplication.sendEvent(window.view.viewport(),ime)
        self.assertEqual(self.plain(window,(1,2)),'São José')

    def test_focus_on_sidebar_preserves_cursor_text_and_cell_target(self):
        window,item=self.editor();self.type(window,item,text='Ação')
        cursor=window.table_edit.text.textCursor();cursor.select(QTextCursor.SelectionType.Document)
        window.table_edit.text.setTextCursor(cursor)
        field=QLineEdit(window);field.show();field.setFocus();self.app.processEvents()
        self.assertIs(window.table_edit.item,item)
        self.assertEqual(window.table_edit.text.textCursor().selectedText(),'Ação')
        self.assertEqual(self.plain(window,(1,1)),'Ação')

    def test_click_outside_commits_and_escape_exits_text_then_cells(self):
        window,item=self.editor();self.type(window,item,text='Salvo')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Escape)
        self.assertIsNone(window.table_edit.item);self.assertIsNotNone(item.selected_range)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Escape)
        self.assertIsNone(item.selected_range)
        self.type(window,item,text=' fora')
        QTest.mouseClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=self.point(window,item,760,470))
        self.assertIsNone(window.table_edit.item)
        self.assertEqual(self.plain(window,(1,1)),'Salvo fora')

    def test_tab_and_shift_tab_visit_anchors_and_do_not_insert_rows(self):
        window,item=self.editor();self.type(window,item,(0,0),' A')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Tab)
        self.assertEqual(window.table_edit.anchor,(0,2))
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Tab,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(window.table_edit.anchor,(0,0))
        window.table_edit.finish();self.type(window,item,(2,2),'fim')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Tab)
        self.assertEqual(window.table_edit.anchor,(2,2));self.assertEqual(item.data['rows'],3)

    def test_arrows_navigate_cells_and_shift_extends_without_moving_object(self):
        window,item=self.editor();item.select_cell(0,0)
        before=item.pos();count=len(window.history._undo_stack)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Right)
        self.assertEqual(item.selection_cursor,(0,2))
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(item.selected_range,(0,2,1,2))
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Up,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(item.selected_range,(0,2,0,2))
        self.assertEqual(item.pos(),before);self.assertEqual(len(window.history._undo_stack),count)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Return)
        self.assertIs(window.table_edit.item,item)

    def test_delete_edits_text_clears_cells_or_deletes_object_by_context(self):
        window,item=self.editor();self.type(window,item,text='ABC')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Backspace)
        self.assertEqual(self.plain(window,(1,1)),'AB')
        window.table_edit.finish();item.select_cell(1,1)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Delete)
        self.assertEqual(self.plain(window,(1,1)),'');self.assertIs(item.scene(),window.scene)
        item.clear_cell_selection();window.delete_selected_items()
        self.assertFalse(window.get_current_scene_state().get('tables'))
        window.undo();self.assertEqual(len(window.get_current_scene_state()['tables']),1)

    def test_cell_paste_is_literal_multiline_and_does_not_change_structure(self):
        window,item=self.editor();self.type(window,item,text='')
        self.app.clipboard().setText('1\t2\n<imagem> 😀')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.plain(window,(1,1)),'1\t2\n<imagem> 😀')
        self.assertEqual(len(item.data['cells']),8)

    def test_local_text_undo_checkpoint_and_document_redo_preserve_table(self):
        window,item=self.editor();before=deepcopy(window.get_current_scene_state()['tables'])
        self.type(window,item,text='Novo')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.plain(window,(1,1)),'')
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.plain(window,(1,1)),'Novo')
        window.table_edit.checkpoint()
        self.assertIs(window.table_edit.item,item)
        self.assertEqual(self.plain(window,(1,1)),'Novo')
        window.undo();self.assertEqual(window.get_current_scene_state()['tables'],before)
        window.redo();self.assertEqual(self.plain(window,(1,1)),'Novo')

    def test_page_switch_commits_active_cell_and_releases_editor(self):
        window,item=self.editor(add_blank_back_page(sample()))
        self.type(window,item,text='Página 1')
        window.switch_model_page('back');self.assertIsNone(window.table_edit.item)
        window.switch_model_page('front');self.assertEqual(self.plain(window,(1,1)),'Página 1')
        self.assertFalse(any(isinstance(i,CellTextItem) for i in window.scene.items()))

    def test_text_edits_only_rebuild_target_cell_and_move_selection_reuses_layout(self):
        window,item=self.editor();original=item.layout
        docs=[e.document for e in original.cells]
        with patch('features.editor.editor_window.EditorWindow.apply_scene_state',side_effect=AssertionError('recriou cena')):
            self.type(window,item,text='Uma célula');item.moveBy(8,9)
            item.select_cell(1,1);window.table_edit.finish()
        self.assertIs(item.layout,original)
        target=next(i for i,e in enumerate(original.cells) if (e.cell['row'],e.cell['column']) == (1,1))
        self.assertEqual(sum(a is not b.document for a,b in zip(docs,original.cells)),1)
        self.assertIsNot(docs[target],original.cells[target].document)

    def test_optional_delimiters_are_not_removed_by_editing_or_checkpoint(self):
        window,item=self.editor();self.type(window,item,(0,0),'!')
        self.assertIn('|Detalhe: {detalhe}|',self.plain(window,(0,0)))
        window.table_edit.finish();self.assertIn('|Detalhe: {detalhe}|',self.plain(window,(0,0)))

    def test_drag_cell_selection_expands_merges_and_deactivation_releases_pointer(self):
        window,item=self.editor()
        item.select_cell(0, 0)
        start=self.point(window,item,330,60);end=self.point(window,item,540,350)
        QTest.mousePress(window.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(window.view.viewport().mapToGlobal(end)),
                         Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.view.viewport(),event)
        self.assertEqual(item.selected_range,(0,0,2,2))
        QApplication.sendEvent(window,QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(item._selecting_cells);self.assertIsNone(window.scene.mouseGrabberItem())
        self.assertEqual(window.view._pointer_buttons,Qt.MouseButton.NoButton)

    def test_content_limit_is_atomic_and_keeps_last_accepted_text(self):
        window,item=self.editor();self.type(window,item,text='Válido')
        self.app.clipboard().setText('X'*(MAX_CELL_HTML_BYTES+100))
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.plain(window,(1,1)),'Válido')
        self.assertTrue(window.table_edit.last_error)
        window.table_edit.finish();self.assertEqual(self.plain(window,(1,1)),'Válido')

    def test_ctrl_s_finishes_active_edit_through_existing_save_shortcut(self):
        window,item=self.editor();self.type(window,item,text='Salve este texto')
        received=[]
        window.shortcut_save.activated.disconnect()
        def save():
            window._finish_page_interaction()
            received.append(window.get_current_scene_state())
        window.shortcut_save.activated.connect(save)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(received),1)
        self.assertIsNone(window.table_edit.item)
        self.assertIn('Salve este texto',cell_at(received[0]['tables'][0],1,1)['html'])

    def test_frame_drag_moves_object_without_rebuilding_documents(self):
        window,item=self.editor();layout=item.layout
        before=item.pos()
        start=self.point(window,item,-8,210);end=start+window.view.mapFromScene(QPointF(30,30))-window.view.mapFromScene(QPointF(0,0))
        QTest.mousePress(window.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(window.view.viewport().mapToGlobal(end)),
                         Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.view.viewport(),event)
        QTest.mouseRelease(window.view.viewport(),Qt.MouseButton.LeftButton,pos=end)
        self.assertNotEqual(item.pos(),before);self.assertIs(item.layout,layout)
        self.assertIsNone(item.selected_range)
        self.assertFalse(item._is_mouse_dragging)

    def test_invalid_replacement_preserves_scene_and_active_draft(self):
        window,item=self.editor();text=self.type(window,item,text='Preservado')
        invalid=sample();invalid['pages'][0]['tables'][0]['row_heights'][0]=-1
        from core.model_document import ModelValidationError
        with self.assertRaises(ModelValidationError):window._load_document_into_scene(invalid)
        self.assertIs(window.table_edit.text,text);self.assertIs(window.table_edit.item,item)
        self.assertEqual(self.plain(window,(1,1)),'Preservado')

    def test_select_all_and_delete_cells_is_one_atomic_history_action(self):
        window,item=self.editor();before=deepcopy(window.get_current_scene_state()['tables'])
        item.select_cell(0,0)
        QTest.keyClick(window.view.viewport(),Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(item.selected_range,(0,0,2,2))
        count=len(window.history._undo_stack)
        with patch('features.editor.table_item.validate_table',wraps=__import__('core.table_model',fromlist=['validate_table']).validate_table) as validate:
            QTest.keyClick(window.view.viewport(),Qt.Key.Key_Delete)
            self.assertEqual(validate.call_count,1)
        self.assertEqual(len(window.history._undo_stack),count+1)
        self.assertTrue(all(c['html']=='' for c in item.data['cells']))
        window.undo();self.assertEqual(window.get_current_scene_state()['tables'],before)

    def test_document_text_budget_counts_live_tables_and_inactive_pages(self):
        source=add_model_table(sample(),new_table(1,1,width=100,height=100))
        source=add_blank_back_page(source)
        source=add_model_table(source,new_table(1,1,width=100,height=100),'back')
        window,_=self.editor(source)
        item=next(i for i in window.scene.items() if isinstance(i,TableItem) and i.data['rows']==3)
        other=next(i for i in window.scene.items() if isinstance(i,TableItem) and i is not item)
        other.publish_cell_html((0,0),'X'*500)
        self.type(window,item,text='Aceito')
        session=window.table_edit
        current=cell_at(item.data,*session.anchor)['id']
        replaced=cell_at(other.data,0,0)['id']
        # Orçamento sintético exato: não depende do tamanho do cabeçalho HTML Qt.
        total=sum(len(c['html'].encode()) for t in source['pages'][0]['tables']+source['pages'][1]['tables']
                  for c in t['cells'] if c['id'] not in (current,replaced))+500+len(session.accepted_html.encode())
        with patch('features.editor.table_edit.MAX_DOCUMENT_TABLE_HTML_BYTES',total):
            self.assertTrue(session._fits_budget(session.accepted_html))
            self.assertFalse(session._fits_budget(session.accepted_html+'x'))

    def test_active_cell_preserves_colors_and_alignment_without_cursor_overlay(self):
        from core.table_model import format_cells
        source=sample()
        table=format_cells(source['pages'][0]['tables'][0],1,0,1,0,
            {'font_color':'#d02070','align':'right','vertical_align':'bottom','fill_color':'#cceeff'})
        source['pages'][0]['tables'][0]=table
        window,item=self.editor(source);item.overlays_enabled=False
        def render():
            image=QImage(900,650,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
            painter=QPainter(image)
            try:window.scene.render(painter,QRectF(0,0,900,650),QRectF(0,0,900,650))
            finally:painter.end()
            return image
        before=render()
        window.table_edit.begin(item,(1,0));window.table_edit.text.clearFocus()
        self.assertEqual(render(),before)

    def test_table_on_organogram_loads_edits_and_survives_scene_switch(self):
        from core.organogram import add_organogram
        source=add_organogram(sample())
        source=add_model_table(source,new_table(2,2,width=300,height=200),'organogram')
        window,_=self.editor(source);window.switch_model_page('organogram')
        item=next(i for i in window.scene.items() if isinstance(i,TableItem))
        self.type(window,item,text='Quadro');table_id=item.data['object_id']
        window.switch_model_page('front');window.switch_model_page('organogram')
        loaded=next(i for i in window.scene.items() if isinstance(i,TableItem))
        self.assertEqual(loaded.data['object_id'],table_id)
        self.assertEqual(self.plain(window,(1,1)),'Quadro')

    def test_save_and_recovery_include_unfinished_cell_in_public_and_protected_packages(self):
        for mode in (PUBLIC_MODE,FULL_MODE):
            with self.subTest(mode=mode):
                source=sample();source['name']='Tabela de teste'
                path=self.root/(mode+'.fornax')
                sessions=FornaxSessionManager()
                if mode==PUBLIC_MODE:
                    save_public_fornax(source,path);status=sessions.select(path)
                else:
                    save_protected_fornax(source,path,'senha-teste',mode=mode);status=sessions.unlock(path,'senha-teste')
                window=EditorWindow();self.windows.append(window)
                try:
                    window.load_from_fornax(sessions.document(),path=path,mode=mode,
                        model_id=status.descriptor.model_id,asset_provider=sessions.asset,session_manager=sessions)
                    item=next(i for i in window.scene.items() if isinstance(i,TableItem))
                    self.type(window,item,text='Ainda digitando')
                    before=path.read_bytes();window._write_fornax_recovery()
                    deadline=time.monotonic()+30
                    while window._recovery_worker is not None and time.monotonic()<deadline:QTest.qWait(10)
                    self.assertIsNone(window._recovery_worker)
                    recovered=sessions.read_recovery(window.fornax_recovery_path(path),path=path).document()
                    self.assertIn('Ainda digitando',cell_at(recovered['pages'][0]['tables'][0],1,1)['html'])
                    self.assertEqual(path.read_bytes(),before)
                    self.assertIs(window.table_edit.item,item)
                    window._finish_page_interaction()
                    with patch.object(window,'_show_save_success_dialog'):
                        window._export_to_fornax(window.get_current_scene_state(),skip_close_dialog=True)
                    self.assertIn('Ainda digitando',cell_at(sessions.document()['pages'][0]['tables'][0],1,1)['html'])
                    self.assertFalse(window.fornax_recovery_path(path).exists())
                finally:
                    window._finish_page_interaction();sessions.close()


if __name__=='__main__':unittest.main()
