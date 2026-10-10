"""Etapa 05: controles reais, clipboard por contexto e publicação segura."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QMimeData, QCoreApplication, QEvent, QRectF
from PySide6.QtGui import QTextCursor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from PySide6.QtTest import QTest
import test_table_canvas as canvas
from core.table_model import (new_table, set_cell_html, format_cells, cell_at,
                              effective_cell_style, validate_table)
from core.table_clipboard import TABLE_RANGE_MIME
from core.model_document import normalize_model_document, add_model_table
from core.html_utils import TextOnlyDocument
from core.themes import theme_manager
from features.editor.table_item import TableItem


class TableControlsTest(unittest.TestCase):
    setUp = canvas.TableCanvasTest.setUp
    tearDown = canvas.TableCanvasTest.tearDown
    editor = canvas.TableCanvasTest.editor
    type = canvas.TableCanvasTest.type
    plain = canvas.TableCanvasTest.plain

    @classmethod
    def setUpClass(cls):
        canvas.TableCanvasTest.setUpClass.__func__(cls)
        theme_manager().select(os.environ.get('FORNAX_TEST_THEME','dark'))

    @classmethod
    def tearDownClass(cls):
        cls.app.clipboard().clear()
        canvas.TableCanvasTest.tearDownClass.__func__(cls)

    def select(self,item,top=1,left=0,bottom=2,right=1):
        item.setSelected(True);item.select_cell(top,left);item.select_cell(bottom,right,extend=True)

    def history(self,w):return len(w.history._undo_stack)

    def test_elements_menu_stable_id_and_table_action_dialog_cancel(self):
        w,item = self.editor()
        self.assertEqual(w.btn_elements.objectName(),'addFormas')
        self.assertTrue(any('Elementos' in label.text() for label in w.btn_elements.findChildren(QLabel)))
        self.assertEqual(w.action_add_table.text(),'Tabela')
        before = w.get_current_scene_state();count = self.history(w)
        with patch.object(QDialog,'exec',return_value=QDialog.DialogCode.Rejected) as dialog:
            w.action_add_table.trigger()
        dialog.assert_called_once()
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)

    def test_insert_public_table_v6_and_refuse_limit_before_mutation(self):
        w,item = self.editor()
        self.assertTrue(w.table_controller.add_table(4,5))
        tables = [i for i in w.scene.items() if isinstance(i,TableItem)]
        self.assertEqual(len(tables),2);self.assertIn(item,tables)
        source = w._capture_document_history_state()['document']
        self.assertEqual(source['schema_version'],6)
        current = w.table_controller.selected();self.assertEqual(current.data['rows'],4)
        self.assertEqual(current.data['columns'],5)
        before = w.get_current_scene_state();count = self.history(w)
        self.assertFalse(w.table_controller.add_table(100,100))
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)
        self.assertTrue(w.table_panel.message.text())

    def test_new_table_starts_with_one_line_height_and_30_mm_columns(self):
        from core.table_layout import TableLayout
        from features.editor.canvas_items import px_to_mm
        w, old = self.editor()
        source = old.to_data()
        self.assertTrue(w.table_controller.add_table(3, 3))
        item = w.table_controller.selected()
        for width in item.data['column_widths']:
            self.assertAlmostEqual(px_to_mm(width), 30)
        entry = item.layout.cells[0]
        self.assertGreaterEqual(entry.inner.height(), entry.text_height)
        self.assertLess(entry.inner.height()-entry.text_height, 1)
        from core.table_model import set_cell_html
        single = TableLayout(set_cell_html(item.to_data(), 0, 0, '<p>Nome do aluno</p>'))
        self.assertEqual(single.warnings, [])
        multi = TableLayout(set_cell_html(item.to_data(), 0, 0, '<p>Nome</p><p>Função</p>'))
        self.assertTrue(multi.warnings[0]['overflow_y'])
        self.assertEqual(old.to_data(), source)

    def test_mixed_selection_sync_does_not_edit_or_snapshot(self):
        table = new_table(2,2)
        table = format_cells(table,0,0,0,0,{'font_size':9.5,'fill_color':'#112233','wrap':False})
        source = add_model_table(normalize_model_document({'canvas_size':{'w':900,'h':650}}),table)
        w,item = self.editor(source);self.select(item,0,0,1,1)
        before = w.get_current_scene_state();count = self.history(w)
        with patch.object(w.table_panel,'load',wraps=w.table_panel.load) as load:
            for _ in range(3):w.table_controller.refresh()
        load.assert_not_called()
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)
        self.assertTrue(w.editor_texto_panel.table_size.property('mixed'))
        self.assertEqual(w.editor_texto_panel.table_size.lineEdit().placeholderText(),'Vários')
        self.assertEqual(w.table_panel.fill.placeholderText(),'Vários')
        self.assertEqual(w.table_panel.wrap.checkState(),Qt.CheckState.PartiallyChecked)
        w._table_section.header.setChecked(False);w.table_controller.refresh()
        self.assertFalse(w._table_section.header.isChecked())

    def test_fill_only_retains_documents_and_changes_selected_cells_once(self):
        w,item = self.editor();self.select(item)
        docs = [entry.document for entry in item.layout.cells];count = self.history(w)
        with patch.object(w.scene,'clear',side_effect=AssertionError('Reconstrução global')):
            w.table_panel.fill.setText('#123456');w.table_panel.apply_color('fill')
        self.assertEqual(self.history(w),count+1)
        self.assertEqual([entry.document for entry in item.layout.cells],docs)
        self.assertEqual(effective_cell_style(item.data,cell_at(item.data,2,1))['fill_color'],'#123456')
        self.assertEqual(w.table_panel.fill.text(),'#123456')
        self.assertNotEqual(effective_cell_style(item.data,cell_at(item.data,0,0))['fill_color'],'#123456')

    def test_typography_fractional_size_bold_and_keyboard_in_grid(self):
        w,item = self.editor();self.select(item,0,0,0,1)
        w.editor_texto_panel.table_size.setValue(9.5)
        self.assertEqual(effective_cell_style(item.data,cell_at(item.data,0,0))['font_size'],9.5)
        self.assertIn('{nome}',cell_at(item.data,0,0)['html'])
        w.view.setFocus();QTest.keyClick(w.view.viewport(),Qt.Key.Key_B,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(item.layout.cells[0].document.begin().begin().fragment().charFormat().fontWeight() >= QFont.Weight.Bold)
        self.assertIsNone(w.table_edit.item)
        w.editor_texto_panel.btn_bold.click()
        self.assertFalse(item.layout.cells[0].document.begin().begin().fragment().charFormat().fontWeight() >= QFont.Weight.Bold)

    def test_active_text_style_preserves_cursor_text_and_focus(self):
        w,item = self.editor();self.type(w,item,text='Texto inteiro')
        cursor = w.table_edit.text.textCursor();cursor.setPosition(0)
        cursor.setPosition(5,QTextCursor.MoveMode.KeepAnchor);w.table_edit.text.setTextCursor(cursor)
        self.assertTrue(w.table_controller.cell_style({'fill_color':'#aabbcc','vertical_align':'bottom'}))
        self.assertIs(w.table_edit.item,item)
        self.assertEqual(w.table_edit.text.textCursor().selectedText(),'Texto')
        self.assertEqual(w.table_edit.document.toPlainText(),'Texto inteiro')
        w.editor_texto_panel.btn_italic.click()
        self.assertTrue(w.table_edit.text.textCursor().charFormat().fontItalic())
        self.assertTrue(w.table_edit.text.hasFocus())
        w.table_edit.finish()
        self.assertIn('Texto',cell_at(item.data,1,1)['html'])
        self.assertEqual(effective_cell_style(item.data,cell_at(item.data,1,1))['vertical_align'],'bottom')
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_empty_cell_bold_style_survives_typing(self):
        w,item = self.editor();self.select(item,1,1,1,1)
        w.editor_texto_panel.btn_bold.click()
        self.assertTrue(w.editor_texto_panel.btn_bold.isChecked())
        self.type(w,item,text='Nome novo')
        self.assertTrue(w.table_edit.text.textCursor().charFormat().fontWeight() >= QFont.Weight.Bold)
        w.table_edit.finish()
        w.table_controller.refresh()
        self.assertTrue(w.editor_texto_panel.btn_bold.isChecked())

    def test_structure_sequence_roundtrip_with_full_history(self):
        w,item = self.editor();self.select(item,1,0,1,1)
        initial = w._capture_document_history_state()['document']
        for op in ('merge','split','row_after','column_after','remove_rows','remove_columns'):
            self.assertTrue(w.table_controller.structure(op))
        final = w._capture_document_history_state()['document']
        validate_table(w.get_current_scene_state()['tables'][0])
        for _ in range(6):w.undo()
        self.assertEqual(w._capture_document_history_state()['document'],initial)
        for _ in range(6):w.redo()
        self.assertEqual(w._capture_document_history_state()['document'],final)

    def test_track_batch_panel_mm_and_invalid_padding_atomic(self):
        w,item = self.editor();self.select(item)
        w.table_panel.row_height.setValue(20)
        self.assertAlmostEqual(item.data['row_heights'][1],20*300/25.4)
        self.assertEqual(item.data['row_heights'][1],item.data['row_heights'][2])
        self.type(w,item,text='Rascunho')
        before = w.get_current_scene_state();count = self.history(w);active = w.table_edit.text
        self.assertFalse(w.table_controller.cell_style({'padding':500}))
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)
        self.assertIs(w.table_edit.text,active);self.assertEqual(w.table_edit.document.toPlainText(),'Rascunho')

    def test_internal_grid_copy_paste_keeps_style_merges_and_new_ids(self):
        w,item = self.editor();self.select(item,0,0,0,1)
        QApplication.clipboard().clear()
        w.view.setFocus();QTest.keyClick(w.view.viewport(),Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(QApplication.clipboard().mimeData().hasFormat(TABLE_RANGE_MIME))
        self.assertIn('{nome}',QApplication.clipboard().text())
        old_id = cell_at(item.data,0,0)['id'];item.select_cell(2,0)
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(cell_at(item.data,2,0)['column_span'],2)
        self.assertIn('{nome}',cell_at(item.data,2,0)['html'])
        self.assertNotEqual(cell_at(item.data,2,0)['id'],old_id)
        self.assertIsNone(w.table_edit.item)

    def test_external_grid_paste_content_only_and_text_mode_multiline(self):
        w,item = self.editor();self.select(item)
        w.table_controller.cell_style({'fill_color':'#123456'})
        original_id = cell_at(item.data,1,0)['id']
        QApplication.clipboard().setText('Ana\tProfessor\nJosé\tDiretor')
        w.table_controller.paste_selection()
        self.assertEqual(cell_at(item.data,1,0)['id'],original_id)
        self.assertEqual(self.plain(w,(2,0)),'José')
        self.assertEqual(effective_cell_style(item.data,cell_at(item.data,1,0))['fill_color'],'#123456')
        self.type(w,item,anchor=(1,2),text='')
        QApplication.clipboard().setText('uma\tduas\ntrês')
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.table_edit.document.toPlainText(),'uma\tduas\ntrês')
        self.assertEqual(self.plain(w,(2,0)),'José')

    def test_bad_mime_or_nonfitting_grid_paste_keeps_data_and_history(self):
        w,item = self.editor();self.select(item,2,2,2,2)
        before = w.get_current_scene_state();count = self.history(w)
        mime = QMimeData();mime.setData(TABLE_RANGE_MIME,b'invalid');mime.setText('fallback')
        QApplication.clipboard().setMimeData(mime);w.table_controller.paste_selection()
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)
        QApplication.clipboard().setText('a\tb');w.table_controller.paste_selection()
        self.assertEqual(w.get_current_scene_state(),before);self.assertEqual(self.history(w),count)
        self.assertTrue(w.table_panel.message.text())

    def test_external_literal_markup_survives_format_edit_and_checkpoint(self):
        w,item = self.editor();self.select(item,1,1,1,1)
        literal = '<img src="x"> url(x) @import'
        QApplication.clipboard().setText(literal)
        w.table_controller.paste_selection()
        self.assertEqual(self.plain(w,(1,1)),literal)
        w.editor_texto_panel.btn_bold.click()
        self.type(w,item,text='!');w.table_edit.finish()
        self.assertEqual(self.plain(w,(1,1)),literal+'!')
        validate_table(item.to_data())

    def test_sidebar_borders_apply_to_all_selected_cell_edges_and_preserve_history(self):
        w,item = self.editor();self.select(item)
        panel = w.table_panel
        panel.edge.setText('#abcdef');panel.edge.editingFinished.emit()
        panel.edge_width.setValue(.4)
        selected = [('h',1,0),('h',2,0),('h',3,1),('v',1,1),('v',2,2)]
        for key in selected:
            edge = item.layout.edge_style(key)
            self.assertEqual(edge['color'],'#abcdef')
            self.assertAlmostEqual(edge['width'],.4*300/25.4)
        self.assertNotEqual(item.layout.edge_style(('h',0,2))['color'],'#abcdef')
        border_state = lambda table: {key:table[key] for key in ('border','edges','cells')}
        before = border_state(item.to_data())
        panel.edge_opacity.setValue(0)
        for key in selected:
            edge = item.layout.edge_style(key)
            self.assertEqual(edge['opacity'],0)
            self.assertTrue(edge['visible'])
        after = border_state(item.to_data())
        w.undo();self.assertEqual(border_state(w.get_current_scene_state()['tables'][0]),before)
        w.redo();self.assertEqual(border_state(w.get_current_scene_state()['tables'][0]),after)

    def test_hidden_legacy_borders_load_without_mutation_and_restore_with_opacity(self):
        w,item = self.editor();self.select(item)
        self.assertTrue(w.table_controller.edge_style({'visible':False}))
        source = w._document_with_active_page()
        reopened,item = self.editor(source);self.select(item)
        before = item.to_data()
        reopened.table_controller.refresh()
        self.assertEqual(item.to_data(),before)
        self.assertEqual(reopened.table_panel.edge_opacity.value(),0)
        reopened.table_panel.edge_opacity.setValue(60)
        for key in [('h',1,0),('h',2,0),('v',1,1)]:
            edge = item.layout.edge_style(key)
            self.assertTrue(edge['visible']);self.assertEqual(edge['opacity'],.6)
        item.select_cell(0,0,extend=True)
        self.assertTrue(reopened.table_panel.edge_opacity.property('mixed'))

    def test_simplified_sidebar_keeps_cell_measures_and_compact_border_opacity(self):
        from PySide6.QtWidgets import QAbstractSpinBox
        w,item = self.editor();self.select(item)
        panel = w.table_panel
        headings = [label.text() for label in panel.findChildren(QLabel)
                    if label.objectName() == 'propertySectionHeading']
        self.assertEqual(headings,['MEDIDAS','CÉLULAS','BORDAS'])
        for removed in ('quantity','edge_target','edge_visible'):
            self.assertFalse(hasattr(panel,removed),removed)
        self.assertFalse(isinstance(panel.actions,dict))
        self.assertIsNone(panel.findChild(QAbstractSpinBox,'tableWidth'))
        self.assertIsNone(panel.findChild(QAbstractSpinBox,'tableHeight'))
        self.assertEqual(panel.edge_opacity.parentWidget().objectName(),'compact')
        self.assertEqual(panel.edge_opacity.buttonSymbols(),QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.assertIs(panel.edge.parentWidget(),panel.edge_opacity.parentWidget().parentWidget())

    def test_partial_updates_and_unchanged_topology_paste_match_renderer_exactly(self):
        w,item = self.editor();self.select(item,1,0,1,0)
        docs = {(e.cell['row'],e.cell['column']):e.document for e in item.layout.cells}
        w.table_controller.cell_style({'fill_color':'#123456','fill_opacity':.3,'padding':0})
        w.table_controller.edge_style({'color':'#aabbcc','width':8})
        w.table_controller.cell_style({'padding':4,'vertical_align':'bottom'})
        self.assertTrue(all(e.document is docs[e.cell['row'],e.cell['column']] for e in item.layout.cells))
        w.table_controller.copy_selection();item.select_cell(1,1)
        w.table_controller.paste_selection()
        self.assertTrue(all(e.document is docs[e.cell['row'],e.cell['column']] for e in item.layout.cells
                            if (e.cell['row'],e.cell['column']) != (1,1)))
        item.overlays_enabled=False
        image=QImage(900,650,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:w.scene.render(painter,QRectF(0,0,900,650),QRectF(0,0,900,650))
        finally:painter.end()
        expected=canvas.NativeRenderer(canvas.adapt_model_page(w._document_with_active_page())).render_preview_image()
        self.assertEqual(image,expected)

    def test_table_panel_restores_standard_text_mode_when_deselected(self):
        w,item = self.editor();self.select(item)
        self.assertTrue(w.editor_texto_panel._table_mode)
        self.assertTrue(w.editor_texto_panel.spin_size.isHidden())
        self.assertFalse(w.editor_texto_panel.table_size.isHidden())
        w.scene.clearSelection();self.app.processEvents()
        self.assertFalse(w.editor_texto_panel._table_mode)
        self.assertFalse(w.editor_texto_panel.spin_size.isHidden())
        self.assertTrue(w.editor_texto_panel.table_size.isHidden())
        self.assertFalse(w.table_panel.isEnabled())
        w.add_new_box();item.setSelected(True)
        self.assertFalse(w.editor_texto_panel.isEnabled())
        before = w.get_current_scene_state()
        w.update_font_size(42)
        self.assertEqual(w.get_current_scene_state(),before)


if __name__ == '__main__':unittest.main()
