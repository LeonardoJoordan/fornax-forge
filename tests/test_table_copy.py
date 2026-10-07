"""Cópia da seleção para planilhas: grade, texto, formatação e atalhos reais."""
import csv
from io import StringIO
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QPoint, QTimer, QEvent
from PySide6.QtGui import QContextMenuEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QWidget, QAbstractButton

from features.spreadsheet.table_panel import RichTableWidget, TablePanel
from features.spreadsheet.headers import BLOCK_DESTINATION_ROLE, SIGNATURE_ID_ROLE
from features.spreadsheet.clipboard import router
from features.spreadsheet.delegates import RichTextEditor


class TableCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.host = QWidget()
        cls.host.resize(650, 300)
        cls.host.show()

    @classmethod
    def tearDownClass(cls):
        cls.app.clipboard().clear()
        cls.host.close()
        cls.host.deleteLater()
        cls.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def table(self, *, blocks=False):
        table = RichTableWidget(3, 4, self.host)
        table.setHorizontalHeaderLabels(['Cópias', 'Bloco' if blocks else 'Nome', 'Função', 'Assinatura'])
        table.horizontalHeaderItem(3).setData(SIGNATURE_ID_ROLE, 'signature:test')
        if blocks:
            table.horizontalHeaderItem(1).setData(BLOCK_DESTINATION_ROLE, True)
            table.set_block_names(['SetorX', 'Comando'])
        for row, name in enumerate(['Ana', 'Bruno', 'Carla']):
            table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            table.setItem(row, 1, QTableWidgetItem('SetorX' if blocks else name))
            table.setItem(row, 2, QTableWidgetItem('Função ' + name))
            table.setItem(row, 3, table._signature_item(Qt.CheckState.Checked if row % 2 == 0 else Qt.CheckState.Unchecked))
        table.resize(600, 250)
        table.show()
        self.app.processEvents()
        def cleanup():
            table._row_height_timer.stop()
            table.close()
            table.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)
        return table

    def select(self, table, top, left, bottom, right, *, add=False):
        flags = QItemSelectionModel.SelectionFlag.Select if add else QItemSelectionModel.SelectionFlag.ClearAndSelect
        table.selectionModel().select(QItemSelection(table.model().index(top, left), table.model().index(bottom, right)), flags)

    def copied(self):
        return list(csv.reader(StringIO(self.app.clipboard().text()), delimiter='\t'))

    def test_ctrl_c_copies_rectangle_including_empty_cells(self):
        table = self.table()
        table.takeItem(1, 2)
        self.select(table, 0, 1, 2, 2)
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.copied(), [['Ana', 'Função Ana'], ['Bruno', ''], ['Carla', 'Função Carla']])
        mime = self.app.clipboard().mimeData()
        self.assertTrue(mime.hasHtml())
        self.assertTrue(mime.hasText())

    def test_ctrl_a_copies_entire_table_and_signature_states(self):
        table = self.table()
        table.setCurrentCell(0, 0)
        QTest.keyClick(table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.copied(), [['1', 'Ana', 'Função Ana', 'TRUE'],
                                         ['2', 'Bruno', 'Função Bruno', 'FALSE'],
                                         ['3', 'Carla', 'Função Carla', 'TRUE']])

    def test_frontend_corner_click_selects_all_without_changing_signature_states(self):
        source = self.table(blocks=True)
        source.takeItem(1, 2)
        panel = TablePanel()
        panel.setParent(self.host)
        panel.resize(650, 600)
        table = panel.table
        def cleanup():
            table._row_height_timer.stop()
            panel.close()
            panel.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)
        table.setRowCount(source.rowCount())
        table.setColumnCount(source.columnCount())
        for column in range(source.columnCount()):
            table.setHorizontalHeaderItem(column, source.horizontalHeaderItem(column).clone())
            for row in range(source.rowCount()):
                item = source.item(row, column)
                if item is not None:
                    table.setItem(row, column, item.clone())
        panel.show()
        self.app.processEvents()
        table.setCurrentCell(0, 2)
        corner_point = QPoint(table.verticalHeader().geometry().center().x(),
                              table.horizontalHeader().geometry().center().y())
        corner = table.childAt(corner_point)
        self.assertIsInstance(corner, QAbstractButton)
        self.assertTrue(table.isCornerButtonEnabled())
        QTest.mouseClick(corner, Qt.MouseButton.LeftButton)
        self.assertEqual({(index.row(), index.column()) for index in table.selectedIndexes()},
                         {(row, column) for row in range(3) for column in range(4)})
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.copied(), [['1', 'SetorX', 'Função Ana', 'TRUE'],
                                         ['2', 'SetorX', '', 'FALSE'],
                                         ['3', 'SetorX', 'Função Carla', 'TRUE']])
        self.assertEqual([table.item(row, 3).checkState() for row in range(3)],
                         [Qt.CheckState.Checked, Qt.CheckState.Unchecked, Qt.CheckState.Checked])

    def test_multiple_rows_or_columns_copy_only_selected_entries(self):
        table = self.table()
        self.select(table, 0, 0, 0, 3)
        self.select(table, 2, 0, 2, 3, add=True)
        table._copy_to_clipboard()
        self.assertEqual([row[1] for row in self.copied()], ['Ana', 'Carla'])
        self.select(table, 0, 1, 2, 1)
        self.select(table, 0, 3, 2, 3, add=True)
        table._copy_to_clipboard()
        self.assertEqual(self.copied(), [['Ana', 'TRUE'], ['Bruno', 'FALSE'], ['Carla', 'TRUE']])

    def test_mouse_header_selection_copies_multiple_rows_and_columns(self):
        table = self.table()
        vertical = table.verticalHeader()
        for row, modifiers in ((0, Qt.KeyboardModifier.NoModifier), (1, Qt.KeyboardModifier.ShiftModifier)):
            point = QPoint(8, vertical.sectionViewportPosition(row) + vertical.sectionSize(row) // 2)
            QTest.mouseClick(vertical.viewport(), Qt.MouseButton.LeftButton, modifiers, pos=point)
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual([row[1] for row in self.copied()], ['Ana', 'Bruno'])
        horizontal = table.horizontalHeader()
        for col, modifiers in ((1, Qt.KeyboardModifier.NoModifier), (2, Qt.KeyboardModifier.ShiftModifier)):
            point = QPoint(horizontal.sectionViewportPosition(col) + horizontal.sectionSize(col) // 2, 8)
            QTest.mouseClick(horizontal.viewport(), Qt.MouseButton.LeftButton, modifiers, pos=point)
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.copied(), [['Ana', 'Função Ana'], ['Bruno', 'Função Bruno'], ['Carla', 'Função Carla']])

    def test_visual_column_order_is_preserved_after_reordering(self):
        table = self.table()
        table.horizontalHeader().setSectionsMovable(True)
        table.horizontalHeader().moveSection(3, 1)
        table.selectAll()
        table._copy_to_clipboard(include_headers=True)
        self.assertEqual(self.copied()[0], ['Cópias', 'Assinatura', 'Nome', 'Função'])
        self.assertEqual(self.copied()[1], ['1', 'TRUE', 'Ana', 'Função Ana'])

    def test_disjoint_cells_do_not_copy_unselected_data(self):
        table = self.table()
        self.select(table, 0, 1, 0, 1)
        self.select(table, 2, 2, 2, 2, add=True)
        table._copy_to_clipboard()
        self.assertEqual(self.copied(), [['Ana', ''], ['', 'Função Carla']])

    def test_unicode_quotes_tabs_and_multiline_text_are_escaped_without_splitting_cells(self):
        table = self.table()
        values = ['São José & <grupo>', 'Linha 1\nLinha 2', 'Texto\tcom "aspas"']
        for row, value in enumerate(values):
            table.item(row, 1).setText(value)
        self.select(table, 0, 1, 2, 1)
        table._copy_to_clipboard()
        self.assertEqual(self.copied(), [[value] for value in values])
        mime = self.app.clipboard().mimeData()
        self.assertIn('São José &amp; &lt;grupo&gt;', mime.html())
        self.assertIn('Linha 1<br>Linha 2', mime.html())

    def test_html_preserves_emphasis_and_can_be_pasted_back_into_table(self):
        table = self.table()
        table.item(0, 1).setData(table.RICH_ROLE, '<b>Ana</b>')
        table.item(0, 2).setData(table.RICH_ROLE, '<i><u>Função Ana</u></i>')
        self.select(table, 0, 1, 0, 2)
        table._copy_to_clipboard()
        mime = self.app.clipboard().mimeData()
        parsed = router(mime.html(), mime.text())
        self.assertEqual([cell.plain for cell in parsed[0]], ['Ana', 'Função Ana'])
        self.assertIn('<b>', parsed[0][0].rich_html)
        self.assertIn('<i>', parsed[0][1].rich_html)
        self.assertIn('<u>', parsed[0][1].rich_html)
        table.clearSelection()
        table.setCurrentCell(1, 1)
        table._paste_from_clipboard()
        self.assertEqual(table.item(1, 1).text(), 'Ana')
        self.assertIn('<b>', table.item(1, 1).data(table.RICH_ROLE))

    def test_no_selection_keeps_clipboard_unchanged(self):
        table = self.table()
        table.clearSelection()
        self.app.clipboard().setText('Anterior')
        table._copy_to_clipboard()
        self.assertEqual(self.app.clipboard().text(), 'Anterior')

    def test_context_menu_can_copy_with_headers(self):
        table = self.table()
        self.select(table, 0, 1, 1, 2)
        def choose():
            menu = self.app.activePopupWidget()
            action = next(action for action in menu.actions() if action.text() == 'Copiar com cabeçalhos')
            action.trigger()
            menu.close()
        QTimer.singleShot(0, choose)
        table.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10), table.mapToGlobal(QPoint(10, 10))))
        self.assertEqual(self.copied(), [['Nome', 'Função'], ['Ana', 'Função Ana'], ['Bruno', 'Função Bruno']])

    def test_block_popup_shortcuts_copy_actual_destination_and_select_table(self):
        table = self.table(blocks=True)
        index = table.model().index(0, 1)
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualRect(index).center())
        editor = table.indexWidget(index)
        QTest.keyClick(editor.view(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.copied(), [['SetorX']])
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualRect(index).center())
        editor = table.indexWidget(index)
        QTest.keyClick(editor.view(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.copied()), 3)
        self.assertEqual(len(self.copied()[0]), 4)

    def test_editing_text_still_copies_only_selected_text(self):
        table = self.table()
        index = table.model().index(0, 1)
        table.edit(index)
        editor = table.indexWidget(index)
        self.assertIsInstance(editor, RichTextEditor)
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        QTest.keyClick(editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), 'An')


if __name__ == '__main__':
    unittest.main()
