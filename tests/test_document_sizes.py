"""Presets, orientação e histórico conservam o desenho e as dimensões físicas."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from core.fornax_container import save_public_fornax, open_public_fornax
from core.model_document import add_blank_back_page
from features.editor.editor_window import EditorWindow
from features.editor.document_sizes import PRESETS, supported_size
from test_organogram import card_document, board_document


class DocumentSizesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def editor(self, document=None):
        w = EditorWindow()
        w._load_document_into_scene(document or card_document())
        def cleanup():
            w._last_saved_state = w.get_current_scene_state()
            w._last_saved_document_state = w._capture_document_history_state()
            w.close()
        self.addCleanup(cleanup)
        return w

    def choose(self, w, key):
        c = w.document_size_controls
        c.choose_preset(c.combo.findData(key))

    def dimensions(self, w):
        return w.spin_phys_w.value(), w.spin_phys_h.value()

    def test_all_presets_apply_exact_dimensions_despite_proportion_lock(self):
        w = self.editor()
        w.chk_doc_proporcao.setChecked(True)
        for key, dimensions in PRESETS.items():
            with self.subTest(preset=key):
                self.assertTrue(supported_size(*dimensions))
                self.choose(w, key)
                self.assertEqual(self.dimensions(w), dimensions)
                self.assertEqual(w.document_size_controls.combo.currentData(), key)
                self.assertTrue(w.chk_doc_proporcao.isChecked())

    def test_technical_limit_preserves_document(self):
        w = self.editor()
        before = w.get_current_scene_state()
        with patch.object(QMessageBox, 'warning') as warning:
            w.document_size_controls.apply('custom', 10001, 10001)
        warning.assert_called_once()
        self.assertEqual(w.get_current_scene_state(), before)

    def test_three_metre_document_keeps_artwork_and_supports_history(self):
        w = self.editor()
        artwork = w.get_current_scene_state()['boxes']
        original = self.dimensions(w)
        w.document_size_controls.apply('custom', 3000, 3000)
        self.assertEqual(self.dimensions(w), (3000, 3000))
        self.assertEqual(w.get_current_scene_state()['boxes'], artwork)
        w.undo()
        self.assertEqual(self.dimensions(w), original)
        w.redo()
        self.assertEqual(self.dimensions(w), (3000, 3000))
        path = self.root / 'large.fornax'
        save_public_fornax(w._document_with_active_page(), path)
        other = self.editor(open_public_fornax(path).document())
        self.assertEqual(self.dimensions(other), (3000, 3000))

    def test_manual_large_dimensions_remain_custom_without_warning(self):
        w = self.editor()
        self.choose(w, 'A1')
        w.chk_doc_proporcao.setChecked(False)
        with patch.object(QMessageBox, 'warning') as warning:
            w.spin_phys_w.setValue(3000)
            w.spin_phys_h.setValue(3000)
        warning.assert_not_called()
        self.assertEqual(self.dimensions(w), (3000, 3000))
        self.assertEqual(w.document_size_controls.combo.currentData(), 'custom')

    def test_orientation_is_one_undo_step_and_keeps_artwork_unchanged(self):
        w = self.editor()
        self.choose(w, 'A4')
        artwork = w.get_current_scene_state()['boxes']
        index = w.history._current_index
        w.document_size_controls.landscape.click()
        self.assertEqual(self.dimensions(w), (297, 210))
        self.assertEqual(w.history._current_index, index + 1)
        self.assertEqual(w.get_current_scene_state()['boxes'], artwork)
        w.undo()
        self.assertEqual(self.dimensions(w), (210, 297))
        self.assertTrue(w.document_size_controls.portrait.isChecked())
        self.assertAlmostEqual(w._doc_aspect_ratio, 210 / 297)
        w.redo()
        self.assertEqual(self.dimensions(w), (297, 210))
        self.assertTrue(w.document_size_controls.landscape.isChecked())

    def test_preset_respects_existing_landscape_orientation(self):
        w = self.editor()
        w.document_size_controls.landscape.click()
        self.choose(w, 'A6')
        self.assertEqual(self.dimensions(w), (148, 105))

    def test_manual_dimensions_switch_to_custom_and_survive_save_and_undo(self):
        w = self.editor()
        w.chk_doc_proporcao.setChecked(False)
        self.choose(w, 'A4')
        w.spin_phys_w.setValue(211)
        w.save_snapshot()
        self.assertEqual(w.document_size_controls.combo.currentData(), 'custom')
        document = w._document_with_active_page()
        save_public_fornax(document, self.root / 'custom.fornax')
        opened = open_public_fornax(self.root / 'custom.fornax')
        other = self.editor(opened.document())
        self.assertEqual(other.document_size_controls.combo.currentData(), 'custom')
        self.assertEqual(self.dimensions(other), (211, 297))
        w.undo()
        self.assertEqual(w.document_size_controls.combo.currentData(), 'A4')
        w.redo()
        self.assertEqual(w.document_size_controls.combo.currentData(), 'custom')

    def test_legacy_document_recognizes_size_without_changing_canvas(self):
        document = card_document()
        document['target_w_mm'], document['target_h_mm'] = 148, 105
        w = self.editor(document)
        self.assertEqual(w.document_size_controls.combo.currentData(), 'A6')
        self.assertEqual(w.get_current_scene_state()['canvas_size'], document['canvas_size'])

    def test_square_keeps_1_to_1_selected_and_custom_keeps_dimensions(self):
        w = self.editor()
        self.choose(w, 'square')
        self.assertEqual(self.dimensions(w), (100, 100))
        self.assertFalse(w.document_size_controls.portrait.isEnabled())
        self.assertFalse(w.document_size_controls.landscape.isEnabled())
        self.assertTrue(w.document_size_controls.square.isEnabled())
        self.assertTrue(w.document_size_controls.square.isChecked())
        self.assertFalse(w.document_size_controls.portrait.isChecked())
        self.assertFalse(w.document_size_controls.landscape.isChecked())
        index = w.history._current_index
        w.document_size_controls.square.click()
        self.assertTrue(w.document_size_controls.square.isChecked())
        self.assertEqual(w.history._current_index, index)
        self.choose(w, 'custom')
        self.assertEqual(self.dimensions(w), (100, 100))
        saved = self.editor(w._document_with_active_page())
        self.assertEqual(saved.document_size_controls.combo.currentData(), 'custom')
        self.assertTrue(saved.document_size_controls.square.isChecked())

    def test_exactly_one_orientation_stays_selected_through_resize_and_history(self):
        w = self.editor()
        c = w.document_size_controls
        for width, height, selected in ((100, 100, c.square), (100, 150, c.portrait),
                                        (150, 100, c.landscape), (250, 250, c.square)):
            c.apply('custom', width, height)
            self.assertEqual([b for b in c.orientation_group.buttons() if b.isChecked()], [selected])
            self.assertEqual(c.square.isEnabled(), width == height)
            selected.click()
            self.assertTrue(selected.isChecked())
        w.undo()
        self.assertTrue(c.landscape.isChecked())
        self.assertFalse(c.square.isEnabled())
        w.redo()
        self.assertTrue(c.square.isChecked())
        self.assertFalse(c.landscape.isEnabled())

    def test_orientation_controls_fit_the_row_at_standard_inspector_width(self):
        w = self.editor()
        w.resize(1500, 900)
        w.show()
        for _ in range(5):
            self.app.processEvents()
        c = w.document_size_controls
        self.assertLessEqual(c.height(), 34)
        for button in c.orientation_group.buttons():
            self.assertEqual((button.width(), button.height()), (30, 30))
            self.assertTrue(c.rect().contains(button.geometry()))
            self.assertFalse(button.icon().isNull())
        controls_bottom = c.mapToGlobal(c.rect().bottomLeft()).y()
        dimensions_top = w.spin_phys_w.parentWidget().mapToGlobal(
            w.spin_phys_w.parentWidget().rect().topLeft()).y()
        self.assertLess(controls_bottom, dimensions_top)

    def test_organogram_controls_disabled_and_front_size_preserved(self):
        w = self.editor(board_document())
        self.choose(w, 'A5')
        w.switch_model_page('organogram')
        c = w.document_size_controls
        self.assertFalse(c.combo.isEnabled())
        self.assertFalse(c.portrait.isEnabled())
        self.assertFalse(c.square.isEnabled())
        c.apply('A1', 594, 841)
        w.switch_model_page('front')
        self.assertEqual(self.dimensions(w), (148, 210))
        self.assertEqual(c.combo.currentData(), 'A5')

    def test_cached_page_switch_restores_preset_and_proportion_ratio(self):
        w = self.editor(add_blank_back_page(card_document()))
        self.choose(w, 'A4')
        w.switch_model_page('back')
        self.assertEqual(w.document_size_controls.combo.currentData(), 'A4')
        w.document_size_controls.landscape.click()
        w.switch_model_page('front')
        self.assertEqual(self.dimensions(w), (297, 210))
        self.assertAlmostEqual(w._doc_aspect_ratio, 297 / 210)
        self.assertEqual(w.document_size_controls.combo.currentData(), 'A4')


if __name__ == '__main__':
    unittest.main()
