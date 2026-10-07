"""Nomes únicos e distribuição real dos dados da planilha entre blocos."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
import zipfile
from unittest.mock import patch

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QDialogButtonBox, QComboBox
from PySide6.QtTest import QTest
from pypdf import PdfReader

from core.fornax_container import save_public_fornax, save_protected_fornax, unlock_fornax, FULL_MODE, open_public_fornax
from core.fornax_session import FornaxSessionManager
from core.organogram import (BLOCK_DESTINATION_KEY, DISABLED_ROW_KEY, new_group,
                            assigned_slots, assignment_plan, row_is_valid)
from core.model_document import ModelValidationError, normalize_model_document
from core.model_library import scan_model_library
from features.generator.organogram import OrganogramRenderer, OrganogramWorker
from features.spreadsheet.headers import is_block_header, table_column_key
from test_signature_preview import PreviewWorkspace
import test_organogram as fixtures


class BlockAssignmentTest(unittest.TestCase):
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

    def document(self):
        document = fixtures.board_document(2, 1)
        board = document["organogram"]
        board["groups"][0]["name"] = "SetorX"
        other = new_group(document, columns=1, rows=1, y=-1500)
        other["name"] = "Comando"
        board["groups"].append(other)
        board["connections"] = [{"source": other["id"], "target": board["groups"][0]["id"]}]
        return document

    def workspace(self, document=None):
        path = self.root / "chart.fornax"
        save_public_fornax(document or self.document(), path)
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        sessions.select(path)
        settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        window = PreviewWorkspace(path, sessions, settings)
        window.table_panel.lbl_board_status = QLabel(window)
        def cleanup():
            window._preview_refresh_timer.stop()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window, path, sessions

    def paste(self, window, text):
        table = window.table_panel.table
        table.setCurrentCell(0, 1)
        self.app.clipboard().setText(text)
        table._paste_from_clipboard()
        window._refresh_preview_after_data_change()
        return table

    def open_block_menu(self, table, row=0):
        table.resize(650, 300)
        table.show()
        self.app.processEvents()
        index = table.model().index(row, 1)
        point = table.visualRect(index).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()
        editor = table.indexWidget(index)
        self.assertIsInstance(editor, QComboBox)
        self.assertTrue(editor.view().isVisible())
        return editor

    def test_single_click_selects_available_block_and_can_clear_destination(self):
        window, _, _ = self.workspace()
        table = window.table_panel.table
        editor = self.open_block_menu(table)
        self.assertFalse(editor.isEditable())
        self.assertEqual([editor.itemData(i) for i in range(editor.count())],
                         ['', 'SetorX', 'Comando'])
        QTest.keyClick(editor.view(), Qt.Key.Key_End)
        QTest.keyClick(editor.view(), Qt.Key.Key_Return)
        self.assertEqual(table.item(0, 1).text(), 'Comando')
        self.assertIsNone(table.item(0, 1).data(table.RICH_ROLE))
        editor = self.open_block_menu(table)
        QTest.keyClick(editor.view(), Qt.Key.Key_Home)
        QTest.keyClick(editor.view(), Qt.Key.Key_Return)
        self.assertEqual(table.item(0, 1).text(), '')

    def test_destination_editor_fits_compact_cell_with_real_workspace_style(self):
        from core.themes import theme_manager, themed_style
        from features.workspace.frontend import STYLE
        document = self.document()
        document['organogram']['groups'][0]['name'] = 'Setor com um nome longo que ultrapassa a largura da coluna'
        window, _, _ = self.workspace(document)
        table = window.table_panel.table
        themed_style(window, STYLE)
        manager = theme_manager()
        previous = manager.theme_id, manager.current
        self.addCleanup(lambda: manager.select(previous[0], previous[1]))
        for theme in ('dark', 'light'):
            manager.select(theme)
            table.setRowHeight(0, 25)
            editor = self.open_block_menu(table)
            cell = table.visualRect(table.model().index(0, 1))
            self.assertTrue(cell.contains(editor.geometry()), (theme, cell, editor.geometry()))
            self.assertLessEqual(editor.view().window().width(), cell.width())
            self.assertEqual(editor.currentIndex(), -1)
            self.assertEqual(editor.placeholderText(), 'Selecione um bloco')
            self.assertIsNone(table.item(0, 1))
            QTest.keyClick(editor.view(), Qt.Key.Key_Escape)
            QTest.keyClick(editor, Qt.Key.Key_Escape)

    def test_repeated_menu_selection_with_application_wheel_guard_has_no_exceptions(self):
        from core.wheel_focus import WheelFocusGuard
        from shiboken6 import isValid
        from PySide6.QtCore import QEvent
        window, _, _ = self.workspace()
        table = window.table_panel.table
        guard = WheelFocusGuard(self.app)
        self.app.installEventFilter(guard)
        self.addCleanup(guard.deleteLater)
        self.addCleanup(lambda: self.app.removeEventFilter(guard))
        errors = []
        with patch('sys.excepthook', lambda *args: errors.append(args)):
            for _ in range(5):
                editor = self.open_block_menu(table)
                view = editor.view()
                point = view.visualRect(view.model().index(1, 0)).center()
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.assertEqual(table.item(0, 1).text(), 'SetorX')
                self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertFalse(isValid(editor))
                point = table.visualRect(table.model().index(0, 2)).center()
                QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.assertIsNone(guard._armed)
        self.assertEqual(errors, [])

    def test_menu_cancellation_preserves_unknown_and_normalized_pasted_destinations(self):
        window, _, _ = self.workspace()
        table = self.paste(window, 'Inexistente\tAna\n setorx \tBruno')
        for row, selected in ((0, -1), (1, 1)):
            expected = table.item(row, 1).text()
            editor = self.open_block_menu(table, row)
            self.assertEqual(editor.currentIndex(), selected)
            QTest.keyClick(editor.view(), Qt.Key.Key_Escape)
            QTest.keyClick(editor, Qt.Key.Key_Escape)
            self.assertEqual(table.item(row, 1).text(), expected)

    def test_spreadsheet_paste_works_while_destination_menu_is_open(self):
        window, _, _ = self.workspace()
        table = window.table_panel.table
        editor = self.open_block_menu(table)
        self.app.clipboard().setText('SetorX\tAna\tAnalista\nComando\tBruno\tDiretor')
        QTest.keyClick(editor.view(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(table.item(0, 1).text(), 'SetorX')
        self.assertEqual(table.item(1, 1).text(), 'Comando')
        self.assertEqual(table.item(1, 2).text(), 'Bruno')
        self.app.processEvents()
        table.setCurrentCell(0, 1)
        point = table.visualRect(table.model().index(1, 1)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ShiftModifier, pos=point)
        self.assertGreater(len(table.selectedIndexes()), 1)
        self.assertIsNone(table.indexWidget(table.model().index(1, 1)))

    def test_real_spreadsheet_paste_routes_interleaved_rows_and_pdf_uses_same_plan(self):
        window, _, _ = self.workspace()
        table = self.paste(window, " setorx \tAna\tAnalista\nComando\tBruno\tDiretor\nSETORX\tCarla\tAnalista")
        self.assertTrue(is_block_header(table.horizontalHeaderItem(1)))
        self.assertEqual(table_column_key(table.horizontalHeaderItem(1)), BLOCK_DESTINATION_KEY)
        plain, rich = window._scrape_table_data()
        renderer = OrganogramRenderer(window.cached_model_document, plain, rich)
        sector, command = window.cached_model_document["organogram"]["groups"]
        actual = [(slot[0], slot[1], slot[3]["Nome"]) for slot in renderer.slots]
        self.assertEqual(actual, [(sector["id"], 0, "Ana"), (command["id"], 0, "Bruno"), (sector["id"], 1, "Carla")])
        self.assertEqual(renderer.assignment_issues, [])
        self.assertNotIn(BLOCK_DESTINATION_KEY, window._get_row_data_rich(0))
        self.assertNotIn("Bloco", plain[0])
        path = self.root / "chart.pdf"
        renderer.export_pdf(path)
        text = PdfReader(path).pages[0].extract_text()
        self.assertTrue(all(name in text for name in ("Ana", "Bruno", "Carla")))
        self.assertIn("3 cartão", window.table_panel.lbl_board_status.text())

    def test_missing_unknown_and_overflow_report_rows_and_block_generation(self):
        window, _, _ = self.workspace()
        self.paste(window, "SetorX\tAna\nSetorX\tBruno\nSetorX\tCarla\nInexistente\tDiana\n\tElisa")
        plain, rich = window._scrape_table_data()
        slots, issues = assignment_plan(window.cached_model_document, plain, rich)
        self.assertEqual(len(slots), 2)
        self.assertEqual([(issue["row"], issue["reason"]) for issue in issues], [(2, "overflow"), (3, "unknown"), (4, "missing")])
        tooltip = window.table_panel.lbl_board_status.toolTip()
        self.assertIn("Linha 3", tooltip)
        self.assertIn("Inexistente", tooltip)
        self.assertIn("Linha 5", tooltip)
        with patch("features.workspace.main_window.QMessageBox.warning") as warning:
            window._generate_organogram(window.cached_model_document, plain, rich, self.root, None, None)
            self.assertIn("Linha 3", warning.call_args.args[2])
        worker = OrganogramWorker(window.cached_model_document, plain, rich, self.root, "pdf")
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(len(errors), 1)
        self.assertIn("Linha 4", errors[0])
        self.assertFalse((self.root / "organograma.pdf").exists())
        self.assertFalse((self.root / ".organograma.partial.pdf").exists())

    def test_empty_cards_and_disabled_rows_keep_vacancies_without_activating_metadata(self):
        document = self.document()
        document["organogram"]["groups"][0]["columns"] = 4
        rows = [{BLOCK_DESTINATION_KEY: "SetorX"},
                {BLOCK_DESTINATION_KEY: "SetorX", "Nome": "Oculto", DISABLED_ROW_KEY: True},
                {BLOCK_DESTINATION_KEY: "SetorX", "Nome": "Ana"},
                {BLOCK_DESTINATION_KEY: "Inexistente"}, {}]
        slots, issues = assignment_plan(document, rows)
        self.assertEqual([(slot[1], slot[3]["Nome"]) for slot in slots], [(2, "Ana")])
        self.assertEqual(issues, [])
        self.assertFalse(row_is_valid(document, rows[0]))
        self.assertFalse(row_is_valid(document, rows[1]))

    def test_destination_does_not_conflict_with_a_card_placeholder_named_bloco(self):
        document = self.document()
        document["pages"][0]["boxes"][0]["html"] = "{Bloco}"
        document["pages"][0]["field_ids"].append("Bloco")
        document["placeholders"].append("Bloco")
        window, _, _ = self.workspace(document)
        table = window.table_panel.table
        headers = [table.horizontalHeaderItem(col) for col in range(table.columnCount())]
        placeholder_col = next(col for col, header in enumerate(headers) if header.text() == "Bloco" and not is_block_header(header))
        from PySide6.QtWidgets import QTableWidgetItem
        table.setItem(0, 1, QTableWidgetItem("SetorX"))
        table.setItem(0, placeholder_col, QTableWidgetItem("Conteúdo do cartão"))
        plain, rich = window._scrape_table_data()
        self.assertEqual(plain[0][BLOCK_DESTINATION_KEY], "SetorX")
        self.assertEqual(plain[0]["Bloco"], "Conteúdo do cartão")
        self.assertEqual(len(list(assigned_slots(window.cached_model_document, plain, rich))), 1)
        table.edit(table.model().index(0, placeholder_col))
        from features.spreadsheet.delegates import RichTextEditor
        self.assertIsInstance(table.indexWidget(table.model().index(0, placeholder_col)), RichTextEditor)

    def test_duplicate_and_blank_names_are_rejected_in_model_validation(self):
        for name in (" setorx ", "SETORX", "", "   "):
            with self.subTest(name=name):
                document = self.document()
                document["organogram"]["groups"][1]["name"] = name
                with self.assertRaises(ModelValidationError):
                    normalize_model_document(document)

    def test_legacy_names_migrate_without_changing_source_geometry_or_connections(self):
        document = self.document()
        board = document["organogram"]
        board.pop("block_names_version")
        board["groups"][0]["name"] = "Bloco 1"
        board["groups"][1]["name"] = "Bloco 1"
        # Um nome único posterior deve ser reservado antes da migração.
        for name in ("Bloco 2", "SetorX", " setorx ", "SetorX — cópia", ""):
            group = new_group(document, columns=1, rows=1)
            group["name"] = name
            board["groups"].append(group)
        original = deepcopy(document)
        migrated = normalize_model_document(document)
        names = [group["name"] for group in migrated["organogram"]["groups"]]
        self.assertEqual(names, ["Bloco 1", "Bloco 3", "Bloco 2", "SetorX", "setorx — cópia 2", "SetorX — cópia", "Bloco 4"])
        expected = deepcopy(original)
        expected["organogram"]["block_names_version"] = 1
        for group, name in zip(expected["organogram"]["groups"], names):
            group["name"] = name
        self.assertEqual(migrated, expected)
        self.assertEqual(document, original)
        self.assertEqual(normalize_model_document(migrated), migrated)

    def test_legacy_public_package_is_listed_without_restoring_backup_or_rewriting_file(self):
        directory = self.root / "models"
        directory.mkdir()
        path = directory / "old.fornax"
        save_public_fornax(self.document(), path)
        old = self.root / "old-package.fornax"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(old, "w") as target:
            for entry in source.infolist():
                data = source.read(entry.filename)
                if entry.filename == "public/document.json":
                    document = json.loads(data)
                    document["organogram"].pop("block_names_version")
                    document["organogram"]["groups"][1]["name"] = "SetorX"
                    data = json.dumps(document).encode("utf-8")
                target.writestr(entry, data)
        backup = path.with_name(path.name + ".bak")
        backup.write_bytes(path.read_bytes())
        path.write_bytes(old.read_bytes())
        original, old_backup = path.read_bytes(), backup.read_bytes()
        with patch("core.model_library.shutil.copyfile", side_effect=AssertionError("Não deve restaurar backup")):
            models = scan_model_library(directory)
        self.assertEqual([model.path for model in models], [path])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), old_backup)
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        sessions.select(path)
        migrated = sessions.document()
        self.assertEqual([group["name"] for group in migrated["organogram"]["groups"]], ["SetorX", "SetorX — cópia"])
        window = self.editor(migrated)
        window.switch_model_page("organogram")
        self.assertEqual(len(window._board_items()), 2)
        self.assertEqual(window._board_connections_data(), document["organogram"]["connections"])
        sessions.save(migrated, path=path, asset_provider=sessions.asset)
        self.assertEqual(open_public_fornax(path).document()["organogram"]["block_names_version"], 1)

    def test_legacy_encrypted_package_migrates_only_after_unlocking(self):
        from core.organogram import validate_organogram, upgrade_legacy_block_names
        document = self.document()
        document["organogram"].pop("block_names_version")
        document["organogram"]["groups"][1]["name"] = "SetorX"
        def previous_validation(board):
            copy = deepcopy(board)
            upgrade_legacy_block_names(copy)
            validate_organogram(copy)
        path = self.root / "old-protected.fornax"
        # Produz um pacote antigo real, inclusive a autenticação criptográfica.
        with patch("core.organogram.upgrade_legacy_block_names", return_value=None), \
                patch("core.organogram.validate_organogram", side_effect=previous_validation):
            save_protected_fornax(document, path, "senha-de-teste", mode=FULL_MODE)
        original = path.read_bytes()
        opened = unlock_fornax(path, "senha-de-teste")
        migrated = opened.document()
        self.assertFalse(opened.public_changed)
        self.assertEqual([group["name"] for group in migrated["organogram"]["groups"]], ["SetorX", "SetorX — cópia"])
        self.assertEqual(migrated["organogram"]["connections"], document["organogram"]["connections"])
        self.assertEqual(path.read_bytes(), original)

    def test_manual_rename_warns_keeps_dialog_open_and_preserves_connections_and_undo(self):
        window = self.editor(self.document())
        window.switch_model_page("organogram")
        item = window._board_items()[1]
        identity, connections = item.data["id"], deepcopy(window._board_connections_data())
        records = []
        def edit():
            dialog = self.app.activeModalWidget()
            field = dialog.findChild(QLineEdit, "boardBlockName")
            buttons = dialog.findChild(QDialogButtonBox)
            for name in (" setorx ", "   "):
                field.setText(name)
                buttons.accepted.emit()
                records.append((dialog.isVisible(), item.data["name"]))
            field.setText("  Chefia  ")
            buttons.accepted.emit()
        with patch("features.editor.organogram_editor.QMessageBox.warning") as warning:
            QTimer.singleShot(0, edit)
            window.edit_board_group(item)
            self.assertEqual(warning.call_count, 2)
            self.assertIn("já está em uso", warning.call_args_list[0].args[2])
        self.assertEqual(records, [(True, "Comando"), (True, "Comando")])
        self.assertEqual(item.data["name"], "Chefia")
        self.assertEqual(item.data["id"], identity)
        self.assertEqual(window._board_connections_data(), connections)
        window.undo()
        restored = next(item for item in window._board_items() if item.data["id"] == identity)
        self.assertEqual(restored.data["name"], "Comando")
        self.assertEqual(window._board_connections_data(), connections)

    def test_duplicate_names_are_unique_even_with_case_and_spaces(self):
        window = self.editor(self.document())
        window.switch_model_page("organogram")
        group = new_group(window._model_document, columns=1, rows=1, x=1800)
        group["name"] = " SETORX — CÓPIA "
        window.add_board_group(group)
        window.scene.clearSelection()
        window._board_items()[0].setSelected(True)
        window.duplicate_board_selection()
        self.assertEqual(window._selected_board_group().data["name"], "SetorX — cópia 2")
        window.add_board_group(new_group(window._model_document, columns=1, rows=1))
        names = [item.data["name"].strip().casefold() for item in window._board_items()]
        self.assertEqual(len(names), len(set(names)))

    def test_saving_renamed_block_updates_pasted_destinations_by_uuid(self):
        window, path, sessions = self.workspace()
        table = self.paste(window, " setorx \tAna\nCOMANDO\tBruno")
        old_name = window.preview_panel.cbo_models.currentText()
        document = deepcopy(window.cached_model_document)
        document["organogram"]["groups"][0]["name"] = "Novo setor"
        document["organogram"]["groups"][1]["name"] = "Chefia"
        sessions.save(document, path=path, asset_provider=sessions.asset)
        def reload(**_):
            window._load_fornax_document(sessions.document(path), sessions.asset, sessions.status(path))
        with patch.object(window, "_reload_models_from_disk", side_effect=reload):
            window._on_editor_saved(old_name, document["placeholders"], str(path))
        self.assertEqual(table.item(0, 1).text(), "Novo setor")
        self.assertEqual(table.item(1, 1).text(), "Chefia")
        self.assertEqual(table.item(0, 2).text(), "Ana")
        self.assertEqual(table.item(1, 2).text(), "Bruno")
        self.assertEqual(table.block_names, ('Novo setor', 'Chefia'))
        plain, rich = window._scrape_table_data()
        self.assertEqual(assignment_plan(window.cached_model_document, plain, rich)[1], [])

    def test_ordinary_models_do_not_get_destination_column(self):
        window, _, _ = self.workspace(fixtures.card_document())
        table = window.table_panel.table
        self.assertFalse(any(is_block_header(table.horizontalHeaderItem(col)) for col in range(table.columnCount())))
        self.assertEqual(table.columnCount(), 3)
        self.assertEqual(table.horizontalHeaderItem(1).text(), "Nome")
        self.assertEqual(table.block_names, ())


if __name__ == "__main__":
    unittest.main()
