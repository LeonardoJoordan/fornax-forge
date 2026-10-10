"""Operações de tabela no editor: preflight completo e publicação localizada."""
from copy import deepcopy
import csv
from math import ceil
from io import StringIO

from PySide6.QtCore import Qt, QMimeData, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QSpinBox,
                              QDialogButtonBox, QLabel, QGraphicsItem)
from shiboken6 import isValid
from core.i18n import tr
from core.html_utils import TextOnlyDocument
from core.model_document import add_model_table, replace_model_page, ModelValidationError
from core.table_model import (new_table, format_cells, format_edges, merge_cells,
    split_cell, insert_rows, insert_columns, remove_rows, remove_columns, resize_table,
    set_track_sizes, table_size, effective_cell_style, TableValidationError, cell_at, visible_edge_keys)
from core.table_clipboard import (copy_range, encode_range, decode_range, paste_range,
                                 table_from_tsv, TABLE_RANGE_MIME, MAX_CLIPBOARD_BYTES)
from core.table_layout import build_cell_document, logical_text_device
from core.themes import themed_style
from .canvas_items import mm_to_px, px_to_mm
from .table_item import TableItem
from .table_panel import mixed_spin, swatch_style


def common(values):
    return values[0] if values and all(value == values[0] for value in values) else None


class TableController:
    def __init__(self, window):
        self.window = window
        self._refreshing = False
        self._format_signature = None
        self._presentation_key = None
        from .table_floating import TableFloatingBar
        self.floating_bar = TableFloatingBar(self)

    @property
    def panel(self):
        return self.window.table_panel

    def selected(self):
        if not isValid(self.window) or not isValid(self.window.scene):
            return None
        items = self.window.scene.selectedItems()
        return items[0] if len(items) == 1 and isinstance(items[0], TableItem) else None

    def bounds(self, item):
        return item.selected_range or (0, 0, item.data['rows']-1, item.data['columns']-1)

    def entries(self, item):
        top,left,bottom,right = self.bounds(item)
        return [entry for entry in item.layout.cells
                if top <= entry.cell['row'] <= bottom and left <= entry.cell['column'] <= right]

    def error(self, error):
        self.panel.message.setText(tr(str(error)))
        self._presentation_key = None
        self.refresh()

    def preflight(self, item, candidate):
        page = self.window.get_current_scene_state()
        page['tables'] = [candidate if table['object_id'] == item.data['object_id'] else table
                          for table in page.get('tables', [])]
        replace_model_page(self.window._model_document, page, self.window._active_page_id)

    def transact(self, operation, *, selection=None, keep_edit=False):
        item = self.selected()
        if item is None or not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            return False
        session = self.window.table_edit
        anchor = session.anchor if session.item is item else None
        cursor = session.text.textCursor() if anchor is not None else None
        cursor_positions = (cursor.anchor(), cursor.position()) if cursor is not None else None
        try:
            before = item.to_data()
            candidate = operation(deepcopy(before), self.bounds(item))
            self.preflight(item, candidate)
            if candidate == before:
                return True
        except (TableValidationError, ModelValidationError, ValueError) as error:
            self.error(error)
            return False
        session.finish()
        item.publish_table_data(candidate)
        if selection is not None:
            top,left,bottom,right = selection
        else:
            top,left,bottom,right = self.bounds(item)
        top,bottom = min(top,item.data['rows']-1),min(bottom,item.data['rows']-1)
        left,right = min(left,item.data['columns']-1),min(right,item.data['columns']-1)
        item.select_cell(top,left,notify=False)
        item.select_cell(bottom,right,extend=True)
        self.panel.message.clear()
        self.window.sync_placeholders_list()
        self.window.save_snapshot()
        self.window.refresh_layer_list()
        if keep_edit and anchor is not None:
            session.begin(item, anchor)
            restored = session.text.textCursor()
            restored.setPosition(min(cursor_positions[0], session.document.characterCount()-1))
            restored.setPosition(min(cursor_positions[1], session.document.characterCount()-1), QTextCursor.MoveMode.KeepAnchor)
            session.text.setTextCursor(restored)
        self.refresh()
        return True

    def show_create_dialog(self):
        from core.dialog_buttons import style_dialog_button_box
        dialog = QDialog(self.window)
        dialog.setWindowTitle(tr('Adicionar tabela'))
        form = QFormLayout(dialog)
        rows, columns = QSpinBox(), QSpinBox()
        for control in (rows, columns):
            control.setRange(1, 100);control.setValue(3)
        form.addRow(tr('Linhas'), rows);form.addRow(tr('Colunas'), columns)
        hint = QLabel(tr('Até 1.000 posições por tabela e 2.000 por modelo.'))
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        style_dialog_button_box(buttons)
        form.addRow(buttons)
        def accept():
            if self.add_table(rows.value(), columns.value()):
                dialog.accept()
            else:
                hint.setText(self.panel.message.text())
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def add_table(self, rows=3, columns=3):
        self.window._finish_page_interaction()
        try:
            data = new_table(rows, columns, width=columns*mm_to_px(30),
                             height=rows*mm_to_px(20),
                             name=self.window._unique_layer_name(tr('Tabela')))
            # Uma linha da fonte padrão, mais o espaço interno e os meios-traços.
            inset = 2*data['style']['padding'] + data['border']['width']
            device = logical_text_device()
            probe = build_cell_document(data['cells'][0], data['style'], device,
                                        data['column_widths'][0]-inset)
            row_height = ceil(probe.documentLayout().documentSize().height()+inset)
            data['row_heights'] = [row_height]*rows
            data['layer_id'] = self.window._get_next_layer_id()
            center = self.window.view.mapToScene(self.window.view.viewport().rect().center())
            width,height = table_size(data)
            data.update(x=center.x()-width/2,y=center.y()-height/2,
                        z_value=max([i.zValue() for i in self.window.scene.items()
                                     if getattr(i,'layer_id',None) is not None]+[100])+1)
            if self.window._active_page_id == 'organogram':
                data['board_behind'] = False
            document = self.window._capture_document_history_state()['document']
            updated = add_model_table(document, data, self.window._active_page_id)
            item = TableItem(data, self.window)
        except (ValueError, ModelValidationError) as error:
            self.error(error)
            return False
        self.window.canvas_edit.finish()
        self.window.scene.clearSelection()
        self.window._model_document = updated
        self.window.scene.addItem(item)
        item.setSelected(True)
        item.setFocus(Qt.FocusReason.OtherFocusReason)
        self.window.refresh_layer_list()
        self.window.sync_placeholders_list()
        self.window.save_snapshot()
        self.refresh()
        return True

    def structure(self, operation, count=1):
        def change(table, bounds):
            top,left,bottom,right = bounds
            if operation == 'row_before':return insert_rows(table,top,count)
            if operation == 'row_after':return insert_rows(table,bottom+1,count)
            if operation == 'column_before':return insert_columns(table,left,count)
            if operation == 'column_after':return insert_columns(table,right+1,count)
            if operation == 'remove_rows':return remove_rows(table,top,bottom-top+1)
            if operation == 'remove_columns':return remove_columns(table,left,right-left+1)
            if operation == 'merge':return merge_cells(table,*bounds)
            if operation == 'split':
                for cell in list(table['cells']):
                    if (top <= cell['row'] <= bottom and left <= cell['column'] <= right
                            and (cell['row_span'] > 1 or cell['column_span'] > 1)):
                        table = split_cell(table,cell['row'],cell['column'])
                return table
            raise TableValidationError('Operação de estrutura inválida.')
        return self.transact(change)

    def resize(self, axis, value):
        def change(table, bounds):
            width,height = table_size(table)
            return resize_table(table,mm_to_px(value) if axis=='width' else width,
                                mm_to_px(value) if axis=='height' else height)
        return self.transact(change)

    def track(self, axis, value):
        def change(table, bounds):
            top,left,bottom,right = bounds
            indexes = list(range(top,bottom+1) if axis=='row' else range(left,right+1))
            return set_track_sizes(table,axis,indexes,mm_to_px(value))
        return self.transact(change)

    def cell_style(self, style):
        return self.transact(lambda table,bounds: format_cells(table,*bounds,style),keep_edit=True)

    def edge_style(self, style):
        return self.transact(lambda table,bounds: format_edges(table,*bounds,style,target='all'),keep_edit=True)

    @staticmethod
    def char_format(kind, value):
        fmt = QTextCharFormat()
        if kind == 'bold':fmt.setFontWeight(QFont.Weight.Bold if value else QFont.Weight.Normal)
        elif kind == 'italic':fmt.setFontItalic(bool(value))
        elif kind == 'underline':fmt.setFontUnderline(bool(value))
        elif kind == 'family':fmt.setFontFamilies([value])
        elif kind == 'size':fmt.setFontPointSize(value)
        elif kind == 'color':fmt.setForeground(QColor(value))
        return fmt

    def format_text(self, kind, value):
        item = self.selected()
        if item is None:
            if isValid(self.window.scene) and any(isinstance(root,TableItem) for root in self.window.scene.selectedItems()):
                return True  # Seleção de tipos mistos não formata apenas parte dos objetos.
            return False
        if kind == 'size' and not 1 <= value <= 200:
            self.error(tr('O tamanho da fonte deve estar entre 1 e 200 pontos.'))
            return True
        if kind == 'align':
            self.cell_style({'align': value});return True
        if kind == 'vertical_align':
            self.cell_style({'vertical_align': value});return True
        if kind == 'line_height':
            self.cell_style({'line_height': value});return True
        fmt = self.char_format(kind,value)
        session = self.window.table_edit
        if session.item is item:
            cursor = session.text.textCursor()
            cursor.mergeCharFormat(fmt)
            if session.document.isEmpty():
                cursor.mergeBlockCharFormat(fmt)
            session.text.setTextCursor(cursor)
            session.checkpoint()
            self.sync_active_format()
            self.window.view.setFocus();session.text.setFocus()
            return True
        def change(table, bounds):
            style = ({'font_family':value} if kind=='family' else {'font_size':value} if kind=='size'
                     else {'font_color':QColor(value).name()} if kind=='color' else {})
            if style:table = format_cells(table,*bounds,style)
            top,left,bottom,right = bounds
            entries_by_id = {entry.cell['id']: entry for entry in item.layout.cells}
            for cell in table['cells']:
                if not (top <= cell['row'] <= bottom and left <= cell['column'] <= right):continue
                layout = entries_by_id[cell['id']]
                document = build_cell_document(cell,effective_cell_style(table,cell),item.layout.device,
                                               layout.inner.width(),resolve_values=False)
                cursor = QTextCursor(document);cursor.select(QTextCursor.SelectionType.Document)
                cursor.mergeCharFormat(fmt)
                if document.isEmpty():
                    cursor.mergeBlockCharFormat(fmt)
                cell['html'] = document.toHtml()
            return table
        self.transact(change)
        return True

    def copy_selection(self):
        item = self.selected()
        if item is None or item.selected_range is None or self.window.table_edit.item is not None:
            return False
        try:
            source = copy_range(item.to_data(),*self.bounds(item))
            raw = encode_range(source)
            cells = {(c['row'],c['column']): c for c in source['cells']}
            output = StringIO(newline='');writer = csv.writer(output,delimiter='\t',lineterminator='\n')
            for row in range(source['rows']):
                values = []
                for column in range(source['columns']):
                    cell = cells.get((row,column))
                    document = TextOnlyDocument()
                    document.setHtml(cell['html'] if cell else '')
                    values.append(document.toPlainText())
                writer.writerow(values)
            mime = QMimeData();mime.setData(TABLE_RANGE_MIME,raw);mime.setText(output.getvalue())
            QApplication.clipboard().setMimeData(mime)
            self.panel.message.clear()
        except ValueError as error:
            self.error(error)
        return True

    def paste_selection(self):
        item = self.selected()
        if item is None or item.selected_range is None:
            return False
        session = self.window.table_edit
        if session.item is item:
            cursor = session.text.textCursor();cursor.insertText(QApplication.clipboard().text())
            session.text.setTextCursor(cursor)
            return True
        mime = QApplication.clipboard().mimeData()
        if mime is None:return True
        try:
            internal = mime.hasFormat(TABLE_RANGE_MIME)
            if internal:
                raw = mime.data(TABLE_RANGE_MIME)
                if raw.size() > MAX_CLIPBOARD_BYTES:raise TableValidationError('Área de transferência excessiva.')
                source = decode_range(bytes(raw))
            else:
                source = table_from_tsv(mime.text())
            top,left,_,_ = self.bounds(item)
            self.transact(lambda table,bounds: paste_range(table,source,top,left,content_only=not internal),
                          selection=(top,left,top+source['rows']-1,left+source['columns']-1))
        except ValueError as error:
            self.error(error)
        return True

    def refresh(self):
        if self._refreshing or not isValid(self.window) or not isValid(self.window.scene):
            return
        self._refreshing = True
        try:
            item = self.selected()
            panel = self.window.editor_texto_panel
            panel.set_table_mode(item is not None)
            self.panel.setEnabled(item is not None)
            section = self.window._table_section
            section.set_available(item is not None)
            if item is None:
                self._presentation_key = None
                if any(isinstance(root,TableItem) for root in self.window.scene.selectedItems()):
                    panel.setEnabled(False)
                return
            panel.setEnabled(True)
            session = self.window.table_edit
            key = (id(item),item.presentation_revision,self.bounds(item),
                   id(session.document) if session.item is item else None)
            if key == self._presentation_key:
                return
            self._presentation_key = key
            entries = self.entries(item)
            bounds = self.bounds(item)
            top,left,bottom,right = bounds
            edges = []
            for orientation,r,c in item.layout.visible_edges:
                inside = (top <= r <= bottom+1 and left <= c <= right if orientation=='h'
                          else top <= r <= bottom and left <= c <= right+1)
                if inside:
                    edges.append(item.layout.edge_style((orientation,r,c)))
            self.panel.load(item,bounds,[entry.style for entry in entries],edges)
            if self.window.table_edit.item is item:
                self.sync_active_format(force=True)
            else:
                formats = []
                for entry in entries:
                    start = len(formats)
                    block = entry.document.begin()
                    while block.isValid():
                        iterator = block.begin()
                        while not iterator.atEnd():
                            fragment = iterator.fragment()
                            if fragment.isValid():formats.append((fragment.charFormat(),entry.style))
                            iterator += 1
                        block = block.next()
                    if len(formats) == start:
                        formats.append((entry.document.begin().charFormat(),entry.style))
                self.sync_text([e.style for e in entries],formats)
        finally:
            self._refreshing = False
            self.floating_bar.refresh()

    def sync_active_format(self, *_args, force=False):
        session = self.window.table_edit
        if session.item is None:return
        fmt = session.text.textCursor().charFormat()
        signature = (tuple(fmt.fontFamilies() or []),fmt.fontPointSize(),fmt.foreground().color().rgba(),
                     fmt.fontWeight(),fmt.fontItalic(),fmt.fontUnderline(),session.item.data['object_id'])
        if force or signature != self._format_signature:
            self._format_signature = signature
            self.sync_text([session.entry.style],[(fmt,session.entry.style)])

    def sync_text(self, styles, formats):
        t = self.window.editor_texto_panel
        controls = [t.cbo_font,t.table_size,t.spin_lh,t.cbo_align,t.cbo_valign,t.btn_bold,t.btn_italic,
                    t.btn_underline,t.color_hex,t.text_alpha]
        blockers = [QSignalBlocker(c) for c in controls]
        try:
            fields = {
                'family': common([(f.fontFamilies() or [s['font_family']])[0] for f,s in formats]) if formats
                          else common([s['font_family'] for s in styles]),
                'size': common([f.fontPointSize() or s['font_size'] for f,s in formats]) if formats
                        else common([s['font_size'] for s in styles]),
                'color': common([f.foreground().color().name(QColor.NameFormat.HexArgb) if f.hasProperty(
                    QTextCharFormat.Property.ForegroundBrush) else QColor(s['font_color']).name(QColor.NameFormat.HexArgb)
                    for f,s in formats]) if formats else common([s['font_color'] for s in styles]),
            }
            t.cbo_font.setCurrentFont(QFont(fields['family'])) if fields['family'] else t.cbo_font.setCurrentIndex(-1)
            t.cbo_font.setProperty('mixed',fields['family'] is None)
            if t.cbo_font.lineEdit() is not None:
                t.cbo_font.lineEdit().setPlaceholderText(tr('Vários') if fields['family'] is None else '')
            mixed_spin(t.table_size,fields['size'])
            mixed_spin(t.spin_lh,common([s['line_height'] for s in styles]))
            for combo,key,mapping in ((t.cbo_align,'align',t._align_map),(t.cbo_valign,'vertical_align',t._valign_map)):
                value = common([s[key] for s in styles]);combo.setCurrentIndex(mapping.index(value) if value else -1)
            for key in ('bold','italic','underline'):
                values = [(f.fontWeight()>=QFont.Weight.Bold if key=='bold' else f.fontItalic() if key=='italic'
                           else f.fontUnderline()) for f,s in formats] or [False]
                value = common(values);button = getattr(t,'btn_'+key)
                button.setChecked(bool(value));button.setProperty('mixed',value is None)
                button.setToolTip(tr('Vários valores') if value is None else
                    {'bold':tr('Negrito (Ctrl+B)'), 'italic':tr('Itálico (Ctrl+I)'),
                     'underline':tr('Sublinhado (Ctrl+U)')}[key])
            color = QColor(fields['color']) if fields['color'] else None
            t.color_hex.setText(color.name() if color else '')
            t.color_hex.setPlaceholderText(tr('Vários') if color is None else '#RRGGBB')
            mixed_spin(t.text_alpha,color.alphaF()*100 if color else None)
            swatch_style(t.btn_color,'background: '+(color.name() if color else '@field@')+'; border: 1px solid @border@;')
            for button in t.alignment_buttons:
                key = button.objectName().split('_',1)[-1]
                if key in ('left-align','center-align','right-align','justify'):
                    button.setChecked(t.cbo_align.currentIndex()==('left-align','center-align','right-align','justify').index(key))
                else:
                    button.setChecked(t.cbo_valign.currentIndex()==('top-alignment','mid-alignment','bot-alignment').index(key))
        finally:
            blockers.clear()
