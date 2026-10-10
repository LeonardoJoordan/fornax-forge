"""Setas de seleção: escopo, foco, geometria, temas e isolamento da saída."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QImage, QRegion
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtTest import QTest

import test_table_controls as controls
from core.table_model import cell_at
from core.themes import theme_manager
from core.model_document import adapt_model_page
from features.editor.history_capture import history_inputs
from features.generator.renderer import NativeRenderer


class TableSelectorsTest(unittest.TestCase):
    setUpClass = classmethod(controls.TableControlsTest.setUpClass.__func__)
    tearDownClass = classmethod(controls.TableControlsTest.tearDownClass.__func__)
    setUp = controls.TableControlsTest.setUp
    tearDown = controls.TableControlsTest.tearDown
    editor = controls.TableControlsTest.editor
    type = controls.TableControlsTest.type

    def drain(self):
        for _ in range(4):
            self.app.processEvents()

    def select_table(self, w, item):
        item.setSelected(True)
        w.table_controller.refresh()
        self.drain()
        return w.table_controller.selectors

    def click(self, selectors, axis, index=0, ctrl=False):
        self.drain()
        button = selectors.buttons[axis, index]
        self.assertTrue(button.isVisible())
        self.assertIs(button.parentWidget().childAt(button.geometry().center()), button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier)
        self.drain()

    def anchors(self, item):
        return {(c['row'], c['column']) for c in item.selected_cells()}

    def test_row_column_all_and_ctrl_addition_only_change_selection(self):
        w, item = self.editor()
        selectors = self.select_table(w, item)
        before = deepcopy(w._capture_document_history_state())
        roots, history = set(w.scene.items()), w.history._current_index
        with patch.object(w, 'save_snapshot') as save:
            self.click(selectors, 'row', 1)
            self.assertEqual(self.anchors(item), {(1, 0), (1, 1), (1, 2)})
            self.click(selectors, 'row', 2, ctrl=True)
            self.assertEqual(self.anchors(item), {(r, c) for r in (1, 2) for c in range(3)})
            self.click(selectors, 'column', 2)
            self.assertEqual(self.anchors(item), {(0, 2), (1, 2), (2, 2)})
            self.click(selectors, 'row', 2, ctrl=True)
            self.assertEqual(self.anchors(item), {(0, 2), (1, 2), (2, 0), (2, 1), (2, 2)})
            self.click(selectors, 'all')
            self.assertEqual(len(item.selected_cells()), len(item.data['cells']))
            self.assertTrue(item.selection_is_rectangular())
            save.assert_not_called()
        self.assertEqual(w._capture_document_history_state(), before)
        self.assertEqual(set(w.scene.items()), roots)
        self.assertEqual(w.history._current_index, history)
        self.assertIsNotNone(history_inputs(w))

    def test_column_includes_whole_merged_cell_without_selecting_neighbours(self):
        w, item = self.editor()
        selectors = self.select_table(w, item)
        self.click(selectors, 'column', 1)
        self.assertEqual(self.anchors(item), {(0, 0), (1, 1), (2, 1)})
        self.assertEqual(cell_at(item.data, 0, 0)['column_span'], 2)
        self.assertTrue(w.table_controller.cell_style({'fill_color': '#ffc033'}))
        self.assertNotIn('fill_color', cell_at(item.data, 1, 0)['style'])
        for entry in w.table_controller.entries(item):
            self.assertEqual(entry.style['fill_color'], '#ffc033')
        # Ctrl acrescenta à seleção de células avulsas já existente.
        item.set_cell_selection({cell_at(item.data, 2, 2)['id']})
        self.click(selectors, 'row', 1, ctrl=True)
        self.assertEqual(self.anchors(item), {(1, 0), (1, 1), (1, 2), (2, 2)})

    def test_click_during_text_edit_commits_then_typing_keeps_working(self):
        w, item = self.editor()
        self.type(w, item, text='Texto confirmado')
        selectors = self.select_table(w, item)
        history = w.history._current_index
        self.click(selectors, 'row', 1)
        self.assertIsNone(w.table_edit.item)
        self.assertIn('Texto confirmado', cell_at(item.data, 1, 1)['html'])
        self.assertEqual(w.history._current_index, history+1)
        self.assertIsNone(w.scene.mouseGrabberItem())
        self.assertEqual(self.anchors(item), {(1, 0), (1, 1), (1, 2)})
        w.undo()
        restored = w.get_current_scene_state()['tables'][0]
        self.assertNotIn('Texto confirmado', cell_at(restored, 1, 1)['html'])
        w.redo()
        self.drain()
        self.click(selectors, 'row', 1)
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_F2)
        self.assertIs(w.table_edit.item, w.table_controller.selected())
        self.assertIsNotNone(w.table_edit.item)
        w.table_edit.finish()

    def test_visibility_requires_one_editable_table_and_overlays(self):
        w, item = self.editor()
        selectors = w.table_controller.selectors
        self.drain()
        self.assertFalse(any(b.isVisible() for b in selectors.buttons.values()))
        self.select_table(w, item)
        self.assertEqual(sum(b.isVisible() for b in selectors.buttons.values()), 7)
        item.overlays_enabled = False
        item.update()
        self.drain()
        self.assertFalse(any(b.isVisible() for b in selectors.buttons.values()))
        item.overlays_enabled = True
        item.update()
        self.drain()
        self.assertEqual(sum(b.isVisible() for b in selectors.buttons.values()), 7)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        w.table_controller.refresh()
        self.assertFalse(any(b.isVisible() for b in selectors.buttons.values()))
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        w.scene.clearSelection()
        self.drain()
        self.assertFalse(any(b.isVisible() for b in selectors.buttons.values()))

    def test_selectors_retarget_between_tables_and_hide_for_multiple_objects(self):
        w, first = self.editor()
        selectors = self.select_table(w, first)
        self.assertTrue(w.table_controller.add_table(2, 2))
        second = w.table_controller.selected()
        self.drain()
        self.click(selectors, 'row', 1)
        self.assertEqual(self.anchors(second), {(1, 0), (1, 1)})
        self.assertIsNone(first.selected_range)
        first.setSelected(True)
        self.drain()
        self.assertFalse(any(b.isVisible() for b in selectors.buttons.values()))
        w.scene.clearSelection()
        self.select_table(w, first)
        self.click(selectors, 'column', 2)
        self.assertEqual(self.anchors(first), {(0, 2), (1, 2), (2, 2)})
        self.assertIsNone(second.selected_range)

    def test_narrow_tracks_and_ninety_degree_rotation_keep_separate_hit_areas(self):
        w, item = self.editor()
        self.assertTrue(w.table_controller.add_table(8, 2))
        item = w.table_controller.selected()
        item.setPos(150, 150)
        self.select_table(w, item)
        selectors = w.table_controller.selectors
        for rotation in (0, 90):
            item.setRotation(rotation)
            self.drain()
            buttons = [b for (axis, index), b in selectors.buttons.items()
                       if axis == 'row' and b.isVisible()]
            for index, button in enumerate(buttons):
                for other in buttons[index+1:]:
                    self.assertFalse(button.geometry().intersects(other.geometry()))
            if buttons:
                last = buttons[-1]
                self.click(selectors, 'row', last.index)
                self.assertEqual(self.anchors(item), {(last.index, 0), (last.index, 1)})

    def test_centers_follow_zoom_move_rotation_and_grid_changes(self):
        w, item = self.editor()
        selectors = self.select_table(w, item)
        first = selectors.buttons['column', 1].geometry().center()
        item.setPos(item.pos()+QPointF(25, 30))
        w.view.scale(.8, .8)
        item.setRotation(12)
        self.drain()
        button = selectors.buttons['column', 1]
        transform = item.deviceTransform(w.view.viewportTransform())
        origin = transform.map(QPointF())
        normal = transform.map(QPointF(0, 1))-origin
        normal /= (normal.x()**2+normal.y()**2)**.5
        expected = transform.map(QPointF(item.layout.x[1]+item.data['column_widths'][1]/2, 0))-normal*10
        self.assertLessEqual((QPointF(button.geometry().center())-expected).manhattanLength(), 1)
        self.assertNotEqual(button.geometry().center(), first)
        self.assertAlmostEqual(button.angle, 12)
        item.setRotation(0)
        self.click(selectors, 'row', 1)
        self.assertTrue(w.table_controller.structure('row_after'))
        self.drain()
        self.assertIn(('row', 3), selectors.buttons)
        self.assertTrue(selectors.buttons['row', 3].isVisible())
        w.undo()
        self.drain()
        self.assertTrue(selectors.buttons['row', 3].isHidden())

    def test_selectors_have_clearance_from_resize_handles_and_toolbar(self):
        w, item = self.editor()
        selectors = self.select_table(w, item)
        bar = w.table_controller.floating_bar
        for side in ('top', 'left', 'bottom', 'right'):
            bar.dock_side = side
            bar.reposition()
            self.drain()
            for button in selectors.buttons.values():
                self.assertTrue(button.isVisible())
                hit_area = button.mask().translated(button.x(), button.y())
                self.assertTrue((hit_area & QRegion(bar.geometry())).isEmpty())
                for handle in item.resize_handles.values():
                    if handle.isVisible():
                        region = w.view.mapFromScene(handle.sceneBoundingRect()).boundingRect()
                        hit_area = button.mask().translated(button.x(), button.y())
                        self.assertTrue((hit_area & QRegion(region)).isEmpty())

    def test_theme_changes_icons_and_editor_controls_never_enter_renderer(self):
        w, item = self.editor()
        source = w._document_with_active_page()
        expected = NativeRenderer(adapt_model_page(source)).render_preview_image()
        selectors = self.select_table(w, item)
        self.addCleanup(theme_manager().select, 'dark')
        images = []
        for theme in ('dark', 'light'):
            theme_manager().select(theme)
            self.drain()
            button = selectors.buttons['all', 0]
            self.assertFalse(button.icon().isNull())
            images.append(button.grab().toImage())
            self.assertEqual(NativeRenderer(adapt_model_page(w._document_with_active_page())).render_preview_image(), expected)
        self.assertNotEqual(images[0], images[1])
        # Renderizar a própria cena tampouco inclui widgets do viewport.
        item.overlays_enabled = False
        image = QImage(900, 650, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            w.scene.render(painter, QRectF(0, 0, 900, 650), QRectF(0, 0, 900, 650))
        finally:
            painter.end()
        self.assertEqual(image, expected)


if __name__ == '__main__':
    unittest.main()
