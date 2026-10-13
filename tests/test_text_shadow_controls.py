"""Integração: controles reais, histórico, edição, duplicação e arquivo .fornax."""
import unittest
from copy import deepcopy
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QTextCursor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from features.editor.canvas_items import DesignerBox
from core.fornax_container import save_public_fornax, open_public_fornax
import test_object_floating as objects


class TextShadowControlsTest(unittest.TestCase):
    setUpClass = classmethod(objects.ObjectFloatingTest.setUpClass.__func__)
    tearDownClass = classmethod(objects.ObjectFloatingTest.tearDownClass.__func__)
    setUp = objects.ObjectFloatingTest.setUp
    tearDown = objects.ObjectFloatingTest.tearDown
    editor = objects.ObjectFloatingTest.editor
    drain = objects.ObjectFloatingTest.drain
    select = objects.ObjectFloatingTest.select

    def box(self, window):
        return next(i for i in window.scene.items() if isinstance(i, DesignerBox))

    def setup_text(self):
        w = self.editor()
        box = self.box(w)
        self.select(w, box)
        w._text_section.header.setChecked(True)
        w.save_snapshot()
        self.drain()
        return w, box, w.text_shadow_controls

    def test_default_dimensions_and_arrow_steps_in_millimeters(self):
        from features.editor.canvas_items import px_to_mm
        w, box, controls = self.setup_text()
        self.assertEqual(box.state.shadow, {})
        self.assertAlmostEqual(controls.distance.value(), .25)
        self.assertAlmostEqual(controls.blur.value(), .25)
        self.assertEqual(controls.spread.value(), 0)
        controls.enabled.click()
        for name in ('distance', 'blur'):
            spin = getattr(controls, name)
            spin.setFocus()
            QTest.keyClick(spin, Qt.Key.Key_Up)
            self.assertAlmostEqual(spin.value(), .30)
            self.assertAlmostEqual(px_to_mm(box.state.shadow[name]), .30)
            QTest.keyClick(spin, Qt.Key.Key_Down)
            self.assertAlmostEqual(spin.value(), .25)
            self.assertAlmostEqual(px_to_mm(box.state.shadow[name]), .25)
            QTest.keyClick(spin, Qt.Key.Key_Return)
        controls.spread.setFocus()
        QTest.keyClick(controls.spread, Qt.Key.Key_Up)
        self.assertAlmostEqual(controls.spread.value(), .05)
        self.assertAlmostEqual(px_to_mm(box.state.shadow['spread']), .05)
        QTest.keyClick(controls.spread, Qt.Key.Key_Return)

    def test_existing_shadow_dimensions_are_preserved_when_opening_controls(self):
        from core.text_effects import normalize_shadow
        w, box, controls = self.setup_text()
        shadow = normalize_shadow(dict(enabled=True, distance=8., blur=6.))
        box.set_shadow(shadow)
        controls.sync()
        self.assertEqual(controls.distance.value(), .68)
        self.assertEqual(controls.blur.value(), .51)
        self.assertEqual(box.state.shadow, shadow)

    def test_circle_selects_light_and_projects_shadow_in_opposite_direction(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        dial = controls.angle
        for offset, expected in ((QPointF(25, -25), 135), (QPointF(25, 0), 180),
                                 (QPointF(0, -25), 90), (QPointF(-25, 0), 0),
                                 (QPointF(0, 25), 270)):
            # QPointF evita o meio pixel de diferença do centro de QRect.
            position = QPointF(dial.width()/2, dial.height()/2) + offset
            QTest.mouseClick(dial, Qt.MouseButton.LeftButton, pos=position.toPoint())
            self.assertAlmostEqual(box.state.shadow['angle'], expected, delta=2)
            light = dial.lightPosition() - QPointF(dial.width()/2, dial.height()/2)
            self.assertGreater(QPointF.dotProduct(light, offset), 0)
            self.assertAlmostEqual(controls.light_angle.value(), dial.lightAngle(), delta=.05)

    def test_light_angle_can_be_typed_exactly_and_undo_restores_both_controls(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        index = w.history._current_index
        before = box.state.shadow['angle']
        spin = controls.light_angle
        spin.setFocus()
        spin.lineEdit().selectAll()
        QTest.keyClicks(spin, '4')
        entered = spin.lineEdit().text()
        controls.sync()
        self.assertEqual(spin.lineEdit().text(), entered)
        QTest.keyClicks(spin, '5')
        QTest.keyClick(spin, Qt.Key.Key_Return)
        self.drain()
        self.assertEqual(spin.value(), 45)
        self.assertEqual(controls.angle.lightAngle(), 45)
        self.assertEqual(box.state.shadow['angle'], 135)
        self.assertEqual(w.history._current_index, index+1)
        light = controls.angle.lightPosition() - QPointF(controls.angle.width()/2, controls.angle.height()/2)
        self.assertGreater(light.x(), 0)
        self.assertLess(light.y(), 0)
        w.undo(); self.drain()
        self.assertEqual(self.box(w).state.shadow['angle'], before)
        self.assertEqual(spin.value(), (180-before) % 360)
        w.redo(); self.drain()
        self.assertEqual(self.box(w).state.shadow['angle'], 135)
        self.assertEqual(spin.value(), 45)

    def test_numeric_light_preview_does_not_create_intermediate_history(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        index = w.history._current_index
        spin = controls.light_angle
        spin.setFocus()
        for value in (45., 46.5, 90., 359.9):
            spin.setValue(value)
            self.assertAlmostEqual(box.state.shadow['angle'], (180-value) % 360)
            self.assertAlmostEqual(controls.angle.lightAngle(), value)
            self.assertEqual(w.history._current_index, index)
        QTest.keyClick(spin, Qt.Key.Key_Return)
        self.assertEqual(w.history._current_index, index+1)

    def test_circle_drag_previews_with_one_undo_step_and_keyboard_support(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        dial = controls.angle
        center = QPointF(dial.width()/2, dial.height()/2)
        before = box.state.shadow['angle']
        index = w.history._current_index
        QTest.mousePress(dial, Qt.MouseButton.LeftButton, pos=(center+QPointF(25, 0)).toPoint())
        self.assertEqual(w.history._current_index, index)
        for offset in (QPointF(0, -25), QPointF(25, -25)):
            point = center+offset
            event = QMouseEvent(QEvent.Type.MouseMove, point, QPointF(dial.mapToGlobal(point.toPoint())),
                                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(dial, event)
            self.assertEqual(w.history._current_index, index)
        self.assertAlmostEqual(box.state.shadow['angle'], 135, delta=2)
        QTest.mouseRelease(dial, Qt.MouseButton.LeftButton, pos=(center+QPointF(25, -25)).toPoint())
        final_angle = box.state.shadow['angle']
        self.assertEqual(w.history._current_index, index+1)
        w.undo(); self.drain()
        self.assertAlmostEqual(self.box(w).state.shadow['angle'], before)
        w.redo(); self.drain()
        self.assertEqual(self.box(w).state.shadow['angle'], final_angle)
        QTest.keyClick(dial, Qt.Key.Key_Right)
        self.assertEqual(self.box(w).state.shadow['angle'], final_angle+1)
        QTest.keyClick(dial, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.box(w).state.shadow['angle'], final_angle-14)

    def test_circle_escape_cancels_drag_without_history_or_stuck_selection(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        dial = controls.angle
        before = box.state.shadow['angle']
        index = w.history._current_index
        center = QPointF(dial.width()/2, dial.height()/2)
        point = (center+QPointF(25, 0)).toPoint()
        QTest.mousePress(dial, Qt.MouseButton.LeftButton, pos=point)
        self.assertNotEqual(box.state.shadow['angle'], before)
        QTest.keyClick(dial, Qt.Key.Key_Escape)
        QTest.mouseRelease(dial, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(box.state.shadow['angle'], before)
        self.assertEqual(w.history._current_index, index)
        self.assertFalse(dial._dragging)
        QTest.mouseClick(dial, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(box.state.shadow['angle'], 180)

    def test_live_preview_one_history_step_per_spin_and_undo_redo(self):
        w, box, controls = self.setup_text()
        self.assertTrue(controls.isVisible())
        QTest.mouseClick(controls.enabled, Qt.MouseButton.LeftButton)
        self.drain()
        self.assertTrue(box.state.shadow['enabled'])
        index = w.history._current_index
        controls.opacity.setFocus()
        for value in (49, 48, 47):
            controls.opacity.setValue(value)
            self.assertAlmostEqual(box.state.shadow['opacity'], value/100)
            self.assertEqual(w.history._current_index, index)
        QTest.keyClick(controls.opacity, Qt.Key.Key_Return)
        self.drain()
        self.assertEqual(w.history._current_index, index+1)
        w.undo(); self.drain()
        self.assertAlmostEqual(self.box(w).state.shadow['opacity'], .5)
        w.redo(); self.drain()
        self.assertAlmostEqual(self.box(w).state.shadow['opacity'], .47)

    def test_effect_keeps_editable_text_cursor_and_placeholder(self):
        w, box, controls = self.setup_text()
        w.canvas_edit.begin(box)
        cursor = box.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText('Olá {nome}')
        box.text_item.setTextCursor(cursor)
        before = box.text_item.toHtml(), cursor.position(), box.text_item.y()
        controls.enabled.click()
        self.assertEqual((box.text_item.toHtml(), box.text_item.textCursor().position(),
                          box.text_item.y()), before)
        self.assertIs(w.canvas_edit.box, box)

    def test_duplicate_and_save_reopen_preserve_shadow_without_sharing_state(self):
        w, box, controls = self.setup_text()
        controls.enabled.click()
        controls.spread.setValue(.35)
        QTest.keyClick(controls.spread, Qt.Key.Key_Return)
        expected = deepcopy(box.state.shadow)
        w.duplicate_selected()
        copies = [item for item in w.scene.items() if isinstance(item, DesignerBox)]
        self.assertEqual(len(copies), 2)
        self.assertEqual(copies[0].state.shadow, copies[1].state.shadow)
        self.assertIsNot(copies[0].state.shadow, copies[1].state.shadow)
        document = w._document_with_active_page()
        path = self.root/'shadow.fornax'
        # Este cenário possui uma assinatura pública fictícia criada pelo teste.
        document.setdefault('protection_preferences', {})['public_signatures_acknowledged'] = True
        save_public_fornax(document, path)
        reopened = open_public_fornax(path).document()
        self.assertTrue(all(b['shadow'] == expected for b in reopened['pages'][0]['boxes']))
        w._load_document_into_scene(reopened)
        self.assertTrue(all(i.state.shadow == expected for i in w.scene.items() if isinstance(i, DesignerBox)))

    def test_controls_hidden_for_shapes_and_table_cells(self):
        from features.editor.canvas_items import RectangleItem
        from features.editor.table_item import TableItem
        w, box, controls = self.setup_text()
        for cls in (RectangleItem, TableItem):
            item = next(i for i in w.scene.items() if isinstance(i, cls))
            self.select(w, item)
            self.assertFalse(controls.isVisible())
        self.select(w, box)
        self.assertTrue(controls.isVisible())


if __name__ == '__main__':
    unittest.main()
