import re

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
                               QTableWidgetItem, QApplication, QMenu, QPushButton, QSpinBox,
                               QAbstractItemView, QHeaderView, QStyle,
                               QStyleOptionHeader)
from PySide6.QtGui import QKeySequence, QFontMetrics, QAction
from PySide6.QtCore import Qt, QTimer, QRect, Signal, QSignalBlocker

from .clipboard import parse_clipboard_html_table, parse_tsv, parse_clipboard_html_fragment
from .delegates import HTMLDelegate
from .headers import is_quantity_header, is_signature_header
from core.i18n import tr


class DataHeaderView(QHeaderView):
    """Cabeçalho que torna somente o ícone da assinatura acionável."""

    signatureIconClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMouseTracking(True)
        self._pressed_signature_column = -1

    def signature_icon_rect(self, logical_index):
        model = self.model()
        if model is None or logical_index < 0:
            return QRect()
        header_item = self.parent().horizontalHeaderItem(logical_index)
        if not is_signature_header(header_item) or header_item.icon().isNull():
            return QRect()

        left = self.sectionViewportPosition(logical_index)
        width = self.sectionSize(logical_index)
        height = self.height()
        option = QStyleOptionHeader()
        self.initStyleOptionForIndex(option, logical_index)
        option.rect = QRect(left, 0, width, height)
        label_rect = self.style().subElementRect(
            QStyle.SubElement.SE_HeaderLabel, option, self
        )
        extent = self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, self)
        extent = max(12, min(extent, height - 8))
        x = label_rect.left()
        y = (height - extent) // 2
        # O SVG possui respiro transparente próprio. A tolerância horizontal
        # cobre esse espaço sem transformar o texto do título em botão.
        return QRect(x, y - 3, extent + 14, extent + 6)

    def mousePressEvent(self, event):
        logical = self.logicalIndexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton
                and self.signature_icon_rect(logical).contains(event.position().toPoint())):
            self._pressed_signature_column = logical
            event.accept()
            return
        self._pressed_signature_column = -1
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        logical = self.logicalIndexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton
                and logical == self._pressed_signature_column
                and self.signature_icon_rect(logical).contains(event.position().toPoint())):
            self._pressed_signature_column = -1
            self.signatureIconClicked.emit(logical)
            event.accept()
            return
        self._pressed_signature_column = -1
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        logical = self.logicalIndexAt(event.position().toPoint())
        cursor = (
            Qt.CursorShape.PointingHandCursor
            if self.signature_icon_rect(logical).contains(event.position().toPoint())
            else Qt.CursorShape.ArrowCursor
        )
        self.viewport().setCursor(cursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.viewport().unsetCursor()
        super().leaveEvent(event)


class RichTableWidget(QTableWidget):
    RICH_ROLE = Qt.ItemDataRole.UserRole
    signatureColumnToggled = Signal(int, bool)

    def _signature_columns(self):
        return [
            column for column in range(self.columnCount())
            if is_signature_header(self.horizontalHeaderItem(column))
        ]

    @staticmethod
    def _signature_item(state=Qt.CheckState.Checked):
        item = QTableWidgetItem("")
        item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        item.setCheckState(state)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(tr("Marque para incluir esta assinatura neste item."))
        return item

    def _initialize_functional_cells(self, row, signature_defaults=None):
        if self.columnCount() and is_quantity_header(self.horizontalHeaderItem(0).text()):
            if self.item(row, 0) is None:
                qty_item = QTableWidgetItem("1")
                qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, 0, qty_item)
        for column in self._signature_columns():
            if self.item(row, column) is not None:
                continue
            state = Qt.CheckState.Checked
            if signature_defaults and column in signature_defaults:
                state = signature_defaults[column]
            elif row > 0 and self.item(0, column):
                state = self.item(0, column).checkState()
            self.setItem(row, column, self._signature_item(state))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        header = DataHeaderView(self)
        self.setHorizontalHeader(header)
        header.signatureIconClicked.connect(self.toggle_signature_column)
        self.setItemDelegate(HTMLDelegate(self))
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._full_content_mode = False
        self._pending_height_rows = set()
        self._row_height_timer = QTimer(self)
        self._row_height_timer.setSingleShot(True)
        self._row_height_timer.setInterval(60)
        self._row_height_timer.timeout.connect(self._resize_pending_rows)
        self.itemChanged.connect(self._force_qty_alignment)
        self.itemChanged.connect(lambda item: self._queue_row_height_update({item.row()}))
        self.horizontalHeader().sectionResized.connect(self._queue_all_row_heights)
        self.model().rowsInserted.connect(
            lambda parent, first, last: self._queue_row_height_update(range(first, last + 1))
        )

    def toggle_signature_column(self, column):
        """Marca todas quando houver alguma desmarcada; senão, desmarca todas."""
        if not (0 <= column < self.columnCount()):
            return
        if not is_signature_header(self.horizontalHeaderItem(column)):
            return

        self._initialize_functional_cells_for_all_rows()
        items = [self.item(row, column) for row in range(self.rowCount())]
        if not items:
            return
        checked = not all(
            item.checkState() == Qt.CheckState.Checked for item in items
        )
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        with QSignalBlocker(self):
            for item in items:
                item.setCheckState(state)
        self.viewport().update()
        self.signatureColumnToggled.emit(column, checked)

    def _initialize_functional_cells_for_all_rows(self):
        for row in range(self.rowCount()):
            self._initialize_functional_cells(row)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_bold = QAction(tr("Negrito (Ctrl+B)"), self)
        act_bold.triggered.connect(lambda: self._toggle_format("b"))
        act_italic = QAction(tr("Itálico (Ctrl+I)"), self)
        act_italic.triggered.connect(lambda: self._toggle_format("i"))
        act_underline = QAction(tr("Sublinhado (Ctrl+U)"), self)
        act_underline.triggered.connect(lambda: self._toggle_format("u"))
        act_clear = QAction(tr("Limpar Formatação"), self)
        act_clear.triggered.connect(self._clear_formatting)

        menu.addActions([act_bold, act_italic, act_underline])
        menu.addSeparator()
        menu.addAction(act_clear)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            key = event.key()
            if key == Qt.Key.Key_B:
                self._toggle_format("b")
                return
            elif key == Qt.Key.Key_I:
                self._toggle_format("i")
                return
            elif key == Qt.Key.Key_U:
                self._toggle_format("u")
                return
        
        if event.matches(QKeySequence.StandardKey.Paste):
            self._paste_from_clipboard()
            return

        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._handle_delete()
            return

        super().keyPressEvent(event)

    def _add_rows(self, count: int):
        for _ in range(count):
            row_idx = self.rowCount()
            self.insertRow(row_idx)
            self._initialize_functional_cells(row_idx)

    def _duplicate_selected_rows(self):
        indexes = self.selectionModel().selectedIndexes()
        if not indexes: return
        
        rows_to_dup = sorted(list(set(idx.row() for idx in indexes)), reverse=True)
        cols = self.columnCount()
        
        for r in rows_to_dup:
            new_row = r + 1
            self.insertRow(new_row)
            
            for c in range(cols):
                old_item = self.item(r, c)
                if not old_item:
                    continue
                
                new_item = QTableWidgetItem(old_item.text())
                
                if is_signature_header(self.horizontalHeaderItem(c)):
                    new_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    new_item.setCheckState(old_item.checkState())
                    new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Caso especial: Coluna de Qtd ou texto comum (copia alinhamento)
                else:
                    new_item.setTextAlignment(Qt.AlignmentFlag(old_item.textAlignment()))

                # Preserva os dados Rich Text (HTML) se existirem
                rich_data = old_item.data(self.RICH_ROLE)
                if rich_data:
                    new_item.setData(self.RICH_ROLE, rich_data)
                        
                self.setItem(new_row, c, new_item)

    def _delete_selected_rows_action(self):
        # selectedIndexes pega as coordenadas visuais, mesmo se a célula estiver virgem/vazia
        indexes = self.selectionModel().selectedIndexes()
        if not indexes: return
        
        rows_to_del = sorted(list(set(idx.row() for idx in indexes)), reverse=True)
        
        for r in rows_to_del:
            self.removeRow(r)
            
        # Se a tabela ficar vazia, recria a linha inicial padrão
        if self.rowCount() == 0:
            self.insertRow(0)
            self._initialize_functional_cells(0)

    def _handle_delete(self):
        sel_rows = self.selectionModel().selectedRows()
        if sel_rows:
            rows_to_del = sorted([idx.row() for idx in sel_rows], reverse=True)
            for r in rows_to_del:
                self.removeRow(r)
            if self.rowCount() == 0:
                self.insertRow(0)
                self._initialize_functional_cells(0)
        else:
            for item in self.selectedItems():
                item.setText("")
                item.setData(self.RICH_ROLE, None)

    def _paste_from_clipboard(self):
        md = QApplication.clipboard().mimeData()
        if not md: return

        grid_struct = []
        grid_style = []

        # Chama diretamente o nosso Porteiro (router), passando HTML e Texto
        html_raw = md.html() if md.hasHtml() else ""
        text_raw = md.text() if md.hasText() else ""
        
        from .clipboard import router
        grid_struct = router(html_raw, text_raw)

        if not grid_struct: return

        header = self.horizontalHeader()
        signature_columns = set(self._signature_columns())

        # --- LÓGICA DE PREENCHIMENTO EM MASSA (1 célula copiada -> Várias selecionadas) ---
        is_single_cell = (len(grid_struct) == 1 and len(grid_struct[0]) == 1)
        selected_indexes = self.selectionModel().selectedIndexes()
        
        if is_single_cell and len(selected_indexes) > 1:
            val_plain = grid_struct[0][0].plain
            val_rich = grid_struct[0][0].rich_html
            
            affected_cols_logical = set()
            for idx in selected_indexes:
                r = idx.row()
                c_visual = idx.column()
                c_logical = header.logicalIndex(c_visual)
                
                if c_logical in signature_columns:
                    continue  # Protege a checkbox
                    
                item = self.item(r, c_logical)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(r, c_logical, item)
                    
                item.setText(val_plain)
                item.setData(self.RICH_ROLE, val_rich)
                affected_cols_logical.add(c_logical)
                
            if affected_cols_logical:
                # Autoajuste de colunas baseado nas recém alteradas
                QTimer.singleShot(0, lambda: self._autofit_columns_after_paste(
                    affected_cols_logical, 0, self.rowCount() - 1, padding_px=20
                ))
            return

        # --- LÓGICA PADRÃO DE COLAGEM (Tabela/Bloco) ---
        curr = self.currentIndex()
        if not curr.isValid():
            start_row = 0
            start_col_logical = 0
        else:
            start_row = curr.row()
            start_col_logical = curr.column()

        start_visual_col = header.visualIndex(start_col_logical)
        
        # Colunas funcionais de assinatura não recebem texto colado.
        while start_col_logical in signature_columns:
            start_visual_col += 1
            if start_visual_col >= self.columnCount():
                return
            start_col_logical = header.logicalIndex(start_visual_col)
            
        required_rows = start_row + len(grid_struct)
        if required_rows > self.rowCount():
            self.setRowCount(required_rows)

        affected_cols_logical = set()
        row_end = start_row + len(grid_struct) - 1

        for r, row_data in enumerate(grid_struct):
            dest_row = start_row + r
            self._initialize_functional_cells(dest_row)

            for c, cell_data in enumerate(row_data):
                target_visual_col = start_visual_col + c
                if target_visual_col >= self.columnCount():
                    break
                dest_col_logical = header.logicalIndex(target_visual_col)
                if dest_col_logical in signature_columns:
                    continue
                item = self.item(dest_row, dest_col_logical)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(dest_row, dest_col_logical, item)

                item.setText(cell_data.plain)
                item.setData(self.RICH_ROLE, cell_data.rich_html)

                affected_cols_logical.add(dest_col_logical)

        if affected_cols_logical:
            QTimer.singleShot(0, lambda: self._autofit_columns_after_paste(
                affected_cols_logical, start_row, row_end, padding_px=20
            ))

    def _toggle_word_wrap(self, state: bool):
        self._full_content_mode = bool(state)
        self.setWordWrap(state)
        if state:
            self.setTextElideMode(Qt.TextElideMode.ElideNone)
            self._queue_all_row_heights()
        else:
            self._row_height_timer.stop()
            self._pending_height_rows.clear()
            self.setTextElideMode(Qt.TextElideMode.ElideRight)
            for r in range(self.rowCount()):
                self.setRowHeight(r, 25)

    def _queue_row_height_update(self, rows):
        if not self._full_content_mode:
            return
        self._pending_height_rows.update(
            row for row in rows if 0 <= row < self.rowCount()
        )
        self._row_height_timer.start()

    def _queue_all_row_heights(self, *_):
        self._queue_row_height_update(range(self.rowCount()))

    def _resize_pending_rows(self):
        if not self._full_content_mode:
            return
        rows = sorted(self._pending_height_rows)
        self._pending_height_rows.clear()
        for row in rows:
            if row >= self.rowCount():
                continue
            needs_expansion = False
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if not item:
                    continue
                text = item.text()
                available = max(1, self.columnWidth(column) - 20)
                if '\n' in text or self.fontMetrics().horizontalAdvance(text) > available:
                    needs_expansion = True
                    break
            if not needs_expansion:
                self.setRowHeight(row, 25)
                continue
            self.resizeRowToContents(row)
            self.setRowHeight(row, max(25, self.rowHeight(row) + 8))

    def _toggle_format(self, tag: str):
        items = self.selectedItems()
        if not items: return

        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"

        for item in items:
            current_html = item.data(self.RICH_ROLE)
            if not current_html:
                current_html = item.text()

            check = current_html.strip()
            if check.startswith(start_tag) and check.endswith(end_tag):
                new_html = check[len(start_tag):-len(end_tag)]
            else:
                new_html = f"{start_tag}{check}{end_tag}"

            item.setData(self.RICH_ROLE, new_html)
        self.viewport().update()

    def _clear_formatting(self):
        for item in self.selectedItems():
            text = item.text()
            item.setData(self.RICH_ROLE, None)
            item.setText(text)

    def _force_qty_alignment(self, item):
        # Se a mudança foi na coluna 0, bloqueia sinais para evitar loop e centraliza
        if item.column() == 0:
            self.blockSignals(True)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.blockSignals(False)    

    def _text_width_px(self, text: str) -> int:
        fm = QFontMetrics(self.font())
        lines = (text or "").splitlines() or [""]
        return max(fm.horizontalAdvance(line) for line in lines)

    def _autofit_columns_after_paste(self, cols_logical: set[int], row_start: int, row_end: int, padding_px: int = 20):
        header = self.horizontalHeader()
        for col in cols_logical:
            header_item = self.horizontalHeaderItem(col)
            best = self._text_width_px(header_item.text() if header_item else "")
            for r in range(row_start, row_end + 1):
                it = self.item(r, col)
                if it is None: continue
                w = self._text_width_px(it.text())
                if w > best: best = w
            desired = best + padding_px
            if desired > self.columnWidth(col):
                self.setColumnWidth(col, desired)
                    

class TablePanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Controles lógicos e visuais usados diretamente pelo frontend atual.
        self.spin_add_rows = QSpinBox()
        self.spin_add_rows.setRange(1, 500)
        self.btn_add_rows = QPushButton()
        self.btn_duplicate_row = QPushButton()
        self.btn_delete_rows = QPushButton()
        self.btn_toggle_wrap = QPushButton()
        self.btn_toggle_wrap.setCheckable(True)
        self.table = RichTableWidget(0, 0)
        self.table.horizontalHeader().setSectionsMovable(True)

        self.btn_add_rows.clicked.connect(
            lambda: self.table._add_rows(self.spin_add_rows.value())
        )
        self.btn_duplicate_row.clicked.connect(self.table._duplicate_selected_rows)
        self.btn_delete_rows.clicked.connect(self.table._delete_selected_rows_action)
        self.btn_toggle_wrap.toggled.connect(self.table._toggle_word_wrap)

        from .frontend import install_frontend
        install_frontend(self)
