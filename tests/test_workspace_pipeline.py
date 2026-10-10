"""Regressões de notificações, navegação e validação incremental da planilha."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QMimeData, QEvent
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QTableWidgetItem
from core.fornax_container import PUBLIC_MODE
from core.dynamic_images import resolve_dynamic_image
import test_signature_preview as signature_tests
import test_organogram_preview as board_tests


class WorkspacePipelineTest(unittest.TestCase):
    setUpClass = classmethod(signature_tests.SignaturePreviewTest.setUpClass.__func__)
    setUp = signature_tests.SignaturePreviewTest.setUp
    make_workspace = signature_tests.SignaturePreviewTest.make_workspace
    dispose_workspace = signature_tests.SignaturePreviewTest.dispose_workspace

    def test_navigation_renders_once_and_preserves_copy_index(self):
        w = self.make_workspace(PUBLIC_MODE)
        table = w.table_panel.table
        table.setRowCount(3)
        for row, qty in enumerate((0, 2, 1)):
            table.setItem(row, 0, QTableWidgetItem(str(qty)))
            table.setItem(row, 3, QTableWidgetItem(f"Pessoa {row}"))
        w._preview_refresh_timer.stop()
        table.setCurrentCell(0, 3)
        with patch.object(w.preview_renderer, "render_to_pixmap", wraps=w.preview_renderer.render_to_pixmap) as render, patch.object(
            w, "_scrape_table_data", wraps=w._scrape_table_data
        ) as scrape:
            w._on_preview_index_requested(0)
            self.assertEqual(table.currentRow(), 1)
            self.assertEqual(render.call_count, 1)
            w._on_preview_index_requested(1)
            self.assertEqual(w._preview_item_index, 1)
            self.assertEqual(table.currentRow(), 1)
            self.assertEqual(render.call_count, 1)
            table.setCurrentCell(1, 0)
            self.assertEqual(render.call_count, 1)
            w._on_preview_index_requested(2)
            self.assertEqual(table.currentRow(), 2)
            self.assertEqual(render.call_count, 2)
            self.assertEqual(scrape.call_count, 0)

    def test_paste_notifies_once_and_preserves_signatures_and_rich_text(self):
        w = self.make_workspace(PUBLIC_MODE)
        t = w.table_panel.table
        t.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
        t.setCurrentCell(0, 3)
        self.app.clipboard().setText("Ana\nBruno\nCarla")
        changes, batches = [], []
        t.itemChanged.connect(changes.append)
        t.dataBatchChanged.connect(batches.append)
        revision = w._sheet_preview_revision
        t._paste_from_clipboard()
        self.assertEqual(changes, [])
        self.assertEqual(len(batches), 1)
        self.assertEqual(w._sheet_preview_revision - revision, 1)
        self.assertEqual([t.item(r, 3).text() for r in range(3)], ["Ana", "Bruno", "Carla"])
        self.assertTrue(all(t.item(r, 1).checkState() == Qt.CheckState.Unchecked for r in range(3)))
        self.assertTrue(all(t.item(r, 2).checkState() == Qt.CheckState.Checked for r in range(3)))
        for row in range(3):
            self.assertEqual(t.item(row, 0).text(), "1")
            self.assertTrue(t.item(row, 0).textAlignment() & Qt.AlignmentFlag.AlignHCenter)
        t.toggle_signature_column(1)
        self.assertTrue(all(t.item(r, 1).checkState() == Qt.CheckState.Checked for r in range(3)))

    def test_bulk_fill_uses_logical_selection_after_columns_are_reordered(self):
        w = self.make_workspace(PUBLIC_MODE)
        t = w.table_panel.table
        t.setRowCount(2)
        t._initialize_functional_cells(1)
        t.horizontalHeader().moveSection(3, 1)
        selection = QItemSelection(t.model().index(0, 3), t.model().index(1, 3))
        t.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.app.clipboard().setText("Nome colado")
        t._paste_from_clipboard()
        self.assertEqual(t.item(0, 3).text(), "Nome colado")
        self.assertEqual(t.item(1, 3).text(), "Nome colado")
        self.assertEqual(t.item(1, 1).checkState(), Qt.CheckState.Checked)

    def test_paste_updates_formula_editor_and_preserves_rich_text(self):
        from features.spreadsheet.table_panel import TablePanel
        panel = TablePanel()
        def cleanup():
            self.app.clipboard().clear()
            panel.table._row_height_timer.stop()
            panel.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.addCleanup(cleanup)
        t = panel.table
        t.setColumnCount(2)
        t.setHorizontalHeaderLabels(["Cópias", "Nome"])
        t.setRowCount(1)
        t.setCurrentCell(0, 1)
        mime = QMimeData()
        mime.setHtml("<table><tr><td><b>Ana</b></td></tr><tr><td>Bruno</td></tr></table>")
        mime.setText("Ana\nBruno")
        self.app.clipboard().setMimeData(mime)
        t._paste_from_clipboard()
        self.assertEqual(panel.cell_editor.toPlainText(), "Ana")
        self.assertEqual(t.item(0, 1).text(), "Ana")
        self.assertTrue(t.item(0, 1).data(t.RICH_ROLE))
        self.assertTrue(panel.cell_editor.has_rich_formatting())
        self.assertEqual(t.item(1, 1).text(), "Bruno")

    def test_lightweight_navigation_agrees_with_full_data_for_invalid_quantities(self):
        w = self.make_workspace(PUBLIC_MODE)
        t = w.table_panel.table
        quantities = ["0", "-1", "2", "inválido", "", " 3 "]
        t.setRowCount(len(quantities))
        for row, value in enumerate(quantities):
            t.setItem(row, 0, QTableWidgetItem(value))
        self.assertEqual(w._preview_source_rows(), w._scrape_table_data(include_sources=True)[2])

    def test_image_validation_only_resolves_changed_image_cells(self):
        w = self.make_workspace(PUBLIC_MODE)
        t = w.table_panel.table
        w.cached_model_document["pages"][0].setdefault("shapes", []).append({"dynamic_image_field": "Nome"})
        w.table_panel.txt_dynamic_image_dir.setText(str(self.root))
        image = QImage(2, 2, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        image.save(str(self.root / "photo.png"))
        t.setRowCount(4)
        for row in range(4):
            t.setItem(row, 0, QTableWidgetItem("1"))
            t.setItem(row, 3, QTableWidgetItem("photo.png"))
        w._refresh_dynamic_image_status()
        with patch("features.workspace.main_window.resolve_dynamic_image", wraps=resolve_dynamic_image) as resolve, patch.object(
            w, "_on_table_selection"
        ), patch.object(w, "_start_sheet_preview_preload"):
            t.item(0, 0).setText("2")
            w._refresh_preview_after_data_change()
            self.assertEqual(resolve.call_count, 0)
            t.item(1, 3).setText("missing.png")
            w._refresh_preview_after_data_change()
            self.assertEqual(resolve.call_count, 1)
            self.assertIn("1 referência", w.table_panel.lbl_dynamic_image_status.text())
            t.item(1, 3).setText("photo.png")
            w._refresh_preview_after_data_change()
            self.assertEqual(resolve.call_count, 2)
            self.assertIn("Pasta pronta", w.table_panel.lbl_dynamic_image_status.text())
            # A checagem completa deve detectar alterações externas à planilha.
            (self.root / "photo.png").unlink()
            w._refresh_dynamic_image_status()
            self.assertEqual(resolve.call_count, 6)
            self.assertIn("4 referência", w.table_panel.lbl_dynamic_image_status.text())
            t.removeRow(0)
            w._refresh_preview_after_data_change()
            self.assertEqual(resolve.call_count, 9)
            self.assertIn("3 referência", w.table_panel.lbl_dynamic_image_status.text())
            # A geração não confia no status visual previamente calculado.
            with patch("features.workspace.main_window.QMessageBox.warning") as warning, patch(
                "features.workspace.main_window.RenderManager"
            ) as manager:
                w._generate_cards_async()
                warning.assert_called_once()
                manager.assert_not_called()
                self.assertEqual(resolve.call_count, 12)

    def test_imposition_refresh_scrapes_and_builds_plan_once(self):
        from features.generator.production_plan import build_imposition_plan
        w = self.make_workspace(PUBLIC_MODE)
        w._preview_mode = "sheet"
        w._preview_sheet_index = 0
        settings = {"enabled": True, "sheet_w_mm": 210, "sheet_h_mm": 297,
                    "target_w_mm": 90, "target_h_mm": 60}
        with patch.object(w, "_resolve_imposition_settings", return_value=settings), patch.object(
            w, "_start_sheet_preview_preload"
        ), patch.object(w, "_scrape_table_data", wraps=w._scrape_table_data) as scrape, patch(
            "features.workspace.main_window.build_imposition_plan", wraps=build_imposition_plan
        ) as plan:
            w._refresh_preview_after_data_change()
            self.assertEqual(scrape.call_count, 1)
            self.assertEqual(plan.call_count, 1)
        self.assertIsNone(w._preview_update_cache)

    def test_preview_snapshot_is_scoped_and_invalidated_by_edits(self):
        from features.workspace.preview_update import preview_update
        w = self.make_workspace(PUBLIC_MODE)

        @preview_update
        def update(window):
            a = window._preview_rows(include_sources=True)
            self.assertIs(a, window._preview_rows(include_sources=True))
            window.table_panel.table.setItem(0, 3, QTableWidgetItem("Novo valor"))
            b = window._preview_rows(include_sources=True)
            self.assertIsNot(a, b)
            self.assertEqual(b[0][0]["Nome"], "Novo valor")

        with patch.object(w, "_scrape_table_data", wraps=w._scrape_table_data) as scrape:
            update(w)
            self.assertEqual(scrape.call_count, 2)
        self.assertIsNone(w._preview_update_cache)


class BoardPipelineTest(unittest.TestCase):
    setUpClass = classmethod(board_tests.OrganogramPreviewTest.setUpClass.__func__)
    setUp = board_tests.OrganogramPreviewTest.setUp
    workspace = board_tests.OrganogramPreviewTest.workspace

    def test_selection_reuses_board_but_edit_and_mode_switch_refresh_it(self):
        w = self.workspace()
        w._on_preview_mode_changed("sheet")
        t = w.table_panel.table
        with patch("features.generator.organogram.OrganogramRenderer.preview", return_value=QImage(40, 30, QImage.Format.Format_ARGB32)) as paint:
            t.setCurrentCell(0, 2)
            t.setCurrentCell(0, 3)
            self.assertEqual(paint.call_count, 0)
            w._on_preview_data_changed()
            with patch.object(w, "_scrape_table_data", wraps=w._scrape_table_data) as scrape:
                w._refresh_preview_after_data_change()
                self.assertEqual(scrape.call_count, 1)
            self.assertEqual(paint.call_count, 1)
            w._on_preview_mode_changed("item")
            w._on_preview_mode_changed("sheet")
            self.assertEqual(paint.call_count, 2)


if __name__ == "__main__":
    unittest.main()
