"""A recuperação automática preserva a edição e os gestos em andamento."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QImage, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.fornax_container import (
    PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE, inspect_fornax,
    save_public_fornax, save_protected_fornax,
)
from core.fornax_session import FornaxSessionManager
from core.model_document import normalize_model_document
from features.editor.canvas_items import DesignerBox, RectangleItem
from features.editor.editor_window import EditorWindow


class EditorAutosaveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch("core.paths._data_home", return_value=self.root / "data"))

    def editor(self, mode=PUBLIC_MODE):
        image = QImage(12, 12, QImage.Format.Format_ARGB32)
        image.fill(QColor("red"))
        asset = self.root / "image.png"
        self.assertTrue(image.save(str(asset)))
        image.fill(QColor("blue"))
        signature = self.root / "signature.png"
        self.assertTrue(image.save(str(signature)))
        document = normalize_model_document({
            "name": "Convite", "canvas_size": {"w": 1000, "h": 1000},
            "boxes": [{"x": 150, "y": 150, "w": 600, "h": 160,
                       "html": "<p>Convite:</p>", "rich_text_version": 1, "layer_id": 1}],
            "images": [{"path": str(asset), "x": 20, "y": 20,
                        "width": 50, "height": 50, "layer_id": 2}],
            "shapes": [{"x": 150, "y": 500, "width": 300, "height": 200,
                        "shape_type": "rectangle", "layer_id": 3}],
            "signatures": [{"path": str(signature), "x": 800, "y": 800,
                            "width": 50, "height": 50, "signature_id": "director", "layer_id": 4}],
            "protection_preferences": {"public_signatures_acknowledged": True},
        })
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        path = self.root / f"{mode}.fornax"
        if mode == PUBLIC_MODE:
            save_public_fornax(document, path)
            status = sessions.select(path)
        else:
            save_protected_fornax(document, path, "senha-de-teste", mode=mode)
            status = sessions.unlock(path, "senha-de-teste")
        window = EditorWindow()
        self.addCleanup(self.close_editor, window)
        window.load_from_fornax(sessions.document(), path=path, mode=mode,
                                model_id=status.descriptor.model_id, asset_provider=sessions.asset,
                                session_manager=sessions)
        window.show()
        window.activateWindow()
        self.app.processEvents()
        window._zoom_to_fit()
        return window, sessions, path

    def close_editor(self, window):
        window._autosave_timer.stop()
        window._finish_page_interaction()
        window._last_saved_state = window.get_current_scene_state()
        window._last_saved_document_state = window._capture_document_history_state()
        window.close()
        self.app.processEvents()

    def begin_typing(self, window):
        box = next(item for item in window.scene.items() if isinstance(item, DesignerBox))
        window.canvas_edit.begin(box)
        QTest.keyClicks(window.view.viewport(), " cerimonia formal")
        self.app.processEvents()
        self.assertTrue(box.text_item.hasFocus())
        return box

    def test_timer_writes_current_text_and_assets_without_ending_editing_in_any_protection_mode(self):
        for mode in (PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE):
            with self.subTest(mode=mode):
                window, sessions, path = self.editor(mode)
                original = path.read_bytes()
                box = self.begin_typing(window)
                cursor = box.text_item.textCursor()
                cursor.setPosition(9)
                cursor.setPosition(18, QTextCursor.MoveMode.KeepAnchor)
                box.text_item.setTextCursor(cursor)
                position, anchor = cursor.position(), cursor.anchor()
                undo_steps = box.text_item.document().availableUndoSteps()
                history_index = window.history._current_index
                html = box.state.html_content
                before = window.canvas_edit.before
                window._autosave_timer.timeout.emit()
                self.app.processEvents()
                self.assertIs(window.canvas_edit.box, box)
                self.assertTrue(box.text_item.hasFocus())
                self.assertEqual((box.text_item.textCursor().position(), box.text_item.textCursor().anchor()),
                                 (position, anchor))
                self.assertEqual(box.state.html_content, html)
                self.assertEqual(window.canvas_edit.before, before)
                self.assertEqual(box.text_item.document().availableUndoSteps(), undo_steps)
                self.assertEqual(window.history._current_index, history_index)
                recovery = window.fornax_recovery_path(path)
                self.assertEqual(inspect_fornax(recovery).mode, mode)
                opened = sessions.read_recovery(recovery, path=path)
                saved = opened.document()
                self.assertEqual(saved["pages"][0]["boxes"][0]["html"], html)
                reference = saved["pages"][0]["images"][0]["path"]
                self.assertEqual(opened.asset(reference), (self.root / "image.png").read_bytes())
                self.assertEqual(path.read_bytes(), original)
                cursor = box.text_item.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                box.text_item.setTextCursor(cursor)
                QTest.keyClicks(window.view.viewport(), " completa")
                self.assertEqual(box.text_item.toPlainText(), "Convite: cerimonia formal completa")

    def test_unchanged_document_does_not_create_recovery(self):
        window, _sessions, path = self.editor()
        window._autosave_timer.timeout.emit()
        self.assertFalse(window.fornax_recovery_path(path).exists())

    def test_recovery_write_error_does_not_interrupt_typing(self):
        window, sessions, _path = self.editor()
        box = self.begin_typing(window)
        with patch.object(sessions, "write_recovery", side_effect=OSError("Disco indisponível")), \
             patch("builtins.print") as warning:
            window._autosave_timer.timeout.emit()
        warning.assert_called_once()
        self.assertIs(window.canvas_edit.box, box)
        self.assertTrue(box.text_item.hasFocus())
        QTest.keyClicks(window.view.viewport(), " continua")
        self.assertEqual(box.text_item.toPlainText(), "Convite: cerimonia formal continua")

    def test_timer_defers_recovery_during_mouse_gesture_and_saves_after_release(self):
        window, _sessions, path = self.editor()
        self.begin_typing(window)
        window.canvas_edit.finish()
        rectangle = next(item for item in window.scene.items()
                         if isinstance(item, RectangleItem) and item.layer_id == 3)
        start = window.view.mapFromScene(rectangle.mapToScene(rectangle.rect().center()))
        QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        self.assertIsNotNone(window.scene.mouseGrabberItem())
        window._autosave_timer.timeout.emit()
        self.assertFalse(window.fornax_recovery_path(path).exists())
        self.assertEqual(window.view._pointer_buttons, Qt.MouseButton.LeftButton)
        self.assertIsNotNone(window.scene.mouseGrabberItem())
        QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(10, 10))
        window._autosave_timer.timeout.emit()
        self.assertTrue(window.fornax_recovery_path(path).exists())


if __name__ == "__main__":
    unittest.main()
