"""Escolha, edição e distribuição dos exemplos sem alterar modelos existentes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow
from core.fornax_container import save_public_fornax, open_public_fornax
from core.model_document import add_blank_back_page, ModelValidationError
from core.organogram import group_rect
from core.board_borders import bordered_group_bounds, border_style
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
        self.pick("personnel-board", columns=4, rows=10)
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
        self.assertEqual(len(window._model_document["organogram"]["boxes"]), 1)

    def test_new_structures_offer_distinct_purposes_and_styles_survive_editor_and_save(self):
        expected = {
            "personnel-board": (20, 0), "command-responsibilities": (5, 4),
            "sectors-teams": (22, 6), "classes-groups": (21, 0),
            "activity-team": (19, 3),
        }
        self.assertEqual([template.id for template in starter_catalog("organogram")], list(expected))
        for template in starter_catalog("organogram"):
            with self.subTest(template=template.id):
                document = organogram_from_starter(fixtures.card_document(), template)
                board = document["organogram"]
                slots = sum(group["columns"] * group["rows"] for group in board["groups"])
                self.assertEqual((slots, len(board["connections"])), expected[template.id])
                self.assertEqual(board["connector_style"]["width_mm"], 1.25)
                self.assertEqual(board["connector_style"]["radius_mm"], 15)
                self.assertEqual(len(board["boxes"]), 1)
                title = board["boxes"][0]
                self.assertFalse(title["locked"])
                self.assertIn(title["object_id"], board["layer_order"])
                for group in board["groups"]:
                    outline = border_style(group)
                    self.assertTrue(outline["cards"])
                    self.assertEqual(border_style(group, "cards")["width_mm"], 1)
                    self.assertEqual(outline["group"], group["columns"] * group["rows"] > 1)
                window = self.editor(document)
                window.switch_model_page("organogram")
                current = window._document_with_active_page()
                # O editor acrescenta metadados opcionais à caixa de texto;
                # o conteúdo, a geometria e o acabamento precisam permanecer.
                for key, value in board.items():
                    if key == "connections":
                        self.assertCountEqual(current["organogram"][key], value)
                    elif key != "boxes":
                        self.assertEqual(current["organogram"][key], value)
                self.assertEqual(len(current["organogram"]["boxes"]), 1)
                for key, value in title.items():
                    self.assertEqual(current["organogram"]["boxes"][0][key], value)
                self.assertEqual(starter_thumbnail(current).toImage(), starter_thumbnail(document).toImage())
                current["name"] = "Minha estrutura"
                destination = self.root / f"{template.id}.fornax"
                save_public_fornax(current, destination)
                self.assertEqual(open_public_fornax(destination).document()["organogram"], current["organogram"])

    def test_decorated_layouts_keep_titles_and_outlines_clear_for_different_card_ratios(self):
        for dimensions in ((590, 826), (826, 590), (590, 1770)):
            document = fixtures.card_document()
            document["canvas_size"].update(w=dimensions[0], h=dimensions[1])
            for template in starter_catalog("organogram"):
                with self.subTest(dimensions=dimensions, template=template.id):
                    board = organogram_from_starter(document, template)["organogram"]
                    title = board["boxes"][0]
                    title_rect = QRectF(title["x"], title["y"], title["w"], title["h"])
                    for index, group in enumerate(board["groups"]):
                        bounds = bordered_group_bounds(group)
                        self.assertFalse(title_rect.intersects(bounds))
                        self.assertFalse(any(bounds.intersects(bordered_group_bounds(other))
                                             for other in board["groups"][index + 1:]))
        template = starter_catalog("organogram")[0]
        small = organogram_from_starter(document, template, columns=1, rows=1)
        self.assertLess(small["organogram"]["boxes"][0]["font_size"], 90)
        self.assertFalse(starter_thumbnail(small).isNull())

    def test_external_version_one_structure_remains_supported(self):
        source = self.root / "legacy.json"
        source.write_text(json.dumps({"preset_version": 1,
            "groups": [{"name": "Equipe", "columns": 2, "rows": 2, "level": 0, "column": 0}],
            "connections": []}), encoding="utf-8")
        template = StarterTemplate("legacy", "organogram", "Estrutura antiga", "", source)
        board = organogram_from_starter(fixtures.card_document(), template)["organogram"]
        self.assertEqual(board["groups"][0]["name"], "Equipe")
        self.assertEqual(board["boxes"], [])

    def test_revised_command_structure_has_central_responsible_and_four_surrounding_cards(self):
        template = next(t for t in starter_catalog("organogram") if t.id == "command-responsibilities")
        board = organogram_from_starter(fixtures.card_document(), template)["organogram"]
        groups = {group["name"]: group for group in board["groups"]}
        principal = groups["Responsável principal"]
        center = group_rect(principal).center()
        left = group_rect(groups["Responsável da área 1"]).center()
        below = group_rect(groups["Responsável da área 2"]).center()
        above = group_rect(groups["Responsável da área 3"]).center()
        right = group_rect(groups["Substituto"]).center()
        self.assertLess(left.x(), center.x())
        self.assertGreater(right.x(), center.x())
        self.assertAlmostEqual(left.y(), center.y())
        self.assertAlmostEqual(right.y(), center.y())
        self.assertLess(above.y(), center.y())
        self.assertGreater(below.y(), center.y())
        self.assertAlmostEqual(above.x(), center.x())
        self.assertAlmostEqual(below.x(), center.x())
        self.assertCountEqual(principal["entry_sides"], ["top", "right", "bottom", "left"])
        self.assertEqual(groups["Substituto"]["exit_sides"], ["left"])
        self.assertCountEqual(groups["Responsável da área 3"]["exit_sides"], ["top", "bottom"])
        self.assertTrue(all(edge["source"] == principal["id"] for edge in board["connections"]))
        title = board["boxes"][0]
        outer_width = max(bordered_group_bounds(g).right() for g in groups.values()) - min(
            bordered_group_bounds(g).left() for g in groups.values())
        self.assertGreater(title["w"], outer_width)

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
