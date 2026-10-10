"""Interação pública da tabela: objeto, células, alças e seções vazias."""
from copy import deepcopy
import os
import unittest

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QGraphicsItem

import test_table_canvas as canvas
from core.table_model import format_cells, new_table
from features.editor.frontend import Section
from features.editor.canvas_items import RectangleItem
from features.editor.table_item import TableItem


class TableInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.themes import theme_manager
        canvas.TableCanvasTest.setUpClass.__func__(cls)
        theme_manager().select(os.environ.get('FORNAX_TEST_THEME', 'dark'))
    tearDownClass = classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp = canvas.TableCanvasTest.setUp
    tearDown = canvas.TableCanvasTest.tearDown
    editor = canvas.TableCanvasTest.editor
    point = canvas.TableCanvasTest.point
    type = canvas.TableCanvasTest.type

    def drag(self, window, start, end):
        QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end),
                           QPointF(window.view.viewport().mapToGlobal(end)),
                           Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.view.viewport(), event)
        QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

    def test_first_click_selects_whole_table_even_with_transparent_cells(self):
        w, item = self.editor()
        item.publish_table_data(format_cells(item.data, 0, 0, 2, 2, {'fill_opacity': 0}))
        source = item.to_data()
        point = self.point(w, item, 330, 210)
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(item.isSelected())
        self.assertIsNone(item.selected_range)
        self.assertIsNone(w.table_edit.item)
        self.assertEqual(item.to_data(), source)
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(item.selected_range, (1, 1, 1, 1))
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_F2)
        self.assertIs(w.table_edit.item, item)

    def test_body_drag_moves_object_without_rebuilding_layout_then_click_selects_cell(self):
        w, item = self.editor()
        layout = item.layout
        docs = [entry.document for entry in layout.cells]
        for _ in range(2):
            before = item.pos()
            start = self.point(w, item, 330, 210)
            self.drag(w, start, start + self.point(w, item, 380, 230) - start)
            self.assertNotEqual(item.pos(), before)
            self.assertIs(item.layout, layout)
            self.assertEqual([entry.document for entry in layout.cells], docs)
            self.assertIsNone(item.selected_range)
            self.assertFalse(item._is_mouse_dragging)
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.point(w, item, 330, 210))
        self.assertEqual(item.selected_range, (1, 1, 1, 1))

    def test_corner_and_side_handles_resize_rotated_table_and_undo_redo(self):
        for rotation, name, delta in ((0, 'right', QPointF(70, 0)),
                                      (20, 'bottom_right', QPointF(50, 35))):
            with self.subTest(rotation=rotation, handle=name):
                w, item = self.editor()
                item.setRotation(rotation)
                item.keep_proportion = False
                item.setSelected(True)
                self.app.processEvents()
                self.assertEqual(len(item.resize_handles), 8)
                self.assertTrue(all(h.isVisible() for h in item.resize_handles.values()))
                w.history.clear(); w._history_capture_cache = None; w.save_snapshot()
                original = item.to_data()
                original_document = deepcopy(w._capture_document_history_state()['document'])
                handle = item.resize_handles[name]
                anchor = item.mapToScene(QPointF(0, item.rect().height()/2)
                                         if name == 'right' else QPointF(0, 0))
                start = w.view.mapFromScene(handle.mapToScene(QPointF()))
                end = w.view.mapFromScene(item.mapToScene(handle.pos() + delta))
                self.drag(w, start, end)
                self.assertGreater(item.rect().width(), 660)
                if name == 'right': self.assertAlmostEqual(item.rect().height(), 420)
                updated_anchor = item.mapToScene(QPointF(0, item.rect().height()/2)
                                                 if name == 'right' else QPointF(0, 0))
                self.assertLess((updated_anchor-anchor).manhattanLength(), .01)
                changed = item.to_data()
                changed_document = deepcopy(w._capture_document_history_state()['document'])
                self.assertEqual([c['html'] for c in original['cells']],
                                 [c['html'] for c in changed['cells']])
                self.assertEqual(handle.pos(), QPointF(item.rect().width(),
                    item.rect().height()/2 if name == 'right' else item.rect().height()))
                w.undo()
                restored = next(i for i in w.scene.items() if isinstance(i, TableItem))
                self.assertEqual(w._capture_document_history_state()['document'], original_document)
                w.redo()
                restored = next(i for i in w.scene.items() if isinstance(i, TableItem))
                self.assertEqual(w._capture_document_history_state()['document'], changed_document)

    def test_invalid_handle_resize_does_not_move_anchor_or_change_content(self):
        w, item = self.editor()
        dense = new_table(1, 20, width=660, height=420)
        item.publish_table_data(dense)
        item.keep_proportion = False
        item.setSelected(True); self.app.processEvents()
        before = item.to_data()
        handle = item.resize_handles['left']
        self.drag(w, w.view.mapFromScene(handle.mapToScene(QPointF())),
                  self.point(w, item, 620, 210))
        self.assertEqual(item.to_data(), before)
        self.assertTrue(w.table_panel.message.text())
        self.assertFalse(handle._is_resizing)

    def test_new_table_starts_in_object_context_with_handles_and_body_drag(self):
        w, _ = self.editor()
        self.assertTrue(w.table_controller.add_table(2, 2))
        item = w.table_controller.selected()
        self.assertIsNone(item.selected_range)
        self.assertTrue(item.resize_handles['right'].isVisible())
        before = item.pos()
        start = self.point(w, item, 40, 40)
        self.drag(w, start, self.point(w, item, 65, 65))
        self.assertNotEqual(item.pos(), before)

    def test_resize_finishes_active_cell_and_preserves_text(self):
        w, item = self.editor()
        self.type(w, item, text='Texto preservado')
        handle = item.resize_handles['bottom_right']
        self.drag(w, w.view.mapFromScene(handle.mapToScene(QPointF())),
                  self.point(w, item, 700, 445))
        self.assertIsNone(w.table_edit.item)
        self.assertIn('Texto preservado', item.to_data()['cells'][3]['html'])
        self.assertGreater(item.rect().width(), 660)

    def test_geometry_toolbar_matches_table_on_select_and_after_handle_resize(self):
        from features.editor.canvas_items import px_to_mm
        w, item = self.editor(); item.setSelected(True)
        self.app.processEvents()
        self.assertAlmostEqual(w.caixa_texto_panel.spin_w.value(), px_to_mm(660), places=2)
        self.assertAlmostEqual(w.caixa_texto_panel.spin_h.value(), px_to_mm(420), places=2)
        self.assertTrue(item.resize_from_handle(800, 500))
        self.assertAlmostEqual(w.caixa_texto_panel.spin_w.value(), px_to_mm(800), places=2)
        self.assertAlmostEqual(w.caixa_texto_panel.spin_h.value(), px_to_mm(500), places=2)

    def test_group_body_drag_keeps_relative_positions_on_board_grid(self):
        from core.organogram import add_organogram
        from features.editor.canvas_items import DesignerBox
        source = add_organogram(canvas.sample())
        w, _ = self.editor(source)
        w.switch_model_page('organogram')
        self.assertTrue(w.table_controller.add_table(2, 2))
        item = w.table_controller.selected()
        w.add_new_box()
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
        item.setPos(80, 80); box.setPos(400, 140)
        w.scene.clearSelection(); item.setSelected(True); box.setSelected(True)
        w.group_selected_items(); self.app.processEvents()
        offset = box.pos()-item.pos(); before = item.pos()
        self.drag(w, self.point(w, item, 25, 25), self.point(w, item, 85, 70))
        self.assertNotEqual(item.pos(), before)
        self.assertLess(((box.pos()-item.pos())-offset).manhattanLength(), .001)
        self.assertEqual(set(w.scene.selectedItems()), {item, box})
        self.assertIsNone(item.selected_range)

    def test_deactivation_cancels_pending_cell_click_and_releases_pointer(self):
        w, item = self.editor(); item.setSelected(True)
        QTest.mousePress(w.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.point(w, item, 330, 210))
        QApplication.sendEvent(w, QEvent(QEvent.Type.WindowDeactivate))
        self.assertIsNone(item._pending_cell)
        self.assertIsNone(item.selected_range)
        self.assertFalse(item._is_mouse_dragging)
        self.assertIsNone(w.scene.mouseGrabberItem())

    def test_handles_hidden_for_multi_selection_locked_table_and_clean_paint(self):
        w, item = self.editor(); item.setSelected(True); self.app.processEvents()
        self.assertTrue(item.resize_handles['right'].isVisible())
        shape = RectangleItem(80, 80); shape.setPos(820, 80); w.scene.addItem(shape)
        shape.layer_id = 99; shape.setSelected(True); self.app.processEvents()
        self.assertFalse(any(h.isVisible() for h in item.resize_handles.values()))
        shape.setSelected(False); self.app.processEvents()
        self.assertTrue(item.resize_handles['right'].isVisible())
        item.overlays_enabled = False
        self.assertFalse(any(h.isVisible() for h in item.resize_handles.values()))
        item.overlays_enabled = True
        item.setSelected(False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        item.setSelected(True); self.app.processEvents()
        self.assertFalse(any(h.isVisible() for h in item.resize_handles.values()))

    def test_empty_properties_collapses_and_reenables_for_shape(self):
        w, item = self.editor(); item.setSelected(True); self.app.processEvents()
        props = w._inspector_sections['properties']
        self.assertFalse(props.header.isEnabled())
        self.assertFalse(props.header.isChecked())
        self.assertFalse(props._reveal.isVisible())
        props.header.setChecked(True); self.app.processEvents()
        self.assertFalse(props.header.isChecked())
        self.assertTrue(w.caixa_texto_panel.spin_w.isEnabled())
        shape = RectangleItem(80, 80); shape.setPos(820, 80); shape.layer_id = 99
        w.scene.addItem(shape); w.scene.clearSelection(); shape.setSelected(True)
        self.app.processEvents()
        self.assertTrue(props.header.isEnabled())
        self.assertTrue(props.header.isChecked())
        w.scene.clearSelection(); item.setSelected(True); self.app.processEvents()
        self.assertFalse(props.header.isEnabled())
        self.assertFalse(props.header.isChecked())
        self.assertFalse(props._reveal.isVisible())

    def test_disabled_section_cannot_expand_even_during_animation(self):
        section = Section('Exemplo', QWidget(), expanded=True)
        section.show(); self.addCleanup(section.deleteLater)
        section.set_available(False)
        self.assertFalse(section.header.isEnabled())
        self.assertFalse(section._reveal.isVisible())
        section.header.setChecked(True)
        self.assertFalse(section.header.isChecked())
        section.set_available(True); section.header.click()
        self.assertTrue(section.header.isChecked())
        section.set_available(False); QTest.qWait(220)
        self.assertFalse(section.header.isChecked())
        self.assertFalse(section._reveal.isVisible())


if __name__ == '__main__': unittest.main()
