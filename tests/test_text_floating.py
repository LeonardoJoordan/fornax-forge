"""Atalhos de texto: gestos reais, escopo, foco, histórico e geometria."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

import test_object_floating as objects
from features.editor.canvas_items import DesignerBox


class TextFloatingTest(unittest.TestCase):
    setUpClass = classmethod(objects.ObjectFloatingTest.setUpClass.__func__)
    tearDownClass = classmethod(objects.ObjectFloatingTest.tearDownClass.__func__)
    setUp = objects.ObjectFloatingTest.setUp
    tearDown = objects.ObjectFloatingTest.tearDown
    editor = objects.ObjectFloatingTest.editor
    drain = objects.ObjectFloatingTest.drain
    select = objects.ObjectFloatingTest.select
    shape = objects.ObjectFloatingTest.shape
    click_through_window = objects.ObjectFloatingTest.click_through_window
    assert_toolbar_geometry = objects.ObjectFloatingTest.assert_toolbar_geometry

    def box(self, w):
        return next(item for item in w.scene.items() if isinstance(item, DesignerBox))

    def setup_text(self):
        w = self.editor()
        box = self.box(w)
        box.state.html_content = '<p>Primeiro segundo</p>'
        box.apply_state()
        self.select(w, box)
        w.save_snapshot()
        return w, box, w.object_floating_bar

    def open_tool(self, bar, key):
        self.click_through_window(bar.buttons[key])
        menu = bar.alignment_menus[key]
        self.assertTrue(menu.isVisible(), key)
        return menu

    def set_size(self, bar, size):
        self.open_tool(bar, 'text_size')
        spin = bar.text_tools.size
        QTest.keyClick(spin, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(spin, str(size))
        QTest.keyClick(spin, Qt.Key.Key_Return)
        self.drain()

    def test_whole_box_size_family_and_alignment_are_undoable_and_sidebar_stays(self):
        w, box, bar = self.setup_text()
        original = box.text_item.toHtml()
        index = w.history._current_index
        self.set_size(bar, 24)
        self.assertEqual(box.text_item.document().find('Primeiro').charFormat().fontPointSize(), 24)
        self.assertEqual(box.text_item.document().find('segundo').charFormat().fontPointSize(), 24)
        self.assertEqual(w.editor_texto_panel.spin_size.value(), 24)
        self.assertEqual(w.history._current_index, index+1)
        w.undo(); self.drain()
        self.assertEqual(self.box(w).text_item.toHtml(), original)
        w.redo(); self.drain()
        self.assertEqual(self.box(w).text_item.document().find('segundo').charFormat().fontPointSize(), 24)
        self.open_tool(bar, 'text_font')
        font = bar.text_tools.font
        QTest.keyClick(font.lineEdit(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(font.lineEdit(), 'DejaVu Serif')
        QTest.keyClick(font.lineEdit(), Qt.Key.Key_Return)
        self.drain()
        box = self.box(w)
        self.assertIn('DejaVu Serif', box.text_item.document().find('segundo').charFormat().fontFamilies())
        self.assertEqual(w.editor_texto_panel.cbo_font.currentFont().family(), 'DejaVu Serif')
        for key, value, attr in (('text_align', 'justify', 'align'), ('text_valign', 'bottom', 'vertical_align')):
            old = getattr(box.state, attr)
            self.open_tool(bar, key)
            self.click_through_window(bar.text_tools.choices[key][value])
            self.assertEqual(getattr(box.state, attr), value)
            w.undo(); self.drain()
            self.assertEqual(getattr(self.box(w).state, attr), old)
            w.redo(); self.drain()
            box = self.box(w)
            self.assertEqual(getattr(box.state, attr), value)
        self.assertTrue(w.editor_texto_panel.cbo_font.isVisible())
        self.assertTrue(w.editor_texto_panel.spin_size.isVisible())

    def test_selected_range_keeps_scope_cursor_and_typing_after_popup(self):
        w, box, bar = self.setup_text()
        w.canvas_edit.begin(box); self.drain()
        cursor = box.text_item.document().find('Primeiro')
        box.text_item.setTextCursor(cursor)
        selection = (cursor.position(), cursor.anchor())
        self.set_size(bar, 29)
        self.assertIs(w.canvas_edit.box, box)
        self.assertEqual(box.text_item.document().find('Primeiro').charFormat().fontPointSize(), 29)
        self.assertNotEqual(box.text_item.document().find('segundo').charFormat().fontPointSize(), 29)
        self.assertEqual((box.text_item.textCursor().position(), box.text_item.textCursor().anchor()), selection)
        self.assertIs(w.scene.focusItem(), box.text_item)
        for key, value in (('text_align', 'right'), ('text_valign', 'center')):
            self.open_tool(bar, key)
            self.click_through_window(bar.text_tools.choices[key][value])
            self.assertEqual(box.text_item.toPlainText(), 'Primeiro segundo')
            self.assertEqual((box.text_item.textCursor().position(), box.text_item.textCursor().anchor()), selection)
        with patch('features.editor.text_floating.QColorDialog.getColor', return_value=QColor('#123456')):
            self.click_through_window(bar.buttons['text_color'])
        self.assertEqual(box.text_item.document().find('Primeiro').charFormat().foreground().color().name(), '#123456')
        self.assertNotEqual(box.text_item.document().find('segundo').charFormat().foreground().color().name(), '#123456')
        self.assertIs(w.scene.focusItem(), box.text_item)
        QTest.keyClicks(w.view.viewport(), 'Novo')
        self.assertEqual(box.text_item.toPlainText(), 'Novo segundo')

    def test_opacity_is_object_wide_and_color_keeps_existing_text_alpha(self):
        w, box, bar = self.setup_text()
        w.update_font_color('#80112233')
        with patch('features.editor.text_floating.QColorDialog.getColor', return_value=QColor('#abcdef')):
            self.click_through_window(bar.buttons['text_color'])
        color = box.text_item.document().find('Primeiro').charFormat().foreground().color()
        self.assertEqual(color.name(), '#abcdef')
        self.assertEqual(color.alpha(), 128)
        self.open_tool(bar, 'opacity')
        bar.opacity_spin.setValue(50)
        QTest.keyClick(bar.opacity_spin, Qt.Key.Key_Return)
        self.drain()
        self.assertAlmostEqual(box.opacity(), .5)
        self.assertEqual(box.text_item.document().find('Primeiro').charFormat().foreground().color().alpha(), 128)
        self.assertEqual(w.caixa_texto_panel.spin_opacity.value(), 50)
        w.undo(); self.drain(); self.assertAlmostEqual(self.box(w).opacity(), 1)
        w.redo(); self.drain(); self.assertAlmostEqual(self.box(w).opacity(), .5)

    def test_font_dropdown_formats_selected_text_and_restores_focus(self):
        w, box, bar = self.setup_text()
        w.canvas_edit.begin(box)
        box.text_item.setTextCursor(box.text_item.document().find('Primeiro'))
        self.open_tool(bar, 'text_font')
        combo = bar.text_tools.font
        self.click_through_window(combo, QPoint(combo.width()-10, combo.height()//2))
        self.assertTrue(combo.view().isVisible())
        index = combo.model().index(combo.findText('DejaVu Serif'), 0)
        self.assertTrue(index.isValid())
        # Percorrer a lista real também cobre o uso sem mouse.
        QTest.keyClick(combo.view(), Qt.Key.Key_Home)
        for _ in range(index.row()):
            QTest.keyClick(combo.view(), Qt.Key.Key_Down)
        QTest.keyClick(combo.view(), Qt.Key.Key_Return)
        self.drain()
        self.assertIn('DejaVu Serif', box.text_item.document().find('Primeiro').charFormat().fontFamilies())
        self.assertNotIn('DejaVu Serif', box.text_item.document().find('segundo').charFormat().fontFamilies() or ())
        self.assertFalse(bar.text_tools.menus['text_font'].isVisible())
        self.assertIs(w.scene.focusItem(), box.text_item)

    def test_sidebar_and_cursor_changes_refresh_the_floating_values(self):
        w, box, bar = self.setup_text()
        w.editor_texto_panel.spin_size.setValue(31)
        self.drain()
        self.assertEqual(bar.buttons['text_size'].text(), '31')
        w.editor_texto_panel.cbo_align.setCurrentIndex(2)
        self.assertTrue(bar.text_tools.choices['text_align']['right'].isChecked())
        w.canvas_edit.begin(box)
        cursor = box.text_item.document().find('Primeiro')
        box.text_item.setTextCursor(cursor)
        w.update_font_size(20)
        box.text_item.setTextCursor(box.text_item.document().find('segundo'))
        self.drain()
        self.assertEqual(bar.buttons['text_size'].text(), '31')
        box.text_item.setTextCursor(box.text_item.document().find('Primeiro'))
        self.drain()
        self.assertEqual(bar.buttons['text_size'].text(), '20')

    def test_cancel_and_stale_menu_or_dialog_do_not_edit_another_item(self):
        w, box, bar = self.setup_text()
        before = box.text_item.toHtml()
        self.open_tool(bar, 'text_size')
        QTest.keyClicks(bar.text_tools.size, '88')
        QTest.keyClick(bar.text_tools.size, Qt.Key.Key_Escape)
        self.drain()
        self.assertEqual(box.text_item.toHtml(), before)
        self.open_tool(bar, 'text_size')
        self.select(w, self.shape(w))
        bar.text_tools.apply('size', 60)
        self.assertEqual(box.text_item.toHtml(), before)
        self.select(w, box)
        def switch_selection(*_):
            self.select(w, self.shape(w))
            return QColor('#123456')
        with patch('features.editor.text_floating.QColorDialog.getColor', side_effect=switch_selection):
            bar.text_tools.choose_color()
        self.assertEqual(box.text_item.toHtml(), before)
        self.assertEqual(self.shape(w).fill_color, '#ffffff')

    def test_docks_and_collapsed_anchor_and_alignment_popup_orientation(self):
        w, box, bar = self.setup_text()
        before = deepcopy(w.get_current_scene_state())
        for side in ('top', 'right', 'bottom', 'left'):
            with self.subTest(side=side):
                bar.dock_side = side; bar.reposition(); self.drain()
                self.assert_toolbar_geometry(bar, side)
                grip = bar.grip.mapTo(w.view.viewport(), QPoint())
                self.open_tool(bar, 'text_align')
                choices = list(bar.text_tools.choices['text_align'].values())
                for a,b in zip(choices, choices[1:]):
                    if side in ('left', 'right'):
                        self.assertEqual(a.x(), b.x())
                        self.assertLess(a.geometry().bottom(), b.y())
                    else:
                        self.assertEqual(a.y(), b.y())
                        self.assertLess(a.geometry().right(), b.x())
                bar.text_tools.menus['text_align'].close()
                self.click_through_window(bar.collapse_button)
                self.assert_toolbar_geometry(bar, side)
                self.assertEqual(grip, bar.grip.mapTo(w.view.viewport(), QPoint()))
                self.click_through_window(bar.collapse_button)
                self.assert_toolbar_geometry(bar, side)
        self.assertEqual(before, w.get_current_scene_state())


if __name__ == '__main__':
    unittest.main()
