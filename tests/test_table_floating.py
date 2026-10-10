"""Barra contextual, seleção transitória e encontros dos contornos da tabela."""
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStyleOptionGraphicsItem

import test_table_canvas as canvas
from core.table_layout import TableLayout
from core.table_model import new_table, format_edges, merge_cells, cell_at
from core.table_paint import paint_table_local
from core.themes import theme_manager


class TableFloatingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        canvas.TableCanvasTest.setUpClass.__func__(cls)
        theme_manager().select(os.environ.get('FORNAX_TEST_THEME', 'dark'))
    tearDownClass = classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp = canvas.TableCanvasTest.setUp
    tearDown = canvas.TableCanvasTest.tearDown
    editor = canvas.TableCanvasTest.editor
    type = canvas.TableCanvasTest.type

    def drain(self):
        for _ in range(4):
            self.app.processEvents()

    def choose(self, bar, button, action):
        QTest.mouseClick(bar.buttons[button], Qt.MouseButton.LeftButton)
        self.drain()
        if button in bar.alignment_choices:
            menu = next(m for m in bar.menus if m.isVisible())
            self.assertTrue(menu.isVisible())
            choices = list(bar.alignment_choices[button].values())
            if bar.dock_side in ('left', 'right'):
                self.assertEqual(choices[0].x(), choices[1].x())
                self.assertLess(choices[0].y(), choices[1].y())
                self.assertGreater(menu.height(), menu.width())
            else:
                self.assertEqual(choices[0].y(), choices[1].y())
                self.assertLess(choices[0].x(), choices[1].x())
                self.assertGreater(menu.width(), menu.height())
            value = action[len(button)+1:]
            QTest.mouseClick(bar.alignment_choices[button][value], Qt.MouseButton.LeftButton)
            self.drain()
            self.assertFalse(menu.isVisible())
            return
        menu = next(m for m in bar.menus if bar.actions[action] in m.actions())
        self.assertTrue(menu.isVisible())
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                         pos=menu.actionGeometry(bar.actions[action]).center())
        self.drain()
        self.assertFalse(menu.isVisible())

    def painted_item(self, item):
        image = QImage(700, 460, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        option = QStyleOptionGraphicsItem()
        option.exposedRect = item.boundingRect()
        painter = QPainter(image)
        try:
            painter.translate(20, 20)
            item.paint(painter, option)
        finally:
            painter.end()
        return image

    def test_selected_cells_have_soft_fill_and_do_not_modify_document_or_export(self):
        w, item = self.editor()
        source = item.to_data()
        item.setSelected(True)
        before = self.painted_item(item)
        item.select_cell(1, 0); item.select_cell(2, 1, extend=True)
        after = self.painted_item(item)
        self.assertNotEqual(before.pixelColor(60, 200), after.pixelColor(60, 200))
        self.assertEqual(before.pixelColor(550, 200), after.pixelColor(550, 200))
        self.assertEqual(item.to_data(), source)
        item.overlays_enabled = False
        self.assertEqual(before.pixelColor(60, 200), self.painted_item(item).pixelColor(60, 200))
        item.overlays_enabled = True
        item.clear_cell_selection()
        self.assertEqual(before, self.painted_item(item))

    def test_toolbar_tracks_selection_zoom_scroll_rotation_and_stays_inside_viewport(self):
        w, item = self.editor()
        bar = w.table_controller.floating_bar
        self.assertFalse(bar.isVisible())
        item.setSelected(True); self.drain()
        self.assertTrue(bar.isVisible())
        original_size = bar.size()
        layout = item.layout
        with patch.object(w, 'save_snapshot') as save:
            for zoom in (.5, 2):
                w.view.resetTransform(); w.view.scale(zoom, zoom)
                w.view.centerOn(item.sceneBoundingRect().center())
                item.setRotation(17)
                w.view.horizontalScrollBar().setValue(w.view.horizontalScrollBar().value()+30)
                self.drain()
                self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
                self.assertEqual(bar.size(), original_size)
            save.assert_not_called()
        self.assertIs(item.layout, layout)
        item.setSelected(False); self.drain()
        self.assertFalse(bar.isVisible())

    def test_toolbar_merge_split_and_structure_reuse_history_and_sidebar(self):
        w, item = self.editor(); item.select_cell(1, 0); item.select_cell(1, 1, extend=True)
        self.drain(); bar = w.table_controller.floating_bar
        self.assertTrue(w.table_panel.isEnabled())
        self.assertTrue(w._table_section.isEnabled())
        selection = item.selected_range
        from PySide6.QtCore import QPoint
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
        self.assertEqual(item.selected_range, selection)
        self.assertEqual(w.scene.selectedItems(), [item])
        w.history.clear(); w._history_capture_cache = None; w.save_snapshot()
        before = item.to_data()
        QTest.mouseClick(bar.buttons['merge'], Qt.MouseButton.LeftButton)
        self.assertEqual(cell_at(item.data, 1, 0)['column_span'], 2)
        self.assertTrue(bar.buttons['split'].isEnabled())
        QTest.mouseClick(bar.buttons['split'], Qt.MouseButton.LeftButton)
        self.assertEqual(cell_at(item.data, 1, 0)['column_span'], 1)
        self.choose(bar, 'rows', 'row_after')
        self.assertEqual(item.data['rows'], before['rows']+1)
        w.undo()
        # Undo pode restaurar sem seleção; o documento continua íntegro.
        table = w.get_current_scene_state()['tables'][0]
        self.assertEqual(table['rows'], before['rows'])
        w.redo()
        self.assertEqual(w.get_current_scene_state()['tables'][0]['rows'], before['rows']+1)

    def test_toolbar_fill_and_alignment_preserve_active_text_and_focus(self):
        w, item = self.editor(); self.type(w, item, text='Conteúdo em edição')
        self.drain(); bar = w.table_controller.floating_bar
        self.choose(bar, 'align', 'align_center')
        self.assertIs(w.table_edit.item, item)
        self.assertIn('Conteúdo em edição', item.to_data()['cells'][3]['html'])
        self.assertEqual(cell_at(item.data, 1, 1)['style']['align'], 'center')
        self.assertEqual(bar.buttons['align'].icon().cacheKey(), bar.actions['align_center'].icon().cacheKey())
        with patch('features.editor.table_floating.QColorDialog.getColor', return_value=QColor('#cceedd')):
            QTest.mouseClick(bar.buttons['fill'], Qt.MouseButton.LeftButton)
        self.assertEqual(cell_at(item.data, 1, 1)['style']['fill_color'], '#cceedd')
        self.assertIs(w.table_edit.item, item)
        self.assertIs(w.scene.focusItem(), w.table_edit.text)
        QTest.keyClicks(w.view.viewport(), ' final')
        self.assertIn('final', item.to_data()['cells'][3]['html'])

    def test_alignment_icon_picker_tracks_all_choices_selection_and_mixed_values(self):
        w, item = self.editor(); item.select_cell(1, 0); self.drain()
        bar = w.table_controller.floating_bar
        for axis, values in (('align', ('left', 'center', 'right')),
                             ('vertical_align', ('top', 'center', 'bottom'))):
            for side in ('top', 'left', 'right', 'bottom'):
                bar.dock_side = side; bar.reposition(); self.drain()
                for value in values:
                    for _ in range(2):  # Escolher a mesma opção deve conservar o destaque.
                        self.choose(bar, axis, axis+'_'+value)
                        entry = next(e for e in item.layout.cells if e.cell['row'] == 1 and e.cell['column'] == 0)
                        self.assertEqual(entry.style[axis], value)
                        self.assertEqual(bar.buttons[axis].icon().cacheKey(), bar.actions[axis+'_'+value].icon().cacheKey())
                        self.assertTrue(bar.alignment_choices[axis][value].isChecked())
                        self.assertTrue(all(not button.icon().isNull() for button in bar.alignment_choices[axis].values()))
        item.select_cell(1, 1); self.drain()
        self.assertEqual(bar.buttons['align'].icon().cacheKey(), bar.actions['align_left'].icon().cacheKey())
        item.select_cell(1, 0, extend=True); self.drain()
        self.assertTrue(bar.buttons['align'].property('mixed'))
        self.assertFalse(any(button.isChecked() for button in bar.alignment_choices['align'].values()))
        self.choose(bar, 'align', 'align_center')
        self.assertFalse(bar.buttons['align'].property('mixed'))

    def test_toolbar_hidden_for_multiselection_locked_export_and_page_change(self):
        from features.editor.canvas_items import RectangleItem
        from core.model_document import add_blank_back_page
        w, item = self.editor(add_blank_back_page(canvas.sample())); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        other = RectangleItem(30, 30); w.scene.addItem(other)
        other.setSelected(True); self.drain()
        self.assertFalse(bar.isVisible())
        other.setSelected(False); self.drain()
        self.assertTrue(bar.isVisible())
        item.overlays_enabled = False; w.view.viewport().update(); self.drain()
        self.assertFalse(bar.isVisible())
        item.overlays_enabled = True; w.view.viewport().update(); self.drain()
        self.assertTrue(bar.isVisible())
        from PySide6.QtWidgets import QGraphicsItem
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        w.table_controller.refresh(); self.drain()
        self.assertFalse(bar.isVisible())
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        w.scene.removeItem(other)
        w.switch_model_page('back'); self.drain()
        self.assertFalse(bar.isVisible())

    def test_popup_cannot_apply_to_a_different_table_and_cancel_preserves_draft(self):
        w, item = self.editor(); self.type(w, item, text='Rascunho preservado')
        self.drain(); bar = w.table_controller.floating_bar
        with patch('features.editor.table_floating.QColorDialog.getColor', return_value=QColor()):
            QTest.mouseClick(bar.buttons['fill'], Qt.MouseButton.LeftButton)
        self.assertIs(w.table_edit.item, item)
        self.assertIn('Rascunho preservado', item.to_data()['cells'][3]['html'])
        QTest.mouseClick(bar.buttons['rows'], Qt.MouseButton.LeftButton)
        self.drain()
        self.assertTrue(any(menu.isVisible() for menu in bar.menus))
        self.assertTrue(w.table_controller.add_table(2, 2)); self.drain()
        current = w.table_controller.selected()
        self.assertFalse(any(menu.isVisible() for menu in bar.menus))
        source = current.to_data()
        bar.actions['row_after'].trigger()
        self.assertEqual(current.to_data(), source)

    def test_context_bar_on_organogram_and_compact_view_does_not_create_scene_items(self):
        from core.organogram import add_organogram
        w, _ = self.editor(add_organogram(canvas.sample()))
        w.switch_model_page('organogram')
        self.assertTrue(w.table_controller.add_table(2, 2)); self.drain()
        item = w.table_controller.selected(); bar = w.table_controller.floating_bar
        self.assertTrue(bar.isVisible())
        layout, roots = item.layout, tuple(w.scene.items())
        viewport = w.view.viewport()
        w.view.setFixedWidth(300)
        self.drain()
        w.view.centerOn(item.sceneBoundingRect().center())
        self.drain()
        self.assertTrue(bar.isVisible())
        self.assertTrue(viewport.rect().contains(bar.geometry()))
        self.assertEqual(bar.buttons['rows'].text(), '')
        self.assertEqual(tuple(w.scene.items()), roots)
        self.assertIs(item.layout, layout)


class TableJunctionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = canvas.QApplication.instance() or canvas.QApplication([])

    def paint(self, table):
        image = QImage(320, 220, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.translate(20, 20)
            paint_table_local(painter, TableLayout(table))
        finally:
            painter.end()
        return image

    def test_thick_outer_corners_are_complete_rectangles(self):
        table = new_table(2, 2, width=280, height=180)
        table = format_edges(table, 0, 0, 1, 1, {'width': 12, 'color': '#000000'})
        image = self.paint(table)
        for x, y in ((17,17), (303,17), (17,203), (303,203)):
            self.assertEqual(image.pixelColor(x, y).name(), '#000000')
        self.assertEqual(image.pixelColor(12, 12).name(), '#ffffff')

    def test_equal_translucent_edges_do_not_dark_multiply_at_corners_or_junctions(self):
        table = new_table(2, 2, width=280, height=180)
        table = format_edges(table, 0, 0, 1, 1, {'width': 12, 'color': '#000000', 'opacity': .5})
        image = self.paint(table)
        edge = image.pixelColor(60, 20)
        for x, y in ((17,17), (160,110), (160,20)):
            self.assertEqual(image.pixelColor(x, y), edge)

    def test_merged_hidden_segments_and_independent_border_styles_are_preserved(self):
        table = merge_cells(new_table(2, 2, width=280, height=180), 0, 0, 0, 1)
        table = format_edges(table, 0, 0, 1, 1, {'width': 12, 'color': '#ff0000'}, target='outer')
        table = format_edges(table, 0, 0, 1, 1, {'width': 4, 'color': '#0000ff'}, target='inner')
        image = self.paint(table)
        self.assertEqual(image.pixelColor(160, 60).name(), '#ffffff')
        self.assertEqual(image.pixelColor(160, 150).name(), '#0000ff')
        self.assertEqual(image.pixelColor(17, 17).name(), '#ff0000')


if __name__ == '__main__':
    unittest.main()
