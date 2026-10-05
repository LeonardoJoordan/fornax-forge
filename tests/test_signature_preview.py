"""Regressões da prévia após colagem e salvamento de modelos .fornax."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QMainWindow, QWidget

from core.fornax_container import (
    FULL_MODE, PUBLIC_MODE, SIGNATURES_MODE, save_protected_fornax, save_public_fornax,
)
from core.fornax_session import FornaxSessionManager
from core.image_memory_cache import ImageMemoryCache
from core.model_document import normalize_model_document
from core.model_library import LibraryModel
from features.generator.renderer import renderers_for_document
from features.preview.preview_panel import PreviewPanel
from features.spreadsheet.table_panel import RichTableWidget
from features.workspace.main_window import MainWindow


class PreviewWorkspace(MainWindow):
    """Usa o fluxo real de prévia sem abrir a biblioteca/preferências do usuário."""

    def __init__(self, path, sessions, settings):
        QMainWindow.__init__(self)
        self.settings = settings
        self._fornax_sessions = sessions
        self.preview_panel = PreviewPanel()
        self.preview_panel.setParent(self)
        self.table_panel = SimpleNamespace(
            table=RichTableWidget(self), dynamic_image_footer=QWidget(self),
            txt_dynamic_image_dir=QLineEdit(self), lbl_dynamic_image_status=QLabel(self),
        )
        self.log_panel = SimpleNamespace(append=lambda message: None)
        self.cbo_export_format = QComboBox(self)
        self.cbo_export_format.addItem("PNG", "png")
        self._export_mode_tooltips = {}
        self.cbo_presets_main = QComboBox(self)
        self._presets_main_base_tooltip = ""
        self._preview_mode = "item"
        self._preview_item_index = self._preview_page_index = 0
        self._selecting_preview_item = False
        self._sheet_preview_revision = 0
        self._sheet_preview_paths = {}
        self._sheet_preview_worker = self._sheet_preview_dir = None
        self._preview_renderers = []
        self.cached_model_data = self.cached_model_document = None
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(100)
        self._preview_refresh_timer.timeout.connect(self._refresh_preview_after_data_change)
        table = self.table_panel.table
        table.itemSelectionChanged.connect(self._on_table_selection)
        table.itemChanged.connect(self._on_preview_data_changed)
        table.signatureColumnToggled.connect(lambda *_: self._on_preview_data_changed())
        table.model().rowsInserted.connect(self._on_preview_rows_changed)
        table.model().rowsRemoved.connect(self._on_preview_rows_changed)
        status = sessions.status(path)
        self.active_model_name = "Teste de assinatura"
        model = LibraryModel("test", self.active_model_name, path, "fornax", status.descriptor)
        self._active_library_model = model
        self._library_models_by_key = {model.key: model}
        self.preview_panel.cbo_models.addItem(model.display_name, model.key)
        self._load_fornax_document(sessions.document(), sessions.asset, status)


class SignaturePreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(patch("core.paths._data_home", return_value=self.root / "data"))
        warning = patch(
            "features.workspace.main_window.QMessageBox.warning",
            side_effect=lambda parent, title, message: self.fail(message),
        )
        warning.start()
        self.addCleanup(warning.stop)

    def make_workspace(self, mode, *, saved_preset=True):
        pages = []
        for face, color in (("front", "red"), ("back", "blue")):
            image = QImage(20, 20, QImage.Format.Format_ARGB32)
            image.fill(QColor(color))
            path = self.root / f"{face}.png"
            self.assertTrue(image.save(str(path)))
            page = normalize_model_document({
                "name": "Teste de assinatura", "canvas_size": {"w": 200, "h": 150},
                "placeholders": ["Nome"],
                "boxes": [{"html": "{Nome}", "x": 10, "y": 10, "w": 150, "h": 30}],
                "signatures": [{
                    "path": str(path), "signature_id": face,
                    "x": 20, "y": 90, "width": 20, "height": 20,
                }],
            })
            page["pages"][0]["page_id"] = face
            pages.append(page["pages"][0])
        document = page
        document["pages"] = pages
        document["protection_preferences"] = {"public_signatures_acknowledged": True}
        if saved_preset:
            document["imposition_settings"] = {
                "enabled": False, "active_preset_name": MainWindow.SYSTEM_IMPOSITION_PRESET,
            }
        target = self.root / f"{mode}.fornax"
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        if mode == PUBLIC_MODE:
            save_public_fornax(document, target)
            sessions.select(target)
        else:
            save_protected_fornax(document, target, "senha-de-teste", mode=mode)
            sessions.unlock(target, "senha-de-teste")
        settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        window = PreviewWorkspace(target, sessions, settings)
        self.addCleanup(self.dispose_workspace, window)
        return window

    def dispose_workspace(self, window):
        window._preview_refresh_timer.stop()
        window.deleteLater()
        self.app.processEvents()

    def assert_signature(self, window, visible, color="red"):
        # Aguarda a atualização disparada pelos sinais da tabela.
        QTest.qWait(150)
        pixmap = window.preview_panel.preview._pixmap
        self.assertIsNotNone(pixmap)
        expected = QColor(color if visible else "white")
        self.assertEqual(pixmap.toImage().pixelColor(25, 95), expected)

    def test_paste_and_toggle_after_saving_with_uncached_assets(self):
        for mode in (PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE):
            with self.subTest(mode=mode):
                window = self.make_workspace(mode)
                table = window.table_panel.table
                # Um cache limitado/evicto também precisa conseguir reler os assets.
                for renderer in window._preview_renderers:
                    renderer._image_cache = ImageMemoryCache(max_bytes=0)
                table.setCurrentCell(0, 1)
                self.assert_signature(window, True)
                table.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
                self.assert_signature(window, False)
                table.setCurrentCell(0, 3)
                self.app.clipboard().setText("Ana\nBruno\nCarla")
                table._paste_from_clipboard()
                self.assertEqual(table.rowCount(), 3)
                window._update_template_json({"last_export_mode": "png"})
                for row in range(3):
                    table.setCurrentCell(row, 1)
                    table.item(row, 1).setCheckState(Qt.CheckState.Checked)
                    self.assert_signature(window, True)
                    table.item(row, 1).setCheckState(Qt.CheckState.Unchecked)
                    self.assert_signature(window, False)
                table.toggle_signature_column(1)
                self.assert_signature(window, True)
                # A assinatura do verso deve continuar independente da frente.
                window._on_preview_page_changed(1)
                self.assert_signature(window, True, "blue")
                table.item(2, 2).setCheckState(Qt.CheckState.Unchecked)
                self.assert_signature(window, False, "blue")
                window._on_preview_page_changed(0)
                self.assert_signature(window, True)
                plain, rich = window._scrape_table_data()
                snapshot = window._fornax_sessions.borrow_job()
                try:
                    renderers = renderers_for_document(snapshot.document(), asset_provider=snapshot.asset)
                    for face, color in enumerate(("red", "white")):
                        image = renderers[face].render_to_qimage(plain[2], rich[2])
                        self.assertEqual(image.pixelColor(25, 95), QColor(color))
                finally:
                    snapshot.close()

    def test_initial_preset_save_keeps_signatures_visible(self):
        window = self.make_workspace(SIGNATURES_MODE, saved_preset=False)
        window.table_panel.table.setCurrentCell(0, 1)
        self.assert_signature(window, True)
        window._on_preview_page_changed(1)
        self.assert_signature(window, True, "blue")

    def test_save_preserves_selected_face_and_dynamic_image_directory(self):
        window = self.make_workspace(SIGNATURES_MODE)
        window.table_panel.table.setCurrentCell(0, 1)
        window._on_preview_page_changed(1)
        window.cached_model_document["__dynamic_image_dir"] = str(self.root)
        window._update_template_json({"last_export_mode": "pdf_item"})
        self.assertEqual(window._preview_page_index, 1)
        self.assertEqual(window.preview_renderer.page_id, "back")
        self.assertEqual(window.preview_renderer.dynamic_image_dir, str(self.root))
        self.assert_signature(window, True, "blue")


if __name__ == "__main__":
    unittest.main()
