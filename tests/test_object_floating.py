"""Atalhos de formas/grupos/blocos: escopo, operações reais e estado transitório."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint, QPointF, QRect
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsItem, QLabel

import test_table_canvas as canvas
import test_table_floating_drag as drag
from test_organogram import board_document
from core.organogram import new_group
from core.document_layers import upgrade_layers
from core.themes import theme_manager
from features.editor.editor_window import EditorWindow
from features.editor.canvas_items import RectangleItem, ImageItem, SignatureItem, DesignerBox
from features.editor.organogram_editor import BoardGroupItem, BoardConnectorItem


class ObjectFloatingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        canvas.TableCanvasTest.setUpClass.__func__(cls)
        theme_manager().select(os.environ.get('FORNAX_TEST_THEME', 'dark'))
    tearDownClass = classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp = canvas.TableCanvasTest.setUp
    tearDown = canvas.TableCanvasTest.tearDown
    drain = drag.TableFloatingDragTest.drain
    begin = drag.TableFloatingDragTest.begin
    move = drag.TableFloatingDragTest.move
    drop = drag.TableFloatingDragTest.drop
    assert_clean = drag.TableFloatingDragTest.assert_clean

    def editor(self, document=None):
        if document is None:
            document = canvas.sample()
            page = document['pages'][0]
            page['shapes'] = [dict(x=120, y=160, width=180, height=120, layer_id=i,
                                   shape_type=kind, fill_color='#ffffff', object_id=f'shape:{i}')
                              for i, kind in enumerate(('rectangle', 'ellipse', 'line'), 1)]
            page['boxes'] = [dict(x=120, y=160, w=180, h=120, layer_id=4,
                                  object_id='text:4', html='<p>Texto</p>')]
            path = self.root/'image.png'
            image = QImage(80, 60, QImage.Format.Format_RGB32); image.fill(QColor('#336699'))
            image.save(str(path))
            page['images'] = [dict(x=350, y=160, width=80, height=60, layer_id=5,
                                   object_id='image:5', path=str(path))]
            page['signatures'] = [dict(x=350, y=240, width=80, height=60, layer_id=6,
                                       object_id='signature:6', path=str(path))]
            page['layer_order'].extend(['shape:1', 'shape:2', 'shape:3', 'text:4', 'image:5', 'signature:6'])
        w = EditorWindow(); self.windows.append(w)
        w._load_document_into_scene(document)
        w.resize(1600, 1100); w.show(); w.activateWindow(); self.drain()
        w._zoom_to_fit(); self.drain()
        return w

    def select(self, w, *items):
        with w._selection_batch():
            w.scene.clearSelection()
            for item in items:
                item.setSelected(True)
        self.drain()

    def shape(self, w, identifier=1):
        return next(item for item in w.scene.items() if isinstance(item, RectangleItem)
                    and item.layer_id == identifier and not getattr(item, 'is_document_background', False))

    def tools(self, bar):
        return {key for key, button in bar.buttons.items() if button.isVisible() and key != 'collapse'}

    def click_through_window(self, widget, point=None):
        point = widget.rect().center() if point is None else point
        handle = widget.window().windowHandle()
        QTest.mouseClick(handle, Qt.MouseButton.LeftButton,
                         pos=handle.mapFromGlobal(widget.mapToGlobal(point)))
        self.drain()

    def start_mask_picker(self, bar, through_window=False):
        if through_window:
            self.click_through_window(bar.buttons['mask'])
        else:
            QTest.mouseClick(bar.buttons['mask'], Qt.MouseButton.LeftButton); self.drain()
        self.assertEqual(len(bar.mask_menu.actions()), 2)
        self.assertFalse(bar.buttons['mask'].isChecked())
        point = bar.mask_menu.actionGeometry(bar.mask_menu.actions()[0]).center()
        if through_window:
            self.click_through_window(bar.mask_menu, point)
        else:
            QTest.mouseClick(bar.mask_menu, Qt.MouseButton.LeftButton, pos=point)
        self.drain()
        self.assertIsNotNone(bar.mask_picker.shape)
        self.assertTrue(bar.mask_picker.hint.isVisible())

    def click_canvas(self, w, item):
        point = w.view.mapFromScene(item.mapToScene(item.rect().center()))
        QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.drain()

    def test_only_approved_contexts_show_the_bar_and_tables_keep_their_bar(self):
        w = self.editor(); bar = w.object_floating_bar
        for identifier in (1, 2):
            self.select(w, self.shape(w, identifier))
            self.assertTrue(bar.isVisible())
            self.assertEqual(self.tools(bar), {'fill', 'outline', 'opacity', 'mask'})
            self.assertFalse(w.table_controller.floating_bar.isVisible())
        text = next(item for item in w.scene.items() if isinstance(item, DesignerBox))
        self.select(w, text)
        self.assertTrue(bar.isVisible())
        self.assertEqual(self.tools(bar), set(bar.text_tools.keys))
        excluded = [item for item in w.scene.items() if isinstance(item, SignatureItem)
                    or isinstance(item, ImageItem) and not isinstance(item, RectangleItem)
                    or getattr(item, 'is_document_background', False)]
        excluded.append(self.shape(w, 3))
        excluded.append(next(item for item in w.scene.items() if isinstance(item, canvas.TableItem)))
        for item in excluded:
            self.select(w, item)
            self.assertFalse(bar.isVisible(), type(item).__name__)
        self.assertTrue(w.table_controller.floating_bar.isVisible())
        rectangle = self.shape(w)
        self.select(w, rectangle)
        rectangle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        bar.refresh(); self.assertFalse(bar.isVisible())

    def test_fill_outline_opacity_use_existing_controls_and_undo_redo(self):
        w = self.editor(); self.select(w, self.shape(w)); bar = w.object_floating_bar
        start = w.history._current_index
        with patch('features.editor.object_floating.QColorDialog.getColor', return_value=QColor('#123456')):
            QTest.mouseClick(bar.buttons['fill'], Qt.MouseButton.LeftButton)
        self.assertEqual(self.shape(w).fill_color, '#123456')
        self.assertEqual(w._shape_quick_controls['color'].text(), '#123456')
        self.assertEqual(w.history._current_index, start+1)
        w.undo(); self.drain(); self.assertEqual(self.shape(w).fill_color, '#ffffff')
        w.redo(); self.drain(); self.assertEqual(self.shape(w).fill_color, '#123456')
        previous = self.shape(w).outline_enabled
        QTest.mouseClick(bar.buttons['outline'], Qt.MouseButton.LeftButton)
        self.assertEqual(self.shape(w).outline_enabled, not previous)
        self.assertEqual(bar.buttons['outline'].isChecked(), not previous)
        w.undo(); self.drain(); self.assertEqual(self.shape(w).outline_enabled, previous)
        w.redo(); self.drain()
        QTest.mouseClick(bar.buttons['opacity'], Qt.MouseButton.LeftButton); self.drain()
        bar.opacity_spin.setValue(40); bar.opacity_spin.editingFinished.emit(); self.drain()
        self.assertAlmostEqual(self.shape(w).opacity(), .4)
        self.assertEqual(w.caixa_texto_panel.spin_opacity.value(), 40)
        w.undo(); self.drain(); self.assertAlmostEqual(self.shape(w).opacity(), 1)
        w.redo(); self.drain(); self.assertAlmostEqual(self.shape(w).opacity(), .4)

    def test_cancelled_or_stale_color_and_opacity_do_not_edit_another_selection(self):
        w = self.editor(); rectangle, ellipse = self.shape(w), self.shape(w, 2)
        self.select(w, rectangle); bar = w.object_floating_bar
        start = w.history._current_index
        with patch('features.editor.object_floating.QColorDialog.getColor', return_value=QColor()):
            bar.choose_fill()
        self.assertEqual(start, w.history._current_index)
        def changed_selection(*args):
            self.select(w, ellipse)
            return QColor('#123456')
        with patch('features.editor.object_floating.QColorDialog.getColor', side_effect=changed_selection):
            bar.choose_fill()
        self.assertEqual(rectangle.fill_color, '#ffffff')
        self.assertEqual(ellipse.fill_color, '#ffffff')
        self.select(w, rectangle)
        QTest.mouseClick(bar.buttons['opacity'], Qt.MouseButton.LeftButton); self.drain()
        self.select(w, ellipse)
        bar.opacity_spin.setValue(20); bar.apply_opacity()
        self.assertAlmostEqual(rectangle.opacity(), 1)
        self.assertAlmostEqual(ellipse.opacity(), 1)
        self.assertEqual(start, w.history._current_index)

    def test_mask_creation_edit_session_removal_and_history_preserve_image(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar
        image = w._free_mask_images()[0]
        QTest.mouseClick(bar.buttons['mask'], Qt.MouseButton.LeftButton); self.drain()
        self.assertTrue(bar.mask_menu.isVisible())
        self.assertEqual(len(bar.mask_menu.actions()), 2)
        bar.mask_menu.close(); bar.mask_menu.actions()[0].trigger(); self.drain()
        self.assertTrue(w._free_mask_images())
        self.assertFalse(bar.isVisible())
        self.click_canvas(w, image)
        self.assertIs(image.parentItem(), shape)
        self.assertIsNotNone(w._mask_edit_session)
        self.assertTrue(bar.isVisible())
        self.assertEqual(self.tools(bar), {'mask_cancel', 'mask_finish'})
        w.finish_mask_edit(True); self.select(w, shape)
        self.assertTrue(bar.buttons['mask'].isChecked())
        QTest.mouseClick(bar.buttons['mask'], Qt.MouseButton.LeftButton); self.drain()
        self.assertFalse(shape.masked_images())
        self.assertIsNone(image.parentItem())
        self.assertIn(image, w.scene.items())
        w.undo(); self.drain(); self.assertEqual(len(self.shape(w).masked_images()), 1)
        w.redo(); self.drain(); self.assertFalse(self.shape(w).masked_images())
        shape = self.shape(w); self.select(w, shape)
        shape.dynamic_image_field = 'Foto'; bar.refresh()
        self.assertTrue(bar.buttons['mask'].isEnabled())
        self.assertTrue(bar.buttons['mask'].isChecked())

    def test_group_shortcut_uses_group_rule_and_is_undoable(self):
        w = self.editor(); first, second = self.shape(w), self.shape(w, 2)
        self.select(w, first, second); bar = w.object_floating_bar
        self.assertEqual(self.tools(bar), {'group'})
        QTest.mouseClick(bar.buttons['group'], Qt.MouseButton.LeftButton); self.drain()
        self.assertIsNotNone(first.group_id); self.assertEqual(first.group_id, second.group_id)
        self.assertIn('Desagrupar', bar.buttons['group'].toolTip())
        QTest.mouseClick(bar.buttons['group'], Qt.MouseButton.LeftButton); self.drain()
        self.assertIsNone(first.group_id); self.assertIsNone(second.group_id)
        w.undo(); self.drain()
        self.assertIsNotNone(self.shape(w).group_id)
        self.assertEqual(self.shape(w).group_id, self.shape(w, 2).group_id)
        w.redo(); self.drain(); self.assertIsNone(self.shape(w).group_id)

    def test_mask_menu_cannot_apply_to_a_new_selection_or_deleted_image(self):
        w = self.editor(); first, second = self.shape(w), self.shape(w, 2)
        self.select(w, first); bar = w.object_floating_bar
        bar.popup(bar.buttons['mask'], bar.mask_menu)
        old_action = bar.mask_menu.actions()[0]
        self.select(w, second)
        old_action.trigger(); self.drain()
        self.assertIsNone(bar.mask_picker.shape)
        self.assertFalse(first.masked_images()); self.assertFalse(second.masked_images())
        image = w._free_mask_images()[0]
        target = bar.target_key(second)
        # A ação antiga também não pode reaproveitar uma imagem retirada da cena.
        w.scene.removeItem(image)
        try:
            bar.apply_mask(image, target)
            self.assertFalse(second.masked_images())
        finally:
            w.scene.addItem(image)

    def test_mask_picker_accepts_layer_name_without_changing_selection_first(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar; image = w._free_mask_images()[0]
        self.start_mask_picker(bar)
        row = next(w.layer_list.item(i) for i in range(w.layer_list.count())
                   if w.layer_list.item(i).data(Qt.ItemDataRole.UserRole) is image)
        w.layer_list.scrollToItem(row); self.drain()
        widget = w.layer_list.itemWidget(row)
        label = next(child for child in widget.findChildren(QLabel)
                     if type(child).__name__ == 'ElidedLayerLabel')
        QTest.mouseClick(label, Qt.MouseButton.LeftButton); self.drain()
        self.assertIsNone(bar.mask_picker.shape)
        self.assertIs(image.parentItem(), shape)
        self.assertIsNotNone(w._mask_edit_session)
        w.finish_mask_edit(False); self.drain()
        self.assertEqual(len(w._free_mask_images()), 1)
        self.assertFalse(self.shape(w).masked_images())

    def test_mask_picker_accepts_click_delivered_through_native_window(self):
        for location in ('canvas', 'layers'):
            with self.subTest(location=location):
                w = self.editor(); shape = self.shape(w); self.select(w, shape)
                bar = w.object_floating_bar; image = w._free_mask_images()[0]
                self.start_mask_picker(bar, through_window=True)
                if location == 'canvas':
                    point = w.view.mapFromScene(image.mapToScene(image.rect().center()))
                    self.click_through_window(w.view.viewport(), point)
                else:
                    row = next(w.layer_list.item(i) for i in range(w.layer_list.count())
                               if w.layer_list.item(i).data(Qt.ItemDataRole.UserRole) is image)
                    w.layer_list.scrollToItem(row); self.drain()
                    label = next(child for child in w.layer_list.itemWidget(row).findChildren(QLabel)
                                 if type(child).__name__ == 'ElidedLayerLabel')
                    self.click_through_window(label)
                self.assertIs(image.parentItem(), shape)
                self.assertIsNotNone(w._mask_edit_session)
                self.assertIsNone(bar.mask_picker.shape)
                w.finish_mask_edit(True)
                w.undo(); self.drain(); self.assertFalse(self.shape(w).masked_images())
                w.redo(); self.drain(); self.assertEqual(len(self.shape(w).masked_images()), 1)

    def test_mask_picker_cancels_invalid_click_escape_selection_and_page_interaction(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar
        before = deepcopy(w._document_with_active_page())
        index = w.history._current_index
        signature = next(item for item in w.scene.items() if isinstance(item, SignatureItem))
        for item in (signature, shape):
            self.start_mask_picker(bar)
            self.click_canvas(w, item)
            self.assertIsNone(bar.mask_picker.shape)
            self.assertFalse(shape.masked_images())
        self.start_mask_picker(bar)
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_Escape); self.drain()
        self.assertIsNone(bar.mask_picker.shape)
        self.start_mask_picker(bar)
        w._finish_page_interaction(); self.drain()
        self.assertIsNone(bar.mask_picker.shape)
        self.start_mask_picker(bar)
        self.select(w, self.shape(w, 2))
        self.assertIsNone(bar.mask_picker.shape)
        self.assertEqual(w._document_with_active_page(), before)
        self.assertEqual(w.history._current_index, index)
        self.assertFalse(bar.mask_picker.hint.isVisible())

    def test_floating_mask_finish_returns_shape_toolbar_and_records_one_step(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar; image = w._free_mask_images()[0]
        index = w.history._current_index
        self.start_mask_picker(bar, through_window=True)
        self.click_through_window(w.view.viewport(), w.view.mapFromScene(image.mapToScene(image.rect().center())))
        self.assertEqual(self.tools(bar), {'mask_cancel', 'mask_finish'})
        self.assertFalse(bar.grip.isVisible()); self.assertFalse(bar.collapse_button.isVisible())
        self.assertFalse(w.table_controller.floating_bar.isVisible())
        image.moveBy(10, 0); self.drain()
        self.assertEqual(w.history._current_index, index)
        self.click_through_window(bar.buttons['mask_finish'])
        self.assertIsNone(w._mask_edit_session)
        self.assertEqual(self.tools(bar), {'fill', 'outline', 'opacity', 'mask'})
        self.assertTrue(shape.isSelected()); self.assertTrue(bar.grip.isVisible())
        self.assertEqual(w.history._current_index, index+1)
        w.undo(); self.drain(); self.assertFalse(self.shape(w).masked_images())
        w.redo(); self.drain(); self.assertEqual(len(self.shape(w).masked_images()), 1)

    def test_floating_mask_cancel_rolls_back_new_and_existing_masks(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                w = self.editor(); shape = self.shape(w); self.select(w, shape)
                image = w._free_mask_images()[0]; bar = w.object_floating_bar
                if existing:
                    w.create_mask(image, shape); w.finish_mask_edit(True); self.select(w, shape)
                before = deepcopy(w._document_with_active_page())
                index = w.history._current_index
                if existing:
                    w.begin_mask_edit(image)
                else:
                    w.create_mask(image, shape)
                self.drain()
                image.moveBy(20, 5); self.drain()
                self.click_through_window(bar.buttons['mask_cancel'])
                self.assertIsNone(w._mask_edit_session)
                after = w._document_with_active_page()
                # O restaurador normaliza os níveis z pela layer_order.
                # Comparar a mesma normalização mantém todos os dados e a
                # sequência visual, sem exigir níveis numéricos antigos.
                self.assertEqual({**after, 'pages': [upgrade_layers(page) for page in after['pages']]},
                                 {**before, 'pages': [upgrade_layers(page) for page in before['pages']]})
                self.assertEqual(w.history._current_index, index)
                self.assertEqual(self.tools(bar), {'fill', 'outline', 'opacity', 'mask'})
                self.assertTrue(self.shape(w).isSelected())

    def test_floating_mask_actions_keep_shape_anchor_and_ignore_collapsed_preference(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar; image = w._free_mask_images()[0]
        bar.toggle_collapsed(); self.drain(); self.assertTrue(bar.collapsed)
        w.create_mask(image, shape); self.drain()
        self.assertEqual(self.tools(bar), {'mask_cancel', 'mask_finish'})
        for side in ('top', 'left', 'bottom', 'right'):
            bar.dock_side = side; bar.reposition(); self.drain()
            before = bar.geometry()
            image.moveBy(40, 10); self.drain()
            self.assertEqual(bar.geometry(), before)
            self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
            for key in ('mask_cancel', 'mask_finish'):
                self.assertTrue(bar.buttons[key].isVisible())
                self.assertGreaterEqual(bar.buttons[key].width(),
                                        bar.buttons[key].fontMetrics().horizontalAdvance(bar.buttons[key].text()))
        w.view.scale(.75, .75); self.drain()
        self.assertTrue(bar.isVisible())
        self.click_through_window(bar.buttons['mask_finish'])
        self.assertTrue(bar.collapsed)
        self.assertTrue(bar.grip.isVisible()); self.assertTrue(bar.collapse_button.isVisible())
        self.assertEqual(self.tools(bar), set())
        bar.toggle_collapsed(); self.drain()
        self.assertEqual(self.tools(bar), {'fill', 'outline', 'opacity', 'mask'})

    def test_dynamic_image_shortcut_uses_existing_fields_history_and_removal(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar
        index = w.history._current_index
        QTest.mouseClick(bar.buttons['mask'], Qt.MouseButton.LeftButton); self.drain()
        bar.mask_menu.close(); bar.mask_menu.actions()[1].trigger(); self.drain()
        self.assertTrue(shape.dynamic_image_field)
        self.assertIn(shape.dynamic_image_field, w.get_all_model_placeholders())
        self.assertTrue(w._shape_quick_controls['dynamic'].isChecked())
        self.assertTrue(bar.buttons['mask'].isChecked())
        self.assertEqual(w.history._current_index, index+1)
        w.undo(); self.drain(); self.assertFalse(self.shape(w).dynamic_image_field)
        w.redo(); self.drain(); shape = self.shape(w)
        self.assertTrue(shape.dynamic_image_field)
        self.select(w, shape)
        QTest.mouseClick(bar.buttons['mask'], Qt.MouseButton.LeftButton); self.drain()
        self.assertFalse(shape.dynamic_image_field)
        self.assertFalse(bar.buttons['mask'].isChecked())
        image = w._free_mask_images()[0]; w.scene.removeItem(image)
        try:
            bar.popup(bar.buttons['mask'], bar.mask_menu)
            self.assertFalse(bar.mask_menu.actions()[0].isEnabled())
            self.assertTrue(bar.mask_menu.actions()[1].isEnabled())
        finally:
            bar.mask_menu.close(); w.scene.addItem(image)

    def test_board_connect_shortcut_preserves_connection_workflow_and_history(self):
        document = board_document(1, 1)
        document['organogram']['groups'].append(new_group(document, columns=1, rows=1, x=900, y=1000))
        w = self.editor(document); w.switch_model_page('organogram'); self.drain()
        groups = w._board_items(); child, parent = groups
        self.select(w, child); bar = w.object_floating_bar
        self.assertEqual(self.tools(bar), {'connect'})
        QTest.mouseClick(bar.buttons['connect'], Qt.MouseButton.LeftButton); self.drain()
        self.assertEqual(w._board_connection_sources, {child.data['id']})
        self.assertFalse(bar.isVisible())
        w._connect_to_board_target(parent.data['id']); self.drain()
        self.assertEqual(len(w._board_connections_data()), 1)
        w.undo(); self.drain(); self.assertEqual(w._board_connections_data(), [])
        w.redo(); self.drain(); self.assertEqual(len(w._board_connections_data()), 1)
        connector = next(item for item in w.scene.items() if isinstance(item, BoardConnectorItem))
        self.select(w, connector); self.assertFalse(bar.isVisible())

    def test_docking_collapse_zoom_and_selection_changes_are_transient(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar
        before = deepcopy(w._document_with_active_page())
        with patch.object(w, 'save_snapshot') as save:
            for collapsed in (False, True):
                if bar.collapsed != collapsed:
                    bar.toggle_collapsed(); self.drain()
                for side in ('left', 'bottom', 'right', 'top'):
                    self.begin(bar); point = bar._drag_geometries[side].center()
                    self.move(bar, point); self.drop(bar, point)
                    self.assert_clean(bar); self.assertEqual(bar.dock_side, side)
                    self.assertEqual(bar.collapsed, collapsed)
                    self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
                    self.assert_toolbar_geometry(bar, side)
            self.begin(bar)
            self.select(w, self.shape(w, 2))
            self.assert_clean(bar)
            w.view.scale(.6, .6); self.shape(w, 2).setPos(QPointF(170, 200)); self.drain()
            self.assertTrue(bar.isVisible())
            # Restore the movement made only to check tracking.
            self.shape(w, 2).setPos(QPointF(120, 160)); self.drain()
            save.assert_not_called()
        self.assertEqual(w._document_with_active_page(), before)

    def assert_toolbar_geometry(self, bar, side):
        self.assertTrue(bar.isVisible())
        widgets = [bar.buttons[key] for key in (*bar.tool_keys(), 'collapse')
                   if bar.buttons[key].isVisible()] + [bar.grip]
        rectangles = [QRect(widget.mapTo(bar, QPoint()), widget.size()) for widget in widgets]
        for rect in rectangles:
            self.assertTrue(bar.rect().contains(rect), (bar.rect(), rect))
        vertical = side in ('left', 'right')
        if vertical:
            self.assertGreater(bar.height(), bar.width())
        else:
            self.assertGreater(bar.width(), bar.height())
        for first, second in zip(rectangles, rectangles[1:]):
            if vertical:
                self.assertEqual(first.center().x(), second.center().x())
                self.assertLess(first.bottom(), second.top())
            else:
                self.assertEqual(first.center().y(), second.center().y())
                self.assertLess(first.right(), second.left())

    def test_shape_collapse_keeps_grip_anchor_and_restores_size_on_every_side(self):
        w = self.editor(); shape = self.shape(w); self.select(w, shape)
        bar = w.object_floating_bar
        before = deepcopy(w._document_with_active_page())
        for side in ('top', 'left', 'bottom', 'right'):
            with self.subTest(side=side):
                bar.dock_side = side; bar.reposition(); self.drain()
                expanded = bar.geometry()
                anchor = bar.grip.mapTo(w.view.viewport(), QPoint())
                self.assert_toolbar_geometry(bar, side)
                self.click_through_window(bar.collapse_button); self.drain()
                self.assertTrue(bar.collapsed)
                self.assertEqual(bar.grip.mapTo(w.view.viewport(), QPoint()), anchor)
                if side in ('top', 'bottom'):
                    self.assertEqual(bar.geometry().right(), expanded.right())
                    self.assertLess(bar.width(), expanded.width()/2)
                else:
                    self.assertEqual(bar.geometry().bottom(), expanded.bottom())
                    self.assertLess(bar.height(), expanded.height()/2)
                self.assert_toolbar_geometry(bar, side)
                self.click_through_window(bar.collapse_button); self.drain()
                self.assertFalse(bar.collapsed)
                self.assertEqual(bar.geometry(), expanded)
                self.assert_toolbar_geometry(bar, side)
        self.assertEqual(w._document_with_active_page(), before)


if __name__ == '__main__':
    unittest.main()
