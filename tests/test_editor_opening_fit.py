"""A abertura enquadra o desenho na área final do canvas, sem alterar o modelo."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QPointF
from PySide6.QtWidgets import QApplication, QMainWindow

from features.editor.editor_window import EditorWindow
from test_organogram import card_document, board_document


class EditorOpeningFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.enterContext(patch("core.paths._data_home", return_value=Path(temporary.name)))

    def settle(self):
        for _ in range(6):
            self.app.processEvents()

    def editor(self, *, board=False, workspace=None, blank=False):
        document = board_document(4, 3) if board else card_document()
        document["pages"][0]["boxes"] = []
        document["pages"][0]["layer_order"] = ["shape:1"]
        window = EditorWindow(workspace)
        if not blank:
            window._load_document_into_scene(document)
        if board:
            window.switch_model_page("organogram")
        window.resize(1500, 950)
        def cleanup():
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def assert_fitted(self, window):
        content = window._get_content_rect(for_fit=True)
        viewport = window.view.viewport().rect()
        center = window.view.mapFromScene(content.center())
        self.assertAlmostEqual(center.x(), viewport.center().x(), delta=2)
        self.assertAlmostEqual(center.y(), viewport.center().y(), delta=2)
        bounds = window.view.mapFromScene(content).boundingRect()
        self.assertTrue(viewport.contains(bounds), (viewport, bounds))
        # A mesma folga de 50 unidades usada pelo comando Ajustar à janela.
        padded = content.adjusted(-50, -50, 50, 50)
        expected_scale = min((viewport.width() - 4) / padded.width(),
                             (viewport.height() - 4) / padded.height())
        self.assertAlmostEqual(window.view.transform().m11(), expected_scale, delta=0.002)

    def test_hidden_auxiliary_background_and_handles_do_not_enlarge_content(self):
        window = self.editor()
        self.assertEqual(window._get_content_rect(for_fit=True), window._get_document_rect())

    def test_blank_editor_opening_fits_default_page(self):
        window = self.editor(blank=True)
        window.show()
        self.settle()
        self.assert_fitted(window)

    def test_resize_while_opening_uses_final_viewport(self):
        window = self.editor()
        window.show()
        window.resize(1250, 820)
        self.settle()
        self.assert_fitted(window)

    def test_visible_artwork_outside_page_is_included(self):
        from features.editor.canvas_items import RectangleItem
        window = self.editor()
        shape = next(item for item in window.scene.items()
                     if isinstance(item, RectangleItem) and item.layer_id == 1)
        shape.setPos(-400, 100)
        window.show()
        self.settle()
        self.assertLess(window._get_content_rect(for_fit=True).left(), 0)
        self.assert_fitted(window)

    def test_open_after_final_window_layout_fits_and_centers_card(self):
        window = self.editor()
        before = window.get_current_scene_state()
        window.show()
        self.settle()
        self.assert_fitted(window)
        self.assertEqual(window.get_current_scene_state(), before)

    def test_reopening_discards_previous_pan_and_zoom(self):
        window = self.editor()
        window.show()
        self.settle()
        window.view.scale(3, 3)
        window.view.centerOn(QPointF(1700, 1900))
        window.hide()
        window.resize(1250, 820)
        window.show()
        self.settle()
        self.assert_fitted(window)

    def test_loading_another_document_in_visible_editor_fits(self):
        window = self.editor()
        window.show()
        self.settle()
        window.view.scale(3, 3)
        window.view.centerOn(QPointF(-1000, -1000))
        window.load_starter_document(card_document())
        self.settle()
        self.assert_fitted(window)

    def test_organogram_opening_fits_whole_board(self):
        window = self.editor(board=True)
        window.show()
        self.settle()
        self.assert_fitted(window)
        self.assertGreater(window._get_content_rect(for_fit=True).width(), 590)

    def test_opening_from_maximized_workspace_uses_transferred_size(self):
        workspace = QMainWindow()
        self.addCleanup(workspace.deleteLater)
        workspace.showMaximized()
        self.settle()
        window = self.editor(workspace=workspace)
        window.show()
        self.settle()
        self.assertTrue(window.isMaximized())
        self.assert_fitted(window)

    def test_resize_during_edit_does_not_reset_user_zoom(self):
        window = self.editor()
        window.show()
        self.settle()
        window.view.scale(2, 2)
        window.view.centerOn(QPointF(350, 450))
        scale = window.view.transform().m11()
        with patch.object(window, "_zoom_to_fit", wraps=window._zoom_to_fit) as fit:
            window.resize(1550, 990)
            self.settle()
        self.assertEqual(fit.call_count, 0)
        self.assertEqual(window.view.transform().m11(), scale)


if __name__ == "__main__":
    unittest.main()
