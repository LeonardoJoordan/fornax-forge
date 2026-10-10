"""Atalhos de células; a estrutura flutuante é compartilhada com o editor."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog
from shiboken6 import isValid
from core.i18n import tr
from core.resources import object_icon_path, align_icon_path
from core.theme_icons import themed_svg_icon, tool_icon
from .floating_bar import FloatingBar


class TableFloatingBar(FloatingBar):
    def dock_gap(self, edge):
        from .table_selectors import TableSelectors
        return TableSelectors.BAR_GAP if edge in ('top', 'left') else super().dock_gap(edge)

    def __init__(self, controller):
        super().__init__(controller)
        table_icon = themed_svg_icon(object_icon_path('table'))
        for axis, label, operations in (
            ('rows', tr('Linhas'), (
                ('row_before', tr('Adicionar acima')), ('row_after', tr('Adicionar abaixo')),
                ('remove_rows', tr('Remover linhas')))),
            ('columns', tr('Colunas'), (
                ('column_before', tr('Adicionar à esquerda')), ('column_after', tr('Adicionar à direita')),
                ('remove_columns', tr('Remover colunas'))))):
            button = self.button(axis, label, table_icon, label, label_mode='horizontal')
            menu = self.menu(button)
            for key, text in operations:
                action = menu.addAction(text)
                self.actions[key] = action
                action.triggered.connect(lambda _=False, op=key: self.invoke(
                    'structure', op, 1, from_menu=True))
        self.separator()
        for key, label, path in (
            ('merge', tr('Mesclar células'), '<rect x="3" y="5" width="18" height="14"/><path d="M7 12h10m-3-3 3 3-3 3"/>'),
            ('split', tr('Separar células'), '<rect x="3" y="5" width="18" height="14"/><path d="M12 5v14m-5-7h2m6 0h2"/>')):
            button = self.button(key, '', tool_icon(path), label)
            button.clicked.connect(lambda _=False, op=key: self.invoke('structure', op))
        self.separator()
        for axis, choices in (
            ('align', (('left', 'left-align', tr('Esquerda')), ('center', 'center-align', tr('Centro')),
                       ('right', 'right-align', tr('Direita')))),
            ('vertical_align', (('top', 'top-alignment', tr('Topo')), ('center', 'mid-alignment', tr('Meio')),
                                ('bottom', 'bot-alignment', tr('Base'))))):
            button = self.button(axis, '', themed_svg_icon(align_icon_path(choices[0][1])),
                                 tr('Alinhamento horizontal') if axis == 'align' else tr('Alinhamento vertical'))
            self.choice_menu(axis, [
                (value, themed_svg_icon(align_icon_path(asset)), label)
                for value, asset, label in choices
            ], lambda value, key=axis: self.invoke('cell_style', {key: value}, from_menu=True))
        self.separator()
        button = self.color_button('fill', tr('Cor do preenchimento das células'))
        button.clicked.connect(self.choose_fill)
        self.finish_setup()

    def collapse_tooltip(self, collapsed):
        return tr('Expandir barra da tabela') if collapsed else tr('Recolher barra da tabela')

    def invoke(self, method, *args, from_menu=False):
        item = self.controller.selected()
        if item is None or (from_menu and item.data['object_id'] != self._menu_target):
            return
        getattr(self.controller, method)(*args)
        self.refresh()
        self.restore_focus()

    def restore_focus(self):
        self.view.setFocus(Qt.FocusReason.OtherFocusReason)
        session = self.controller.window.table_edit
        if session.text is not None and isValid(session.text):
            session.text.setFocus(Qt.FocusReason.OtherFocusReason)

    def choose_fill(self):
        item = self.controller.selected()
        if item is None:
            return
        target = item.data['object_id']
        color = QColorDialog.getColor(QColor(self.controller.panel.fill.text() or '#ffffff'),
                                      self.controller.window, tr('Cor'))
        current = self.controller.selected()
        if color.isValid() and current is not None and current.data['object_id'] == target:
            self.controller.cell_style({'fill_color': color.name()})
        self.restore_focus()

    def refresh(self):
        item = self.controller.selected()
        states = dict.fromkeys(('merge', 'split', 'remove_rows', 'remove_columns'), False)
        if item is not None:
            top,left,bottom,right = self.controller.bounds(item)
            entries = self.controller.entries(item)
            states.update(
                merge=len(entries) > 1 and item.selection_is_rectangular(),
                split=any(e.cell['row_span'] > 1 or e.cell['column_span'] > 1 for e in entries),
                remove_rows=len(item.selected_track_indexes('row')) < item.data['rows'],
                remove_columns=len(item.selected_track_indexes('column')) < item.data['columns'])
        for key in ('merge', 'split'):
            self.buttons[key].setEnabled(states[key])
        for key in ('remove_rows', 'remove_columns'):
            self.actions[key].setEnabled(states[key])
        text_panel = self.controller.window.editor_texto_panel
        for axis, combo, values in (
            ('align', text_panel.cbo_align, ('left', 'center', 'right')),
            ('vertical_align', text_panel.cbo_valign, ('top', 'center', 'bottom'))):
            for index, value in enumerate(values):
                action = self.actions[axis+'_'+value]
                action.setChecked(combo.currentIndex() == index)
                self.alignment_choices[axis][value].setChecked(action.isChecked())
            selected = combo.currentIndex()
            # Mistos não devem sugerir que todas as células têm a mesma opção.
            icon = (self.actions[axis+'_'+values[selected]].icon() if selected in range(len(values))
                    else tool_icon('<path d="M4 7h16M7 12h10M4 17h16"/>'))
            self.buttons[axis].setIcon(icon)
            self.buttons[axis].setProperty('mixed', selected < 0)
        self.reposition()

