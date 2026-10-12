"""Primeiro uso, exclusão do exemplo e aviso sem modelo exportável."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from core.initial_library import ensure_initial_library
from core.fornax_container import save_public_fornax, open_public_fornax
from core.paths import get_models_dir
from core.resources import PROJECT_ROOT
from core.ui_font import install_ui_font
from core.starter_templates import starter_catalog, model_from_starter
from core.model_document import adapt_model_page
from features.generator.renderer import NativeRenderer
from features.workspace.main_window import MainWindow
from scripts.release_tools import selected_files
from test_organogram import card_document


class InitialLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        install_ui_font(cls.app)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        self.enterContext(patch('features.workspace.main_window.get_app_settings', return_value=settings))

    def window(self):
        w = MainWindow()
        self.addCleanup(w.close)
        return w

    def test_first_use_has_one_public_birthday_model_matching_the_gallery(self):
        w = self.window()
        self.assertEqual(w.preview_panel.cbo_models.count(), 1)
        entry = w._current_library_entry()
        self.assertTrue(entry.is_fornax)
        opened = open_public_fornax(entry.path)
        document = opened.document()
        self.assertEqual(document['name'], 'Cartão de aniversário de pessoal')
        self.assertCountEqual(document['placeholders'], ['nome', 'data', 'cargo'])
        self.assertEqual(document['target_w_mm'], 148)
        self.assertEqual(document['target_h_mm'], 105)
        self.assertTrue(document['pages'][0]['images'])
        self.assertFalse(document['pages'][0]['signatures'])
        template = next(item for item in starter_catalog('model') if item.id == 'personnel')
        source = open_public_fornax(template.path)
        digest = lambda content: hashlib.sha256(content).hexdigest()
        self.assertCountEqual([digest(opened.asset(ref)) for ref in opened.asset_references],
                              [digest(source.asset(ref)) for ref in source.asset_references])
        expected, provider = model_from_starter(template)
        self.assertEqual(NativeRenderer(adapt_model_page(document), asset_provider=opened.asset)
                         .render_preview_image(max_side=600),
                         NativeRenderer(adapt_model_page(expected), asset_provider=provider)
                         .render_preview_image(max_side=600))
        self.assertFalse(w.preview_panel.preview._pixmap.isNull())
        self.assertTrue(w.btn_generate_cards.isEnabled())

    def test_existing_library_is_preserved_and_initialized_without_inserting_example(self):
        path = get_models_dir() / 'mine.fornax'
        save_public_fornax(card_document(), path)
        original = path.read_bytes()
        self.assertFalse(ensure_initial_library(path.parent))
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(path.read_bytes(), original)
        path.unlink()
        self.assertFalse(ensure_initial_library(path.parent))
        self.assertEqual(list(path.parent.iterdir()), [])

    def test_deleting_last_model_shows_notice_and_remains_empty_after_restart(self):
        w = self.window()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            w._on_remove_model()
        self.assertEqual(w.preview_panel.cbo_models.count(), 0)
        self.assertIs(w.preview_panel.preview_stack.currentWidget(), w.preview_panel.empty_library)
        self.assertTrue(w.preview_panel.navigation_widget.isHidden())
        self.assertIsNone(w.cached_model_data)
        self.assertIsNone(w.cached_model_document)
        self.assertFalse(w.btn_generate_cards.isEnabled())
        self.assertFalse(w.btn_config_model.isEnabled())
        self.assertFalse(w._model_actions_button.isEnabled())
        self.assertFalse(w._output_config_action.isEnabled())
        with patch.object(w, '_scrape_table_data') as scrape:
            w._generate_cards_async()
        scrape.assert_not_called()
        w.close()
        reopened = self.window()
        self.assertEqual(reopened.preview_panel.cbo_models.count(), 0)
        self.assertIs(reopened.preview_panel.preview_stack.currentWidget(), reopened.preview_panel.empty_library)
        self.assertTrue(reopened._new_model_action.isEnabled())

    def test_creating_or_importing_model_replaces_notice_and_reenables_actions(self):
        directory = get_models_dir()
        ensure_initial_library(directory)
        for path in directory.iterdir():
            path.unlink()
        w = self.window()
        with patch('features.editor.starter_dialog.StarterDialog') as choose:
            choose.return_value.exec.return_value = QDialog.DialogCode.Rejected
            w.preview_panel.btn_create_model.click()
        choose.assert_called_once_with('model', w)
        path = directory / 'new.fornax'
        save_public_fornax(card_document(), path)
        w._reload_models_from_disk()
        self.assertIs(w.preview_panel.preview_stack.currentWidget(), w.preview_panel.preview)
        self.assertFalse(w.preview_panel.navigation_widget.isHidden())
        self.assertTrue(w.btn_generate_cards.isEnabled())
        self.assertTrue(w.btn_config_model.isEnabled())
        self.assertTrue(w._model_actions_button.isEnabled())

    def test_release_selection_contains_only_official_starters_and_no_user_library(self):
        files = selected_files()
        self.assertIn(PROJECT_ROOT / 'assets/templates/models/birthday-personnel.fornax', files)
        fornax = [p.relative_to(PROJECT_ROOT).as_posix() for p in files if p.suffix == '.fornax']
        self.assertEqual(len(fornax), 5)
        self.assertTrue(all(path.startswith('assets/templates/models/') for path in fornax))
        self.assertFalse(any(p.is_relative_to(get_models_dir()) for p in files))

    def test_example_can_be_recreated_only_by_explicitly_resetting_initialization(self):
        directory = get_models_dir()
        self.assertTrue(ensure_initial_library(directory))
        self.assertFalse(ensure_initial_library(directory))
        self.assertEqual(len(list(directory.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
