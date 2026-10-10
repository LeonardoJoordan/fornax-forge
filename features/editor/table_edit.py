"""Sessão curta da célula ativa e encaminhamento de atalhos por contexto."""
from PySide6.QtCore import QObject, QEvent, Qt, QSignalBlocker, QRectF
from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont, QKeySequence
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QApplication, QStyleOptionGraphicsItem, QStyle
from shiboken6 import isValid

from core.table_layout import build_cell_document
from core.table_model import (cell_at, MAX_CELL_HTML_BYTES,
                              MAX_TABLE_HTML_BYTES, MAX_DOCUMENT_TABLE_HTML_BYTES)
from core.model_document import _document_tables
from core.i18n import tr
from .table_item import TableItem


class CellTextItem(QGraphicsTextItem):
    """Editor nativo recortado na célula, com as mesmas métricas da pintura."""
    def __init__(self, session, document):
        self.session = session
        self.layout_owner = session.item.layout  # Dispositivo vivo até o descarte do editor Qt.
        super().__init__(session.item)
        self.setDocument(document)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)

    def boundingRect(self):
        entry = self.session.entry
        return QRectF(0, -self.session.offset_y, entry.inner.width(), entry.inner.height())

    def paint(self, painter, option, widget=None):
        painter.save()
        try:
            painter.setClipRect(self.boundingRect(), Qt.ClipOperation.IntersectClip)
            clean = QStyleOptionGraphicsItem(option)
            clean.state &= ~QStyle.StateFlag.State_HasFocus
            super().paint(painter, clean, widget)
        finally:
            painter.restore()

    def focusOutEvent(self, event):
        # O painel pode receber foco sem encerrar/descartar a célula alvo.
        super().focusOutEvent(event)
        self.session.changed()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            item = self.session.item
            hit = item.layout.hit(item.mapFromScene(event.scenePos()))
            if hit is not None:
                self.session.finish()
                item.begin_ctrl_cell_selection(hit, event.screenPos())
                # O editor temporário foi removido; a tabela recebe o restante
                # do gesto, incluindo o release, em vez de perder o arraste.
                item.grabMouse()
                item._ctrl_cell_grabbed = True
                event.accept()
                return
        super().mousePressEvent(event)


class TableEdit(QObject):
    SHORTCUTS = ('shortcut_delete','shortcut_dup','shortcut_copy','shortcut_paste',
                 'shortcut_select_all','shortcut_rename','shortcut_undo','shortcut_redo',
                 'shortcut_redo_alt','shortcut_bold','shortcut_italic','shortcut_underline')

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.item = self.text = self.document = None
        self.dirty = False
        self.shortcuts = []
        self.last_error = ''
        window.view.installEventFilter(self)
        window.view.viewport().installEventFilter(self)
        window.scene.selectionChanged.connect(self.selection_changed)

    def selected_table(self):
        if not isValid(self.window) or not isValid(self.window.scene):
            return None
        selected = self.window.scene.selectedItems()
        return selected[0] if len(selected) == 1 and isinstance(selected[0], TableItem) else None

    def begin(self, item, anchor=None, *, position=None):
        self.finish()
        self.window.canvas_edit.finish()
        if not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            return
        anchor = anchor or item.selection_anchor or (0,0)
        cell = cell_at(item.data, *anchor)
        self.anchor = cell['row'],cell['column']
        item.select_cell(*self.anchor)
        self.item = item
        self.entry = next(e for e in item.layout.cells if (e.cell['row'],e.cell['column']) == self.anchor)
        self.document = build_cell_document(cell, self.entry.style, item.layout.device,
                                           self.entry.inner.width(), resolve_values=False)
        self.document.setUndoRedoEnabled(True)
        self.document.clearUndoRedoStacks()
        self.initial_html = self.accepted_html = self.document.toHtml()
        self.dirty = False
        self.offset_y = 0
        self.text = CellTextItem(self, self.document)
        item.editing_cell = cell['id']
        self._position_text()
        self.document.contentsChanged.connect(self.changed)
        controller = getattr(self.window, 'table_controller', None)
        if controller:
            self.text.document().cursorPositionChanged.connect(controller.sync_active_format)
        self.window.view.setFocus()
        self.text.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.text.textCursor()
        if position is not None:
            index = self.document.documentLayout().hitTest(self.text.mapFromParent(position),Qt.HitTestAccuracy.FuzzyHit)
            cursor.setPosition(max(0, index))
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.document.isEmpty():
            cursor.mergeCharFormat(self.document.begin().charFormat())
        self.text.setTextCursor(cursor)
        for name in self.SHORTCUTS:
            shortcut = getattr(self.window,name,None)
            if shortcut:
                self.shortcuts.append((shortcut,shortcut.isEnabled()))
                shortcut.setEnabled(False)
        item.update(self.entry.rect)
        if controller:
            controller.refresh()

    def _position_text(self):
        self.text.prepareGeometryChange()
        height = self.document.documentLayout().documentSize().height()
        self.offset_y = max(0,self.entry.inner.height()-height)*{'top':0,'center':.5,'bottom':1}[self.entry.style['vertical_align']]
        self.text.setPos(self.entry.inner.left(),self.entry.inner.top()+self.offset_y)
        self.text.update()

    def _fits_budget(self, html):
        size = len(html.encode('utf-8'))
        if size > MAX_CELL_HTML_BYTES:
            return False
        current_id = cell_at(self.item.data,*self.anchor)['id']
        other = sum(len(c['html'].encode('utf-8')) for c in self.item.data['cells'] if c['id'] != current_id)
        if other+size > MAX_TABLE_HTML_BYTES:
            return False
        # A página ativa pode conter outras tabelas editadas desde o último
        # checkpoint do documento. Os dados vivos substituem sua cópia antiga.
        tables = {t['object_id']: t for t in _document_tables(self.window._model_document or {})}
        for root in self.window.scene.items():
            if isinstance(root, TableItem):
                tables[root.data['object_id']] = root.data
        inactive = sum(len(c['html'].encode('utf-8')) for t in tables.values()
                       if t['object_id'] != self.item.data['object_id'] for c in t['cells'])
        return inactive+other+size <= MAX_DOCUMENT_TABLE_HTML_BYTES

    def changed(self):
        if self.item is None:
            return
        html = self.document.toHtml()
        if not self._fits_budget(html):
            self.last_error = tr('O texto excede o limite de conteúdo da tabela.')
            position = self.text.textCursor().position()
            with QSignalBlocker(self.document):
                self.document.setHtml(self.accepted_html)
            cursor = self.text.textCursor()
            cursor.setPosition(min(position,self.document.characterCount()-1))
            self.text.setTextCursor(cursor)
            self.window.view.setToolTip(self.last_error)
        else:
            self.accepted_html = html
            self.dirty = html != self.initial_html
        self._position_text()
        self.item.update(self.entry.rect)

    def checkpoint(self):
        if self.item is None:
            return
        self.changed()
        if self.dirty:
            self.item.publish_cell_html(self.anchor,self.accepted_html)
            self.initial_html = self.accepted_html
            self.dirty = False
            self.window.sync_placeholders_list()
            self.window.save_snapshot()
            self.document.clearUndoRedoStacks()
        controller = getattr(self.window, 'table_controller', None)
        if controller:
            controller.sync_active_format(force=True)

    def finish(self):
        if self.item is None:
            return
        self.changed()
        item,text,document = self.item,self.text,self.document
        dirty,anchor,html = self.dirty,self.anchor,self.accepted_html
        if dirty:
            item.publish_cell_html(anchor,html)
        self.item = self.text = self.document = None
        self.dirty = False
        document.contentsChanged.disconnect(self.changed)
        controller = getattr(self.window, 'table_controller', None)
        if controller:
            document.cursorPositionChanged.disconnect(controller.sync_active_format)
        text.clearFocus()
        item.editing_cell = None
        item.scene().removeItem(text)
        text.setParentItem(None)
        text.deleteLater()
        for shortcut,enabled in self.shortcuts:
            shortcut.setEnabled(enabled)
        self.shortcuts.clear()
        item.update()
        if dirty:
            self.window.sync_placeholders_list()
            self.window.save_snapshot()
        if controller:
            controller.refresh()

    def selection_changed(self):
        if self.item and not self.item.isSelected():
            self.finish()

    def navigate(self, item, backwards=False):
        was_editing = self.item is not None
        anchor = self.anchor if was_editing else item.selection_anchor or (0,0)
        self.finish()
        cells = sorted(item.data['cells'],key=lambda c:(c['row'],c['column']))
        index = next(i for i,c in enumerate(cells) if (c['row'],c['column']) == anchor)
        index = min(max(0,index+(-1 if backwards else 1)),len(cells)-1)
        target = cells[index]['row'],cells[index]['column']
        item.select_cell(*target)
        if was_editing:
            self.begin(item,target)

    def clear_selected(self, item):
        anchors = [(c['row'], c['column']) for c in item.selected_cells()]
        item.publish_cells_html({anchor:'' for anchor in anchors})
        self.window.sync_placeholders_list()
        self.window.save_snapshot()

    def navigate_arrow(self, item, key, extend=False):
        cell = cell_at(item.data, *(item.selection_cursor or item.selection_anchor))
        row, column = cell['row'], cell['column']
        if key == Qt.Key.Key_Left:
            column -= 1
        elif key == Qt.Key.Key_Right:
            column += cell['column_span']
        elif key == Qt.Key.Key_Up:
            row -= 1
        else:
            row += cell['row_span']
        row = min(max(0, row), item.data['rows']-1)
        column = min(max(0, column), item.data['columns']-1)
        item.select_cell(row, column, extend=extend)

    def eventFilter(self, source, event):
        if event.type() not in (QEvent.Type.ShortcutOverride,QEvent.Type.InputMethod,
                               QEvent.Type.KeyPress,QEvent.Type.KeyRelease):
            return False
        item = self.item or self.selected_table()
        cells_active = item is not None and item.selected_range is not None
        arrows = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
        if event.type() == QEvent.Type.KeyRelease:
            return cells_active and self.item is None and event.key() in arrows
        if event.type() == QEvent.Type.ShortcutOverride and cells_active:
            if event.matches(QKeySequence.StandardKey.Save):
                return False
            event.accept()
            return True
        if event.type() == QEvent.Type.InputMethod and cells_active and self.item is None:
            self.begin(item)
            self.window.scene.sendEvent(self.text,event)
            return True
        if event.type() != QEvent.Type.KeyPress or not cells_active:
            return False
        if event.key() == Qt.Key.Key_Escape:
            self.window._finish_canvas_pointer_interaction(leave_pan=True)
            if self.item:
                self.finish()
            else:
                item.clear_cell_selection()
            return True
        if event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
            self.navigate(item,event.key() == Qt.Key.Key_Backtab or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return True
        if self.item:
            for sequence,operation in ((QKeySequence.StandardKey.Undo,'undo'),(QKeySequence.StandardKey.Redo,'redo')):
                if event.matches(sequence):
                    if getattr(self.document,'isUndoAvailable' if operation == 'undo' else 'isRedoAvailable')():
                        getattr(self.document,operation)()
                    else:
                        self.finish()
                        getattr(self.window,operation)()
                    return True
            if event.matches(QKeySequence.StandardKey.Paste):
                cursor = self.text.textCursor()
                cursor.insertText(QApplication.clipboard().text())
                self.text.setTextCursor(cursor)
                return True
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() in (Qt.Key.Key_B,Qt.Key.Key_I,Qt.Key.Key_U):
                cursor = self.text.textCursor();fmt = cursor.charFormat();change = QTextCharFormat()
                if event.key() == Qt.Key.Key_B:
                    change.setFontWeight(QFont.Weight.Normal if fmt.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold)
                elif event.key() == Qt.Key.Key_I:change.setFontItalic(not fmt.fontItalic())
                else:change.setFontUnderline(not fmt.fontUnderline())
                cursor.mergeCharFormat(change)
                if self.document.isEmpty():cursor.mergeBlockCharFormat(change)
                self.text.setTextCursor(cursor)
                return True
            return False  # Cursor, seleção, Enter e composição: editor nativo Qt.
        if event.key() == Qt.Key.Key_D and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.window.duplicate_selected()
            return True
        if event.key() in arrows:
            self.navigate_arrow(item,event.key(),bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return True
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_F2):
            self.begin(item)
            return True
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            self.clear_selected(item)
            return True
        if event.matches(QKeySequence.StandardKey.SelectAll):
            item.selection_anchor = (0,0)
            item.select_cell(item.data['rows']-1,item.data['columns']-1,extend=True)
            return True
        for sequence,operation in ((QKeySequence.StandardKey.Undo,'undo'),(QKeySequence.StandardKey.Redo,'redo')):
            if event.matches(sequence):
                getattr(self.window,operation)()
                return True
        if event.matches(QKeySequence.StandardKey.Paste):
            self.window.table_controller.paste_selection()
            return True
        if event.matches(QKeySequence.StandardKey.Copy):
            self.window.table_controller.copy_selection()
            return True
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() in (Qt.Key.Key_B,Qt.Key.Key_I,Qt.Key.Key_U):
            key = {Qt.Key.Key_B:'bold', Qt.Key.Key_I:'italic', Qt.Key.Key_U:'underline'}[event.key()]
            getattr(self.window.editor_texto_panel,'btn_'+key).click()
            return True
        if event.text() and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self.begin(item)
            self.window.scene.sendEvent(self.text,event)
            return True
        return False
