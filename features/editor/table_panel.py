"""Medidas das células e aparência da tabela gráfica."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton,
                              QCheckBox, QLineEdit, QColorDialog, QVBoxLayout)
from core.custom_widgets import MathDoubleSpinBox
from core.i18n import tr
from core.themes import themed_style, theme_manager
from core.resources import state_icon_path
from .canvas_items import px_to_mm


def mixed_spin(control, value):
    control.setProperty('mixed', value is None)
    if value is None:
        control.lineEdit().clear()
        control.lineEdit().setPlaceholderText(tr('Vários'))
    else:
        control.setValue(value)
        control.lineEdit().setPlaceholderText('')


def swatch_style(button, template):
    """Não repolir widgets por reaplicação da mesma apresentação."""
    if theme_manager().styles.get(button) != template:
        themed_style(button,template)


class TablePanel(QWidget):
    def __init__(self, window):
        super().__init__()
        from .frontend import column, property_heading, field, row, square_control, compact
        self.window = window
        self._syncing = False
        body, layout = column()
        # Usar o mesmo espaçamento/containers dos demais painéis.
        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.addWidget(body)
        self.summary = QLabel(tr('Selecione uma tabela ou suas células.'))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        property_heading(layout, tr('MEDIDAS'))
        self.row_height = self.spin('tableRowHeight', .09, 5000)
        self.column_width = self.spin('tableColumnWidth', .09, 5000)
        self.row_height.setToolTip(tr('Altura das linhas selecionadas, em milímetros'))
        self.column_width.setToolTip(tr('Largura das colunas selecionadas, em milímetros'))
        row(layout, field(tr('Linhas (mm)'), self.row_height),
            field(tr('Colunas (mm)'), self.column_width))
        self.row_height.valueChanged.connect(lambda value: self.dispatch('track', 'row', value))
        self.column_width.valueChanged.connect(lambda value: self.dispatch('track', 'column', value))
        property_heading(layout, tr('CÉLULAS'), separated=True)
        self.padding = self.spin('tablePadding', 0, 42.33)
        self.padding.valueChanged.connect(lambda value: self.dispatch('cell_style', {'padding': value*300/25.4}))
        layout.addWidget(field(tr('Espaçamento interno (mm)'), self.padding))
        self.wrap = QCheckBox(tr('Quebrar texto automaticamente'))
        self.wrap.setTristate(True)
        self.wrap.clicked.connect(lambda checked: self.dispatch('cell_style', {'wrap': bool(checked)}))
        layout.addWidget(self.wrap)
        self.fill = QLineEdit()
        self.fill.setMaxLength(7)
        self.fill.setPlaceholderText('#RRGGBB')
        self.fill.setObjectName('tableFillColor')
        self.fill_button = QPushButton()
        square_control(self.fill_button)
        self.fill_button.setToolTip(tr('Cor do preenchimento das células'))
        self.fill_button.clicked.connect(lambda: self.choose_color('fill'))
        self.fill.editingFinished.connect(lambda: self.apply_color('fill'))
        self.fill_opacity = self.spin('tableFillOpacity', 0, 100, 0)
        self.fill_opacity.valueChanged.connect(lambda value: self.dispatch('cell_style', {'fill_opacity': value/100}))
        fill_row = row(layout, self.fill_button, self.fill, compact(
            state_icon_path('opacity'), self.fill_opacity, '%', 85, tr('Opacidade do preenchimento')))
        fill_row.setStretch(1, 1)
        property_heading(layout, tr('BORDAS'), separated=True)
        self.edge = QLineEdit()
        self.edge.setObjectName('tableEdgeColor')
        self.edge.setMaxLength(7)
        self.edge_button = QPushButton()
        square_control(self.edge_button)
        self.edge_button.setToolTip(tr('Cor das bordas das células'))
        self.edge_button.clicked.connect(lambda: self.choose_color('edge'))
        self.edge.editingFinished.connect(lambda: self.apply_color('edge'))
        self.edge_width = self.spin('tableEdgeWidth', 0, 8.46)
        self.edge_opacity = self.spin('tableEdgeOpacity', 0, 100, 0)
        self.edge_width.valueChanged.connect(lambda value: self.dispatch('edge_style', {'width': value*300/25.4}))
        # Modelos anteriores podem ter bordas ocultas por visible=False.
        # Alterar a opacidade permite reexibi-las sem modificar o modelo ao carregar.
        self.edge_opacity.valueChanged.connect(lambda value: self.dispatch(
            'edge_style', {'opacity': value/100, 'visible': True}))
        layout.addWidget(field(tr('Espessura'), compact('', self.edge_width, 'mm')))
        edge_row = row(layout, self.edge_button, self.edge, compact(
            state_icon_path('opacity'), self.edge_opacity, '%', 85, tr('Opacidade das bordas')))
        edge_row.setStretch(1, 1)
        self.message = QLabel('')
        self.message.setObjectName('tableStatus')
        self.message.setWordWrap(True)
        themed_style(self.message, 'color: @muted@; font-size: 11px;')
        layout.addWidget(self.message)
        self.setEnabled(False)

    @property
    def controller(self):
        return self.window.table_controller

    @staticmethod
    def spin(name, low, high, decimals=2):
        control = MathDoubleSpinBox()
        control.setObjectName(name)
        control.setRange(low, high)
        control.setDecimals(decimals)
        control.setKeyboardTracking(False)
        control.setMinimumWidth(0)
        return control

    def dispatch(self, method, *args):
        if not self._syncing:
            getattr(self.controller, method)(*args)

    def choose_color(self, target):
        control = self.fill if target == 'fill' else self.edge
        color = QColorDialog.getColor(QColor(control.text()), self.window, tr('Cor'))
        if color.isValid():
            control.setText(color.name())
            self.apply_color(target)

    def apply_color(self, target):
        control = self.fill if target == 'fill' else self.edge
        color = QColor(control.text())
        if color.isValid() and len(control.text()) == 7:
            if target == 'fill':
                self.controller.cell_style({'fill_color': color.name()})
            else:
                self.controller.edge_style({'color': color.name()})
        else:
            self.controller.refresh()

    def load(self, item, bounds, styles, edges):
        self._syncing = True
        controls = self.findChildren(MathDoubleSpinBox)+[self.wrap, self.fill, self.edge]
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            top,left,bottom,right = bounds
            self.summary.setText(tr('{rows} linhas × {columns} colunas; seleção: {count} células.').format(
                rows=item.data['rows'], columns=item.data['columns'], count=len(styles)))
            mixed = lambda values: values[0] if values and all(v == values[0] for v in values) else None
            for control,key,start,stop in ((self.row_height,'row_heights',top,bottom),
                                           (self.column_width,'column_widths',left,right)):
                value = mixed(item.data[key][start:stop+1])
                mixed_spin(control, px_to_mm(value) if value is not None else None)
            for control,key,factor in ((self.padding,'padding',25.4/300),
                                        (self.fill_opacity,'fill_opacity',100),
                                        (self.edge_width,'width',25.4/300),
                                        (self.edge_opacity,'opacity',100)):
                values = edges if key in ('width','opacity') else styles
                value = mixed([0 if key == 'opacity' and not s['visible'] else s[key] for s in values])
                mixed_spin(control, value*factor if value is not None else None)
            value = mixed([s['wrap'] for s in styles])
            self.wrap.setCheckState(Qt.CheckState.PartiallyChecked if value is None else
                                   Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
            for control,button,key,values in ((self.fill,self.fill_button,'fill_color',styles),
                                              (self.edge,self.edge_button,'color',edges)):
                value = mixed([s[key] for s in values])
                control.setText(value or '')
                control.setPlaceholderText(tr('Vários') if value is None else '#RRGGBB')
                swatch_style(button, 'background: '+(value or '@field@')+';')
        finally:
            blockers.clear()
            self._syncing = False
