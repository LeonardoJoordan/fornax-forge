"""Encaixe da barra flutuante: eventos de ponteiro, foco e estado transitório."""
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
from PySide6.QtGui import QMouseEvent, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QWidget

import test_table_canvas as canvas
from core.themes import theme_manager


class TableFloatingDragTest(unittest.TestCase):
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

    def begin(self, bar):
        QTest.mousePress(bar.grip, Qt.MouseButton.LeftButton, pos=bar.grip.rect().center())
        self.assertTrue(bar._dragging)

    def move(self, bar, point, buttons=Qt.MouseButton.LeftButton):
        global_position = bar.parentWidget().mapToGlobal(point)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(bar.grip.mapFromGlobal(global_position)),
                            QPointF(global_position), Qt.MouseButton.NoButton, buttons,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(bar.grip, event)
        self.drain()

    def drop(self, bar, point):
        global_position = bar.parentWidget().mapToGlobal(point)
        QTest.mouseRelease(bar.grip, Qt.MouseButton.LeftButton,
                          pos=bar.grip.mapFromGlobal(global_position))
        self.drain()

    def assert_clean(self, bar):
        self.assertFalse(bar._dragging)
        self.assertTrue(all(target.isHidden() for target in bar._dock_targets.values()))
        self.assertEqual(bar.grip.cursor().shape(), Qt.CursorShape.OpenHandCursor)

    def test_grip_shows_other_seven_targets_without_editing_document(self):
        w, item = self.editor()
        # Deixar espaço acima para ambas as ancoragens, incluindo os seletores.
        item.setPos(item.pos()+QPointF(0, 160))
        item.select_cell(1, 1); self.drain()
        bar = w.table_controller.floating_bar
        self.assertEqual(bar.dock_side, 'top')
        source, layout, roots, selection = item.to_data(), item.layout, tuple(w.scene.items()), item.selected_range
        with patch.object(w, 'save_snapshot') as save:
            self.begin(bar)
            self.assertEqual({side for side, target in bar._dock_targets.items() if target.isVisible()},
                             set(bar.DOCK_SIDES) - {'top'})
            self.assertTrue(all(target.graphicsEffect().opacity() == .5
                                for target in bar._dock_targets.values()))
            self.assertEqual(bar.grip.cursor().shape(), Qt.CursorShape.ClosedHandCursor)
            self.drop(bar, bar._drag_geometries['top'].center())
            save.assert_not_called()
        self.assert_clean(bar)
        self.assertEqual(item.to_data(), source)
        self.assertEqual(tuple(w.scene.items()), roots)
        self.assertIs(item.layout, layout)
        self.assertEqual(item.selected_range, selection)

    def test_drag_and_drop_all_four_sides_change_orientation_and_keep_selection(self):
        w, item = self.editor(); item.select_cell(1, 0); item.select_cell(2, 1, extend=True); self.drain()
        bar = w.table_controller.floating_bar
        source, selection = item.to_data(), item.selected_range
        with patch.object(w, 'save_snapshot') as save:
            for side in ('left', 'right', 'bottom', 'top'):
                with self.subTest(side=side):
                    self.begin(bar)
                    point = bar._drag_geometries[side].center()
                    self.move(bar, point)
                    self.assertTrue(bar._dock_targets[side].property('active'))
                    self.drop(bar, point)
                    self.assert_clean(bar)
                    self.assertEqual(bar.dock_side, side)
                    vertical = side in ('left', 'right')
                    self.assertEqual(bar._layout.direction(), QBoxLayout.Direction.TopToBottom if vertical
                                     else QBoxLayout.Direction.LeftToRight)
                    self.assertEqual(bar.buttons['rows'].text(), '' if vertical else 'Linhas')
                    self.assertGreater(bar.height(), bar.width()) if vertical else self.assertGreater(bar.width(), bar.height())
                    self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
                    self.assertEqual(item.selected_range, selection)
            save.assert_not_called()
        self.assertEqual(item.to_data(), source)

    def test_chosen_side_survives_zoom_movement_and_selection_changes(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        self.begin(bar); point = bar._drag_geometries['right'].center(); self.move(bar, point); self.drop(bar, point)
        size = bar.size()
        item.setPos(item.pos()+QPointF(30, 20))
        w.view.scale(.6, .6); self.drain()
        self.assertEqual(bar.dock_side, 'right')
        self.assertEqual(bar.size(), size)
        item.setSelected(False); self.drain(); self.assertFalse(bar.isVisible())
        item.setSelected(True); self.drain()
        self.assertTrue(bar.isVisible()); self.assertEqual(bar.dock_side, 'right')

    def test_escape_lost_button_and_deactivation_cancel_drag_and_hide_targets(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        for cancellation in ('escape', 'button', 'deactivate', 'ungrab'):
            with self.subTest(cancellation=cancellation):
                self.begin(bar); point = bar._drag_geometries['bottom'].center(); self.move(bar, point)
                if cancellation == 'escape':
                    QTest.keyClick(w.view, Qt.Key.Key_Escape)
                elif cancellation == 'button':
                    self.move(bar, point, Qt.MouseButton.NoButton)
                elif cancellation == 'deactivate':
                    QApplication.sendEvent(w, QEvent(QEvent.Type.WindowDeactivate))
                else:
                    QApplication.sendEvent(bar.grip, QEvent(QEvent.Type.UngrabMouse))
                self.drain(); self.assert_clean(bar)
                self.assertEqual(bar.dock_side, 'top')
                # Limpar também o estado de botão da infraestrutura QTest.
                QTest.mouseRelease(bar.grip, Qt.MouseButton.LeftButton)

    def test_drop_outside_targets_returns_to_previous_slot(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar; original = bar.geometry()
        self.begin(bar)
        point = w.view.mapFromScene(item.mapToScene(item.rect().center()))
        self.assertIsNone(bar.target_at(point))
        self.move(bar, point); self.drop(bar, point)
        self.assert_clean(bar); self.assertEqual(bar.geometry(), original)

    def test_drag_during_text_edit_preserves_cursor_focus_and_typing(self):
        w, item = self.editor(); self.type(w, item, text='Texto preservado'); self.drain()
        bar = w.table_controller.floating_bar
        cursor = w.table_edit.text.textCursor(); position = cursor.position()
        self.begin(bar); point = bar._drag_geometries['left'].center(); self.move(bar, point); self.drop(bar, point)
        self.assertIs(w.table_edit.item, item)
        self.assertIs(w.scene.focusItem(), w.table_edit.text)
        self.assertEqual(w.table_edit.text.textCursor().position(), position)
        QTest.keyClicks(w.view.viewport(), ' final')
        self.assertIn('Texto preservado final', item.to_data()['cells'][3]['html'])
        # Os menus continuam funcionais na coluna vertical.
        QTest.mouseClick(bar.buttons['align'], Qt.MouseButton.LeftButton); self.drain()
        menu = next(m for m in bar.menus if m.isVisible())
        self.assertTrue(menu.isVisible())
        QTest.mouseClick(bar.alignment_choices['align']['right'], Qt.MouseButton.LeftButton)
        self.assertEqual(item.data['cells'][3]['style']['align'], 'right')

    def test_changing_page_during_drag_removes_destinations_and_releases_session(self):
        from core.model_document import add_blank_back_page
        w, item = self.editor(add_blank_back_page(canvas.sample())); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar; self.begin(bar)
        w.switch_model_page('back'); self.drain()
        self.assert_clean(bar); self.assertFalse(bar.isVisible())

    def test_collapse_keeps_end_anchor_in_all_four_positions_without_document_changes(self):
        w, item = self.editor(); item.select_cell(1, 0); self.drain()
        bar = w.table_controller.floating_bar
        source, selection, roots = item.to_data(), item.selected_range, tuple(w.scene.items())
        self.assertIsNone(bar.graphicsEffect())
        self.assertTrue(all(button.graphicsEffect() is None for button in bar.buttons.values()))
        with patch.object(w, 'save_snapshot') as save:
            for side in ('top', 'bottom', 'left', 'right'):
                with self.subTest(side=side):
                    bar.dock_side = side; bar.reposition(); self.drain()
                    expanded = bar.geometry()
                    QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()
                    self.assertTrue(bar.collapsed)
                    self.assertEqual({key for key, button in bar.buttons.items() if button.isVisible()},
                                     {'collapse'})
                    self.assertTrue(bar.grip.isVisible())
                    self.assertTrue(all(separator.isHidden() for separator in bar._separators))
                    self.assertIn('Expandir', bar.collapse_button.toolTip())
                    if side in ('top', 'bottom'):
                        self.assertEqual(bar.geometry().right(), expanded.right())
                        self.assertEqual(bar.geometry().top(), expanded.top())
                        self.assertLess(bar.width(), expanded.width()/2)
                    else:
                        self.assertEqual(bar.geometry().bottom(), expanded.bottom())
                        self.assertEqual(bar.geometry().left(), expanded.left())
                        self.assertLess(bar.height(), expanded.height()/2)
                    QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()
                    self.assertFalse(bar.collapsed)
                    self.assertEqual(bar.geometry(), expanded)
                    self.assertTrue(all(button.isVisible() for button in bar.buttons.values()))
            save.assert_not_called()
        self.assertEqual(item.to_data(), source)
        self.assertEqual(item.selected_range, selection)
        self.assertEqual(tuple(w.scene.items()), roots)

    def test_collapsed_bar_can_dock_and_follow_zoom_and_selection(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()
        for side in ('left', 'bottom', 'right', 'top'):
            self.begin(bar); point = bar._drag_geometries[side].center()
            self.move(bar, point); self.drop(bar, point); self.assert_clean(bar)
            self.assertEqual(bar.dock_side, side)
            self.assertTrue(bar.collapsed)
            self.assertTrue(w.view.viewport().rect().contains(bar.geometry()))
        item.setSelected(False); self.drain(); self.assertFalse(bar.isVisible())
        item.setSelected(True); w.view.scale(.6, .6); self.drain()
        self.assertTrue(bar.isVisible()); self.assertTrue(bar.collapsed)
        self.assertTrue(bar.grip.isVisible()); self.assertTrue(bar.collapse_button.isVisible())

    def test_collapse_while_editing_preserves_cursor_and_typing(self):
        w, item = self.editor(); self.type(w, item, text='Texto preservado'); self.drain()
        bar = w.table_controller.floating_bar
        position = w.table_edit.text.textCursor().position()
        for _ in range(2):
            QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()
            self.assertIs(w.scene.focusItem(), w.table_edit.text)
            self.assertEqual(w.table_edit.text.textCursor().position(), position)
        QTest.keyClicks(w.view.viewport(), ' final')
        self.assertIn('Texto preservado final', item.to_data()['cells'][3]['html'])

    def test_collapsed_drag_uses_same_destinations_as_expanded_after_view_transforms(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        for scale, angle, position in ((1, 0, QPointF(80, 80)),
                                       (.6, 17, QPointF(130, 110)),
                                       (1.3, -12, QPointF(20, 60))):
            with self.subTest(scale=scale, angle=angle):
                # Recuperar o estado também se uma verificação anterior falhar.
                bar.end_dock_drag(restore_focus=False)
                if bar.collapsed:
                    bar.toggle_collapsed()
                w.view.resetTransform(); w.view.scale(scale, scale)
                item.setRotation(angle); item.setPos(position)
                w.view.centerOn(item.sceneBoundingRect().center()); self.drain()
                source, selection = item.to_data(), item.selected_range
                self.begin(bar)
                expanded_destinations = dict(bar._drag_geometries)
                self.drop(bar, expanded_destinations[bar.dock_side].center())
                QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()
                minimized_geometry = bar.geometry()
                with patch.object(w, 'save_snapshot') as save:
                    self.begin(bar)
                    self.assertEqual(bar._drag_geometries, expanded_destinations)
                    for side, target in bar._dock_targets.items():
                        if target.isVisible():
                            self.assertEqual(target.geometry(), expanded_destinations[side])
                    self.assertEqual(bar.geometry(), minimized_geometry)
                    self.move(bar, expanded_destinations['left'].center())
                    self.drop(bar, expanded_destinations['left'].center())
                    self.assertEqual(bar.dock_side, 'left')
                    self.assertTrue(bar.collapsed)
                    available = bar.parentWidget().rect().adjusted(8, 8, -8, -8)
                    rectangle = w.view.mapFromScene(item.mapToScene(item.rect())).boundingRect()
                    full_slot = bar.dock_geometries(rectangle, available, collapsed=False)['left']
                    self.assertEqual(bar.geometry().bottom(), full_slot.bottom())
                    self.assert_clean(bar)
                    save.assert_not_called()
                self.assertEqual(item.to_data(), source)
                self.assertEqual(item.selected_range, selection)
                QTest.mouseClick(bar.collapse_button, Qt.MouseButton.LeftButton); self.drain()

    def test_destinations_fit_table_dimensions_without_resizing_dropped_bar(self):
        w, item = self.editor(); w.resize(1600, 1100)
        item.select_cell(1, 1); self.drain()
        bar = w.table_controller.floating_bar
        source, selection = item.to_data(), item.selected_range
        with patch.object(w, 'save_snapshot') as save:
            for scale in (.3, 1):
                w.view.resetTransform(); w.view.scale(scale, scale)
                w.view.centerOn(item.sceneBoundingRect().center()); self.drain()
                rectangle = w.view.mapFromScene(item.mapToScene(item.rect())).boundingRect()
                available = bar.parentWidget().rect().adjusted(8, 8, -8, -8)
                slots = bar.dock_geometries(rectangle, available, collapsed=False)
                self.assertEqual(set(slots), set(bar.DOCK_SIDES))
                for collapsed in (False, True):
                    if bar.collapsed != collapsed:
                        bar.toggle_collapsed(); self.drain()
                    for side in ('left', 'bottom', 'right', 'top'):
                        with self.subTest(scale=scale, collapsed=collapsed, side=side):
                            self.begin(bar)
                            targets = bar._drag_geometries
                            for target_side, target in targets.items():
                                full = slots[target_side]
                                if bar.dock_edge(target_side) in ('top', 'bottom'):
                                    self.assertEqual(target.width(), min(full.width(), rectangle.width()))
                                    self.assertEqual(target.height(), full.height())
                                    self.assertLessEqual(abs(target.center().x()-rectangle.center().x()), 1)
                                else:
                                    self.assertEqual(target.height(), min(full.height(), rectangle.height()))
                                    self.assertEqual(target.width(), full.width())
                                    self.assertLessEqual(abs(target.center().y()-rectangle.center().y()), 1)
                                self.assertTrue(available.contains(target))
                                self.assertFalse(target.intersects(rectangle))
                                for other_side, other in targets.items():
                                    if bar.dock_edge(target_side) != bar.dock_edge(other_side):
                                        self.assertFalse(target.intersects(other))
                            point = targets[side].center()
                            self.move(bar, point)
                            self.assertTrue(bar._dock_targets[side].property('active'))
                            self.assertEqual(bar._dock_targets[side].geometry(), targets[side])
                            self.drop(bar, point); self.assert_clean(bar)
                            self.assertEqual(bar.dock_side, side)
                            self.assertEqual(bar.collapsed, collapsed)
                            if not collapsed:
                                self.assertEqual(bar.geometry(), slots[side])
                if bar.collapsed:
                    bar.toggle_collapsed(); self.drain()
            save.assert_not_called()
        self.assertEqual(item.to_data(), source)
        self.assertEqual(item.selected_range, selection)

    def test_surface_is_translucent_and_buttons_opaque_in_both_themes(self):
        w, item = self.editor(); item.setSelected(True); self.drain()
        bar = w.table_controller.floating_bar
        previous = theme_manager().theme_id
        def capture(widget):
            scale = widget.devicePixelRatioF()
            pixels = QImage(round(widget.width()*scale), round(widget.height()*scale),
                            QImage.Format.Format_ARGB32_Premultiplied)
            pixels.setDevicePixelRatio(scale)
            pixels.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixels)
            # Pintar a superfície uma vez, sem o pré-preenchimento da janela.
            widget.render(painter, QPoint(), renderFlags=QWidget.RenderFlag.DrawChildren)
            painter.end()
            return pixels, scale
        try:
            for theme in ('dark', 'light'):
                with self.subTest(theme=theme):
                    theme_manager().select(theme); self.drain()
                    pixels, scale = capture(bar)
                    self.assertEqual(pixels.pixelColor(round(3*scale), pixels.height()//2).alpha(), 191)
                    point = bar.buttons['rows'].mapTo(bar, QPoint(6, 6))
                    self.assertEqual(pixels.pixelColor(round(point.x()*scale), round(point.y()*scale)).alpha(), 255)
                    self.assertIsNone(bar.graphicsEffect())
                    self.assertIsNone(bar.grip.graphicsEffect())
                    for side in ('top', 'left', 'right', 'bottom'):
                        bar.dock_side = side; bar.reposition(); self.drain()
                        for axis, menu in bar.alignment_menus.items():
                            bar.popup(bar.buttons[axis], menu); self.drain()
                            pixels, scale = capture(menu)
                            self.assertEqual(pixels.pixelColor(round(3*scale), pixels.height()//2).alpha(), 191)
                            self.assertEqual(pixels.pixelColor(0, 0).alpha(), 0)
                            choice = next(iter(bar.alignment_choices[axis].values()))
                            point = choice.mapTo(menu, QPoint(6, 6))
                            self.assertEqual(pixels.pixelColor(round(point.x()*scale), round(point.y()*scale)).alpha(), 255)
                            if side in ('left', 'right'):
                                self.assertEqual(menu.width(), bar.width())
                            else:
                                self.assertEqual(menu.height(), bar.height())
                            menu.close()
        finally:
            theme_manager().select(previous)


if __name__ == '__main__':
    unittest.main()
