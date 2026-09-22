from core.themes import themed_style, theme_color, theme_manager
"""Apresentação da planilha; preserva os controles e as operações da tabela."""
from PySide6.QtCore import Qt, QSize, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QTextEdit, QLineEdit,
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QTextCharFormat, QTextCursor
from shiboken6 import isValid
from features.editor.frontend import icon
from core.resources import action_icon_path, align_icon_path
from core.theme_icons import themed_svg_icon
from core.i18n import tr
from .headers import is_signature_header


class CellContentEditor(QTextEdit):
    """Campo superior: Enter confirma; Shift+Enter cria uma nova linha."""

    commitRequested = Signal()
    formatStateChanged = Signal(bool, bool, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.document().setDefaultStyleSheet("b, strong { font-weight: 800; }")
        self.currentCharFormatChanged.connect(lambda *_: self._emit_format_state())
        self.cursorPositionChanged.connect(self._emit_format_state)

    def _emit_format_state(self):
        fmt = self.currentCharFormat()
        self.formatStateChanged.emit(
            fmt.fontWeight() >= QFont.Weight.Bold,
            fmt.fontItalic(),
            fmt.fontUnderline(),
        )

    def toggle_format(self, kind):
        current = self.currentCharFormat()
        fmt = QTextCharFormat()
        if kind == 'b':
            fmt.setFontWeight(
                QFont.Weight.Normal
                if current.fontWeight() >= QFont.Weight.Bold else QFont.Weight.ExtraBold
            )
        elif kind == 'i':
            fmt.setFontItalic(not current.fontItalic())
        elif kind == 'u':
            fmt.setFontUnderline(not current.fontUnderline())
        else:
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            self.setTextCursor(cursor)
        else:
            self.mergeCurrentCharFormat(fmt)
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._emit_format_state()

    def has_rich_formatting(self):
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if (fmt.fontWeight() >= QFont.Weight.Bold
                            or fmt.fontItalic() or fmt.fontUnderline()):
                        return True
                iterator += 1
            block = block.next()
        return False

    def set_rich_html(self, html):
        self.setHtml(html)
        ranges = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().fontWeight() >= QFont.Weight.Bold:
                    ranges.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        for position, length in ranges:
            cursor = self.textCursor()
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            fmt.setFontWeight(QFont.Weight.ExtraBold)
            cursor.mergeCharFormat(fmt)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            formats = {
                Qt.Key.Key_B: 'b', Qt.Key.Key_I: 'i', Qt.Key.Key_U: 'u',
            }
            if event.key() in formats:
                self.toggle_format(formats[event.key()])
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.commitRequested.emit()
                event.accept()
                return
        super().keyPressEvent(event)


def sheet_icon(path):
    return icon(path)


def install_frontend(panel):
    layout = panel.layout()
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)

    heading = QFrame()
    heading.setObjectName('sheetHeading')
    heading.setFixedHeight(58)
    head = QHBoxLayout(heading)
    head.setContentsMargins(14, 14, 14, 14)
    title = QLabel(tr('Dados para o modelo'))
    title.setObjectName('sheetTitle')
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    head.addSpacing(70)
    head.addStretch(1)
    head.addWidget(title)
    head.addStretch(1)
    count = QLabel()
    count.setObjectName('sheetCount')
    count.setFixedWidth(70)
    count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    head.addWidget(count)
    layout.addWidget(heading)

    toolbar = QFrame()
    toolbar.setObjectName('sheetToolbar')
    toolbar_layout = QVBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(0, 0, 0, 0)
    toolbar_layout.setSpacing(0)
    line_tools_title = QLabel(tr('LINHAS'))
    line_tools_title.setObjectName('sheetSectionTitle')
    line_tools_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    line_tools_title.setContentsMargins(14, 9, 14, 0)
    toolbar_layout.addWidget(line_tools_title)
    actions = QHBoxLayout()
    actions.setContentsMargins(4, 5, 4, 9)
    actions.setSpacing(4)
    panel.spin_add_rows.setFixedWidth(46)
    panel.spin_add_rows.setAccessibleName(tr('Quantidade de linhas a adicionar'))
    specs = (
        (panel.btn_add_rows, tr('Adicionar'), tr('Adicionar linhas'), None),
        (panel.btn_duplicate_row, tr('Duplicar'), tr('Duplicar linhas selecionadas'), None),
        (panel.btn_delete_rows, tr('Excluir'), tr('Excluir linhas selecionadas'), None),
    )
    for button, text, tip, path in specs:
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setIcon(sheet_icon(path) if path else QIcon())
        button.setIconSize(QSize(18, 18))
        button.setObjectName('sheetLineAction' if text else 'sheetSquare')
        if not text:
            button.setFixedSize(30, 30)
    actions.addWidget(panel.spin_add_rows)
    actions.addWidget(panel.btn_add_rows)
    separator = QFrame()
    separator.setFixedSize(1, 20)
    themed_style(separator, 'background: @border@; border: none;')
    actions.addWidget(separator)
    actions.addWidget(panel.btn_duplicate_row)
    actions.addWidget(panel.btn_delete_rows)
    actions.addStretch()
    panel.btn_toggle_wrap.setText(tr('Exibir conteúdo completo'))
    panel.btn_toggle_wrap.setToolTip(
        tr('Alterna entre linhas compactas e altura automática para mostrar todo o conteúdo')
    )
    panel.btn_toggle_wrap.setIcon(themed_svg_icon(action_icon_path('expand-content')))
    panel.btn_toggle_wrap.setObjectName('sheetLineAction')
    actions.addWidget(panel.btn_toggle_wrap)
    toolbar_layout.addLayout(actions)
    layout.addWidget(toolbar)

    formula_bar = QFrame()
    formula_bar.setObjectName('formulaBar')
    formula_layout = QVBoxLayout(formula_bar)
    formula_layout.setContentsMargins(0, 0, 0, 0)
    formula_layout.setSpacing(0)
    editor_row = QHBoxLayout()
    editor_row.setContentsMargins(12, 8, 12, 5)
    editor_row.setSpacing(8)
    formula_label = QLabel('fx')
    formula_label.setObjectName('formulaLabel')
    formula_label.setFixedWidth(24)
    formula_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    editor_row.addWidget(formula_label)
    cell_editor = CellContentEditor()
    panel.cell_editor = cell_editor
    cell_editor.setObjectName('cellEditor')
    cell_editor.setPlaceholderText(tr('Selecione uma célula para visualizar ou editar seu conteúdo'))
    cell_editor.setFixedHeight(58)
    cell_editor.setEnabled(False)
    editor_row.addWidget(cell_editor, 1)
    formula_layout.addLayout(editor_row)
    format_row = QHBoxLayout()
    format_row.setContentsMargins(44, 0, 12, 8)
    format_row.setSpacing(8)
    format_buttons = {}
    for asset_name, tag, tooltip in [
        ('bold', 'b', tr('Negrito · Ctrl+B')),
        ('italic', 'i', tr('Itálico · Ctrl+I')),
        ('underline', 'u', tr('Sublinhado · Ctrl+U')),
    ]:
        button = QPushButton()
        button.setObjectName('sheetSquare')
        button.setCheckable(True)
        button.setFixedSize(30, 30)
        button.setToolTip(tooltip)
        button.setIcon(themed_svg_icon(align_icon_path(asset_name)))
        button.setIconSize(QSize(14, 14))
        button.clicked.connect(lambda checked=False, t=tag: cell_editor.toggle_format(t))
        format_buttons[tag] = button
        format_row.addWidget(button)
    panel.format_buttons = format_buttons
    format_row.addStretch(1)
    formula_layout.addLayout(format_row)
    layout.addWidget(formula_bar)

    hint = QLabel(tr('Selecione uma célula para começar · Cole do Excel ou Google Sheets com Ctrl+V'))
    hint.setObjectName('sheetHint')
    layout.addWidget(hint)
    table = panel.table
    cell_editor.commitRequested.connect(lambda: table.setFocus(Qt.FocusReason.OtherFocusReason))
    table.setObjectName('dataGrid')
    table.setAlternatingRowColors(False)
    table.verticalHeader().setDefaultSectionSize(25)
    table.verticalHeader().setMinimumSectionSize(25)
    table.verticalHeader().setMinimumWidth(38)
    table.horizontalHeader().setMinimumSectionSize(64)
    table.horizontalHeader().setDefaultSectionSize(150)
    table.horizontalHeader().setFixedHeight(36)
    table.setCornerButtonEnabled(False)
    table.setWordWrap(False)
    panel.btn_toggle_wrap.setChecked(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    themed_style(table, '')
    layout.addWidget(table, 1)
    table.show()

    image_footer = QFrame()
    image_footer.setObjectName('dynamicImageFooter')
    # Alinha o início deste rodapé ao conjunto de saída (100 px) e à barra
    # de progresso (8 px) existentes no painel de pré-visualização.
    image_footer.setMinimumHeight(108)
    image_footer_layout = QVBoxLayout(image_footer)
    image_footer_layout.setContentsMargins(14, 9, 14, 11)
    image_footer_layout.setSpacing(6)
    image_title = QLabel(tr('IMAGENS VARIÁVEIS'))
    image_title.setObjectName('sheetSectionTitle')
    image_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image_footer_layout.addWidget(image_title)
    image_row = QHBoxLayout()
    image_row.setSpacing(8)
    image_path = QLineEdit()
    image_path.setObjectName('dynamicImageDirectory')
    image_path.setReadOnly(True)
    image_path.setFixedHeight(34)
    image_path.setPlaceholderText(tr('Selecione a pasta que contém as imagens'))
    image_path.setToolTip(tr('Pasta usada para localizar os arquivos indicados na tabela'))
    image_button = QPushButton()
    # Usa exatamente a mesma construção visual do seletor de pasta de saída.
    image_button.setObjectName('outputFolderBrowse')
    image_button.setIcon(themed_svg_icon(action_icon_path('more')))
    image_button.setIconSize(QSize(18, 18))
    image_button.setFixedSize(34, 34)
    image_button.setToolTip(tr('Selecionar pasta de imagens'))
    image_row.addWidget(image_path, 1)
    image_row.addWidget(image_button)
    image_footer_layout.addLayout(image_row)
    image_status = QLabel()
    image_status.setObjectName('dynamicImageStatus')
    image_status.setWordWrap(True)
    image_footer_layout.addWidget(image_status)
    layout.addWidget(image_footer)
    image_footer.hide()
    panel.dynamic_image_footer = image_footer
    panel.txt_dynamic_image_dir = image_path
    panel.btn_dynamic_image_dir = image_button
    panel.lbl_dynamic_image_status = image_status

    def update_format_buttons(bold, italic, underline):
        for button, checked in zip(
            (format_buttons['b'], format_buttons['i'], format_buttons['u']),
            (bold, italic, underline),
        ):
            with QSignalBlocker(button):
                button.setChecked(checked)
    cell_editor.formatStateChanged.connect(update_format_buttons)

    def update_state(*_):
        if not isValid(table) or not isValid(count):
            return
        rows = table.rowCount()
        count.setText(
            tr('{count} linha').format(count=rows)
            if rows == 1 else tr('{count} linhas').format(count=rows)
        )
        selected = bool(table.selectedIndexes())
        panel.btn_duplicate_row.setEnabled(selected)
        panel.btn_delete_rows.setEnabled(selected)
    table.model().rowsInserted.connect(update_state)
    table.model().rowsRemoved.connect(update_state)
    table.model().modelReset.connect(update_state)
    table.itemSelectionChanged.connect(update_state)
    def load_cell_editor(row, column, *_):
        header = table.horizontalHeaderItem(column) if column >= 0 else None
        signature_cell = is_signature_header(header)
        hint.setText(
            tr('Linha {row}  /  {column}    ·    Duplo clique para editar').format(
                row=row + 1, column=header.text()
            ) if row >= 0 and header else tr('Cole do Excel ou Google Sheets com Ctrl+V')
        )
        item = table.item(row, column) if row >= 0 and column >= 0 else None
        with QSignalBlocker(cell_editor):
            rich = item.data(table.RICH_ROLE) if item else None
            if rich:
                cell_editor.set_rich_html(rich)
            else:
                cell_editor.setPlainText(item.text() if item else '')
        cell_editor.setEnabled(row >= 0 and column >= 0 and not signature_cell)
        for button in format_buttons.values():
            button.setEnabled(row >= 0 and column >= 0 and not signature_cell)
        cell_editor._emit_format_state()

    updating_from_formula = False
    def update_from_formula():
        nonlocal updating_from_formula
        row, column = table.currentRow(), table.currentColumn()
        if row < 0 or column < 0:
            return
        item = table.item(row, column)
        if item is None:
            from PySide6.QtWidgets import QTableWidgetItem
            item = QTableWidgetItem()
            table.setItem(row, column, item)
        value = cell_editor.toPlainText()
        rich = cell_editor.toHtml() if cell_editor.has_rich_formatting() else None
        if item.text() != value or item.data(table.RICH_ROLE) != rich:
            updating_from_formula = True
            try:
                item.setText(value)
                item.setData(table.RICH_ROLE, rich)
            finally:
                updating_from_formula = False
            table.viewport().update()

    def refresh_formula_from_item(item):
        if item.row() == table.currentRow() and item.column() == table.currentColumn():
            if updating_from_formula:
                return
            # A edição no campo superior já contém este mesmo valor. Recarregá-lo
            # a cada tecla levaria o cursor para o início e inverteria a digitação.
            with QSignalBlocker(cell_editor):
                rich = item.data(table.RICH_ROLE)
                if rich:
                    cell_editor.set_rich_html(rich)
                else:
                    cell_editor.setPlainText(item.text())
            cell_editor._emit_format_state()

    table.currentCellChanged.connect(load_cell_editor)
    table.itemChanged.connect(refresh_formula_from_item)
    cell_editor.textChanged.connect(update_from_formula)
    update_state()
    themed_style(panel, '''
        QFrame#sheetHeading, QFrame#sheetToolbar { background: @panel@; border: none; border-bottom: 1px solid @border@; }
        QLabel#sheetTitle { color: @text@; font-size: 12px; font-weight: 600; }
        QLabel#sheetCount { color: @muted@; font-size: 11px; }
        QLabel#sheetSectionTitle { color: @muted@; font-size: 10px; font-weight: 600; }
        QLabel#sheetHint { background: @surface@; color: @muted@; padding: 10px 14px; font-size: 11px; }
        QPushButton#sheetSquare { padding: 0; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }
        QPushButton#sheetAction { padding: 0 10px; min-height: 28px; max-height: 28px; }
        QPushButton#sheetLineAction { padding: 0 3px; min-height: 28px; max-height: 28px; }
        QSpinBox { padding: 0 5px; min-height: 28px; max-height: 28px; }
        QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px; background: @border@; border-left: 1px solid @border_strong@; }
        QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; background: @border@; border-left: 1px solid @border_strong@; }
        QSpinBox::up-arrow { image: url(@spin_up@); width: 10px; height: 6px; }
        QSpinBox::down-arrow { image: url(@spin_down@); width: 10px; height: 6px; }
        QTableWidget#dataGrid { background: @field@; alternate-background-color: @alternate@; border: none; border-radius: 0; gridline-color: @grid@; selection-background-color: @selection@; selection-color: @text@; }
        QTableWidget#dataGrid::item { padding: 6px 10px; }
        QHeaderView::section { background: @header@; color: @icon@; font-weight: 600; border: none; border-right: 1px solid @border@; border-bottom: 1px solid @border@; padding: 6px 10px; }
        QTableCornerButton::section { background: @header@; border: none; }
    ''' + '''
        QWidget#dataPanel { background: @field@; border: none; border-radius: 0; padding: 0; }
        QFrame#sheetHeading { background: @panel@; border: none; }
        QLabel#sheetTitle { color: @text@; font-size: 18px; font-weight: 600; }
        QLabel#sheetCount { color: @muted@; font-size: 12px; }
        QLabel#sheetSectionTitle { color: @muted@; font-size: 10px; font-weight: 600; }
        QFrame#sheetToolbar { background: @surface@; border: none; border-bottom: 1px solid @border@; }
        QFrame#formulaBar { background: @panel@; border: none; border-bottom: 1px solid @border@; }
        QLabel#formulaLabel { color: @accent@; font-size: 13px; font-style: italic; }
        QTextEdit#cellEditor { background: @field@; color: @text@; border: 1px solid @border@; border-radius: 5px; padding: 5px 8px; selection-background-color: @selection@; }
        QTextEdit#cellEditor:focus { border-color: @accent@; }
        QTextEdit#cellEditor:disabled { color: @disabled@; background: @panel@; }
        QLabel#sheetHint { background: @panel@; color: @muted@; padding: 9px 14px; font-size: 11px; border-bottom: 1px solid @border@; }
        QFrame#dynamicImageFooter { background: @panel@; border: none; border-top: 1px solid @border@; }
        QLabel#dynamicImageStatus { color: @muted@; font-size: 11px; }
        QPushButton#sheetSquare, QPushButton#sheetAction, QPushButton#sheetLineAction { background: transparent; color: @text@; border: 1px solid transparent; border-radius: 5px; }
        QPushButton#sheetSquare:hover, QPushButton#sheetAction:hover, QPushButton#sheetLineAction:hover { background: @hover@; }
        QPushButton#sheetSquare:pressed, QPushButton#sheetAction:checked, QPushButton#sheetLineAction:checked { background: @selection@; color: @text@; }
        QPushButton#sheetSquare:disabled { color: @disabled@; }
        QSpinBox { background: @field@; color: @text@; border: 1px solid @border@; border-radius: 5px; }
        QSpinBox::up-button, QSpinBox::down-button { background: @border@; border: none; }
        QTableWidget#dataGrid { background: @field@; color: @text@; alternate-background-color: @field@; gridline-color: @grid@; selection-background-color: @selection@; selection-color: @text@; font-size: 13px; }
        QHeaderView { background: @surface@; }
        QHeaderView::section { background: @surface@; color: @muted@; font-size: 11px; font-weight: 500; border: none; border-right: 1px solid @grid@; border-bottom: 1px solid @border@; padding: 6px 8px; }
        QHeaderView::section:checked { background: @selection@; color: @accent@; }
        QTableCornerButton::section { background: @surface@; border: none; }
        QTextEdit { background: @field@; color: @text@; border: 2px solid @accent@; border-radius: 0; padding: 2px 6px; selection-background-color: @selection@; selection-color: @text@; }
        QScrollBar:vertical, QScrollBar:horizontal { background: @scroll_track@; }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: @scroll_handle@; border-radius: 2px; }
        QScrollBar::handle:hover { background: @scroll_hover@; }
        QAbstractScrollArea::corner { background: @scroll_track@; }
    ''')
    image_path.setFixedHeight(34)
    image_button.setFixedSize(34, 34)
