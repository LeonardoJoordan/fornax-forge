"""Seletores temporários da tabela não podem ficar ativos após a destruição."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QSpinBox, QWidget
from shiboken6 import isValid

from core.wheel_focus import WheelFocusGuard


class WheelFocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def click():
        return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    def test_deleted_combo_is_disarmed_before_the_next_click(self):
        guard = WheelFocusGuard()
        combo = QComboBox()
        combo.addItems(['Setor', 'Comando'])
        guard.eventFilter(combo, self.click())
        combo.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(combo))
        other = QWidget()
        self.addCleanup(other.deleteLater)
        self.assertFalse(guard._belongs_to_combo_popup(other))
        self.assertFalse(guard.eventFilter(other, self.click()))
        self.assertIsNone(guard._armed)

    def test_deleted_watched_widget_is_ignored(self):
        guard = WheelFocusGuard()
        widget = QWidget()
        widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(guard.eventFilter(widget, self.click()))

    def test_popup_is_recognized_while_combo_is_alive(self):
        guard = WheelFocusGuard()
        combo = QComboBox()
        self.addCleanup(combo.deleteLater)
        combo.addItems(['Setor', 'Comando'])
        guard.eventFilter(combo, self.click())
        self.assertTrue(guard._belongs_to_combo_popup(combo.view().viewport()))
        guard.eventFilter(combo.view().viewport(), self.click())
        self.assertIs(guard._armed, combo)

    def test_unarmed_wheel_scrolls_panel_and_armed_control_keeps_wheel(self):
        guard = WheelFocusGuard()
        scroll = QScrollArea()
        self.addCleanup(scroll.deleteLater)
        content = QWidget()
        content.resize(200, 1500)
        spin = QSpinBox(content)
        spin.setValue(5)
        scroll.setWidget(content)
        scroll.resize(200, 200)
        scroll.show()
        self.app.processEvents()
        wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        self.assertTrue(guard.eventFilter(spin, wheel))
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        self.assertEqual(spin.value(), 5)
        guard.eventFilter(spin, self.click())
        self.assertFalse(guard.eventFilter(spin, wheel))

    def test_child_click_arms_selector_and_outside_click_disarms_it(self):
        guard = WheelFocusGuard()
        spin = QSpinBox()
        other = QWidget()
        self.addCleanup(spin.deleteLater)
        self.addCleanup(other.deleteLater)
        guard.eventFilter(spin.lineEdit(), QEvent(QEvent.Type.Polish))
        self.assertEqual(spin.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        guard.eventFilter(spin.lineEdit(), self.click())
        self.assertIs(guard._armed, spin)
        guard.eventFilter(other, QEvent(QEvent.Type.FocusIn))
        self.assertIs(guard._armed, spin)
        guard.eventFilter(other, self.click())
        self.assertIsNone(guard._armed)

    def test_deleted_selector_is_cleared_even_on_unrelated_events(self):
        guard = WheelFocusGuard()
        spin = QSpinBox()
        other = QWidget()
        self.addCleanup(other.deleteLater)
        guard.eventFilter(spin, self.click())
        spin.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(guard.eventFilter(other, QEvent(QEvent.Type.LayoutRequest)))
        self.assertIsNone(guard._armed)

    def test_shift_wheel_and_touchpad_pixels_keep_scrolling_the_panel(self):
        guard = WheelFocusGuard()
        scroll = QScrollArea()
        self.addCleanup(scroll.deleteLater)
        content = QWidget()
        content.resize(1500, 1500)
        spin = QSpinBox(content)
        spin.setValue(5)
        scroll.setWidget(content)
        scroll.resize(200, 200)
        scroll.show()
        self.app.processEvents()
        for modifiers, pixels, angle, bar in (
            (Qt.KeyboardModifier.ShiftModifier, QPoint(), QPoint(-120, 0), scroll.horizontalScrollBar()),
            (Qt.KeyboardModifier.NoModifier, QPoint(0, -25), QPoint(), scroll.verticalScrollBar()),
        ):
            with self.subTest(modifiers=modifiers, pixels=pixels):
                before = bar.value()
                wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), pixels, angle,
                                    Qt.MouseButton.NoButton, modifiers,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                self.assertTrue(guard.eventFilter(spin.lineEdit(), wheel))
                self.assertGreater(bar.value(), before)
                self.assertEqual(spin.value(), 5)

    def test_installed_filter_preserves_real_spinbox_wheel_delivery(self):
        guard = WheelFocusGuard()
        spin = QSpinBox()
        self.addCleanup(spin.deleteLater)
        self.app.installEventFilter(guard)
        self.addCleanup(lambda: self.app.removeEventFilter(guard))
        spin.setValue(5)

        def send_wheel():
            wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            self.app.sendEvent(spin, wheel)

        send_wheel()
        self.assertEqual(spin.value(), 5)
        self.app.sendEvent(spin.lineEdit(), self.click())
        send_wheel()
        self.assertGreater(spin.value(), 5)


class WheelFocusWorkTest(unittest.TestCase):
    setUpClass = classmethod(WheelFocusTest.setUpClass.__func__)

    def test_layout_and_paint_events_do_not_walk_widget_ancestors(self):
        guard = WheelFocusGuard()
        spin = QSpinBox()
        self.addCleanup(spin.deleteLater)
        with patch.object(guard, '_selector_for', wraps=guard._selector_for) as lookup:
            for kind in (QEvent.Type.Paint, QEvent.Type.LayoutRequest,
                         QEvent.Type.Resize, QEvent.Type.FocusIn, QEvent.Type.MouseMove):
                self.assertFalse(guard.eventFilter(spin.lineEdit(), QEvent(kind)))
        lookup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
