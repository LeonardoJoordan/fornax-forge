from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QWidget, QButtonGroup,
    QAbstractItemView, QHBoxLayout,
)
from PySide6.QtCore import Qt
from core.template_manager import slugify_model_name
from core.i18n import tr
from core.themes import themed_style
from core.dialog_buttons import NEUTRAL_STYLE
from features.workspace.transfer_dialog import TransferDialog


class ImportModelsDialog(TransferDialog):
    def __init__(self, parent, zip_models, existing_slugs):
        super().__init__(parent, tr('Importar modelos'), tr(
            'Revise o conteúdo recebido e escolha o que adicionar à biblioteca. O arquivo de origem será preservado.'))
        self.resize(820, 560)
        self.zip_models = []
        for model in zip_models:
            if isinstance(model, (tuple, list)):
                key, name = model[:2]
                note = model[2] if len(model) > 2 else tr('Modelo antigo')
            else:
                key = name = model
                note = tr('Modelo antigo')
            self.zip_models.append((key, name, note))
        self.actions = {}
        self.model_row_offset = 0
        self.table = QTableWidget(len(self.zip_models), 3)
        self.table.setHorizontalHeaderLabels([tr('Modelo'), tr('Proteção / formato'), tr('Na biblioteca')])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.body.addWidget(self.table, 1)
        for row, (_, name, note) in enumerate(self.zip_models):
            conflict = slugify_model_name(name) in existing_slugs
            item = QTableWidgetItem(name)
            item.setToolTip(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if conflict else Qt.CheckState.Checked)
            self.table.setItem(row, 0, item)
            note_item = QTableWidgetItem(note)
            note_item.setToolTip(note)
            self.table.setItem(row, 1, note_item)
            if conflict:
                choices = QWidget()
                layout = QHBoxLayout(choices)
                layout.setContentsMargins(6, 4, 6, 4)
                layout.setSpacing(6)
                group = QButtonGroup(choices)
                group.setExclusive(True)
                for action_id, label in ((0, tr('Criar cópia')), (1, tr('Substituir'))):
                    button = QPushButton(label)
                    button.setCheckable(True)
                    button.setAutoDefault(False)
                    button.setFixedHeight(24)
                    button.setMinimumWidth(button.fontMetrics().horizontalAdvance(label) + 36)
                    themed_style(button, NEUTRAL_STYLE + """
                        QPushButton:checked { background: @selection@; border-color: @accent@; }
                        QPushButton:checked:disabled { background: @surface@; border-color: @border@; }
                    """)
                    group.addButton(button, action_id)
                    layout.addWidget(button)
                group.button(0).setChecked(True)
                group.button(0).setToolTip(tr('Importar com outro nome, preservando o modelo existente.'))
                group.button(1).setToolTip(tr('Trocar o modelo existente pelo modelo recebido.'))
                self.actions[row] = group
                self.table.setCellWidget(row, 2, choices)
                group.buttonClicked.connect(self._refresh)
            else:
                self.table.setItem(row, 2, QTableWidgetItem(tr('Adicionar novo')))
        if self.actions:
            self.table.insertRow(0)
            self.model_row_offset = 1
            self.actions = {row + 1: group for row, group in self.actions.items()}
            label = QTableWidgetItem(tr('Aplicar a todos os modelos repetidos'))
            label.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(0, 0, label)
            batch_widget = QWidget()
            batch = QHBoxLayout(batch_widget)
            batch.setContentsMargins(6, 4, 6, 4)
            batch.setSpacing(6)
            self.copy_all = QPushButton(tr('Criar cópia'))
            self.replace_all = QPushButton(tr('Substituir'))
            for button in (self.copy_all, self.replace_all):
                button.setAutoDefault(False)
                button.setFixedHeight(24)
                themed_style(button, NEUTRAL_STYLE)
                button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 36)
                batch.addWidget(button)
            self.copy_all.setToolTip(tr('Criar cópias de todos os modelos repetidos.'))
            self.replace_all.setToolTip(tr('Substituir todos os modelos repetidos selecionados para importar.'))
            self.copy_all.clicked.connect(lambda: self._apply_global_conflict(0))
            self.replace_all.clicked.connect(lambda: self._apply_global_conflict(1))
            self.table.setCellWidget(0, 2, batch_widget)
        # Fixar a área das ações impede que o header comprima os layouts internos.
        # O restante pertence ao nome, abreviado pelo delegate padrão do Qt.
        action_widgets = [self.table.cellWidget(row, 2)
                          for row in range(self.table.rowCount())
                          if self.table.cellWidget(row, 2) is not None]
        buttons = [button for widget in action_widgets
                   for button in widget.findChildren(QPushButton)]
        button_width = max((max(button.sizeHint().width(), button.minimumWidth())
                            for button in buttons), default=100)
        for widget in action_widgets:
            widget.setObjectName('importRowActions')
            widget.setAutoFillBackground(False)
            themed_style(widget, 'QWidget#importRowActions { background: transparent; border: none; }')
            widget.layout().setContentsMargins(8, 2, 8, 2)
            widget.layout().setSpacing(8)
            widget.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
            for button in widget.findChildren(QPushButton):
                button.setFixedWidth(button_width)
        self.table.setColumnWidth(2, button_width * 2 + 36)
        self.table.setColumnWidth(1, 210)
        self.add_footer(tr('Continuar'))
        self.search.textChanged.connect(self._filter)
        self.select_all.clicked.connect(lambda: self._select(True))
        self.clear_selection.clicked.connect(lambda: self._select(False))
        self.table.itemChanged.connect(self._refresh)
        self._refresh()

    def get_decisions(self):
        return {key: {'import': self.table.item(row, 0).checkState() == Qt.CheckState.Checked,
                      'action': ('replace' if self.actions[row].checkedId() == 1 else 'rename') if row in self.actions else 'new'}
                for row, (key, _, _) in enumerate(self.zip_models, start=self.model_row_offset)}

    def _filter(self, text):
        for row, (_, name, _) in enumerate(self.zip_models, start=self.model_row_offset):
            self.table.setRowHidden(row, text.casefold() not in name.casefold())

    def _select(self, checked):
        self.table.blockSignals(True)
        for row in range(self.model_row_offset, self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._refresh()

    def _apply_global_conflict(self, action_id):
        for group in self.actions.values():
            group.button(action_id).setChecked(True)
        self._refresh()

    def _refresh(self, *_):
        if not hasattr(self, 'primary'):
            return
        choices = self.get_decisions()
        selected = [choice for choice in choices.values() if choice['import']]
        for row, group in self.actions.items():
            for button in group.buttons():
                button.setEnabled(self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self.update_count(len(selected), len(self.zip_models))
        replacements = sum(choice['action'] == 'replace' for choice in selected)
        self.summary.setText(
            tr('{count} modelo(s) existente(s) serão substituídos. Confira as escolhas antes de continuar.').format(count=replacements)
            if replacements else tr('Os modelos existentes serão preservados. Para nomes repetidos, selecione Criar cópia ou Substituir existente.'))
