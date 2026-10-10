"""Células avulsas: gestos reais, escopo exato, aparência e transações."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QImage, QPainter, QFont, QMouseEvent
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem
from PySide6.QtTest import QTest

import test_table_controls as controls
from core.table_model import (cell_at, new_table, set_cell_html, format_cell_ids,
                              format_cell_edge_ids, cell_edge_keys, TableValidationError)
from core.model_document import normalize_model_document, add_model_table
from features.editor.canvas_items import RectangleItem
from features.editor.history_capture import history_inputs


class DisjointSelectionTest(unittest.TestCase):
    setUpClass = classmethod(controls.TableControlsTest.setUpClass.__func__)
    tearDownClass = classmethod(controls.TableControlsTest.tearDownClass.__func__)
    setUp = controls.TableControlsTest.setUp
    tearDown = controls.TableControlsTest.tearDown
    editor = controls.TableControlsTest.editor
    type = controls.TableControlsTest.type

    def click(self, w, item, row, column, modifier=Qt.KeyboardModifier.ControlModifier):
        cell = cell_at(item.data, row, column)
        entry = next(e for e in item.layout.cells if e.cell['id'] == cell['id'])
        point = w.view.mapFromScene(item.mapToScene(entry.inner.topLeft()+QPointF(12, 12)))
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, modifier, pos=point)
        self.app.processEvents()

    def anchors(self, item):
        return {(c['row'], c['column']) for c in item.selected_cells()}

    def cell_point(self, w, item, anchor):
        cell = cell_at(item.data, *anchor)
        entry = next(e for e in item.layout.cells if e.cell['id'] == cell['id'])
        return w.view.mapFromScene(item.mapToScene(entry.inner.topLeft()+QPointF(12, 12)))

    def move_pressed(self, w, point, buttons=Qt.MouseButton.LeftButton):
        viewport = w.view.viewport()
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point),
            QPointF(viewport.mapToGlobal(point)), Qt.MouseButton.NoButton,
            buttons, Qt.KeyboardModifier.ControlModifier)
        QApplication.sendEvent(viewport, event)
        self.app.processEvents()

    def ctrl_drag(self, w, item, start, *destinations):
        viewport = w.view.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier, pos=self.cell_point(w, item, start))
        for destination in destinations:
            self.move_pressed(w, self.cell_point(w, item, destination))
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.ControlModifier,
                           pos=self.cell_point(w, item, destinations[-1]))
        self.app.processEvents()

    def test_ctrl_drag_adds_rectangle_to_previous_disjoint_selection(self):
        w, item = self.editor()
        self.select_pair(w, item, (0, 0), (2, 2))
        before, history, position = self.document(w), w.history._current_index, item.pos()
        self.ctrl_drag(w, item, (1, 0), (2, 1))
        self.assertEqual(self.anchors(item), {(0, 0), (2, 2), (1, 0), (1, 1), (2, 0), (2, 1)})
        self.assertEqual(self.document(w), before)
        self.assertEqual(w.history._current_index, history)
        self.assertEqual(item.pos(), position)
        self.assertIsNotNone(history_inputs(w))
        self.assertIsNone(item._ctrl_cell_drag)
        self.assertFalse(item._selecting_cells)
        self.assertTrue(w.table_controller.cell_style({'fill_color': '#ffaa33'}))
        self.assertEqual(cell_at(item.data, 0, 2)['style'].get('fill_color'), None)
        for entry in w.table_controller.entries(item):
            self.assertEqual(entry.style['fill_color'], '#ffaa33')

    def test_ctrl_drag_from_selected_cell_shrinks_without_leaving_trail(self):
        w, item = self.editor()
        item.select_cell(1, 0)
        self.ctrl_drag(w, item, (1, 0), (2, 2), (1, 1), (1, 0))
        self.assertEqual(self.anchors(item), {(1, 0)})
        self.ctrl_drag(w, item, (1, 0), (2, 1))
        self.assertEqual(self.anchors(item), {(1, 0), (1, 1), (2, 0), (2, 1)})
        self.click(w, item, 1, 0)
        self.assertEqual(self.anchors(item), {(1, 1), (2, 0), (2, 1)})

    def test_ctrl_drag_reverse_direction_expands_merged_cells_whole(self):
        w, item = self.editor()
        item.select_cell(2, 2)
        self.ctrl_drag(w, item, (1, 1), (0, 2))
        self.assertEqual(self.anchors(item), {(0, 0), (0, 2), (1, 0), (1, 1), (1, 2), (2, 2)})
        self.assertEqual(cell_at(item.data, 0, 0)['column_span'], 2)

    def test_ctrl_drag_from_active_text_commits_and_releases_mouse(self):
        w, item = self.editor()
        self.type(w, item, text='Texto preservado')
        history = w.history._current_index
        self.ctrl_drag(w, item, (1, 1), (2, 2))
        self.assertIsNone(w.table_edit.item)
        self.assertIn('Texto preservado', cell_at(item.data, 1, 1)['html'])
        self.assertEqual(self.anchors(item), {(1, 1), (1, 2), (2, 1), (2, 2)})
        self.assertEqual(w.history._current_index, history+1)
        self.assertIsNone(w.scene.mouseGrabberItem())
        self.assertFalse(item._ctrl_cell_grabbed)
        self.click(w, item, 2, 2)
        self.assertEqual(self.anchors(item), {(1, 1), (1, 2), (2, 1)})

    def test_ctrl_drag_clamps_at_table_edge_and_recovers_missing_release(self):
        w, item = self.editor()
        item.select_cell(0, 0)
        point = self.cell_point(w, item, (1, 1))
        QTest.mousePress(w.view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier, pos=point)
        outside = w.view.mapFromScene(item.mapToScene(QPointF(item.layout.width+40, item.layout.height+40)))
        self.move_pressed(w, outside)
        self.assertEqual(self.anchors(item), {(0, 0), (1, 1), (1, 2), (2, 1), (2, 2)})
        self.move_pressed(w, outside, buttons=Qt.MouseButton.NoButton)
        self.assertFalse(item._selecting_cells)
        self.assertIsNone(item._ctrl_cell_drag)
        QTest.mouseRelease(w.view.viewport(), Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.ControlModifier, pos=outside)
        self.click(w, item, 1, 1)
        self.assertEqual(self.anchors(item), {(0, 0), (1, 2), (2, 1), (2, 2)})

    def test_ctrl_drag_from_text_recovers_window_deactivation(self):
        w, item = self.editor()
        w.table_edit.begin(item, (1, 1))
        viewport = w.view.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier, pos=self.cell_point(w, item, (1, 1)))
        self.move_pressed(w, self.cell_point(w, item, (2, 2)))
        self.assertTrue(item._ctrl_cell_grabbed)
        QApplication.sendEvent(w, QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(item._ctrl_cell_grabbed)
        self.assertFalse(item._selecting_cells)
        self.assertIsNone(item._ctrl_cell_drag)
        self.assertIsNone(w.scene.mouseGrabberItem())
        self.assertEqual(self.anchors(item), {(1, 1), (1, 2), (2, 1), (2, 2)})
        self.click(w, item, 2, 2)
        self.assertEqual(self.anchors(item), {(1, 1), (1, 2), (2, 1)})

    def select_pair(self, w, item, first=(1, 0), second=(2, 2)):
        item.select_cell(*first)
        self.click(w, item, *second)
        self.assertEqual(self.anchors(item), {first, second})

    def document(self, w):
        return deepcopy(w._capture_document_history_state()['document'])

    def test_ctrl_toggles_cells_without_changing_document_or_history(self):
        w, item = self.editor()
        before = self.document(w)
        history = w.history._current_index
        item.select_cell(1, 0)
        with patch.object(w, '_capture_document_history_state', wraps=w._capture_document_history_state) as capture:
            self.click(w, item, 2, 2)
            self.assertEqual(self.anchors(item), {(1, 0), (2, 2)})
            self.assertIn('2 células', w.table_panel.summary.text())
            self.assertFalse(item.selection_is_rectangular())
            self.assertFalse(w.table_controller.floating_bar.buttons['merge'].isEnabled())
            self.assertIsNotNone(history_inputs(w))
            w.save_snapshot()
            capture.assert_not_called()
        self.click(w, item, 1, 0)
        self.assertEqual(self.anchors(item), {(2, 2)})
        self.click(w, item, 2, 2)
        self.assertIsNone(item.selected_range)
        self.assertTrue(item.isSelected())
        self.assertEqual(w.history._current_index, history)
        self.assertEqual(self.document(w), before)

    def test_styles_and_typography_affect_only_chosen_cells_and_preserve_selection(self):
        w, item = self.editor()
        self.select_pair(w, item)
        untouched = [deepcopy(c) for c in item.data['cells'] if (c['row'], c['column']) not in self.anchors(item)]
        before = self.document(w)
        count = w.history._current_index
        layout = item.layout
        self.assertTrue(w.table_controller.cell_style({'fill_color': '#f0a020', 'fill_opacity': .5,
                           'align': 'center', 'vertical_align': 'bottom', 'wrap': False}))
        self.assertEqual(w.history._current_index, count+1)
        self.assertEqual(self.anchors(item), {(1, 0), (2, 2)})
        for kind, value in (('family', 'Inter 18pt'), ('size', 12), ('color', '#123456'),
                            ('bold', True), ('italic', True), ('underline', True)):
            w.table_controller.format_text(kind, value)
            self.assertEqual(self.anchors(item), {(1, 0), (2, 2)})
        self.assertIs(item.layout, layout)
        self.assertEqual([c for c in item.data['cells'] if (c['row'], c['column']) not in self.anchors(item)], untouched)
        for entry in w.table_controller.entries(item):
            fmt = entry.document.begin().charFormat()
            cursor = entry.document.find('Texto')
            if not cursor.isNull(): fmt = cursor.charFormat()
            self.assertGreaterEqual(fmt.fontWeight(), QFont.Weight.Bold)
            self.assertTrue(fmt.fontItalic())
            self.assertTrue(fmt.fontUnderline())
            self.assertEqual(entry.style['fill_color'], '#f0a020')
        final = self.document(w)
        steps = w.history._current_index-count
        for _ in range(steps): w.undo()
        self.assertEqual(self.document(w), before)
        for _ in range(steps): w.redo()
        self.assertEqual(self.document(w), final)

    def test_borders_and_measurements_skip_unselected_middle_tracks(self):
        w, item = self.editor()
        self.select_pair(w, item, (0, 0), (2, 2))
        edge_keys = cell_edge_keys(item.selected_cells())
        self.assertTrue(w.table_controller.edge_style({'color': '#d02030', 'width': 3, 'opacity': .5}))
        self.assertEqual({(e['orientation'], e['row'], e['column']) for e in item.data['edges']}, edge_keys)
        middle = item.data['row_heights'][1]
        self.assertTrue(w.table_controller.track('row', 15))
        self.assertEqual(item.data['row_heights'][1], middle)
        self.assertAlmostEqual(item.data['row_heights'][0], item.data['row_heights'][2])
        self.assertEqual(self.anchors(item), {(0, 0), (2, 2)})

    def test_merged_cells_toggle_whole_and_split_keeps_gaps_unselected(self):
        w, item = self.editor()
        self.select_pair(w, item, (2, 2), (0, 0))
        self.click(w, item, 0, 1)
        self.assertEqual(self.anchors(item), {(2, 2)})
        self.click(w, item, 0, 1)
        self.assertEqual(self.anchors(item), {(0, 0), (2, 2)})
        self.assertTrue(w.table_controller.structure('split'))
        self.assertEqual(self.anchors(item), {(0, 0), (0, 1), (2, 2)})

    def test_merge_refuses_gaps_but_accepts_complete_ctrl_rectangle(self):
        w, item = self.editor()
        self.select_pair(w, item)
        before = self.document(w)
        self.assertFalse(w.table_controller.structure('merge'))
        self.assertEqual(self.document(w), before)
        item.select_cell(1, 0)
        self.click(w, item, 1, 1)
        self.assertTrue(item.selection_is_rectangular())
        self.assertTrue(w.table_controller.floating_bar.buttons['merge'].isEnabled())
        self.assertTrue(w.table_controller.structure('merge'))
        self.assertEqual(cell_at(item.data, 1, 0)['column_span'], 2)

    def test_delete_and_clipboard_never_include_cells_in_the_gaps(self):
        w, item = self.editor()
        item.publish_cell_html((2, 2), '<p>Última</p>')
        item.publish_cell_html((1, 1), '<p>Preservar</p>')
        w.save_snapshot()
        self.select_pair(w, item)
        before = self.document(w)
        QApplication.clipboard().setText('Conteúdo externo')
        self.assertTrue(w.table_controller.copy_selection())
        self.assertEqual(QApplication.clipboard().text(), 'Conteúdo externo')
        self.assertTrue(w.table_controller.paste_selection())
        self.assertEqual(self.document(w), before)
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_Delete)
        self.assertEqual(cell_at(item.data, 1, 0)['html'], '')
        self.assertEqual(cell_at(item.data, 2, 2)['html'], '')
        self.assertEqual(cell_at(item.data, 1, 1)['html'], '<p>Preservar</p>')
        w.undo()
        self.assertEqual(self.document(w), before)

    def test_shift_and_ctrl_a_keep_rectangular_selection_and_ctrl_objects_still_work(self):
        w, item = self.editor()
        self.select_pair(w, item)
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(item.selected_range, (0, 0, 2, 2))
        self.assertIsNone(item._selected_cell_ids)
        item.select_cell(1, 0)
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(item.selected_range, (1, 0, 1, 1))
        self.assertIsNone(item._selected_cell_ids)
        shape = RectangleItem(100, 100)
        shape.layer_id = w._get_next_layer_id()
        shape.setPos(770, 150)
        w.scene.addItem(shape)
        point = w.view.mapFromScene(shape.mapToScene(shape.rect().center()))
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, pos=point)
        self.assertEqual(set(w.scene.selectedItems()), {item, shape})
        w.scene.clearSelection()
        item.setSelected(True)
        self.assertIsNone(item.selected_range)
        self.click(w, item, 1, 0)
        self.assertFalse(item.isSelected())

    def test_ctrl_during_text_edit_commits_and_selects_other_cell(self):
        w, item = self.editor()
        self.type(w, item, text='Rascunho aceito')
        self.click(w, item, 2, 2)
        self.assertIsNone(w.table_edit.item)
        self.assertIn('Rascunho aceito', cell_at(item.data, 1, 1)['html'])
        self.assertEqual(self.anchors(item), {(1, 1), (2, 2)})
        w.table_edit.begin(item, (1, 1))
        self.click(w, item, 1, 1)
        self.assertIsNone(w.table_edit.item)
        self.assertIsNone(item.selected_range)

    def test_highlight_skips_gaps_and_pointer_cancel_keeps_selection(self):
        w, item = self.editor()
        self.select_pair(w, item, (1, 1), (2, 2))
        def paint(overlays):
            image = QImage(660, 420, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            item.overlays_enabled = overlays
            painter = QPainter(image)
            option = QStyleOptionGraphicsItem(); option.exposedRect = item.rect()
            try: item.paint(painter, option)
            finally: painter.end()
            return image
        baseline, selected = paint(False), paint(True)
        for anchor in ((1, 1), (1, 2), (2, 1), (2, 2)):
            entry = next(e for e in item.layout.cells if (e.cell['row'], e.cell['column']) == anchor)
            point = (entry.inner.topLeft()+QPointF(20, 30)).toPoint()
            if anchor in self.anchors(item):
                self.assertNotEqual(selected.pixelColor(point), baseline.pixelColor(point))
            else:
                self.assertEqual(selected.pixelColor(point), baseline.pixelColor(point))
        entry = next(e for e in item.layout.cells if (e.cell['row'], e.cell['column']) == (1, 2))
        point = w.view.mapFromScene(item.mapToScene(entry.inner.topLeft()+QPointF(12, 12)))
        QTest.mousePress(w.view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier, pos=point)
        self.assertTrue(item._selecting_cells)
        self.assertTrue(item._ctrl_cell_selection)
        QApplication.sendEvent(w, QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(item._selecting_cells)
        self.assertFalse(item._ctrl_cell_selection)
        self.assertEqual(self.anchors(item), {(1, 1), (1, 2), (2, 2)})

    def test_remove_separate_rows_preserves_the_middle_row_and_is_atomic(self):
        table = new_table(4, 4, width=800, height=600)
        table = set_cell_html(table, 1, 1, '<p>Linha intermediária</p>')
        w, item = self.editor(add_model_table(normalize_model_document({'canvas_size': {'w': 1000, 'h': 800}}), table))
        self.select_pair(w, item, (0, 0), (2, 0))
        before = self.document(w)
        index = w.history._current_index
        self.assertTrue(w.table_controller.structure('remove_rows'))
        self.assertEqual(item.data['rows'], 2)
        self.assertIn('Linha intermediária', cell_at(item.data, 0, 1)['html'])
        self.assertEqual(w.history._current_index, index+1)
        w.undo()
        self.assertEqual(self.document(w), before)

    def test_invalid_sparse_operations_preserve_source(self):
        table = new_table()
        before = deepcopy(table)
        for operation in (format_cell_ids, format_cell_edge_ids):
            with self.assertRaises(TableValidationError):
                operation(table, {'desconhecida'}, {'fill_color': '#ffffff'} if operation is format_cell_ids else {'width': 3})
            self.assertEqual(table, before)
        with self.assertRaises(TableValidationError):
            format_cell_ids(table, {table['cells'][0]['id']}, {'padding': 500})
        self.assertEqual(table, before)


if __name__ == '__main__':
    unittest.main()
