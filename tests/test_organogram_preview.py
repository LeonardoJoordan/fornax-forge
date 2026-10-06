"""O modo Item usa o cartão; a visualização coletiva usa o quadro completo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.fornax_container import FULL_MODE, save_public_fornax, save_protected_fornax
from core.fornax_session import FornaxSessionManager
from features.generator.organogram import OrganogramRenderer
from test_organogram import board_document
from test_signature_preview import PreviewWorkspace


class OrganogramPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def workspace(self, *, protected=False):
        document = board_document(2, 1)
        target = self.root / ('protected.fornax' if protected else 'public.fornax')
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        if protected:
            save_protected_fornax(document, target, 'senha-de-teste', mode=FULL_MODE)
            sessions.unlock(target, 'senha-de-teste')
        else:
            save_public_fornax(document, target)
            sessions.select(target)
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        window = PreviewWorkspace(target, sessions, settings)
        window._preview_sheet_index = 0
        window.preview_panel.modeChanged.connect(window._on_preview_mode_changed)
        window.preview_panel.indexRequested.connect(window._on_preview_index_requested)
        window.preview_panel.pageChanged.connect(window._on_preview_page_changed)
        def cleanup():
            window._preview_refresh_timer.stop()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def paste(self, window):
        table = window.table_panel.table
        table.setCurrentCell(0, 1)
        name = window.cached_model_document['organogram']['groups'][0]['name']
        self.app.clipboard().setText(f'{name}\tAna\tComandante\n{name}\tBruno\tSubcomandante')
        table._paste_from_clipboard()
        QTest.qWait(150)
        self.assertEqual(table.rowCount(), 2)

    def mode(self, window, mode):
        combo = window.preview_panel.cbo_preview_mode
        self.assertGreaterEqual(combo.findData(mode), 0)
        combo.setCurrentIndex(combo.findData(mode))

    def assert_card(self, window):
        rich = (window._get_row_data_rich(window.table_panel.table.currentRow())
                if window.table_panel.table.currentRow() >= 0 else None)
        expected = window._preview_renderers[0].render_to_pixmap(row_rich=rich, max_side=1600)
        actual = window.preview_panel.preview._pixmap
        self.assertIsNotNone(actual)
        self.assertEqual(actual.toImage(), expected.toImage())
        self.assertEqual(window._preview_mode, 'item')
        self.assertEqual(window.preview_panel.cbo_preview_mode.currentData(), 'item')

    def assert_board(self, window):
        plain, rich = window._scrape_table_data()
        renderer = OrganogramRenderer(
            window.cached_model_document, plain, rich,
            asset_provider=window._fornax_asset_provider,
            dynamic_image_dir=window.table_panel.txt_dynamic_image_dir.text().strip(),
        )
        actual = window.preview_panel.preview._pixmap
        self.assertIsNotNone(actual)
        self.assertEqual(actual.toImage(), QPixmap.fromImage(renderer.preview()).toImage())
        self.assertEqual(window._preview_mode, 'sheet')
        self.assertEqual(window.preview_panel.cbo_preview_mode.currentText(), 'Organograma')
        self.assertEqual(window.preview_panel.lbl_navigation_kind.text(), 'Quadro')
        self.assertFalse(window.preview_panel.btn_next.isEnabled())
        self.assertFalse(window.preview_panel.btn_previous.isEnabled())

    def test_empty_table_initially_shows_page_one_and_offers_whole_chart(self):
        window = self.workspace()
        self.assert_card(window)
        self.assertFalse(window.preview_panel.page_selector.isVisible())
        self.assertTrue(window._sheet_preview_available())
        self.assertEqual(window.preview_panel.cbo_preview_mode.count(), 2)
        self.mode(window, 'sheet')
        self.assertIsNone(window.preview_panel.preview._pixmap)
        self.assertIn('Preencha os dados', window.preview_panel.preview.text())
        self.mode(window, 'item')
        self.assert_card(window)

    def test_item_navigation_and_mode_switch_show_card_and_entire_chart(self):
        window = self.workspace()
        self.paste(window)
        window.table_panel.table.setCurrentCell(0, 1)
        self.assert_card(window)
        self.assertEqual(window.preview_panel.lbl_navigation_total.text(), 'de 2')
        first_card = window.preview_panel.preview._pixmap.toImage()
        window.preview_panel.btn_next.click()
        self.assertEqual(window.table_panel.table.currentRow(), 1)
        self.assert_card(window)
        self.assertNotEqual(window.preview_panel.preview._pixmap.toImage(), first_card)
        self.mode(window, 'sheet')
        self.assert_board(window)
        window.table_panel.table.setCurrentCell(0, 1)
        self.assert_board(window)
        self.mode(window, 'item')
        self.assert_card(window)
        self.assertEqual(window.table_panel.table.currentRow(), 0)

    def test_data_edits_and_saved_revisions_preserve_the_selected_preview_mode(self):
        window = self.workspace()
        self.paste(window)
        self.mode(window, 'sheet')
        window._update_template_json({'last_export_mode': 'pdf_item'})
        QTest.qWait(150)
        self.assert_board(window)
        table = window.table_panel.table
        table.item(1, 2).setText('Carla')
        QTest.qWait(150)
        self.assert_board(window)
        self.mode(window, 'item')
        table.setCurrentCell(1, 1)
        self.assert_card(window)
        table.item(1, 2).setText('Diana')
        QTest.qWait(150)
        self.assert_card(window)

    def test_org_does_not_start_imposition_worker_or_get_replaced_by_late_thumbnail(self):
        window = self.workspace()
        self.paste(window)
        with patch('features.workspace.main_window.SheetPreviewWorker') as worker:
            window._start_sheet_preview_preload()
            self.mode(window, 'sheet')
            window._start_sheet_preview_preload()
            worker.assert_not_called()
        before = window.preview_panel.preview._pixmap.toImage()
        window.table_panel.table.clearSelection()
        window.table_panel.table.setCurrentItem(None)
        thumbnail = self.root / 'card.png'
        self.assertTrue(window._preview_renderers[0].render_to_pixmap().save(str(thumbnail)))
        window._on_preview_ready(window.active_model_name, str(thumbnail))
        self.assertEqual(window.preview_panel.preview._pixmap.toImage(), before)
        self.mode(window, 'item')
        window._on_preview_ready(window.active_model_name, str(thumbnail))
        self.assertEqual(window.preview_panel.preview._pixmap.toImage(), QPixmap(str(thumbnail)).toImage())

    def test_authorized_protected_model_uses_both_preview_modes(self):
        window = self.workspace(protected=True)
        self.assert_card(window)
        self.paste(window)
        self.assert_card(window)
        self.mode(window, 'sheet')
        self.assert_board(window)
        self.mode(window, 'item')
        self.assert_card(window)


if __name__ == '__main__':
    unittest.main()
