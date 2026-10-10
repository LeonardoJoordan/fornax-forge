"""Dicas mantêm atraso, varredura e cancelamento ao filtrar eventos globais."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

import core.custom_tooltip as tooltip_module
from core.custom_tooltip import CustomTooltipManager


class TooltipBehaviorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.manager = CustomTooltipManager(delay_ms=1500)
        self.widget = QWidget()
        self.widget.setToolTip('<b>Editar modelo</b>')
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.manager.hide_tooltip()
        self.manager.tooltip_label.deleteLater()
        self.manager.deleteLater()
        self.widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def send(self, kind, widget=None):
        return self.manager.eventFilter(self.widget if widget is None else widget, QEvent(kind))

    def test_enter_starts_delay_and_timeout_displays_rich_text(self):
        self.assertFalse(self.send(QEvent.Type.Enter))
        self.assertIs(self.manager.current_widget, self.widget)
        self.assertTrue(self.manager.timer.isActive())
        self.assertEqual(self.manager.timer.interval(), 1500)
        self.assertFalse(self.manager.tooltip_label.isVisible())
        self.manager.timer.timeout.emit()
        self.assertTrue(self.manager.tooltip_label.isVisible())
        self.assertEqual(self.manager.tooltip_label.text(), '<b>Editar modelo</b>')

    def test_leave_click_and_deactivation_cancel_pending_and_visible_tooltips(self):
        for kind in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.WindowDeactivate):
            for visible in (False, True):
                with self.subTest(kind=kind, visible=visible):
                    self.manager.last_hidden_time = 0
                    self.send(QEvent.Type.Enter)
                    if visible:
                        self.manager.timer.timeout.emit()
                    with patch('core.custom_tooltip.time.time', return_value=1000):
                        self.assertFalse(self.send(kind))
                    self.assertIsNone(self.manager.current_widget)
                    self.assertFalse(self.manager.timer.isActive())
                    self.assertFalse(self.manager.tooltip_label.isVisible())
                    if visible:
                        self.assertEqual(self.manager.last_hidden_time, 1000)

    def test_quick_sweep_shows_next_tooltip_immediately(self):
        second = QWidget()
        second.setToolTip('Salvar modelo')
        self.addCleanup(second.deleteLater)
        self.send(QEvent.Type.Enter)
        self.manager.timer.timeout.emit()
        with patch('core.custom_tooltip.time.time', return_value=1000):
            self.send(QEvent.Type.Leave)
        with patch('core.custom_tooltip.time.time', return_value=1000.2):
            self.send(QEvent.Type.Enter, second)
        self.assertIs(self.manager.current_widget, second)
        self.assertFalse(self.manager.timer.isActive())
        self.assertTrue(self.manager.tooltip_label.isVisible())
        self.assertEqual(self.manager.tooltip_label.text(), 'Salvar modelo')

    def test_empty_tooltip_and_non_widget_do_not_start_timer(self):
        self.widget.setToolTip('')
        self.assertFalse(self.send(QEvent.Type.Enter))
        self.assertFalse(self.send(QEvent.Type.Enter, QObject()))
        self.assertFalse(self.manager.timer.isActive())
        self.assertIsNone(self.manager.current_widget)

    def test_native_tooltip_is_suppressed_only_for_widgets(self):
        self.assertTrue(self.send(QEvent.Type.ToolTip))
        self.assertFalse(self.send(QEvent.Type.ToolTip, QObject()))

    def test_unrelated_events_preserve_pending_tooltip(self):
        self.send(QEvent.Type.Enter)
        for kind in (QEvent.Type.Paint, QEvent.Type.LayoutRequest,
                     QEvent.Type.Resize, QEvent.Type.FocusIn, QEvent.Type.MouseMove):
            self.assertFalse(self.send(kind))
        self.assertIs(self.manager.current_widget, self.widget)
        self.assertTrue(self.manager.timer.isActive())
        self.assertFalse(self.manager.tooltip_label.isVisible())

    def test_installed_filter_receives_native_events(self):
        self.app.installEventFilter(self.manager)
        try:
            self.app.sendEvent(self.widget, QEvent(QEvent.Type.Enter))
            self.assertIs(self.manager.current_widget, self.widget)
            self.assertTrue(self.manager.timer.isActive())
            self.app.sendEvent(self.widget, QEvent(QEvent.Type.WindowDeactivate))
            self.assertFalse(self.manager.timer.isActive())
            self.assertIsNone(self.manager.current_widget)
        finally:
            self.app.removeEventFilter(self.manager)


class TooltipWorkTest(unittest.TestCase):
    setUpClass = classmethod(TooltipBehaviorTest.setUpClass.__func__)
    setUp = TooltipBehaviorTest.setUp
    cleanup = TooltipBehaviorTest.cleanup
    send = TooltipBehaviorTest.send

    def test_irrelevant_events_do_not_inspect_widgets(self):
        # O isinstance com QWidget atravessa o binding Qt: o filtro global
        # deve descartar os eventos sem utilidade antes dessa consulta.
        with patch.object(tooltip_module, 'isinstance', wraps=isinstance, create=True) as inspect:
            self.send(QEvent.Type.LayoutRequest)
            self.send(QEvent.Type.Paint)
        inspect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
