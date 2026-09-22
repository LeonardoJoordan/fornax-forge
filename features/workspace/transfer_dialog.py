"""Estrutura visual compartilhada pelos seletores de importação e exportação."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QDialogButtonBox, QFrame,
)
from core.i18n import tr
from core.themes import themed_style
from core.dialog_buttons import style_dialog_button_box, NEUTRAL_STYLE


class TransferDialog(QDialog):
    def __init__(self, parent, title, description):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 540)
        self.setMinimumSize(600, 420)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 24, 24, 20)
        self.body.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName('transferHeading')
        self.body.addWidget(heading)
        subtitle = QLabel(description)
        subtitle.setWordWrap(True)
        subtitle.setObjectName('transferDescription')
        self.body.addWidget(subtitle)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Buscar modelos…'))
        self.search.setAccessibleName(tr('Buscar modelos'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(32)
        self.body.addWidget(self.search)
        toolbar = QHBoxLayout()
        self.select_all = QPushButton(tr('Selecionar todos'))
        self.clear_selection = QPushButton(tr('Limpar seleção'))
        for button in (self.select_all, self.clear_selection):
            button.setAutoDefault(False)
            button.setMinimumHeight(28)
            themed_style(button, NEUTRAL_STYLE)
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.counter = QLabel()
        toolbar.addWidget(self.counter)
        self.body.addLayout(toolbar)
        themed_style(self, '''
            QLabel#transferHeading { font-size: 20px; font-weight: 600; }
            QLabel#transferDescription { color: @muted@; }
            QListWidget, QTableWidget {
                background: @field@; border: 1px solid @border@;
                border-radius: 6px; outline: none;
            }
            QListWidget::item { min-height: 24px; padding: 2px 10px; }
            QListWidget::item:selected { background: @selection@; }
            QTableWidget::item { padding: 2px 6px; }
            QHeaderView::section { background: @surface@; padding: 8px; border: none; }
            QFrame#transferDivider { background: @border@; border: none; }
            QLabel#transferSummary { color: @muted@; }
        ''')

    def add_footer(self, action):
        line = QFrame()
        line.setObjectName('transferDivider')
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        self.body.addWidget(line)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName('transferSummary')
        self.body.addWidget(self.summary)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.primary = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.primary.setText(action)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Cancelar'))
        self.primary.setDefault(True)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        style_dialog_button_box(self.button_box)
        self.body.addWidget(self.button_box)

    def update_count(self, selected, total):
        self.counter.setText(tr('{selected} de {total} selecionados').format(
            selected=selected, total=total))
        self.primary.setEnabled(selected > 0)
