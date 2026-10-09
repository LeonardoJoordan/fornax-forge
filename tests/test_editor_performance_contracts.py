"""Contratos de comportamento que devem sobreviver às otimizações do editor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'performance'))
from editor_scenarios import Scenario, scenarios, make_document, fingerprint
from benchmark_editor import distribution

from PySide6.QtCore import QEvent, Qt, QPointF
from PySide6.QtWidgets import QApplication
from features.editor.editor_window import EditorWindow
from features.editor.canvas_items import DesignerBox, RectangleItem
from core.ui_font import install_ui_font


class PerformanceContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        install_ui_font(cls.app)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root/'data'))
        self.errors = []
        self.enterContext(patch('sys.excepthook', side_effect=lambda *args: self.errors.append(args[1])))
        self.addCleanup(lambda: self.assertEqual(self.errors, [], 'Exceção em callback Qt'))

    def editor(self, fixture='simple', size=20):
        doc, provider = make_document(Scenario('test', 'select_all', fixture, size))
        window = EditorWindow()
        def cleanup():
            window._finish_page_interaction()
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)
        window.load_starter_document(doc, provider)
        if fixture in ('connected', 'grid'):
            window.switch_model_page('organogram')
        return window

    def test_fixture_ids_and_input_fingerprints_are_reproducible(self):
        entries = scenarios()
        self.assertEqual(len({case.id for case in entries}), len(entries))
        for fixture, size in (('mixed', 60), ('connected', 40), ('grid', 2500), ('duplex', 60)):
            case = Scenario('test', 'select_all', fixture, size)
            first, provider = make_document(case)
            second, other_provider = make_document(case)
            self.assertEqual(fingerprint(first, provider), fingerprint(second, other_provider))
            if fixture == 'grid':
                self.assertEqual(sum(group['rows'] * group['columns'] for group in first['organogram']['groups']), size)

    def test_summary_keeps_samples_and_interpolates_p95(self):
        result = distribution([3, 1, 4, 2])
        self.assertEqual(result['median_ms'], 2.5)
        self.assertAlmostEqual(result['p95_ms'], 3.85)
        self.assertEqual(result['sample_count'], 4)

    def test_select_all_respects_hidden_and_locked_objects_and_does_not_change_document(self):
        window = self.editor()
        before = window._document_with_active_page()
        window.select_all_items()
        selected = {item.layer_id for item in window.scene.selectedItems() if isinstance(item, DesignerBox)}
        self.assertEqual(selected, set(range(1, 21)) - {1, 5})
        self.assertEqual(window._document_with_active_page(), before)

    def test_layer_refresh_preserves_mask_relationships_order_and_content(self):
        window = self.editor('mixed', 60)
        before = window.get_current_scene_state()
        window.refresh_layer_list()
        after = window.get_current_scene_state()
        self.assertEqual(before, after)
        masks = [item for item in window.scene.items() if isinstance(item, RectangleItem) and item.masked_images()]
        self.assertEqual(len(masks), 6)
        for mask in masks:
            self.assertEqual(len(mask.masked_images()), 1)

    def test_paste_and_history_preserve_existing_content_and_add_exactly_one_copy(self):
        window = self.editor('mixed', 60)
        box = next(item for item in window.scene.items() if isinstance(item, DesignerBox) and item.isVisible()
                   and getattr(item, 'group_id', None) is None and item.layer_id != 1)
        box.setSelected(True)
        before = deepcopy(window.get_current_scene_state())
        window.copy_selected_items()
        window.paste_copied_items()
        after = window.get_current_scene_state()
        self.assertEqual(len(after['boxes']), len(before['boxes']) + 1)
        original = {entry['layer_id']: entry['html'] for entry in before['boxes']}
        self.assertTrue(original.items() <= {entry['layer_id']: entry['html'] for entry in after['boxes']}.items())
        window.undo()
        self.assertEqual(len(window.get_current_scene_state()['boxes']), len(before['boxes']))
        window.redo()
        self.assertEqual(len(window.get_current_scene_state()['boxes']), len(after['boxes']))

    def test_unchanged_snapshots_and_ui_selection_do_not_add_history_steps(self):
        window = self.editor()
        index = window.history._current_index
        window.save_snapshot()
        window.select_all_items()
        window.save_snapshot()
        self.assertEqual(window.history._current_index, index)
        self.assertFalse(window.history.can_redo())

    def test_repeated_page_switching_preserves_masked_objects_and_both_page_contents(self):
        window = self.editor('duplex', 60)
        window.save_snapshot()
        before = window._document_with_active_page()
        for _ in range(3):
            window.switch_model_page('back')
            self.assertEqual(window._active_page_id, 'back')
            window.switch_model_page('front')
        after = window._document_with_active_page()
        # Carregar o verso pode completar propriedades padrão; comparar conteúdo e relações.
        for index in range(2):
            self.assertEqual({box['layer_id']: box['html'] for box in after['pages'][index]['boxes']},
                             {box['layer_id']: box['html'] for box in before['pages'][index]['boxes']})
            self.assertEqual({image['layer_id']: image.get('mask_shape_id') for image in after['pages'][index]['images']},
                             {image['layer_id']: image.get('mask_shape_id') for image in before['pages'][index]['images']})

    def test_group_motion_changes_routes_and_survives_history(self):
        window = self.editor('connected', 10)
        groups = window._board_items()[:4]
        ids = [item.data['id'] for item in groups]
        before = {item.data['id']: QPointF(item.pos()) for item in groups}
        window._move_board_items(groups, QPointF(200, 0))
        window.save_snapshot()
        after = {item.data['id']: QPointF(item.pos()) for item in window._board_items() if item.data['id'] in ids}
        self.assertNotEqual(after, before)
        window.undo()
        self.assertEqual({item.data['id']: item.pos() for item in window._board_items() if item.data['id'] in ids}, before)
        window.redo()
        self.assertEqual({item.data['id']: item.pos() for item in window._board_items() if item.data['id'] in ids}, after)


if __name__ == '__main__':
    unittest.main()
