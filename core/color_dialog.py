"""Seleção de cores com a mesma janela Qt e ações em todas as plataformas."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog

from core.dialog_buttons import style_standard_dialog_later
from core.i18n import tr


def get_color(initial=None, parent=None, title=None):
    dialog = QColorDialog(QColor(Qt.GlobalColor.white) if initial is None else initial, parent)
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dialog.setWindowTitle(tr('Cor') if title is None else title)
    style_standard_dialog_later(dialog)
    try:
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selectedColor()
        return QColor()
    finally:
        dialog.deleteLater()
