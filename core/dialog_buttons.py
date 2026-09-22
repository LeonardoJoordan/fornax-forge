"""Padrão visual portátil para ações de aceitar e cancelar em diálogos."""

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QLabel, QSpacerItem, QSizePolicy,
)

from core.themes import themed_style
from core.i18n import tr


class _DialogButtonStyleFilter(QObject):
    """Captura também rodapés criados internamente pelos diálogos do Qt."""

    def eventFilter(self, watched, event):
        if isinstance(watched, QMessageBox) and event.type() == QEvent.Type.Polish:
            style_message_layout(watched)
        if (isinstance(watched, QDialogButtonBox)
                and event.type() == QEvent.Type.Show
                and not watched.property("fornaxActionButtonsStyled")):
            watched.setProperty("fornaxActionButtonsStyled", True)
            window = watched.window()
            if isinstance(window, QMessageBox):
                style_message_box(window)
            else:
                style_dialog_button_box(watched)
        return False


_style_filter = None


def style_message_layout(message_box):
    """Reserva uma estrutura comum sem trocar os papéis ou sinais dos botões Qt."""
    if message_box.property('fornaxMessageLayoutStyled'):
        return
    message_box.setProperty('fornaxMessageLayoutStyled', True)
    if (message_box.icon() == QMessageBox.Icon.Critical
            and len(message_box.text()) > 1000):
        full_text = message_box.text()
        first_line = full_text.splitlines()[0]
        message_box.setText(first_line if len(first_line) <= 160 else
                            tr('Não foi possível concluir a operação.'))
        existing = message_box.detailedText()
        message_box.setDetailedText(full_text + ('\n\n' + existing if existing else ''))
    layout = message_box.layout()
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setHorizontalSpacing(16)
    layout.setVerticalSpacing(16)
    # Preservar a grade interna (ícone, mensagem, detalhes e botões).
    entries = []
    while layout.count():
        position = layout.getItemPosition(0)
        entries.append((layout.takeAt(0), position))
    for item, (row, column, rows, columns) in entries:
        layout.addItem(item, row + 1, column, rows, columns)
    heading = QLabel(message_box.windowTitle(), message_box)
    heading.setObjectName('fornaxMessageTitle')
    heading.setTextFormat(Qt.TextFormat.PlainText)
    heading.setWordWrap(True)
    layout.addWidget(heading, 0, 0, 1, layout.columnCount())
    themed_style(heading, 'QLabel { color: @text@; font-size: 16px; font-weight: 600; }')
    screen = message_box.screen()
    available = screen.availableGeometry().width() if screen else 800
    content_width = max(240, min(432, available - 96))
    layout.addItem(QSpacerItem(content_width, 8, QSizePolicy.Policy.Minimum,
                              QSizePolicy.Policy.Minimum), layout.rowCount(), 0,
                   1, layout.columnCount())
    message_box.setMinimumHeight(180)
    for label in message_box.findChildren(QLabel):
        if label.objectName() in ('qt_msgbox_label', 'qt_msgbox_informativelabel'):
            label.setWordWrap(True)
    button_box = message_box.findChild(QDialogButtonBox)
    if button_box is not None:
        button_box.setCenterButtons(True)


def install_dialog_button_style(app):
    """Garante o padrão inclusive em QMessageBox.question/getColor nativos."""
    global _style_filter
    if _style_filter is None:
        _style_filter = _DialogButtonStyleFilter(app)
        app.installEventFilter(_style_filter)
    return _style_filter


ACCEPT_STYLE = """
QPushButton {
    background: @accent@;
    color: @on_accent@;
    border: 1px solid @accent@;
    border-radius: 5px;
    padding: 0 14px;
    text-align: center;
    font-weight: 600;
}
QPushButton:hover { background: @accent_hover@; border-color: @accent_hover@; }
QPushButton:pressed { background: @selection@; border-color: @accent@; }
QPushButton:disabled {
    background: @surface@;
    color: @disabled@;
    border-color: @border@;
}
"""

CANCEL_STYLE = """
QPushButton {
    background: @button@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 5px;
    padding: 0 14px;
    text-align: center;
    font-weight: 600;
}
QPushButton:hover {
    background: @danger_background@;
    color: @on_danger@;
    border-color: @danger@;
}
QPushButton:pressed {
    background: @danger@;
    color: @on_danger@;
    border-color: @danger@;
}
QPushButton:disabled {
    background: @surface@;
    color: @disabled@;
    border-color: @border@;
}
"""

NEUTRAL_STYLE = """
QPushButton {
    background: @button@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 5px;
    padding: 0 14px;
    text-align: center;
    font-weight: 600;
}
QPushButton:hover { background: @hover@; border-color: @border_strong@; }
QPushButton:pressed { background: @selection@; border-color: @accent@; }
QPushButton:disabled { background: @surface@; color: @disabled@; border-color: @border@; }
"""


def style_action_pair(accept_buttons, cancel_buttons):
    """Remove ícones e iguala todos os botões do conjunto."""
    accept_buttons = [button for button in accept_buttons if button is not None]
    cancel_buttons = [button for button in cancel_buttons if button is not None]
    buttons = accept_buttons + cancel_buttons
    if not buttons:
        return

    for button in buttons:
        button.setIcon(QIcon())
        themed_style(
            button,
            ACCEPT_STYLE if button in accept_buttons else CANCEL_STYLE,
        )

    # O cálculo ocorre depois que os textos traduzidos foram aplicados.
    width = max(96, max(button.sizeHint().width() for button in buttons))
    height = max(30, max(button.sizeHint().height() for button in buttons))
    for button in buttons:
        button.setFixedSize(width, height)


def style_dialog_button_box(button_box):
    accepts = [
        button_box.button(standard)
        for standard in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Save,
            QDialogButtonBox.StandardButton.Apply,
            QDialogButtonBox.StandardButton.Yes,
        )
    ]
    cancels = [
        button_box.button(standard)
        for standard in (
            QDialogButtonBox.StandardButton.Cancel,
            QDialogButtonBox.StandardButton.Close,
            QDialogButtonBox.StandardButton.No,
        )
    ]
    style_action_pair(accepts, cancels)



def style_message_box(message_box):
    """Aplica o padrão depois que todos os botões da QMessageBox existirem."""
    accept_roles = {
        QMessageBox.ButtonRole.AcceptRole,
        QMessageBox.ButtonRole.YesRole,
        QMessageBox.ButtonRole.ApplyRole,
    }
    cancel_roles = {
        QMessageBox.ButtonRole.RejectRole,
        QMessageBox.ButtonRole.NoRole,
        QMessageBox.ButtonRole.DestructiveRole,
    }
    accepts, cancels = [], []
    for button in message_box.buttons():
        role = message_box.buttonRole(button)
        if role in accept_roles:
            accepts.append(button)
        elif role in cancel_roles:
            cancels.append(button)
    style_action_pair(accepts, cancels)

    # As escolhas adicionais (por exemplo, abrir sem assinaturas) são neutras.
    others = [button for button in message_box.buttons()
              if button not in accepts and button not in cancels]
    for button in others:
        button.setIcon(QIcon())
        themed_style(button, NEUTRAL_STYLE)
    buttons = accepts + cancels + others
    if buttons:
        width = max(96, *(button.sizeHint().width() for button in buttons))
        height = max(30, *(button.sizeHint().height() for button in buttons))
        for button in buttons:
            button.setFixedSize(width, height)


def style_standard_dialog_later(dialog):
    """Usado por diálogos Qt que criam o rodapé somente ao serem exibidos."""
    def apply():
        button_box = dialog.findChild(QDialogButtonBox)
        if button_box is not None:
            style_dialog_button_box(button_box)

    QTimer.singleShot(0, apply)


def get_text(parent, title, label, echo=QLineEdit.EchoMode.Normal, text=""):
    """Equivalente portátil a QInputDialog.getText, com ações padronizadas."""
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextEchoMode(echo)
    dialog.setTextValue(text)
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box is not None:
        style_dialog_button_box(button_box)
    style_standard_dialog_later(dialog)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.textValue(), accepted
