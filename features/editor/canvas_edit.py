"""Sessão de edição textual nativa no canvas Widgets."""
from PySide6.QtCore import QObject, QEvent, Qt, QSignalBlocker
from PySide6.QtGui import QKeySequence, QTextCharFormat, QFont, QTextCursor, QColor
from PySide6.QtWidgets import QGraphicsItem, QApplication, QDoubleSpinBox
from .canvas_items import DesignerBox, _set_resize_handles_visible


class CanvasEdit(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.box = None
        self.shortcuts = []
        window.view.installEventFilter(self)
        window.view.viewport().installEventFilter(self)
        window.scene.selectionChanged.connect(self.selection_changed)

    def begin(self, box):
        if self.box is box:
            return
        self.finish()
        if not box.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            return
        self.window.scene.clearSelection()
        box.setSelected(True)
        self.box = box
        self.before = box.state.html_content
        _set_resize_handles_visible(box, False)
        text = box.text_item
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        text.document().clearUndoRedoStacks()
        text.document().contentsChanged.connect(self.changed)
        text.document().cursorPositionChanged.connect(self.sync_panel)
        self.window.view.setFocus()
        text.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        text.setTextCursor(cursor)
        for name in ('shortcut_delete', 'shortcut_dup', 'shortcut_copy', 'shortcut_paste',
                     'shortcut_select_all',
                     'shortcut_rename', 'shortcut_undo', 'shortcut_redo', 'shortcut_redo_alt'):
            shortcut = getattr(self.window, name, None)
            if shortcut:
                self.shortcuts.append((shortcut, shortcut.isEnabled()))
                shortcut.setEnabled(False)

    def changed(self):
        if self.box:
            self.box.state.rich_text_version = 1
            self.box.state.html_content = self.box.text_item.toHtml()

    def checkpoint(self):
        if self.box:
            self.changed()
            if self.box.state.html_content != self.before:
                self.window.sync_placeholders_list()
                self.window.save_snapshot()
                self.before = self.box.state.html_content

    def finish(self):
        box = self.box
        if box is None:
            return
        self.changed()
        self.box = None
        box.text_item.document().contentsChanged.disconnect(self.changed)
        box.text_item.document().cursorPositionChanged.disconnect(self.sync_panel)
        box.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        _set_resize_handles_visible(box, box.isSelected())
        for shortcut, enabled in self.shortcuts:
            shortcut.setEnabled(enabled)
        self.shortcuts.clear()
        if box.state.html_content != self.before:
            self.window.sync_placeholders_list()
            self.window.refresh_layer_list()
            self.window.save_snapshot()
        self.window.on_selection_changed()

    def selection_changed(self):
        if self.box and not self.box.isSelected():
            self.finish()

    def format(self, kind, enabled):
        box = self.box
        if box is None:
            selected = self.window.scene.selectedItems()
            box = selected[0] if len(selected) == 1 and isinstance(selected[0], DesignerBox) else None
        if box is None:
            return False
        cursor = box.text_item.textCursor()
        if not self.box:
            cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        if kind == 'bold':
            fmt.setFontWeight(QFont.Weight.Bold if enabled else QFont.Weight.Normal)
        elif kind == 'italic':
            fmt.setFontItalic(enabled)
        elif kind == 'underline':
            fmt.setFontUnderline(enabled)
        elif kind == 'family':
            fmt.setFontFamilies([enabled])
        elif kind == 'size':
            fmt.setFontPointSize(enabled)
        elif kind == 'color':
            fmt.setForeground(QColor(enabled))
        cursor.mergeCharFormat(fmt)
        box.state.rich_text_version = 1
        box.state.html_content = box.text_item.toHtml()
        if self.box:
            box.text_item.setTextCursor(cursor)
            self.window.view.setFocus()
            box.text_item.setFocus()
        else:
            self.window.save_snapshot()
        box.recalculate_text_position()
        self.sync_panel()
        return True

    def sync_panel(self, *_):
        selected = self.window.scene.selectedItems()
        box = self.box or (selected[0] if len(selected) == 1 and isinstance(selected[0], DesignerBox) else None)
        if box is None:
            return
        cursor = QTextCursor(box.text_item.document())
        source = box.text_item.textCursor()
        pos = source.selectionStart() if self.box else 0
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        fmt = cursor.charFormat() if source.hasSelection() or not self.box else source.charFormat()
        panel = self.window.editor_texto_panel
        controls = [panel, panel.cbo_font, panel.spin_size, panel.btn_bold, panel.btn_italic, panel.btn_underline]
        blockers = [QSignalBlocker(c) for c in controls]
        panel.cbo_font.setCurrentFont(fmt.font())
        panel.spin_size.setValue(round(fmt.fontPointSize() or box.state.font_size))
        panel.btn_bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        panel.btn_italic.setChecked(fmt.fontItalic())
        panel.btn_underline.setChecked(fmt.fontUnderline())
        color = fmt.foreground().color()
        panel.btn_color.setStyleSheet(f'background: {color.name()};')
        if hasattr(panel, 'color_hex'):
            panel.color_hex.setText(color.name())
        alpha = self.window.findChild(QDoubleSpinBox, 'textColorAlpha')
        if alpha:
            with QSignalBlocker(alpha):
                alpha.setValue(round(color.alphaF()*100))

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.ShortcutOverride and self.box:
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress:
            if self.box:
                if event.key() == Qt.Key.Key_Escape:
                    self.finish()
                    return True
                for sequence, operation in [(QKeySequence.StandardKey.Undo, 'undo'), (QKeySequence.StandardKey.Redo, 'redo')]:
                    if event.matches(sequence):
                        getattr(self.box.text_item.document(), operation)()
                        return True
                if event.matches(QKeySequence.StandardKey.Paste):
                    # External formatting must not introduce incompatible fonts/styles.
                    cursor = self.box.text_item.textCursor()
                    cursor.insertText(QApplication.clipboard().text())
                    self.box.text_item.setTextCursor(cursor)
                    return True
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    kinds = {Qt.Key.Key_B: 'bold', Qt.Key.Key_I: 'italic', Qt.Key.Key_U: 'underline'}
                    kind = kinds.get(event.key())
                    if kind:
                        fmt = self.box.text_item.textCursor().charFormat()
                        active = {'bold': fmt.fontWeight() >= QFont.Weight.Bold, 'italic': fmt.fontItalic(), 'underline': fmt.fontUnderline()}[kind]
                        self.format(kind, not active)
                        return True
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                selected = self.window.scene.selectedItems()
                if len(selected) == 1 and isinstance(selected[0], DesignerBox):
                    self.begin(selected[0])
                    return True
        return super().eventFilter(source, event)
