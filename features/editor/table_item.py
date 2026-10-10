"""Um item de cena por tabela; seleção/cursor não pertencem ao documento."""
from copy import deepcopy

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from core.table_model import validate_table, cell_at, table_fields, effective_cell_style, resize_table
from core.table_layout import TableLayout, build_cell_document
from core.table_paint import paint_table_local
from core.themes import theme_color
from .canvas_items import (_snap_board_position, _invalidate_board_text_cutouts,
    _queue_selection_frame_refresh, _init_resize_handles, _update_resize_handles,
    _set_resize_handles_visible, _invalidate_resize_handle_areas)


class TableItem(QGraphicsRectItem):
    """Layout retido na thread da UI; apenas uma célula ganha editor temporário."""
    def __init__(self, data, window):
        validate_table(data)
        self.data = deepcopy(data)
        self.window = window
        self.layout = TableLayout(self.data)
        self.presentation_revision = 0
        self.selected_range = None
        self.selection_anchor = None
        self.selection_cursor = None
        self.editing_cell = None
        self._selecting_cells = False
        self._is_mouse_dragging = False
        self._pending_cell = None
        self._overlays_enabled = True
        super().__init__(0, 0, self.layout.width, self.layout.height)
        self.custom_name = data['custom_name']
        self.layer_id = data.get('layer_id')
        self.group_id = data.get('group_id')
        self.keep_proportion = data.get('keep_proportion', True)
        self.board_behind = data.get('board_behind', False)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(data.get('x', 0), data.get('y', 0))
        self.setTransformOriginPoint(self.rect().center())
        self.setRotation(data.get('rotation', 0))
        self.setZValue(data.get('z_value', 101))
        self.setOpacity(data.get('opacity', 1))
        self.setVisible(data.get('visible', True))
        if data.get('locked', False):
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        _init_resize_handles(self)

    @property
    def overlays_enabled(self):
        return self._overlays_enabled

    @overlays_enabled.setter
    def overlays_enabled(self, enabled):
        self._overlays_enabled = bool(enabled)
        _set_resize_handles_visible(self, enabled and self.isSelected() and bool(
            self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable))

    def boundingRect(self):
        width = max([self.data['border']['width'], *(e['style'].get('width', self.data['border']['width'])
                                                    for e in self.data['edges'])])
        margin = max(12, width / 2)
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        exposed = option.exposedRect
        if exposed.contains(self.rect()):
            exposed = None  # Pintura completa não precisa testar cada célula.
        paint_table_local(painter, self.layout, editing_cell=self.editing_cell,
                          exposed_rect=exposed)
        if not self.overlays_enabled:
            return
        painter.save()
        try:
            pen = QPen(QColor(theme_color('accent')), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self.isSelected():
                painter.drawRect(self.rect().adjusted(-8, -8, 8, 8))
            if self.selected_range is not None:
                top,left,bottom,right = self.selected_range
                selection = QRectF(self.layout.x[left], self.layout.y[top],
                    self.layout.x[right+1]-self.layout.x[left], self.layout.y[bottom+1]-self.layout.y[top])
                highlight = QColor(theme_color('canvas_selection'))
                highlight.setAlpha(38)
                painter.fillRect(selection, highlight)
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setWidthF(2)
                pen.setColor(QColor(theme_color('canvas_selection')))
                painter.setPen(pen)
                painter.drawRect(selection)
            pen.setColor(QColor('#c64646'))
            pen.setWidthF(1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for entry in self.layout.cells:
                if entry.overflow_x or entry.overflow_y:
                    painter.drawRect(entry.rect.adjusted(2, 2, -2, -2))
        finally:
            painter.restore()

    def select_cell(self, row, column, *, extend=False, notify=True):
        cell = cell_at(self.data, row, column)
        anchor = (cell['row'], cell['column'])
        self.selection_cursor = anchor
        if not extend or self.selection_anchor is None:
            self.selection_anchor = anchor
        start = cell_at(self.data, *self.selection_anchor)
        top,left = min(start['row'],cell['row']),min(start['column'],cell['column'])
        bottom = max(start['row']+start['row_span']-1,cell['row']+cell['row_span']-1)
        right = max(start['column']+start['column_span']-1,cell['column']+cell['column_span']-1)
        # Expandir até incluir por inteiro qualquer mesclagem interceptada.
        while True:
            previous = top,left,bottom,right
            for entry in self.data['cells']:
                r,c,rs,cs = (entry[k] for k in ('row','column','row_span','column_span'))
                if r <= bottom and r+rs-1 >= top and c <= right and c+cs-1 >= left:
                    top,left,bottom,right = min(top,r),min(left,c),max(bottom,r+rs-1),max(right,c+cs-1)
            if previous == (top,left,bottom,right):
                break
        self.selected_range = top,left,bottom,right
        self.setSelected(True)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.update()
        controller = getattr(self.window, 'table_controller', None)
        if controller and notify:
            controller.refresh()

    def clear_cell_selection(self):
        self.selected_range = self.selection_anchor = self.selection_cursor = None
        self._selecting_cells = False
        self.update()
        controller = getattr(self.window, 'table_controller', None)
        if controller:
            controller.refresh()

    def mousePressEvent(self, event):
        hit = self.layout.hit(event.pos())
        scene = self.scene()
        selected = scene.selectedItems() if scene else []
        cell_context = (selected == [self] and self.isSelected()
                        and not event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._pending_cell = None
        if (cell_context and hit is not None and event.button() == Qt.MouseButton.LeftButton
                and (self.selected_range is not None
                     or event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.window.table_edit.finish()
            self.window.canvas_edit.finish()
            self.select_cell(*hit, extend=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self._selecting_cells = True
            event.accept()
            return
        self.window.table_edit.finish()
        self.clear_cell_selection()
        if cell_context and hit is not None and event.button() == Qt.MouseButton.LeftButton:
            # Um clique escolhe a célula; um arraste continua movendo o objeto.
            self._pending_cell = hit
        self._drag_start = self.pos()
        self._is_mouse_dragging = event.button() == Qt.MouseButton.LeftButton
        super().mousePressEvent(event)
        if self._is_mouse_dragging and scene:
            drag_items = selected if self in selected else scene.selectedItems()
            scene._drag_start_positions = {item: item.pos() for item in drag_items}
            scene._group_raw_delta = scene._board_drag_anchor = None

    def mouseMoveEvent(self, event):
        if self._selecting_cells:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self._selecting_cells = False
                event.accept()
                return
            point = event.pos()
            point.setX(min(max(0, point.x()), self.layout.width-0.001))
            point.setY(min(max(0, point.y()), self.layout.height-0.001))
            self.select_cell(*self.layout.hit(point), extend=True)
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self.pos() != getattr(self, '_drag_start', self.pos()):
            self._pending_cell = None

    def mouseReleaseEvent(self, event):
        if self._selecting_cells:
            self._selecting_cells = False
            event.accept()
            return
        self._is_mouse_dragging = False
        super().mouseReleaseEvent(event)
        moved = getattr(self, '_drag_start', self.pos()) != self.pos()
        pending, self._pending_cell = self._pending_cell, None
        if moved:
            self.window.save_snapshot()
        elif (pending is not None and self.scene().selectedItems() == [self]
              and not getattr(self.window, '_finishing_canvas_pointer', False)):
            self.select_cell(*pending)
        if self.scene():
            self.scene()._group_raw_delta = self.scene()._board_drag_anchor = None

    def mouseDoubleClickEvent(self, event):
        hit = self.layout.hit(event.pos())
        if hit is not None:
            self._pending_cell = None
            self._is_mouse_dragging = False
            self._selecting_cells = False
            self.select_cell(*hit)
            self.window.table_edit.begin(self, hit, position=event.pos())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            _invalidate_resize_handle_areas(self)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            if getattr(self.scene(), '_board_grid', 0) and self._is_mouse_dragging:
                value = _snap_board_position(self, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if not value:
                self._pending_cell = None
                self.clear_cell_selection()
            _set_resize_handles_visible(self, self.overlays_enabled and self.isSelected() and bool(
                self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable))
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemScaleHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemTransformOriginPointHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemOpacityHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemParentHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemSceneChange,
                      QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged):
            _invalidate_board_text_cutouts(self)
            _queue_selection_frame_refresh(self)
        return super().itemChange(change, value)

    def hide_resize_handles(self):
        _set_resize_handles_visible(self, False)

    def begin_resize_from_handle(self):
        self.window.table_edit.finish()
        self.clear_cell_selection()

    def resize_from_handle(self, width, height):
        if not self.resize_custom(width, height):
            return False
        self.window.caixa_texto_panel.load_from_image(self)
        return True

    def resize_custom(self, width, height):
        """Valida medidas/conteúdo antes de encerrar a célula ou publicar."""
        try:
            candidate = resize_table(self.to_data(), width, height)
            self.window.table_controller.preflight(self, candidate)
        except ValueError as error:
            self.window.table_controller.error(error)
            self.window.caixa_texto_panel.load_from_image(self)
            return False
        self.window.table_edit.finish()
        self.publish_table_data(candidate)
        self.window.table_panel.message.clear()
        self.window.table_controller.refresh()
        return True

    def get_placeholders(self):
        return table_fields(self.to_data())

    def to_data(self):
        result = deepcopy(self.data)
        session = getattr(self.window, 'table_edit', None)
        if session and session.item is self and session.dirty:
            cell_at(result, *session.anchor)['html'] = session.accepted_html
        result.update(custom_name=self.custom_name, layer_id=self.layer_id, group_id=self.group_id,
            x=self.x(), y=self.y(), rotation=self.rotation(), z_value=self.zValue(),
            opacity=self.opacity(), visible=self.isVisible(), board_behind=self.board_behind,
            locked=not bool(self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
            keep_proportion=self.keep_proportion)
        return result

    def publish_cell_html(self, anchor, html):
        self.publish_cells_html({anchor: html})

    def publish_cells_html(self, changes):
        candidate = deepcopy(self.data)
        for anchor,html in changes.items():
            cell_at(candidate, *anchor)['html'] = html
        self.publish_table_data(candidate)

    def publish_table_data(self, candidate):
        """Mantém o item e os documentos não afetados; estrutura recria só a tabela."""
        validate_table(candidate)  # Publicação atômica; não por tecla.
        self.presentation_revision += 1
        same_grid = all(candidate.get(key) == self.data.get(key) for key in
                        ('rows', 'columns', 'column_widths', 'row_heights'))
        topology = lambda table: sorted((c['row'],c['column'],c['row_span'],c['column_span'])
                                       for c in table['cells'])
        if not same_grid or topology(candidate) != topology(self.data):
            layout = TableLayout(candidate)  # Construir antes de publicar.
            self.prepareGeometryChange()
            self.data, self.layout = deepcopy(candidate), layout
            self.setRect(0, 0, layout.width, layout.height)
            self.setTransformOriginPoint(self.rect().center())
            _update_resize_handles(self)
            _queue_selection_frame_refresh(self)
            self.update()
            _invalidate_board_text_cutouts(self)
            return
        edges_changed = candidate['border'] != self.data['border'] or candidate['edges'] != self.data['edges']
        if edges_changed:
            self.prepareGeometryChange()
        self.data = deepcopy(candidate)
        self.layout.table = deepcopy(candidate)
        self.layout.edge_styles = {(e['orientation'],e['row'],e['column']):
                                   {**candidate['border'],**e['style']} for e in candidate['edges']}
        if edges_changed:
            self.layout.refresh_edges()
        cells = {(cell['row'],cell['column']): cell for cell in self.layout.table['cells']}
        entries = {(entry.cell['row'],entry.cell['column']): entry for entry in self.layout.cells}
        # A ordem de pintura também deve coincidir com a do renderer após colagem.
        self.layout.cells = [entries[c['row'],c['column']] for c in self.layout.table['cells']]
        affected = QRectF()
        for entry in self.layout.cells:
            anchor = entry.cell['row'],entry.cell['column']
            cell = cells[anchor]
            style = effective_cell_style(candidate, cell)
            if not edges_changed and entry.cell == cell and entry.style == style:
                continue
            rebuild = (entry.cell['html'] != cell['html'] or
                       any(entry.style[k] != style[k] for k in style
                           if k not in ('fill_color','fill_opacity','padding','vertical_align')))
            old_inner,old_valign = QRectF(entry.inner),entry.style['vertical_align']
            old_padding = entry.style['padding']
            entry.cell, entry.style = cell, style
            if rebuild or edges_changed or old_padding != style['padding']:
                r,c,rs,cs = (cell[k] for k in ('row','column','row_span','column_span'))
                def inset(keys):
                    strokes = [self.layout.edge_style(key)['width']/2 for key in keys
                               if self.layout.edge_style(key)['visible']]
                    return style['padding']+max(strokes,default=0)
                entry.inner = entry.rect.adjusted(
                    inset(('v',y,c) for y in range(r,r+rs)),
                    inset(('h',r,x) for x in range(c,c+cs)),
                    -inset(('v',y,c+cs) for y in range(r,r+rs)),
                    -inset(('h',r+rs,x) for x in range(c,c+cs)))
            if rebuild:
                entry.document = build_cell_document(cell, style, self.layout.device, entry.inner.width())
            elif old_inner != entry.inner:
                entry.document.setTextWidth(entry.inner.width())
            if rebuild or old_inner != entry.inner or old_valign != style['vertical_align']:
                self._update_cell_metrics(entry)
            affected = affected.united(entry.rect)
        self.layout.warnings = [dict(table_id=self.data['object_id'],table_name=self.custom_name,
            cell_id=e.cell['id'],row=e.cell['row']+1,column=e.cell['column']+1,
            overflow_x=e.overflow_x,overflow_y=e.overflow_y)
            for e in self.layout.cells if (e.overflow_x or e.overflow_y) and e.document.toPlainText().strip()]
        self.update(self.rect() if edges_changed else affected)
        _invalidate_board_text_cutouts(self)

    @staticmethod
    def _update_cell_metrics(entry):
        native = entry.document.documentLayout()
        entry.text_height = native.documentSize().height()
        entry.offset_y = max(0,entry.inner.height()-entry.text_height)*{'top':0,'center':.5,'bottom':1}[entry.style['vertical_align']]
        lines = []
        block = entry.document.begin()
        while block.isValid():
            rectangle = native.blockBoundingRect(block)
            for index in range(block.layout().lineCount()):
                line = block.layout().lineAt(index)
                lines.append((block.position()+line.textStart(),line.textLength(),line.naturalTextRect().x(),
                    rectangle.y()+line.y(),line.naturalTextWidth(),line.height()))
            block = block.next()
        entry.lines = tuple(lines)
        entry.overflow_x = any(line[4] > entry.inner.width()+.01 for line in lines)
        entry.overflow_y = entry.text_height > entry.inner.height()+.01
