"""Run with: python -m unittest discover -s tests -p test_window_handoff.py."""

import os
import sys
import unittest

# Use the real Windows backend by default: offscreen does not reproduce native
# client-area / QWidget size mismatches. Other platforms can run headlessly.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from features.editor.editor_window import EditorWindow


class HandoffEditor(EditorWindow):
    """Exercise the editor lifecycle without model loading or user settings."""

    def __init__(self, workspace):
        QMainWindow.__init__(self)
        self._workspace_window = workspace
        self._workspace_session_active = False
        self.setCentralWidget(QWidget())
        self.state_at_show = None

    def _zoom_to_fit(self):
        self.state_at_show = self.windowState()


class WindowHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.workspace = QMainWindow()
        self.workspace.setCentralWidget(QWidget())
        self.placement = QRect(50, 60, 520, 360)
        self.workspace.setGeometry(self.placement)
        self.editor = HandoffEditor(self.workspace)

    def tearDown(self):
        self.editor.hide()
        self.workspace.hide()
        self.editor.deleteLater()
        self.workspace.deleteLater()
        self.app.processEvents()

    def assert_fills_window(self, window):
        self.app.processEvents()
        self.assertEqual(window.centralWidget().geometry(), window.contentsRect())
        if sys.platform == "win32" and self.app.platformName() == "windows":
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            get_client_rect = ctypes.windll.user32.GetClientRect
            get_client_rect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            get_client_rect.restype = wintypes.BOOL
            self.assertTrue(get_client_rect(int(window.winId()), ctypes.byref(rect)))
            scale = window.devicePixelRatioF()
            self.assertAlmostEqual(window.width() * scale, rect.right - rect.left, delta=1)
            self.assertAlmostEqual(window.height() * scale, rect.bottom - rect.top, delta=1)

    def return_to_workspace(self):
        self.editor._release_workspace_window()
        self.editor.hide()
        self.app.processEvents()
        self.assertTrue(self.workspace.isVisible())
        self.assertFalse(self.editor._workspace_session_active)
        self.assert_fills_window(self.workspace)

    def test_repeated_maximized_round_trips(self):
        self.workspace.showMaximized()
        self.app.processEvents()
        for _ in range(3):
            self.editor.show()
            self.app.processEvents()
            self.assertFalse(self.workspace.isVisible())
            self.assertTrue(self.editor.isMaximized())
            self.assertTrue(self.editor.state_at_show & Qt.WindowState.WindowMaximized)
            self.assert_fills_window(self.editor)
            self.return_to_workspace()
            self.assertTrue(self.workspace.isMaximized())
            self.workspace.showNormal()
            self.app.processEvents()
            self.assertEqual(self.workspace.geometry(), self.placement)
            self.workspace.showMaximized()
            self.app.processEvents()

    def test_normal_editor_resize_transfers_back(self):
        self.workspace.showMaximized()
        self.app.processEvents()
        self.editor.show()
        self.app.processEvents()
        self.editor.showNormal()
        self.app.processEvents()
        changed = QRect(80, 90, 600, 400)
        self.editor.setGeometry(changed)
        self.app.processEvents()
        self.return_to_workspace()
        self.assertFalse(self.workspace.isMaximized())
        self.assertEqual(self.workspace.geometry(), changed)

    def test_restore_editor_then_reopen_and_close(self):
        self.workspace.showMaximized()
        self.app.processEvents()
        self.editor.show()
        self.app.processEvents()
        self.editor.showNormal()
        self.app.processEvents()
        self.assert_fills_window(self.editor)
        self.return_to_workspace()
        self.assertFalse(self.workspace.isMaximized())
        self.assertEqual(self.workspace.geometry(), self.placement)

        for _ in range(3):
            self.editor.show()
            self.app.processEvents()
            self.assert_fills_window(self.editor)
            self.return_to_workspace()
            self.assertFalse(self.workspace.isMaximized())
            self.assertEqual(self.workspace.geometry(), self.placement)

    def test_maximize_editor_transfers_back(self):
        self.workspace.show()
        self.editor.show()
        self.editor.showMaximized()
        self.return_to_workspace()
        self.assertTrue(self.workspace.isMaximized())

    def test_fullscreen_round_trip(self):
        self.workspace.showFullScreen()
        self.editor.show()
        self.assertTrue(self.editor.isFullScreen())
        self.return_to_workspace()
        self.assertTrue(self.workspace.isFullScreen())

    def test_minimized_editor_does_not_minimize_workspace(self):
        self.workspace.showMaximized()
        self.editor.show()
        self.editor.showMinimized()
        self.return_to_workspace()
        self.assertFalse(self.workspace.isMinimized())
        self.assertTrue(self.workspace.isMaximized())


if __name__ == "__main__":
    unittest.main()
