"""Preferências de exibição sobrevivem ao fechamento e à reabertura da janela."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from shiboken6 import isValid
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtWidgets import QApplication

from features.workspace.main_window import MainWindow
from core.version import APP_VERSION


class WorkspacePreferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings_path = self.root / 'settings.ini'
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))
        # Keep real Qt slots while isolating the user's model library.
        self.enterContext(patch.object(MainWindow, '_ensure_starter_pack', lambda self: None))
        self.enterContext(patch.object(MainWindow, '_reload_models_from_disk', lambda self, **kwargs: None))

    def window(self):
        settings = QSettings(str(self.settings_path), QSettings.Format.IniFormat)
        with patch('features.workspace.main_window.get_app_settings', return_value=settings):
            window = MainWindow()
        self.addCleanup(self.dispose, window)
        window.show()
        self.app.processEvents()
        return window

    def dispose(self, window):
        if isValid(window):
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def test_first_start_keeps_log_hidden_and_menu_unchecked(self):
        window = self.window()
        self.assertFalse(window._workspace_log_toggle.isChecked())
        self.assertFalse(window.log_panel.isVisible())

    def test_about_displays_current_product_version(self):
        window = self.window()
        with patch('features.workspace.frontend.QMessageBox.about') as about:
            window._tutorial_menu.actions()[-2].trigger()
        about.assert_called_once()
        self.assertIn(APP_VERSION, about.call_args.args[2])

    def test_main_title_has_only_one_application_name_at_the_end(self):
        previous = self.app.applicationDisplayName()
        self.addCleanup(self.app.setApplicationDisplayName, previous)
        self.app.setApplicationDisplayName('FORNAX Forge')
        window = self.window()
        self.assertEqual(window.windowTitle().count('FORNAX Forge'), 1)
        self.assertTrue(window.windowTitle().endswith(self.app.applicationDisplayName()))

    def test_show_log_is_restored_after_closing_and_reopening(self):
        window = self.window()
        window._workspace_log_toggle.trigger()
        self.assertTrue(window.log_panel.isVisible())
        window.close()
        reopened = self.window()
        self.assertTrue(reopened._workspace_log_toggle.isChecked())
        self.assertTrue(reopened.log_panel.isVisible())
        settings = QSettings(str(self.settings_path), QSettings.Format.IniFormat)
        self.assertTrue(settings.value('workspaceLogVisible', False, type=bool))

    def test_hide_log_is_also_restored_after_reopening(self):
        settings = QSettings(str(self.settings_path), QSettings.Format.IniFormat)
        settings.setValue('workspaceLogVisible', True)
        settings.sync()
        window = self.window()
        self.assertTrue(window.log_panel.isVisible())
        window._workspace_log_toggle.trigger()
        self.assertFalse(window.log_panel.isVisible())
        window.close()
        reopened = self.window()
        self.assertFalse(reopened._workspace_log_toggle.isChecked())
        self.assertFalse(reopened.log_panel.isVisible())
        self.assertFalse(reopened.settings.value('workspaceLogVisible', True, type=bool))


if __name__ == '__main__':
    unittest.main()
