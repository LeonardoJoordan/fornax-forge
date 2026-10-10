"""Contrato comum das barras: oito ancoragens, menus, tema e composição."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest

import test_object_floating as objects
from core.resources import state_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import theme_manager, theme_color
from features.editor.canvas_items import DesignerBox
from features.editor.table_item import TableItem
from features.editor.floating_bar import FloatingBar


class SharedFloatingBarTest(unittest.TestCase):
    setUpClass = classmethod(objects.ObjectFloatingTest.setUpClass.__func__)
    tearDownClass = classmethod(objects.ObjectFloatingTest.tearDownClass.__func__)
    setUp = objects.ObjectFloatingTest.setUp
    tearDown = objects.ObjectFloatingTest.tearDown
    editor = objects.ObjectFloatingTest.editor
    drain = objects.ObjectFloatingTest.drain
    select = objects.ObjectFloatingTest.select
    shape = objects.ObjectFloatingTest.shape
    begin = objects.ObjectFloatingTest.begin
    move = objects.ObjectFloatingTest.move
    drop = objects.ObjectFloatingTest.drop
    assert_clean = objects.ObjectFloatingTest.assert_clean
    click_through_window = objects.ObjectFloatingTest.click_through_window
    assert_toolbar_geometry = objects.ObjectFloatingTest.assert_toolbar_geometry

    def contexts(self, w):
        return (self.shape(w), next(i for i in w.scene.items() if isinstance(i, DesignerBox)),
                next(i for i in w.scene.items() if isinstance(i, TableItem)))

    def bar_for(self, w, item):
        self.select(w, item)
        return w.table_controller.floating_bar if isinstance(item, TableItem) else w.object_floating_bar

    def test_eight_offsets_and_collapse_respect_each_context_clearance(self):
        w = self.editor()
        rectangle, available = QRect(650, 450, 200, 120), QRect(0, 0, 1600, 1100)
        for item in self.contexts(w):
            bar = self.bar_for(w, item)
            for collapsed in (False, True):
                with self.subTest(item=type(item).__name__, collapsed=collapsed):
                    slots = bar.dock_geometries(rectangle, available, collapsed=collapsed)
                    self.assertEqual(set(slots), set(bar.DOCK_SIDES))
                    for edge in ('top', 'bottom', 'left', 'right'):
                        near, far = slots[edge], slots[edge+'_far']
                        self.assertEqual(near.size(), far.size())
                        delta = far.topLeft()-near.topLeft()
                        thickness = near.height() if edge in ('top', 'bottom') else near.width()
                        step = thickness+30
                        self.assertEqual(delta.manhattanLength(), step)
                        distance = {'top': rectangle.top()-near.bottom()-1,
                                    'bottom': near.top()-rectangle.bottom()-1,
                                    'left': rectangle.left()-near.right()-1,
                                    'right': near.left()-rectangle.right()-1}[edge]
                        self.assertEqual(distance, 20)
                        self.assertFalse(near.intersects(far))
                        self.assertTrue(available.contains(far))
                        if edge in ('top', 'bottom'):
                            self.assertEqual(delta.x(), 0)
                            self.assertEqual(delta.y(), -step if edge == 'top' else step)
                        else:
                            self.assertEqual(delta.y(), 0)
                            self.assertEqual(delta.x(), -step if edge == 'left' else step)

    def test_drag_eight_positions_collapsed_and_expanded_preserves_document(self):
        w = self.editor(); w.resize(1800, 1300)
        w.view.resetTransform(); w.view.scale(.6, .6)
        for item in self.contexts(w):
            item.setPos(320, 220)
            bar = self.bar_for(w, item)
            before = deepcopy(w.get_current_scene_state())
            for collapsed in (False, True):
                if bar.collapsed != collapsed:
                    bar.toggle_collapsed(); self.drain()
                for side in bar.DOCK_SIDES:
                    with self.subTest(item=type(item).__name__, collapsed=collapsed, side=side):
                        self.begin(bar)
                        self.assertEqual(len(bar._drag_geometries), 8)
                        point = bar._drag_geometries[side].center()
                        self.assertEqual(bar.target_at(point), side)
                        self.move(bar, point); self.drop(bar, point)
                        self.assert_clean(bar)
                        self.assertEqual(bar.dock_side, side)
                        self.assertEqual(bar.collapsed, collapsed)
                        self.assert_toolbar_geometry(bar, bar.dock_edge(side))
                        self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
            self.assertEqual(before, w.get_current_scene_state())
            if bar.collapsed:
                bar.toggle_collapsed()

    def test_destinations_preserve_toolbar_thickness_and_remain_selectable(self):
        w = self.editor(); bar = self.bar_for(w, self.shape(w))
        available = QRect(0, 0, 800, 600)
        for rectangle in (QRect(300, 220, 80, 45), QRect(0, 0, 80, 45),
                          QRect(760, 540, 40, 60), QRect(2, 180, 798, 60)):
            targets = bar.dock_target_geometries(rectangle, available)
            slots = bar.dock_geometries(rectangle, available, collapsed=False)
            bar._drag_geometries = targets
            for key, target in targets.items():
                self.assertTrue(available.contains(target))
                if bar.dock_edge(key) in ('top', 'bottom'):
                    self.assertEqual(target.height(), slots[key].height())
                    self.assertEqual(target.width(), min(slots[key].width(), rectangle.width()))
                else:
                    self.assertEqual(target.width(), slots[key].width())
                    self.assertEqual(target.height(), min(slots[key].height(), rectangle.height()))
                self.assertEqual(bar.target_at(target.center()), key)
                for other_key, other in targets.items():
                    if key != other_key:
                        self.assertNotEqual(target, other, (key, other_key))

    def test_second_position_leaves_thirty_pixels_after_first_toolbar(self):
        w = self.editor()
        rectangle, available = QRect(650, 450, 200, 120), QRect(0, 0, 1600, 1100)
        for item in self.contexts(w):
            bar = self.bar_for(w, item)
            for collapsed in (False, True):
                slots = bar.dock_geometries(rectangle, available, collapsed=collapsed)
                for edge in ('top', 'bottom', 'left', 'right'):
                    for suffix, expected in (('', 20), ('_far', 96 if edge in ('top', 'bottom') else 94)):
                        slot = slots[edge+suffix]
                        distance = {'top': rectangle.top()-slot.bottom()-1,
                                    'bottom': slot.top()-rectangle.bottom()-1,
                                    'left': rectangle.left()-slot.right()-1,
                                    'right': slot.left()-rectangle.right()-1}[edge]
                        self.assertEqual(distance, expected)

    def test_palette_asset_follows_theme_and_disabled_state_on_all_color_buttons(self):
        w = self.editor()
        buttons = [w.object_floating_bar.buttons['fill'], w.object_floating_bar.buttons['text_color'],
                   w.table_controller.floating_bar.buttons['fill']]
        expected = themed_svg_icon(state_icon_path('palette'))
        previous = theme_manager().theme_id
        try:
            for theme in ('dark', 'light'):
                theme_manager().select(theme); self.drain()
                for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
                    reference = expected.pixmap(24, 24, mode).toImage()
                    colors = {reference.pixelColor(x, y).name() for x in range(reference.width())
                              for y in range(reference.height()) if reference.pixelColor(x, y).alpha() == 255}
                    self.assertEqual(colors, {theme_color('disabled' if mode == QIcon.Mode.Disabled else 'icon')})
                    for button in buttons:
                        self.assertEqual(button.icon().pixmap(24, 24, mode).toImage(), reference)
        finally:
            theme_manager().select(previous)

    def test_new_toolbar_only_registers_tools_and_uses_shared_layout_and_popups(self):
        w = self.editor()
        item = next(i for i in w.scene.items() if isinstance(i, TableItem))
        self.select(w, item)
        bar = FloatingBar(SimpleNamespace(window=w, selected=lambda: item))
        color = bar.color_button('color', 'Cor')
        choices = []
        bar.choice_menu('color', [('test', color.icon(), 'Exemplo'),
                                  ('other', color.icon(), 'Outro')], choices.append)
        bar.finish_setup()
        for side in bar.DOCK_SIDES:
            bar.dock_side = side; bar.reposition(); self.drain()
            self.assert_toolbar_geometry(bar, bar.dock_edge(side))
            bar.popup(color, bar.alignment_menus['color']); self.drain()
            first, second = bar.alignment_choices['color'].values()
            if bar.is_vertical:
                self.assertEqual(first.x(), second.x())
                self.assertLess(first.geometry().bottom(), second.y())
            else:
                self.assertEqual(first.y(), second.y())
                self.assertLess(first.geometry().right(), second.x())
            QTest.mouseClick(bar.alignment_choices['color']['test'], Qt.MouseButton.LeftButton)
            self.drain()
        self.assertEqual(choices, ['test']*8)
        bar.dismiss(); bar.deleteLater()


if __name__ == '__main__':
    unittest.main()
