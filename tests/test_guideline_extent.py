"""Guias acompanham a área de trabalho sem alterar posição ou magnetismo."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication

from features.editor.canvas_items import (
    Guideline, _get_dynamic_snap_distance, _snap_targets, mm_to_px,
)
from features.editor.editor_window import EditorWindow
from test_organogram import card_document


class GuidelineExtentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.enterContext(patch("core.paths._data_home", return_value=Path(temporary.name)))
        self.window = EditorWindow()
        self.window._load_document_into_scene(card_document())
        self.addCleanup(self.close_editor)

    def close_editor(self):
        w = self.window
        w._last_saved_state = w.get_current_scene_state()
        w._last_saved_document_state = w._capture_document_history_state()
        w.close()

    def guides(self):
        return [item for item in self.window.scene.items() if isinstance(item, Guideline)]

    def assert_full_extent(self, guide):
        rect = self.window.scene.sceneRect()
        start = guide.mapToScene(guide.line().p1())
        end = guide.mapToScene(guide.line().p2())
        if guide.is_vertical:
            self.assertAlmostEqual(start.y(), rect.top())
            self.assertAlmostEqual(end.y(), rect.bottom())
            probe = QPointF(guide.x(), rect.bottom() - 1)
        else:
            self.assertAlmostEqual(start.x(), rect.left())
            self.assertAlmostEqual(end.x(), rect.right())
            probe = QPointF(rect.right() - 1, guide.y())
        self.assertTrue(guide.contains(guide.mapFromScene(probe)))

    def test_new_guides_cover_ten_metre_document_and_remain_clickable(self):
        w = self.window
        w.document_size_controls.apply("custom", 10000, 10000)
        for vertical in (True, False):
            w.add_guide(vertical, mm_to_px(9000))
        for guide in self.guides():
            self.assert_full_extent(guide)
        targets = _snap_targets(w.scene)
        self.assertIn(mm_to_px(9000), targets[0])
        self.assertIn(mm_to_px(9000), targets[1])

    def test_existing_guides_follow_resize_zoom_and_negative_workspace(self):
        w = self.window
        w.add_guide(True, 200)
        w.add_guide(False, 300)
        for rect, zoom in ((QRectF(0, 0, mm_to_px(10000), mm_to_px(10000)), .01),
                           (QRectF(-80000, -70000, 160000, 150000), .003),
                           (QRectF(0, 0, 1200, 800), 2)):
            w.view.resetTransform()
            w.view.scale(zoom, zoom)
            w._set_document_rect(rect)
            for guide in self.guides():
                self.assert_full_extent(guide)

    def test_extent_refresh_preserves_history_state_selection_and_snap_formula(self):
        w = self.window
        w.add_guide(True, 200)
        guide = self.guides()[0]
        guide.setSelected(True)
        state = w.get_current_scene_state()
        tolerance = _get_dynamic_snap_distance(w.scene)
        index = w.history._current_index
        w._update_workspace_scene_rect()
        self.assertEqual(w.get_current_scene_state(), state)
        self.assertTrue(guide.isSelected())
        self.assertEqual(w.history._current_index, index)
        self.assertEqual(_get_dynamic_snap_distance(w.scene), tolerance)

    def test_reload_and_undo_redo_restore_extent_for_current_document(self):
        w = self.window
        w.add_guide(True, 200)
        w.add_guide(False, 300)
        w.document_size_controls.apply("custom", 10000, 10000)
        w.undo()
        for guide in self.guides():
            self.assert_full_extent(guide)
        w.redo()
        for guide in self.guides():
            self.assert_full_extent(guide)
        w._load_document_into_scene(w._document_with_active_page())
        for guide in self.guides():
            self.assert_full_extent(guide)


if __name__ == "__main__":
    unittest.main()
