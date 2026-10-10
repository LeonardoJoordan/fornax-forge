"""Atalhos de texto na estrutura flutuante já usada pelos objetos do canvas."""
from PySide6.QtCore import Qt, QSignalBlocker, QObject, QEvent
from PySide6.QtGui import QColor, QIcon, QTextCursor
from PySide6.QtWidgets import QFontComboBox, QSpinBox, QColorDialog

from core.i18n import tr
from core.resources import align_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import themed_style


class TextFloatingTools(QObject):
    keys = ('text_font', 'text_size', 'text_align', 'text_valign', 'text_color', 'opacity')

    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self._closing = False
        self._presentation = None
        self.menus = {}
        self.choices = {}
        self.panel = bar.window.editor_texto_panel
        bar.button('text_font', '', themed_svg_icon(align_icon_path('type')),
                   tr('Selecionar a família da fonte'))
        picker, layout = self.picker('text_font')
        self.font = QFontComboBox(picker)
        self.font.setMinimumWidth(230)
        self.font.setAccessibleName(tr('Fonte'))
        self.font.installEventFilter(self)
        self.font.lineEdit().installEventFilter(self)
        layout.addWidget(self.font)
        bar.set_popup_focus('text_font', self.font)
        self.font.activated.connect(lambda _: self.apply('family', self.font.currentFont()))
        self.font.lineEdit().returnPressed.connect(lambda: self.apply('family', self.font.currentFont()))

        button = bar.button('text_size', '16', QIcon(), tr('Alterar o tamanho da fonte'))
        themed_style(button, 'QPushButton { padding-left: 2px; padding-right: 2px; }')
        picker, layout = self.picker('text_size')
        self.size = QSpinBox(picker)
        self.size.setRange(self.panel.spin_size.minimum(), self.panel.spin_size.maximum())
        self.size.setKeyboardTracking(False)
        self.size.setSuffix(' pt')
        self.size.setAccessibleName(tr('Tamanho'))
        self.size.installEventFilter(self)
        self.size.lineEdit().installEventFilter(self)
        layout.addWidget(self.size)
        bar.set_popup_focus('text_size', self.size)
        self.size.editingFinished.connect(self.apply_size)

        for key, label, options in (
            ('text_align', tr('Alinhamento horizontal'), (
                ('left', 'left-align', tr('Esquerda')), ('center', 'center-align', tr('Centro')),
                ('right', 'right-align', tr('Direita')), ('justify', 'justify', tr('Justificado')))),
            ('text_valign', tr('Alinhamento vertical'), (
                ('top', 'top-alignment', tr('Topo')), ('center', 'mid-alignment', tr('Meio')),
                ('bottom', 'bot-alignment', tr('Base'))))):
            bar.button(key, '', themed_svg_icon(align_icon_path(options[0][1])), label)
            self.menus[key] = bar.choice_menu(key, [
                (value, themed_svg_icon(align_icon_path(asset)), label)
                for value, asset, label in options
            ], lambda value, k=key: self.apply(k, value))
            self.choices[key] = bar.alignment_choices[key]

        button = bar.color_button('text_color', tr('Selecionar a cor do texto'))
        button.clicked.connect(self.choose_color)
        for signal in (self.panel.fontFamilyChanged, self.panel.fontSizeChanged,
                       self.panel.fontColorChanged, self.panel.alignChanged,
                       self.panel.verticalAlignChanged):
            signal.connect(self.refresh)

    def picker(self, key):
        picker, layout = self.bar.picker(key)
        menu = self.bar.alignment_menus[key]
        self.menus[key] = menu
        menu.installEventFilter(self)
        return picker, layout

    def selected(self):
        kind, items = self.bar.selection()
        return items[0] if kind == 'text' else None

    def current_format(self, box):
        # Mesma referência da lateral: o início do trecho selecionado ou o
        # formato no cursor; fora da edição, o primeiro caractere da caixa.
        source = box.text_item.textCursor()
        editing = self.bar.window.canvas_edit.box is box
        if editing and not source.hasSelection():
            return source.charFormat()
        cursor = QTextCursor(box.text_item.document())
        cursor.setPosition(source.selectionStart() if editing else 0)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        return cursor.charFormat()

    def refresh(self, *_, force=False):
        box = self.selected()
        if box is None:
            return
        fmt = self.current_format(box)
        font = fmt.font().resolve(box.text_item.document().defaultFont())
        size = round(fmt.fontPointSize() or box.state.font_size)
        color = fmt.foreground().color()
        presentation = (id(box), font.toString(), size, box.state.align,
                        box.state.vertical_align, color.rgba())
        if presentation == self._presentation and not force:
            return
        self._presentation = presentation
        # Não substituir o valor que o usuário ainda está digitando no popup.
        if not self.menus['text_font'].isVisible():
            with QSignalBlocker(self.font):
                self.font.setCurrentFont(font)
        if not self.menus['text_size'].isVisible():
            with QSignalBlocker(self.size):
                self.size.setValue(size)
        self.bar.buttons['text_font'].setToolTip(tr('Fonte') + ': ' + font.family())
        self.bar.buttons['text_size'].setText(str(size))
        self.bar.buttons['text_size'].setToolTip(tr('Tamanho') + f': {size} pt')
        for key in ('text_font', 'text_size'):
            self.bar.buttons[key].setAccessibleName(self.bar.buttons[key].toolTip())
        for key, current in (('text_align', box.state.align), ('text_valign', box.state.vertical_align)):
            for value, button in self.choices[key].items():
                button.setChecked(value == current)
            self.bar.buttons[key].setIcon(self.choices[key][current].icon())
        themed_style(self.bar.buttons['text_color'], 'border: 1px solid ' + color.name() + ';')

    def popup(self, button, menu):
        self.refresh(force=True)
        self.bar._menu_target = self.bar.target_key(self.selected())
        self.bar.show_menu(button, menu)

    def apply_size(self):
        # Esc e a troca de seleção não confirmam um valor pendente.
        if not self._closing and self.menus['text_size'].isVisible():
            self.apply('size', self.size.value())

    def close_menus(self):
        self._closing = True
        try:
            for menu in self.menus.values():
                menu.close()
        finally:
            self._closing = False

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close_menus()
            self.bar.restore_focus()
            return True
        return False

    def apply(self, kind, value):
        box = self.selected()
        if self._closing or box is None or self.bar.target_key(box) != self.bar._menu_target:
            return
        self.close_menus()
        window = self.bar.window
        source = box.text_item.textCursor()
        selection = (source.anchor(), source.position()) if window.canvas_edit.box is box else None
        if kind == 'family':
            window.update_font_family(value)
        elif kind == 'size':
            window.update_font_size(value)
        elif kind == 'text_align':
            self.panel.cbo_align.setCurrentIndex(self.panel._align_map.index(value))
        elif kind == 'text_valign':
            self.panel.cbo_valign.setCurrentIndex(self.panel._valign_map.index(value))
        if selection is not None and kind in ('text_align', 'text_valign'):
            # apply_state recompõe o QTextDocument ao alinhar a caixa. Manter
            # o trecho ativo permite continuar formatando/digitando no lugar.
            cursor = QTextCursor(box.text_item.document())
            cursor.setPosition(selection[0])
            cursor.setPosition(selection[1], QTextCursor.MoveMode.KeepAnchor)
            box.text_item.setTextCursor(cursor)
            window.canvas_edit.sync_panel()
        window.save_snapshot()
        self.bar.refresh()
        self.bar.restore_focus()

    def choose_color(self):
        box = self.selected()
        if box is None:
            return
        target = self.bar.target_key(box)
        original = self.current_format(box).foreground().color()
        color = QColorDialog.getColor(original, self.bar.window, tr('Selecionar a cor do texto'))
        current = self.selected()
        if color.isValid() and current is not None and self.bar.target_key(current) == target:
            color.setAlpha(original.alpha())
            self.panel.fontColorChanged.emit(color.name(QColor.NameFormat.HexArgb))
            self.bar.window.save_snapshot()
        self.bar.refresh()
        self.bar.restore_focus()
