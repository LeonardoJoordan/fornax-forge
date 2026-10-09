"""Histórico do quadro preserva ações pendentes, guias e a seleção editada."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QGraphicsItem

from core.organogram import new_group
from features.editor.editor_window import EditorWindow
from features.editor.canvas_items import DesignerBox, Guideline
from features.editor.organogram_editor import BoardConnectorItem, BoardGroupItem
from test_organogram import board_document


class OrganogramHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def editor(self):
        document = board_document(1, 1)
        second = new_group(document, columns=1, rows=1, x=1200, y=2000)
        second['name'] = 'Segundo bloco'
        board = document['organogram']
        board['groups'].append(second)
        board['connections'] = [{'source': board['groups'][0]['id'], 'target': second['id']}]
        board['boxes'] = [{'x': 0, 'y': -200, 'w': 300, 'h': 100,
                           'html': '<p>Título</p>', 'rich_text_version': 1,
                           'layer_id': 50, 'object_id': 'text:50'}]
        board['layer_order'] = ['text:50']
        window = EditorWindow()
        def cleanup():
            window._finish_page_interaction()
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        window._load_document_into_scene(document)
        window.switch_model_page('organogram')
        return window

    def guide(self, window):
        return next(item for item in window.scene.items() if isinstance(item, Guideline))

    def text(self, window):
        return next(item for item in window.scene.items() if isinstance(item, DesignerBox))

    def selected_groups(self, window):
        return {item.data['id'] for item in window.scene.selectedItems() if isinstance(item, BoardGroupItem)}

    def selected_edges(self, window):
        return {(item.board_edge['source'], item.board_edge['target'])
                for item in window.scene.selectedItems() if isinstance(item, BoardConnectorItem)}

    def test_guide_lock_is_an_independent_undo_step_and_redo_restores_lock(self):
        window = self.editor()
        window.add_guide(True, 300)
        previous = window.history._current_index
        window.btn_lock_guides.click()
        self.assertEqual(window.history._current_index, previous + 1)
        self.assertFalse(self.guide(window).flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        window.undo()
        self.assertFalse(window.btn_lock_guides.isChecked())
        self.assertTrue(self.guide(window).flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        window.redo()
        self.assertTrue(window.btn_lock_guides.isChecked())
        self.assertFalse(self.guide(window).flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def test_guide_visibility_without_guides_is_undoable_and_survives_page_switch(self):
        window = self.editor()
        previous = window.history._current_index
        window.btn_toggle_guides.click()
        self.assertEqual(window.history._current_index, previous + 1)
        self.assertFalse(window.btn_toggle_guides.isChecked())
        window.undo()
        self.assertTrue(window.btn_toggle_guides.isChecked())
        window.redo()
        self.assertFalse(window.btn_toggle_guides.isChecked())
        window.switch_model_page('front')
        self.assertFalse(window.btn_toggle_guides.isChecked())
        window.switch_model_page('organogram')
        self.assertFalse(window.btn_toggle_guides.isChecked())

    def test_selected_blocks_stay_selected_across_border_undo_and_redo(self):
        window = self.editor()
        selected = window._board_items()
        for item in selected:
            item.setSelected(True)
        identities = self.selected_groups(window)
        window.change_board_border(cards=True, width_mm=0.8)
        window.undo()
        self.assertEqual(self.selected_groups(window), identities)
        self.assertTrue(window.organogram_panel.border_enabled.isEnabled())
        window.redo()
        self.assertEqual(self.selected_groups(window), identities)
        self.assertTrue(window.organogram_panel.border_enabled.isChecked())

    def test_shared_guide_visibility_is_applied_to_guides_when_restoring_each_page(self):
        window = self.editor()
        window.switch_model_page('front')
        window.add_guide(True, 300)
        window.switch_model_page('organogram')
        window.add_guide(False, 500)
        window.btn_toggle_guides.click()
        self.assertFalse(self.guide(window).isVisible())
        window.undo()
        self.assertTrue(self.guide(window).isVisible())
        window.redo()
        self.assertFalse(self.guide(window).isVisible())
        window.switch_model_page('front')
        self.assertFalse(window.btn_toggle_guides.isChecked())
        self.assertFalse(self.guide(window).isVisible())

    def test_loading_a_document_does_not_reuse_previous_history_selection(self):
        window = self.editor()
        for item in window._board_items():
            item.setSelected(True)
        window.change_board_border(cards=True)
        window.undo()
        window.redo()
        document = window._document_with_active_page()
        window._load_document_into_scene(document)
        window.switch_model_page('organogram')
        self.assertEqual(self.selected_groups(window), set())
        self.assertEqual(self.selected_edges(window), set())

    def test_selected_connector_stays_target_of_property_edits_after_undo(self):
        window = self.editor()
        edge = next(item for item in window.scene.items() if isinstance(item, BoardConnectorItem))
        edge.setSelected(True)
        identities = self.selected_edges(window)
        window.change_board_connector_style(radius_mm=7)
        window.undo()
        self.assertEqual(self.selected_edges(window), identities)
        window.organogram_panel.width.setValue(1.2)
        self.assertEqual(window._board_connections_data()[0]['style']['width_mm'], 1.2)
        self.assertNotEqual(window._board_connector_style['width_mm'], 1.2)
        self.assertFalse(window.history.can_redo())

    def test_undo_captures_live_numeric_edit_before_stepping_back(self):
        window = self.editor()
        text = self.text(window)
        text.setSelected(True)
        original = text.rect().width()
        window.caixa_texto_panel.spin_w.setValue(40)
        changed = text.rect().width()
        self.assertNotEqual(changed, original)
        # Ainda não houve editingFinished (ex.: atalho de desfazer).
        window.undo()
        self.assertEqual(self.text(window).rect().width(), original)
        window.redo()
        self.assertAlmostEqual(self.text(window).rect().width(), changed, places=2)

    def test_redo_does_not_overwrite_a_new_numeric_edit_after_undo(self):
        window = self.editor()
        text = self.text(window)
        text.setSelected(True)
        window.caixa_texto_panel.spin_w.setValue(40)
        window.caixa_texto_panel.spin_w.editingFinished.emit()
        window.undo()
        self.assertTrue(window.history.can_redo())
        self.text(window).setSelected(True)
        window.caixa_texto_panel.spin_w.setValue(60)
        changed = self.text(window).rect().width()
        window.redo()
        self.assertAlmostEqual(self.text(window).rect().width(), changed, places=2)
        self.assertFalse(window.history.can_redo())


if __name__ == '__main__':
    unittest.main()
