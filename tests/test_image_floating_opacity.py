"""Imagens na barra compartilhada e prévias de opacidade com um único undo."""
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtTest import QTest

from features.editor.canvas_items import DesignerBox, RectangleItem
from features.generator.renderer import NativeRenderer
from core.board_borders import border_style
import test_object_floating as fixtures
import test_organogram as board_fixtures


class ImageFloatingOpacityTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.ObjectFloatingTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.ObjectFloatingTest.tearDownClass.__func__)
    setUp = fixtures.ObjectFloatingTest.setUp
    tearDown = fixtures.ObjectFloatingTest.tearDown
    editor = fixtures.ObjectFloatingTest.editor
    drain = fixtures.ObjectFloatingTest.drain
    select = fixtures.ObjectFloatingTest.select
    shape = fixtures.ObjectFloatingTest.shape
    tools = fixtures.ObjectFloatingTest.tools
    click_canvas = fixtures.ObjectFloatingTest.click_canvas
    click_through_window = fixtures.ObjectFloatingTest.click_through_window

    def image(self, window):
        return next(item for item in window.scene.items() if window._is_mask_image(item) and item.layer_id == 5)

    def open_opacity(self, bar):
        self.click_through_window(bar.buttons['opacity'])
        self.assertTrue(bar.alignment_menus['opacity'].isVisible())
        return bar.opacity_spin

    def choose_menu_action(self, bar, index=0):
        self.click_through_window(bar.buttons['mask'])
        self.assertTrue(bar.mask_menu.isVisible())
        point = bar.mask_menu.actionGeometry(bar.mask_menu.actions()[index]).center()
        self.click_through_window(bar.mask_menu, point)

    def test_image_shows_only_opacity_and_mask_with_shared_docking(self):
        window = self.editor()
        self.select(window, self.image(window))
        bar = window.object_floating_bar
        self.assertTrue(bar.isVisible())
        self.assertEqual(self.tools(bar), {'opacity', 'mask'})
        for side in ('top', 'bottom', 'left', 'right', 'right_far'):
            bar.dock_side = side
            bar.reposition()
            self.assertEqual(bar.is_vertical, side.startswith(('left', 'right')))
            bar.collapsed = True
            bar.reposition()
            self.assertTrue(bar.collapse_button.isVisible())
            self.assertFalse(bar.buttons['opacity'].isVisible())
            bar.collapsed = False
            bar.reposition()
            self.assertEqual(self.tools(bar), {'opacity', 'mask'})

    def test_arrow_steps_preview_immediately_and_enter_creates_one_undo_for_each_object_type(self):
        for kind in ('shape', 'image', 'text'):
            with self.subTest(kind=kind):
                window = self.editor()
                item = (self.shape(window) if kind == 'shape' else self.image(window) if kind == 'image'
                        else next(item for item in window.scene.items() if isinstance(item, DesignerBox)))
                key = window._item_selection_key(item)
                self.select(window, item)
                window.save_snapshot()
                index = window.history._current_index
                spin = self.open_opacity(window.object_floating_bar)
                for expected in (99, 98, 97):
                    QTest.keyClick(spin, Qt.Key.Key_Down)
                    self.assertAlmostEqual(item.opacity(), expected / 100)
                    self.assertEqual(window.caixa_texto_panel.spin_opacity.value(), expected)
                    self.assertEqual(window.history._current_index, index)
                    self.assertTrue(window.object_floating_bar.alignment_menus['opacity'].isVisible())
                QTest.keyClick(spin, Qt.Key.Key_Return)
                self.drain()
                self.assertEqual(window.history._current_index, index + 1)
                window.undo(); self.drain()
                restored = next(item for item in window.scene.items() if window._item_selection_key(item) == key)
                self.assertAlmostEqual(restored.opacity(), 1)
                window.redo(); self.drain()
                restored = next(item for item in window.scene.items() if window._item_selection_key(item) == key)
                self.assertAlmostEqual(restored.opacity(), .97)

    def test_closing_popup_commits_preview_once_and_escape_cancels_without_history(self):
        window = self.editor()
        self.select(window, self.image(window))
        bar = window.object_floating_bar
        window.save_snapshot()
        index = window.history._current_index
        spin = self.open_opacity(bar)
        spin.setValue(50)
        self.assertAlmostEqual(self.image(window).opacity(), .5)
        self.assertEqual(window.history._current_index, index)
        bar.alignment_menus['opacity'].close()
        self.drain()
        self.assertEqual(window.history._current_index, index + 1)
        spin = self.open_opacity(bar)
        spin.setValue(30)
        QTest.keyClick(spin, Qt.Key.Key_Escape)
        self.drain()
        self.assertAlmostEqual(self.image(window).opacity(), .5)
        self.assertEqual(window.caixa_texto_panel.spin_opacity.value(), 50)
        self.assertEqual(window.history._current_index, index + 1)

    def test_changing_selection_commits_previous_preview_without_editing_new_object(self):
        window = self.editor()
        self.select(window, self.image(window))
        bar = window.object_floating_bar
        window.save_snapshot()
        index = window.history._current_index
        spin = self.open_opacity(bar)
        spin.setValue(70)
        self.select(window, self.shape(window))
        self.assertFalse(bar.alignment_menus['opacity'].isVisible())
        spin.setValue(20)
        bar.apply_opacity()
        self.assertAlmostEqual(self.image(window).opacity(), .7)
        self.assertAlmostEqual(self.shape(window).opacity(), 1)
        self.assertEqual(window.history._current_index, index + 1)
        window.undo(); self.drain()
        self.assertAlmostEqual(self.image(window).opacity(), 1)

    def test_closing_popup_also_confirms_a_typed_percentage(self):
        window = self.editor()
        self.select(window, self.image(window))
        window.save_snapshot()
        index = window.history._current_index
        bar = window.object_floating_bar
        spin = self.open_opacity(bar)
        QTest.keyClick(spin, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(spin, '42')
        bar.alignment_menus['opacity'].close()
        self.drain()
        self.assertAlmostEqual(self.image(window).opacity(), .42)
        self.assertEqual(window.history._current_index, index + 1)

    def test_preview_survives_undo_redo_and_matches_final_raster(self):
        window = self.editor()
        self.select(window, self.image(window))
        window.save_snapshot()
        before = NativeRenderer(window.get_current_scene_state()).render_to_qimage({}, {})
        index = window.history._current_index
        spin = self.open_opacity(window.object_floating_bar)
        spin.setValue(50)
        state = window.get_current_scene_state()
        self.assertEqual(state['images'][0]['opacity'], .5)
        result = NativeRenderer(state).render_to_qimage({}, {})
        original = before.pixelColor(390, 190)
        actual = result.pixelColor(390, 190)
        for channel in ('red', 'green', 'blue'):
            self.assertAlmostEqual(getattr(actual, channel)(), (getattr(original, channel)() + 255) / 2, delta=1)
        # Undo deve preservar o ajuste mesmo sem Enter ou perda de foco.
        window.undo(); self.drain()
        self.assertEqual(window.history._current_index, index)
        self.assertAlmostEqual(self.image(window).opacity(), 1)
        window.redo(); self.drain()
        self.assertAlmostEqual(self.image(window).opacity(), .5)

    def test_image_can_pick_shape_on_canvas_and_remove_mask_from_its_own_bar(self):
        window = self.editor()
        # O exemplo da suíte sobrepõe texto e formas; deixe o alvo exposto.
        self.shape(window).setPos(650, 500)
        window.save_snapshot()
        image = self.image(window)
        self.select(window, image)
        bar = window.object_floating_bar
        self.choose_menu_action(bar)
        self.assertIs(bar.mask_picker.shape, image)
        self.click_canvas(window, self.shape(window))
        self.assertIsNotNone(window._mask_edit_session)
        self.assertIs(image.parentItem(), self.shape(window))
        self.assertEqual(self.tools(bar), {'mask_cancel', 'mask_finish'})
        self.click_through_window(bar.buttons['mask_finish'])
        self.assertEqual(bar.kind, 'image')
        self.select(window, self.image(window))
        self.assertEqual(self.tools(bar), {'opacity', 'mask'})
        self.assertTrue(bar.buttons['mask'].isChecked())
        self.choose_menu_action(bar, 1)
        self.assertIsNone(self.image(window).parentItem())
        self.assertFalse(bar.buttons['mask'].isChecked())
        window.undo(); self.drain()
        self.assertIsInstance(self.image(window).parentItem(), RectangleItem)
        window.redo(); self.drain()
        self.assertIsNone(self.image(window).parentItem())

    def test_image_can_pick_shape_in_layers_and_cancel_framing(self):
        window = self.editor()
        self.select(window, self.image(window))
        bar = window.object_floating_bar
        self.choose_menu_action(bar)
        row = next(window.layer_list.item(i) for i in range(window.layer_list.count())
                   if window.layer_list.item(i).data(Qt.ItemDataRole.UserRole) is self.shape(window, 2))
        window.layer_list.scrollToItem(row)
        point = window.layer_list.visualItemRect(row).center()
        self.click_through_window(window.layer_list.viewport(), point)
        self.assertIsNotNone(window._mask_edit_session)
        self.assertIs(self.image(window).parentItem(), self.shape(window, 2))
        self.click_through_window(bar.buttons['mask_cancel'])
        self.assertIsNone(self.image(window).parentItem())
        self.assertEqual(bar.kind, 'image')

    def test_image_can_edit_existing_mask_and_invalid_click_cancels_picker(self):
        window = self.editor()
        self.select(window, self.image(window))
        bar = window.object_floating_bar
        self.choose_menu_action(bar)
        text = next(item for item in window.scene.items() if isinstance(item, DesignerBox))
        self.click_canvas(window, text)
        self.assertIsNone(bar.mask_picker.shape)
        self.assertIsNone(self.image(window).parentItem())
        window.create_mask(self.image(window), self.shape(window))
        window.finish_mask_edit(True)
        self.select(window, self.image(window))
        self.choose_menu_action(bar)
        self.assertIsNotNone(window._mask_edit_session)
        self.click_through_window(bar.buttons['mask_finish'])
        self.assertIsNone(window._mask_edit_session)

    def test_shape_fill_and_outline_preview_without_extra_undo_entries(self):
        window = self.editor()
        item = self.shape(window)
        self.select(window, item)
        window._shape_quick_controls['outline'].click()
        window.save_snapshot()
        for name, attribute in (('shapeFillAlpha', 'fill_opacity'), ('shapeOutlineAlpha', 'outline_opacity')):
            spin = window.findChild(QDoubleSpinBox, name)
            self.assertIsNotNone(spin)
            index = window.history._current_index
            spin.setValue(80)
            self.assertAlmostEqual(getattr(item, attribute), .8)
            spin.setValue(70)
            self.assertAlmostEqual(getattr(item, attribute), .7)
            self.assertEqual(window.history._current_index, index)
            spin.editingFinished.emit()
            self.assertEqual(window.history._current_index, index + 1)
        window.undo(); self.drain()
        self.assertAlmostEqual(self.shape(window).outline_opacity, 1)
        self.assertAlmostEqual(self.shape(window).fill_opacity, .7)

    def test_text_color_alpha_preview_preserves_active_selection_and_spin_focus(self):
        window = self.editor()
        box = next(item for item in window.scene.items() if isinstance(item, DesignerBox))
        box.state.html_content = '<p>Primeiro segundo</p>'
        box.apply_state()
        self.select(window, box)
        window.canvas_edit.begin(box)
        box.text_item.setTextCursor(box.text_item.document().find('Primeiro'))
        window.save_snapshot()
        index = window.history._current_index
        spin = window.editor_texto_panel.text_alpha
        spin.setFocus()
        for value in (80, 60):
            spin.setValue(value)
            self.assertAlmostEqual(box.text_item.document().find('Primeiro').charFormat().foreground().color().alphaF(), value/100, delta=.003)
            self.assertEqual(box.text_item.document().find('segundo').charFormat().foreground().color().alpha(), 255)
            self.assertTrue(spin.hasFocus())
            self.assertEqual(window.history._current_index, index)
        spin.editingFinished.emit()
        self.assertEqual(window.history._current_index, index + 1)
        window.undo(); self.drain()
        restored = next(item for item in window.scene.items() if isinstance(item, DesignerBox))
        self.assertEqual(restored.text_item.document().find('Primeiro').charFormat().foreground().color().alpha(), 255)

    def test_table_cell_fill_and_border_alpha_preview_and_confirm_once(self):
        window = self.editor()
        item = next(item for item in window.scene.items() if isinstance(item, fixtures.canvas.TableItem))
        self.select(window, item)
        window.save_snapshot()
        for spin, style in ((window.table_panel.fill_opacity, 'cell'), (window.table_panel.edge_opacity, 'edge')):
            index = window.history._current_index
            for value in (80, 60):
                spin.setValue(value)
                if style == 'cell':
                    self.assertAlmostEqual(item.selected_cells()[0]['style']['fill_opacity'], value/100)
                else:
                    self.assertTrue(any(edge['style']['opacity'] == value/100 for edge in item.data['edges']))
                self.assertEqual(window.history._current_index, index)
            spin.editingFinished.emit()
            self.assertEqual(window.history._current_index, index + 1)

    def test_board_contours_and_connectors_preview_before_confirmation(self):
        document = board_fixtures.board_document(1, 1)
        document['organogram']['groups'][0]['border'] = {'cards': True, 'group': True, 'target': 'both'}
        window = self.editor(document)
        window.switch_model_page('organogram')
        item = window._board_items()[0]
        self.select(window, item)
        window.save_snapshot()
        index = window.history._current_index
        spin = window.organogram_panel.border_opacity
        spin.setValue(80)
        self.assertAlmostEqual(border_style(item.data)['opacity'], .8)
        spin.setValue(60)
        self.assertAlmostEqual(border_style(item.data)['opacity'], .6)
        self.assertEqual(window.history._current_index, index)
        spin.editingFinished.emit()
        self.assertEqual(window.history._current_index, index + 1)
        self.select(window)
        index = window.history._current_index
        spin = window.organogram_panel.transparency
        spin.setValue(10)
        spin.setValue(20)
        self.assertAlmostEqual(window._board_connector_style['opacity'], .8)
        self.assertEqual(window.history._current_index, index)
        spin.editingFinished.emit()
        self.assertEqual(window.history._current_index, index + 1)


if __name__ == '__main__':
    unittest.main()
