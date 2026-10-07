"""Escolha, edição e distribuição dos exemplos sem alterar modelos existentes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow
from core.fornax_container import save_public_fornax, open_public_fornax
from core.model_document import add_blank_back_page, ModelValidationError
from core.organogram import group_rect
from core.starter_templates import starter_catalog, model_from_starter, organogram_from_starter, StarterTemplate
from features.editor.starter_dialog import StarterDialog, starter_thumbnail
from features.workspace.main_window import MainWindow
from scripts.release_tools import selected_files
import test_organogram as fixtures


class StarterTemplatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch("core.paths._data_home", return_value=self.root / "data"))

    editor = fixtures.OrganogramTest.editor

    def pick(self, identity, *, columns=None, rows=None, cancel=False):
        def choose():
            dialog = self.app.activeModalWidget()
            if cancel:
                dialog.reject()
                return
            for row in range(dialog.gallery.count()):
                if dialog.gallery.item(row).data(Qt.ItemDataRole.UserRole) == identity:
                    dialog.gallery.setCurrentRow(row)
                    break
            if columns is not None:
                dialog.columns.setValue(columns)
            if rows is not None:
                dialog.rows.setValue(rows)
            dialog.accept()
        QTimer.singleShot(0, choose)

    def test_all_bundled_models_open_as_unnamed_editable_independent_copies(self):
        self.assertEqual(len(starter_catalog("model")), 5)
        self.assertNotIn("class", [template.id for template in starter_catalog("model")])
        self.assertEqual(starter_catalog("model")[-1].id, "corporate-organogram")
        for template in starter_catalog("model"):
            with self.subTest(template=template.id):
                original = template.path.read_bytes()
                document, provider = model_from_starter(template)
                self.assertEqual(document["name"], "")
                self.assertGreater(len(document["pages"][0]["boxes"]), 0)
                self.assertFalse(starter_thumbnail(document, provider).isNull())
                window = self.editor()
                window.load_starter_document(document, provider)
                self.assertIsNone(window._current_model_name)
                self.assertIsNone(window._fornax_path)
                self.assertIsNone(window._current_model_dir)
                current = window._document_with_active_page()
                self.assertEqual(current["placeholders"], document["placeholders"])
                if document.get("organogram") is not None:
                    self.assertEqual(current["organogram"], document["organogram"])
                self.assertFalse(window._states_equal_for_close(window.get_current_scene_state(), window._last_saved_state))
                current["name"] = "Minha cópia"
                destination = self.root / f"{template.id}.fornax"
                save_public_fornax(current, destination, asset_provider=window._save_asset_provider)
                saved = open_public_fornax(destination)
                self.assertEqual(saved.document()["placeholders"], document["placeholders"])
                if document.get("organogram") is not None:
                    saved_board = saved.document()["organogram"]
                    expected_board = deepcopy(document["organogram"])
                    for image in expected_board["images"]:
                        saved_image = next(entry for entry in saved_board["images"]
                                           if entry["object_id"] == image["object_id"])
                        self.assertEqual(saved.asset(saved_image["path"]), provider(image["path"]))
                        # O novo pacote atribui referências próprias aos mesmos bytes.
                        image["path"] = saved_image["path"]
                    self.assertEqual(saved_board, expected_board)
                self.assertEqual(template.path.read_bytes(), original)

    def test_bundled_structures_keep_front_page_and_have_unique_names_and_nonoverlapping_groups(self):
        document = fixtures.card_document()
        original = deepcopy(document)
        self.assertEqual(len(starter_catalog("organogram")), 5)
        for template in starter_catalog("organogram"):
            with self.subTest(template=template.id):
                result = organogram_from_starter(document, template)
                self.assertEqual(result["pages"], original["pages"])
                self.assertEqual(result["canvas_size"], original["canvas_size"])
                self.assertEqual(result["placeholders"], original["placeholders"])
                self.assertEqual(document, original)
                groups = result["organogram"]["groups"]
                names = [group["name"].casefold() for group in groups]
                self.assertEqual(len(names), len(set(names)))
                for index, group in enumerate(groups):
                    self.assertAlmostEqual(group["card_h"] / group["card_w"], original["canvas_size"]["h"] / original["canvas_size"]["w"])
                    self.assertFalse(any(group_rect(group).intersects(group_rect(other)) for other in groups[index + 1:]))
                self.assertFalse(starter_thumbnail(result).isNull())

    def test_grid_selection_creates_configured_block_and_undo_redo_preserve_card(self):
        window = self.editor(fixtures.card_document())
        front = deepcopy(window._model_document["pages"])
        self.pick("grid", columns=4, rows=10)
        window.add_model_organogram()
        self.assertEqual(window._active_page_id, "organogram")
        self.assertEqual(len(window._board_items()), 1)
        block = window._board_items()[0].data
        self.assertEqual((block["columns"], block["rows"]), (4, 10))
        self.assertEqual(window._model_document["pages"], front)
        window.undo()
        self.assertIsNone(window._model_document.get("organogram"))
        self.assertEqual(window._active_page_id, "front")
        self.assertEqual(window._model_document["pages"], front)
        window.redo()
        self.assertEqual(window._active_page_id, "organogram")
        self.assertEqual(len(window._board_items()), 1)

    def test_cancel_does_not_add_composition_and_blank_remains_available(self):
        window = self.editor(fixtures.card_document())
        previous = deepcopy(window._model_document)
        self.pick(None, cancel=True)
        window.add_model_organogram()
        self.assertEqual(window._model_document, previous)
        self.assertEqual(window._active_page_id, "front")
        self.pick(None)
        window.add_model_organogram()
        self.assertEqual(window._active_page_id, "organogram")
        self.assertEqual(window._board_items(), [])
        with self.assertRaises(ModelValidationError):
            organogram_from_starter(add_blank_back_page(fixtures.card_document()), None)

    def test_new_model_cancel_keeps_workspace_and_does_not_create_editor(self):
        workspace = QMainWindow()
        self.addCleanup(workspace.deleteLater)
        self.pick(None, cancel=True)
        with patch("features.workspace.main_window.EditorWindow") as editor:
            MainWindow._on_add_model(workspace)
            editor.assert_not_called()

    def test_new_model_action_loads_choice_in_a_new_editor(self):
        workspace = QMainWindow()
        self.addCleanup(workspace.deleteLater)
        workspace._on_editor_saved = lambda *_: None
        workspace._connect_editor_lifecycle = lambda: None
        self.pick("personnel")
        MainWindow._on_add_model(workspace)
        editor = workspace.editor_window
        def cleanup():
            editor._last_saved_state = editor.get_current_scene_state()
            editor._last_saved_document_state = editor._capture_document_history_state()
            editor.close()
        self.addCleanup(cleanup)
        source, _provider = model_from_starter(next(
            template for template in starter_catalog("model") if template.id == "personnel"
        ))
        self.assertEqual(editor._model_document["placeholders"], source["placeholders"])
        self.assertCountEqual(editor._model_document["placeholders"], ["nome", "data", "cargo"])
        self.assertIsNone(editor._current_model_name)
        self.assertIsNone(editor._fornax_path)

    def test_grid_limit_is_reported_and_missing_catalog_still_allows_blank(self):
        dialog = StarterDialog("organogram", document=fixtures.card_document())
        self.addCleanup(dialog.deleteLater)
        dialog.gallery.setCurrentRow(1)
        dialog.columns.setValue(100)
        dialog.rows.setValue(100)
        dialog._update_grid_preview()
        self.assertIn("2500", dialog.error.text())
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        dialog.gallery.setCurrentRow(0)
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        with patch("features.editor.starter_dialog.starter_catalog", side_effect=FileNotFoundError("Catálogo ausente")):
            fallback = StarterDialog("model")
            self.addCleanup(fallback.deleteLater)
            self.assertEqual(fallback.gallery.count(), 1)
            fallback.accept()
            self.assertEqual(fallback.result(), QDialog.DialogCode.Accepted)
            self.assertIsNone(fallback.result_document)

    def test_public_fornax_with_images_can_be_used_and_saved_without_changing_source(self):
        document = fixtures.card_document()
        image = QImage(20, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("red"))
        photo = self.root / "photo.png"
        self.assertTrue(image.save(str(photo)))
        document["pages"][0]["images"] = [{"object_id": "photo", "path": str(photo), "x": 0, "y": 0, "width": 50, "height": 50, "layer_id": 4}]
        document["pages"][0]["layer_order"].append("photo")
        source = self.root / "example.fornax"
        save_public_fornax(document, source)
        original = source.read_bytes()
        template = StarterTemplate("custom", "model", "Meu modelo", "", source)
        copied, provider = model_from_starter(template)
        window = self.editor()
        window.load_starter_document(copied, provider)
        self.assertEqual(window._model_document["pages"][0]["images"][0]["path"], copied["pages"][0]["images"][0]["path"])
        current = window._document_with_active_page()
        current["name"] = "Novo modelo"
        destination = self.root / "new.fornax"
        save_public_fornax(current, destination, asset_provider=window._save_asset_provider)
        opened = open_public_fornax(destination)
        reference = opened.document()["pages"][0]["images"][0]["path"]
        self.assertEqual(opened.asset(reference), photo.read_bytes())
        self.assertEqual(source.read_bytes(), original)

    def test_custom_structure_follows_card_proportions_and_packaging_includes_catalog(self):
        original = fixtures.board_document(1, 1)
        original["organogram"]["groups"][0].update(y=1000, gap_y=30)
        source = self.root / "custom.fornax"
        save_public_fornax(original, source)
        template = StarterTemplate("custom", "organogram", "Minha estrutura", "", source)
        card, _ = model_from_starter(starter_catalog("model")[0])
        result = organogram_from_starter(card, template)
        self.assertEqual(result["pages"], card["pages"])
        ratio = (card["canvas_size"]["h"] / card["canvas_size"]["w"]) / (original["canvas_size"]["h"] / original["canvas_size"]["w"])
        self.assertAlmostEqual(result["organogram"]["groups"][0]["y"], 1000 * ratio)
        self.assertAlmostEqual(result["organogram"]["groups"][0]["gap_y"], 30 * ratio)
        files = selected_files()
        self.assertTrue(all(template.path in files for kind in ("model", "organogram") for template in starter_catalog(kind)))
        self.assertTrue(any(path.name == "catalog.json" for path in files))


if __name__ == "__main__":
    unittest.main()
