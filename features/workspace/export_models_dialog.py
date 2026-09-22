from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt
from core.i18n import tr
from features.workspace.transfer_dialog import TransferDialog


class ExportModelsDialog(TransferDialog):
    def __init__(self, parent=None, models=None):
        super().__init__(parent, tr('Exportar modelos'), tr(
            'Escolha os modelos que deseja compartilhar. Os originais permanecem na sua biblioteca.'))
        self.list_widget = QListWidget()
        self.body.addWidget(self.list_widget, 1)
        for model in models or []:
            key, name = model if isinstance(model, (tuple, list)) and len(model) == 2 else (model, model)
            item = QListWidgetItem(str(name))
            item.setToolTip(str(name))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)
        self.add_footer(tr('Continuar'))
        self.search.textChanged.connect(self._filter)
        self.select_all.clicked.connect(lambda: self._select(True))
        self.clear_selection.clicked.connect(lambda: self._select(False))
        self.list_widget.itemChanged.connect(self._refresh)
        self._refresh()

    def get_selected_models(self):
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).checkState() == Qt.CheckState.Checked]

    def _filter(self, text):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text.casefold() not in item.text().casefold())

    def _select(self, checked):
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list_widget.blockSignals(False)
        self._refresh()

    def _refresh(self, *_):
        count = len(self.get_selected_models())
        self.update_count(count, self.list_widget.count())
        self.summary.setText(
            tr('Selecione pelo menos um modelo para continuar.') if not count else
            tr('Um modelo: arquivo .fornax. A seguir, escolha as opções de proteção e o destino.') if count == 1 else
            tr('Lote: arquivo ZIP com {count} modelos .fornax. A seguir, escolha as opções de proteção e o destino.').format(count=count))
