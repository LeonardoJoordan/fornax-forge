"""Diálogos de exportação e preferências da interface."""

import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from core.themes import theme_manager, load_theme
from core.paths import get_app_data_dir
from core.dialog_buttons import style_dialog_button_box
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout, QHBoxLayout,
    QComboBox, QFormLayout, QPushButton, QColorDialog, QLineEdit, QMessageBox,
)

from features.generator.export_dialog import ConfigDialog as ExportConfigDialog
from core.i18n import tr


EDITABLE_COLORS = (
    ('accent', 'Destaque'), ('surface', 'Fundo principal'),
    ('panel', 'Painéis'), ('field', 'Campos'), ('text', 'Texto'),
    ('muted', 'Texto secundário'), ('selection', 'Seleção'),
    ('border', 'Bordas'), ('guide', 'Guias'),
)


class CustomThemeDialog(QDialog):
    """Editor avançado aberto apenas pela opção Personalizado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Criar tema personalizado"))
        self.setModal(True)
        self.setMinimumWidth(420)
        self.manager = theme_manager()
        self.original_id = self.manager.theme_id
        self.original = copy.deepcopy(self.manager.current)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(tr("Tema personalizado"))
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel(tr("Use o tema atual como base e salve um novo perfil.")))
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("Nome do perfil"))
        layout.addWidget(self.name)
        form = QFormLayout()
        self.swatches = {}
        color_labels = {
            'accent': tr('Destaque'), 'surface': tr('Fundo principal'),
            'panel': tr('Painéis'), 'field': tr('Campos'), 'text': tr('Texto'),
            'muted': tr('Texto secundário'), 'selection': tr('Seleção'),
            'border': tr('Bordas'), 'guide': tr('Guias'),
        }
        for role, label in EDITABLE_COLORS:
            button = QPushButton()
            button.clicked.connect(lambda checked=False, role=role: self.choose_color(role))
            self.swatches[role] = button
            form.addRow(color_labels[role], button)
        layout.addLayout(form)
        self.refresh_swatches()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('Salvar perfil'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Cancelar'))
        style_dialog_button_box(buttons)
        layout.addWidget(buttons)

    def refresh_swatches(self):
        for role, button in self.swatches.items():
            color = self.manager.color(role)
            foreground = '#000000' if QColor(color).lightness() > 140 else '#ffffff'
            button.setText(color.upper())
            button.setStyleSheet(f'background: {color}; color: {foreground}; padding: 5px;')

    def choose_color(self, role):
        color = QColorDialog.getColor(QColor(self.manager.color(role)), self, tr('Escolher cor'))
        if not color.isValid():
            return
        data = copy.deepcopy(self.manager.current)
        data['colors'][role] = color.name()
        if role == 'accent':
            data['colors']['accent_hover'] = color.lighter(112).name()
            data['colors']['on_accent'] = '#000000' if color.lightness() > 155 else '#ffffff'
        self.manager.select(self.manager.theme_id, data)
        self.refresh_swatches()

    def save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, tr('Nome necessário'), tr('Informe um nome para o perfil.'))
            self.name.setFocus()
            return
        try:
            self.saved_id = self.manager.save_custom(name, self.manager.current['colors'])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr('Não foi possível salvar'), str(error))
            return
        self.accept()

    def reject(self):
        self.manager.select(self.original_id, self.original)
        super().reject()


class ThemeDialog(QDialog):
    """Seleção simples; personalização vive em um segundo modal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Tema da interface"))
        self.setModal(True)
        self.setMinimumWidth(420)
        self.manager = theme_manager()
        self.original_id = self.manager.theme_id
        self.original = copy.deepcopy(self.manager.current)
        self._last_theme_id = self.original_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        title = QLabel(tr("Tema da interface"))
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel(tr("Escolha um perfil para a aparência do programa.")))
        self.choice = QComboBox()
        layout.addWidget(self.choice)
        self._load_choices(self.original_id)
        self.choice.currentIndexChanged.connect(self.select_theme)

        footer = QHBoxLayout()
        self.btn_create_theme = QPushButton(tr('Criar tema'))
        self.btn_create_theme.clicked.connect(self.create_theme)
        footer.addWidget(self.btn_create_theme)
        footer.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Aplicar'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Cancelar'))
        style_dialog_button_box(buttons)
        footer.addWidget(buttons)
        layout.addLayout(footer)
        self.buttons = buttons

    def _load_choices(self, selected):
        self.choice.blockSignals(True)
        self.choice.clear()
        builtin_names = {
            'carbon': tr('FORNAX Carbono'), 'dark': tr('FORNAX Marinho'),
            'graphite': tr('FORNAX Grafite'), 'light': tr('FORNAX Pérola'),
            'rose': tr('FORNAX Rosê'),
        }
        for theme_id, data in self.manager.builtins.items():
            self.choice.addItem(builtin_names.get(theme_id, data['name']), theme_id)
        for path in sorted((get_app_data_dir() / 'themes').glob('custom-*.json')):
            try:
                data = load_theme(path, self.manager.dark['colors'])
                self.choice.addItem(data['name'], path.stem)
            except (OSError, ValueError, TypeError):
                continue
        index = self.choice.findData(selected)
        self.choice.setCurrentIndex(index if index >= 0 else 0)
        self.choice.blockSignals(False)

    def select_theme(self, *args):
        selected = self.choice.currentData()
        try:
            self.manager.select(selected)
            self._last_theme_id = selected
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr('Tema indisponível'), str(error))
            self._load_choices(self._last_theme_id)

    def create_theme(self):
        editor = CustomThemeDialog(self)
        if editor.exec():
            self._last_theme_id = editor.saved_id
            self._load_choices(editor.saved_id)

    def save(self):
        self.manager.persist()
        self.accept()

    def reject(self):
        self.manager.select(self.original_id, self.original)
        super().reject()
