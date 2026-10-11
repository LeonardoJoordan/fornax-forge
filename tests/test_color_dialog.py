"""A seleção de cores é Qt, preserva o alvo e distingue confirmar de cancelar."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QDialogButtonBox, QWidget

from core.color_dialog import get_color


class ColorDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.app.setStyle('Fusion')

    def choose(self, accepted):
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        observations = {}

        def factory(initial, owner):
            dialog = QColorDialog(initial, owner)

            def finish():
                observations['native_disabled'] = dialog.testOption(
                    QColorDialog.ColorDialogOption.DontUseNativeDialog)
                observations['parent'] = dialog.parentWidget()
                observations['title'] = dialog.windowTitle()
                observations['initial'] = dialog.currentColor()
                buttons = dialog.findChild(QDialogButtonBox)
                ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
                cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
                observations['button_sizes'] = ok.size(), cancel.size()
                observations['styled'] = bool(ok.styleSheet()) and bool(cancel.styleSheet())
                if accepted:
                    dialog.setCurrentColor(QColor('#123456'))
                    dialog.accept()
                else:
                    dialog.reject()

            QTimer.singleShot(20, finish)
            return dialog

        with patch('core.color_dialog.QColorDialog', side_effect=factory) as constructor:
            # O símbolo de classe também fornece a enumeração ao helper.
            constructor.ColorDialogOption = QColorDialog.ColorDialogOption
            color = get_color(QColor('#abcdef'), parent, 'Minha cor')
        self.assertTrue(observations['native_disabled'])
        self.assertIs(observations['parent'], parent)
        self.assertEqual(observations['title'], 'Minha cor')
        self.assertEqual(observations['initial'], QColor('#abcdef'))
        self.assertEqual(*observations['button_sizes'])
        self.assertTrue(observations['styled'])
        return color

    def test_accept_returns_chosen_color_with_portable_styled_dialog(self):
        self.assertEqual(self.choose(True), QColor('#123456'))

    def test_cancel_returns_invalid_color(self):
        self.assertFalse(self.choose(False).isValid())


if __name__ == '__main__':
    unittest.main()
