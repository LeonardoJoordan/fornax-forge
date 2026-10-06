"""Ferramentas de quadro integradas ao editor existente."""
from copy import deepcopy
from pathlib import Path
import math
import json
import re
from uuid import uuid4

from PySide6.QtCore import Qt, QPointF, QTimer, QRectF, QSignalBlocker
from PySide6.QtGui import QColor, QPen, QPainterPath, QBrush, QPainter, QPixmap, QShortcut, QPainterPathStroker, QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QPushButton, QSpinBox,
    QDoubleSpinBox, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem,
    QDialog, QDialogButtonBox, QMessageBox, QGraphicsItem, QGraphicsRectItem,
    QGraphicsPathItem, QMenu, QGraphicsView, QColorDialog, QGroupBox, QCheckBox, QGridLayout, QHBoxLayout,
    QStyleOptionGraphicsItem, QStyle,
)
from core.i18n import tr
from core.organogram import (
    UNITS_PER_MM, add_organogram, new_group, group_rect, board_bounds,
    validate_organogram, block_name_key, validate_block_name,
)
from core.board_connectors import (connector_style, connector_pen, connector_paths, connector_clip,
                                   MAX_CURVE_RADIUS_MM, validate_connector_style)
from core.board_routing import board_routes, SIDES
from core.model_document import adapt_model_page, ModelValidationError
from core.dialog_buttons import style_dialog_button_box
from core.resources import object_icon_path, navigation_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import theme_color
from .canvas_items import _snap_board_position, _board_snap_step


class BoardGraphicsView(QGraphicsView):
    def __init__(self, *args):
        super().__init__(*args)
        self._pointer_buttons = Qt.MouseButton.NoButton
        self._pointer_position = QPointF()
        self._pointer_generation = 0
        self._connector_rubber_band = False
        self._initial_connector_selection = set()
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        self._pointer_generation += 1
        self._pointer_buttons |= event.button()
        self._pointer_position = event.position()
        self._initial_connector_selection = {
            item for item in self.scene().selectedItems() if isinstance(item, BoardConnectorItem)
        }
        super().mousePressEvent(event)
        self._connector_rubber_band = (
            event.button() == Qt.MouseButton.LeftButton
            and self.dragMode() == QGraphicsView.DragMode.RubberBandDrag
            and self.scene().mouseGrabberItem() is None
            and bool(getattr(self.scene(), '_board_grid', 0))
        )

    def mouseDoubleClickEvent(self, event):
        self._pointer_generation += 1
        self._pointer_buttons |= event.button()
        self._pointer_position = event.position()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        self._pointer_position = event.position()
        if not self._connector_rubber_band:
            super().mouseMoveEvent(event)
            return
        scene = self.scene()
        before = set(scene.selectedItems())
        with QSignalBlocker(scene):
            super().mouseMoveEvent(event)
            rect = self.rubberBandRect()
            if not rect.isEmpty():
                area = QPainterPath()
                area.addPolygon(self.mapToScene(rect))
                area.closeSubpath()
                add = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                for item in scene.items():
                    if isinstance(item, BoardConnectorItem) and item.isVisible():
                        crossed = area.intersects(item.mapToScene(item.shape()))
                        item.setSelected(crossed or (add and item in self._initial_connector_selection))
        if set(scene.selectedItems()) != before:
            scene.selectionChanged.emit()

    def mouseReleaseEvent(self, event):
        self._pointer_buttons &= ~event.button()
        self._pointer_position = event.position()
        super().mouseReleaseEvent(event)
        self._connector_rubber_band = False
        self._initial_connector_selection.clear()

    def release_pointer(self):
        """Encerra também o arraste interno do Qt quando a soltura se perde."""
        buttons = self._pointer_buttons
        self._pointer_buttons = Qt.MouseButton.NoButton
        self._connector_rubber_band = False
        self._initial_connector_selection.clear()
        position = self._pointer_position
        global_position = QPointF(self.viewport().mapToGlobal(position.toPoint()))
        # Chamar a implementação da view evita recursão nos filtros e entrega
        # a soltura às alças/itens, preservando o histórico da edição concluída.
        for button in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton,
                       Qt.MouseButton.MiddleButton):
            if buttons & button:
                buttons &= ~button
                release = QMouseEvent(
                    QMouseEvent.Type.MouseButtonRelease, position, global_position,
                    button, buttons, Qt.KeyboardModifier.NoModifier,
                )
                super().mouseReleaseEvent(release)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        grid = getattr(self.scene(), "_board_grid", 0)
        if not grid:
            return
        # A grade visual reduz a densidade ao afastar; o encaixe continua em 5 mm.
        zoom = max(0.001, abs(self.transform().m11()))
        grid *= max(1, math.ceil(12 / (grid * zoom)))
        color = QColor(theme_color("border_strong"))
        color.setAlpha(65)
        pen = QPen(color, 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for index in range(math.floor(rect.left() / grid), math.ceil(rect.right() / grid) + 1):
            painter.drawLine(QPointF(index * grid, rect.top()), QPointF(index * grid, rect.bottom()))
        for index in range(math.floor(rect.top() / grid), math.ceil(rect.bottom() / grid) + 1):
            painter.drawLine(QPointF(rect.left(), index * grid), QPointF(rect.right(), index * grid))


class BoardGroupItem(QGraphicsRectItem):
    """Um conjunto é um item; os cartões são pintados sem duplicar o modelo."""
    def __init__(self, window, data, preview):
        self.window = window
        self.data = deepcopy(data)
        self.preview = preview
        rect = group_rect(data)
        super().__init__(0, 0, rect.width(), rect.height())
        self.setPos(data["x"], data["y"])
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(-10)
        window._board_item_refs[id(self)] = self

    def itemChange(self, change, value):
        if self.scene() and change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            grid = getattr(self.scene(), "_board_grid", 0)
            if grid:
                return _snap_board_position(self, value)
        if self.scene() and change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data.update(x=self.pos().x(), y=self.pos().y())
            self.window._update_board_connections()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for index in range(self.data["columns"] * self.data["rows"]):
            x = index % self.data["columns"] * (self.data["card_w"] + self.data["gap_x"])
            y = index // self.data["columns"] * (self.data["card_h"] + self.data["gap_y"])
            rect = QRectF(x, y, self.data["card_w"], self.data["card_h"])
            painter.drawImage(rect, self.preview)
            pen = QPen(QColor(theme_color("border_strong")), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(rect)
        if self.isSelected():
            pen = QPen(QColor(theme_color("accent")), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(self.rect())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = True
            self.scene()._drag_start_positions = {item: item.pos() for item in self.scene().selectedItems()}
            self.scene()._board_drag_anchor = None

    def mouseReleaseEvent(self, event):
        self._is_mouse_dragging = False
        self.scene()._board_drag_anchor = None
        super().mouseReleaseEvent(event)
        self.window._update_board_extent()
        self.window.save_snapshot()

    def mouseDoubleClickEvent(self, event):
        self.window.edit_board_group(self)
        event.accept()


class BoardConnectorItem(QGraphicsPathItem):
    def __init__(self, window, edge):
        super().__init__()
        self.window = window
        self.board_edge = deepcopy(edge)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(-20)
        window._board_item_refs[id(self)] = self

    def cutouts(self):
        from .canvas_items import DesignerBox
        cutouts = QPainterPath()
        cutouts.setFillRule(Qt.FillRule.WindingFill)
        for item in self.scene().items():
            if isinstance(item, DesignerBox) and item.isVisible() and item.opacity() > 0:
                rectangle = QPainterPath()
                rectangle.addPolygon(item.mapToScene(item.rect()))
                rectangle.closeSubpath()
                cutouts.addPath(rectangle)
        return cutouts

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 12))
        shape = stroker.createStroke(self.path())
        return shape.subtracted(self.cutouts()) if self.scene() else shape

    def boundingRect(self):
        # Inclui a tolerância de clique e o realce da seleção no índice da cena.
        return super().boundingRect().adjusted(-6, -6, 6, 6)

    def paint(self, painter, option, widget=None):
        painter.save()
        try:
            painter.setClipPath(connector_clip(self.boundingRect().adjusted(-12, -12, 12, 12), self.cutouts()), Qt.ClipOperation.IntersectClip)
            if self.isSelected():
                highlight = QPen(QColor(theme_color('accent')), max(self.pen().widthF() + 6, 12))
                highlight.setCapStyle(Qt.PenCapStyle.RoundCap)
                highlight.setJoinStyle(self.pen().joinStyle())
                painter.setPen(highlight)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self.path())
            clean_option = QStyleOptionGraphicsItem(option)
            clean_option.state &= ~QStyle.StateFlag.State_Selected
            super().paint(painter, clean_option, widget)
        finally:
            painter.restore()


class StructureTree(QTreeWidget):
    MIME_TYPE = "application/x-fornax-board-blocks"

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setHeaderHidden(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._drop_pending = False

    def startDrag(self, supported_actions):
        if getattr(self.window, "_board_connection_sources", None):
            return
        indexes = self.selectedIndexes()
        if not indexes:
            return
        mime = self.model().mimeData(indexes)
        identifiers = [item.data(0, Qt.ItemDataRole.UserRole) for item in self.selectedItems()]
        mime.setData(self.MIME_TYPE, json.dumps(identifiers).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # QAbstractItemView.startDrag removeria linhas após um MoveAction customizado.
        # O modelo é alterado somente pela operação de hierarquia enfileirada abaixo.
        drag.exec(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if getattr(self.window, "_board_connection_sources", None) or event.source() is not self:
            event.ignore()
            return
        # Capture IDs, nunca mantenha itens Qt vivos atravessando a reconstrução.
        try:
            sources = json.loads(bytes(event.mimeData().data(self.MIME_TYPE)))
        except (ValueError, TypeError):
            event.ignore()
            return
        if not isinstance(sources, list) or not all(isinstance(value, str) for value in sources):
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        parent_id = target.data(0, Qt.ItemDataRole.UserRole) if target else None
        self._drop_pending = True
        def apply_drop():
            self._drop_pending = False
            self.window.set_board_parents(sources, parent_id)
        # O Qt deve terminar o evento antes que a hierarquia mude.
        QTimer.singleShot(0, self, apply_drop)
        event.accept()


class ConnectorSides(QGroupBox):
    """Quatro permissões espaciais em torno de uma representação do bloco."""
    def __init__(self, title, window, key):
        super().__init__(title)
        self.key = key
        grid = QGridLayout(self)
        grid.setContentsMargins(6, 12, 6, 6)
        grid.setSpacing(4)
        block = QLabel(tr("Bloco"))
        block.setAlignment(Qt.AlignmentFlag.AlignCenter)
        block.setFixedSize(48, 34)
        block.setStyleSheet(f'border: 1px solid {theme_color("border_strong")}; border-radius: 3px;')
        grid.addWidget(block, 1, 1)
        self.checks = {}
        for side, label, row, column in (("top", tr("Cima"), 0, 1), ("left", tr("Esquerda"), 1, 0),
                                         ("right", tr("Direita"), 1, 2), ("bottom", tr("Baixo"), 2, 1)):
            checkbox = QCheckBox()
            checkbox.setFixedSize(22, 22)
            checkbox.setAccessibleName(f"{title}: {label}")
            checkbox.setToolTip(tr("Permitir por {lado}. Mantenha pelo menos um lado marcado.").format(lado=label.lower()))
            checkbox.clicked.connect(lambda _checked, side=side, checkbox=checkbox:
                                       window.change_board_ports(key, side, checkbox.checkState() == Qt.CheckState.Checked))
            grid.addWidget(checkbox, row, column, Qt.AlignmentFlag.AlignCenter)
            self.checks[side] = checkbox

    def refresh(self, groups):
        self.setEnabled(bool(groups))
        default = ["bottom"] if self.key == "entry_sides" else ["top"]
        for side, checkbox in self.checks.items():
            states = [side in group.get(self.key, default) for group in groups]
            mixed = bool(states) and any(states) and not all(states)
            with QSignalBlocker(checkbox):
                checkbox.setTristate(mixed)
                checkbox.setCheckState(Qt.CheckState.PartiallyChecked if mixed else
                                       Qt.CheckState.Checked if states and all(states) else Qt.CheckState.Unchecked)


class OrganogramPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._syncing = False
        self._tree_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.size_label = QLabel()
        self.size_label.setWordWrap(True)
        layout.addWidget(self.size_label)
        self.tree = StructureTree(window)
        self.tree.setMinimumHeight(150)
        self.tree.setMaximumHeight(260)
        layout.addWidget(self.tree)
        self.tree.itemSelectionChanged.connect(self.select_from_tree)
        self.tree.itemDoubleClicked.connect(lambda *_: QTimer.singleShot(0, self, window.edit_board_group))
        self.tree.itemClicked.connect(self.click_tree_item)
        self.connect_button = QPushButton(tr("Conectar a elemento"))
        self.connect_button.clicked.connect(window.start_board_connection)
        layout.addWidget(self.connect_button)
        self.connection_hint = QLabel()
        self.connection_hint.setWordWrap(True)
        layout.addWidget(self.connection_hint)
        form = QFormLayout()
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, 1000)
        self.margin.setSuffix(" mm")
        self.margin.setKeyboardTracking(False)
        self.margin.valueChanged.connect(self.change_margin)
        form.addRow(tr("Margem de saída"), self.margin)
        self.parent_combo = QComboBox()
        self.parent_combo.activated.connect(self.change_parent)
        form.addRow(tr("Superior"), self.parent_combo)
        layout.addLayout(form)
        self.edit = QPushButton(tr("Editar bloco selecionado"))
        self.edit.clicked.connect(lambda: window.edit_board_group())
        layout.addWidget(self.edit)
        ports = QGroupBox(tr("Lados permitidos do bloco"))
        port_layout = QHBoxLayout(ports)
        port_layout.setContentsMargins(6, 8, 6, 6)
        self.entry_sides = ConnectorSides(tr("Entrada"), window, "entry_sides")
        self.exit_sides = ConnectorSides(tr("Saída"), window, "exit_sides")
        port_layout.addWidget(self.entry_sides)
        port_layout.addWidget(self.exit_sides)
        layout.addWidget(ports)
        self.routing_hint = QLabel()
        self.routing_hint.setWordWrap(True)
        layout.addWidget(self.routing_hint)
        appearance = QGroupBox(tr("Conectores"))
        style_form = QFormLayout(appearance)
        self.style_target = QLabel()
        self.style_target.setWordWrap(True)
        style_form.addRow(self.style_target)
        self.color = QPushButton()
        self.color.clicked.connect(self.choose_color)
        style_form.addRow(tr("Cor"), self.color)
        self.width = QDoubleSpinBox()
        self.width.setRange(0.05, 20)
        self.width.setDecimals(2)
        self.width.setSingleStep(0.1)
        self.width.setSuffix(" mm")
        self.width.setKeyboardTracking(False)
        self.width.valueChanged.connect(lambda value: window.change_board_connector_style(width_mm=value))
        style_form.addRow(tr("Espessura"), self.width)
        self.transparency = QSpinBox()
        self.transparency.setRange(0, 100)
        self.transparency.setSuffix(" %")
        self.transparency.setKeyboardTracking(False)
        self.transparency.valueChanged.connect(lambda value: window.change_board_connector_style(opacity=1 - value / 100))
        style_form.addRow(tr("Transparência"), self.transparency)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0, MAX_CURVE_RADIUS_MM)
        self.radius.setDecimals(2)
        self.radius.setSingleStep(0.5)
        self.radius.setSuffix(" mm")
        self.radius.setKeyboardTracking(False)
        self.radius.setToolTip(tr("0 mantém as quinas retas. O raio é limitado pelo comprimento dos trechos e pelo espaço entre os blocos."))
        self.radius.valueChanged.connect(lambda value: window.change_board_connector_style(radius_mm=value))
        style_form.addRow(tr("Raio de curva"), self.radius)
        layout.addWidget(appearance)
        hint = QLabel(tr("Arraste na árvore para mudar o superior. O centro dos blocos encaixa em 5 mm e o dos textos em 2,5 mm. Posições sem dados aparecem apenas na edição."))
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def select_from_tree(self):
        if self._syncing or getattr(self.window, "_board_connection_sources", None):
            return
        identifiers = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()}
        self._syncing = True
        try:
            with QSignalBlocker(self.window.scene):
                self.window.scene.clearSelection()
                for item in self.window._board_items():
                    item.setSelected(item.data["id"] in identifiers)
            self.window.on_selection_changed()
        finally:
            self._syncing = False

    def click_tree_item(self, item, column):
        if getattr(self.window, "_board_connection_sources", None):
            identifier = item.data(0, Qt.ItemDataRole.UserRole)
            QTimer.singleShot(0, self, lambda: self.window._connect_to_board_target(identifier))

    def choose_color(self):
        initial = self.window._board_style_for_selection()["color"]
        color = QColorDialog.getColor(QColor(initial), self, tr("Cor do conector"))
        if color.isValid():
            self.window.change_board_connector_style(color=color.name())

    def change_parent(self, index):
        selected = self.window._selected_board_group()
        if selected:
            self.window.set_board_parent(selected.data["id"], self.parent_combo.itemData(index))

    def change_margin(self, value):
        if self.window._active_page_id == "organogram":
            self.window._board_margin_mm = value
            self.window._update_board_extent()
            self.window.save_snapshot()

    def refresh(self):
        window = self.window
        if window._active_page_id != "organogram" or getattr(window, "_loading_board", False):
            return
        groups = [item.data for item in window._board_items()]
        selected = window._selected_board_group()
        selected_ids = {item.data["id"] for item in window.scene.selectedItems() if isinstance(item, BoardGroupItem)}
        selected_id = selected.data["id"] if len(selected_ids) == 1 else None
        parents = {edge["target"]: edge["source"] for edge in window._board_connections_data()}
        signature = tuple((g["id"], g["name"], g["columns"], g["rows"], g["start_row"], parents.get(g["id"])) for g in groups)
        with QSignalBlocker(self.tree):
            if signature != self._tree_signature and not self.tree._drop_pending:
                self.tree.clear()
                self._nodes = {}
                for group in groups:
                    node = QTreeWidgetItem([f'{group["name"]} · {group["columns"]} × {group["rows"]}'])
                    node.setData(0, Qt.ItemDataRole.UserRole, group["id"])
                    node.setToolTip(0, tr("Linha inicial: {linha}").format(linha=group["start_row"] + 1))
                    self._nodes[group["id"]] = node
                for group in groups:
                    node = self._nodes[group["id"]]
                    parent = self._nodes.get(parents.get(group["id"]))
                    if parent:
                        parent.addChild(node)
                    else:
                        self.tree.addTopLevelItem(node)
                self.tree.expandAll()
                self._tree_signature = signature
            for identifier, node in getattr(self, "_nodes", {}).items():
                node.setSelected(identifier in selected_ids)
        self.parent_combo.blockSignals(True)
        self.parent_combo.clear()
        self.parent_combo.addItem(tr("Sem superior"), None)
        for group in groups:
            if group["id"] != selected_id:
                self.parent_combo.addItem(group["name"], group["id"])
        self.parent_combo.setCurrentIndex(max(0, self.parent_combo.findData(parents.get(selected_id))))
        self.parent_combo.blockSignals(False)
        connecting = bool(getattr(window, "_board_connection_sources", None))
        self.parent_combo.setEnabled(selected_id is not None and not connecting)
        self.edit.setEnabled(selected_id is not None and not connecting)
        chosen = [group for group in groups if group["id"] in selected_ids] if not connecting else []
        self.entry_sides.refresh(chosen)
        self.exit_sides.refresh(chosen)
        self.routing_hint.setText(tr("Algumas conexões não têm espaço livre. Afaste os blocos ou permita outros lados de entrada e saída.")
                                  if getattr(window, "_board_routes_crowded", False) else "")
        self.connect_button.setEnabled(connecting or (bool(selected_ids) and len(groups) > len(selected_ids)))
        self.connect_button.setText(tr("Cancelar conexão") if connecting else tr("Conectar a elemento"))
        self.tree.setDragEnabled(not connecting)
        self.connection_hint.setText(getattr(window, "_board_connection_message", "") if connecting else tr("Selecione os blocos, clique em conectar e escolha o superior no desenho ou na árvore."))
        style = window._board_style_for_selection()
        count = len(window._board_selected_connectors())
        self.style_target.setText(tr("Conexões selecionadas: {numero}").format(numero=count) if count else tr("Aparência das novas conexões"))
        self.color.setText(style["color"].upper())
        self.color.setStyleSheet(f'QPushButton {{ border-bottom: 4px solid {style["color"]}; }}')
        for control, value in ((self.width, style["width_mm"]), (self.transparency, round((1 - style["opacity"]) * 100)),
                               (self.radius, style["radius_mm"])):
            with QSignalBlocker(control):
                control.setValue(value)
        self.margin.blockSignals(True)
        self.margin.setValue(window._board_margin_mm)
        self.margin.blockSignals(False)
        rect = board_bounds(window._board_state())
        self.size_label.setText(tr("Tamanho sugerido: {largura:.1f} × {altura:.1f} mm").format(
            largura=rect.width() / UNITS_PER_MM, altura=rect.height() / UNITS_PER_MM))


class OrganogramEditorMixin:
    def change_board_ports(self, key, side, allowed):
        if key not in ("entry_sides", "exit_sides") or side not in SIDES:
            return
        selected = [item for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)]
        default = ["bottom"] if key == "entry_sides" else ["top"]
        changes = []
        for item in selected:
            sides = set(item.data.get(key, default))
            (sides.add if allowed else sides.discard)(side)
            if not sides:
                self.organogram_panel.entry_sides.refresh([i.data for i in selected])
                self.organogram_panel.exit_sides.refresh([i.data for i in selected])
                self.organogram_panel.connection_hint.setText(tr("Mantenha pelo menos um lado permitido em cada entrada e saída."))
                return
            changes.append((item, [side for side in SIDES if side in sides]))
        for item, sides in changes:
            item.data[key] = sides
        self._update_board_connections()
        self._update_board_extent()
        self.save_snapshot()

    def _next_board_name(self, original=None, used_names=None):
        original = original.strip() if original is not None else None
        names = set(used_names if used_names is not None else (item.data["name"] for item in self._board_items()))
        keys = {block_name_key(name) for name in names}
        pattern = re.escape(tr("Bloco {numero}")).replace(re.escape("{numero}"), r"(\d+)")
        if original is None or block_name_key(original) == block_name_key(tr("Bloco")) or re.fullmatch(pattern, original, re.IGNORECASE):
            numbers = [int(match.group(1)) for name in names if (match := re.fullmatch(pattern, name.strip(), re.IGNORECASE))]
            number = max(numbers, default=0) + 1
            while block_name_key(tr("Bloco {numero}").format(numero=number)) in keys:
                number += 1
            return tr("Bloco {numero}").format(numero=number)
        suffix = tr(" — cópia")
        base = re.sub(re.escape(suffix) + r"(?: \d+)?$", "", original, flags=re.IGNORECASE)
        candidate = base + suffix
        number = 2
        while block_name_key(candidate) in keys:
            candidate = f"{base}{suffix} {number}"
            number += 1
        return candidate

    def _move_board_items(self, items, delta):
        movable = [item for item in items if hasattr(item, "rect") and not item.parentItem()
                   and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable]
        if not movable:
            return
        bounds = QRectF()
        for item in movable:
            bounds = bounds.united(item.mapRectToScene(item.rect()))
        anchor = bounds.center()
        step = _board_snap_step(self.scene, movable)
        requested = anchor + delta
        delta = QPointF(round(requested.x() / step) * step, round(requested.y() / step) * step) - anchor
        self.scene._board_snap_suspended = True
        self._board_defer_connections = True
        try:
            for item in movable:
                item.moveBy(delta.x(), delta.y())
        finally:
            self.scene._board_snap_suspended = False
            self._board_defer_connections = False
        self._update_board_connections()

    def _board_selected_connectors(self):
        direct = [item for item in self.scene.selectedItems() if isinstance(item, BoardConnectorItem)]
        if direct:
            return direct
        children = {item.data["id"] for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)}
        return [item for item in self.scene.items() if isinstance(item, BoardConnectorItem)
                and item.board_edge["target"] in children]

    def _board_style_for_selection(self):
        selected = self._board_selected_connectors()
        return connector_style(selected[0].board_edge if selected else None,
                               {"connector_style": getattr(self, "_board_connector_style", {})})

    def change_board_connector_style(self, **changes):
        if self._active_page_id != "organogram":
            return
        validate_connector_style({**self._board_style_for_selection(), **changes})
        selected = self._board_selected_connectors()
        if selected:
            for item in selected:
                item.board_edge["style"] = connector_style(
                    {"style": changes}, {"connector_style": connector_style(
                        item.board_edge, {"connector_style": self._board_connector_style})}
                )
        else:
            self._board_connector_style = connector_style(
                {"style": changes}, {"connector_style": self._board_connector_style}
            )
        self._update_board_connections()
        self._update_board_extent()
        self.save_snapshot()

    def _board_items(self):
        return sorted((item for item in self.scene.items() if isinstance(item, BoardGroupItem)),
                      key=lambda item: item.data.get("order", 0))

    def _selected_board_group(self):
        return next((item for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)), None)

    def _board_connections_data(self):
        ids = {item.data["id"] for item in self._board_items()}
        return sorted((deepcopy(item.board_edge) for item in self.scene.items()
                       if hasattr(item, "board_edge") and item.board_edge["source"] in ids and item.board_edge["target"] in ids),
                      key=lambda edge: (edge["source"], edge["target"]))

    def _board_state(self):
        data = self.get_current_scene_state()
        return {**data, "groups": data.get("__board_groups", []),
                "connections": data.get("__board_connections", []),
                "connector_style": getattr(self, "_board_connector_style", connector_style()),
                "margin_mm": self._board_margin_mm, "grid_mm": self._board_grid_mm}

    def _append_board_state(self, data):
        if self._active_page_id == "organogram":
            data.update(__board_groups=[deepcopy(item.data) for item in self._board_items()],
                        __board_connections=self._board_connections_data(),
                        __board_margin_mm=self._board_margin_mm,
                        __board_grid_mm=self._board_grid_mm,
                        __board_connector_style=deepcopy(self._board_connector_style))
        return data

    def _load_board_items(self, data):
        from features.generator.renderer import NativeRenderer
        # As subclasses têm métodos Python chamados pelo Qt. Mantém referências
        # fortes durante inserções em lote e substitui-as somente após limpar a cena.
        self._board_item_refs = {}
        self._board_grid_mm = data.get("__board_grid_mm", 5)
        self._board_margin_mm = data.get("__board_margin_mm", 10)
        self._board_connector_style = {**connector_style(), **data.get("__board_connector_style", {})}
        self.scene._board_grid = self._board_grid_mm * UNITS_PER_MM if self._active_page_id == "organogram" else 0
        if self._active_page_id != "organogram":
            return
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None
        template = adapt_model_page(self._model_document, "front")
        if self._current_model_dir:
            template["__model_dir"] = str(self._current_model_dir)
        renderer = NativeRenderer(template, asset_provider=self._editor_asset_provider)
        self._board_card_preview = renderer.render_preview_image(max_side=640)
        for index, group in enumerate(data.get("__board_groups", [])):
            group = {**group, "order": index}
            self.scene.addItem(BoardGroupItem(self, group, self._board_card_preview))
        for edge in data.get("__board_connections", []):
            self._add_board_edge(edge)
        self._update_board_connections()

    def _editor_asset_provider(self, reference):
        value = self._authorized_asset_bytes(reference)
        if value is not None:
            return value
        path = Path(reference)
        if not path.is_absolute() and self._current_model_dir:
            path = self._current_model_dir / path
        return path.read_bytes()

    def _update_board_extent(self):
        if self._active_page_id != "organogram" or getattr(self, "_loading_board", False):
            return
        rect = board_bounds(self._board_state())
        self._set_document_rect(rect)
        if self.fallback_bg:
            self.fallback_bg.setRect(rect)
            self.fallback_bg.setBrush(QBrush(Qt.GlobalColor.white))
        for control, value in ((self.spin_phys_w, rect.width() / UNITS_PER_MM),
                               (self.spin_phys_h, rect.height() / UNITS_PER_MM)):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        panel = getattr(self, "organogram_panel", None)
        if panel:
            panel.refresh()

    def _add_board_edge(self, edge):
        item = BoardConnectorItem(self, edge)
        self.scene.addItem(item)
        return item

    def _update_board_connections(self):
        if getattr(self, "_board_defer_connections", False):
            return
        groups = {item.data["id"]: item.data for item in self._board_items()}
        board = {"groups": list(groups.values()), "connections": self._board_connections_data(),
                 "connector_style": self._board_connector_style}
        paths = connector_paths(board)
        self._board_routes_crowded = any(crowded for _, crowded in board_routes(board).values())
        for item in list(self.scene.items()):
            if not hasattr(item, "board_edge"):
                continue
            source = groups.get(item.board_edge["source"])
            target = groups.get(item.board_edge["target"])
            if not source or not target:
                self.scene.removeItem(item)
                continue
            style = connector_style(item.board_edge, {"connector_style": self._board_connector_style})
            item.setPen(connector_pen(style))
            path = paths[(item.board_edge["source"], item.board_edge["target"])]
            if item.path() != path:
                item.setPath(path)
        active = {id(item) for item in self.scene.items()}
        self._board_item_refs = {key: item for key, item in self._board_item_refs.items() if key in active}

    def set_board_parent(self, child_id, parent_id):
        return self.set_board_parents([child_id], parent_id)

    def set_board_parents(self, child_ids, parent_id):
        if self._active_page_id != "organogram":
            return False
        children = set(child_ids)
        ids = {item.data["id"] for item in self._board_items()}
        if not children or not children <= ids or (parent_id is not None and parent_id not in ids):
            return False
        board = self._board_state()
        previous = {edge["target"]: edge for edge in board["connections"]}
        edges = [edge for edge in board["connections"] if edge["target"] not in children]
        if parent_id:
            for child in sorted(children):
                style = connector_style(previous.get(child), board)
                edges.append({"source": parent_id, "target": child, "style": style})
        board["connections"] = edges
        try:
            validate_organogram(board)
        except ModelValidationError as error:
            self._board_connection_message = str(error)
            self.organogram_panel.refresh()
            self.organogram_panel.connection_hint.setText(str(error))
            return False
        # Preserva os itens não alterados e não emite seleção no meio da operação.
        with QSignalBlocker(self.scene):
            existing = {item.board_edge["target"]: item for item in self.scene.items() if isinstance(item, BoardConnectorItem)}
            for child, item in existing.items():
                if child in children and not parent_id:
                    self.scene.removeItem(item)
            for edge in edges:
                item = existing.get(edge["target"])
                if item:
                    item.board_edge = deepcopy(edge)
                else:
                    self._add_board_edge(edge)
        self._update_board_connections()
        self._update_board_extent()
        self.save_snapshot()
        return True

    def cancel_board_connection(self):
        from shiboken6 import isValid
        self._board_connection_sources = set()
        for item, opacity, flags, buttons in getattr(self, "_board_connection_locked", []):
            if isValid(item):
                item.setOpacity(opacity)
                item.setFlags(flags)
                item.setAcceptedMouseButtons(buttons)
        self._board_connection_locked = []
        if hasattr(self, "_board_cancel_shortcut"):
            self._board_cancel_shortcut.setEnabled(False)
        if getattr(self, "view", None):
            self.view.viewport().unsetCursor()
        if hasattr(self, "organogram_panel") and not getattr(self, "_loading_board", False):
            self.organogram_panel.refresh()

    def _connect_to_board_target(self, target_id):
        sources = getattr(self, "_board_connection_sources", set())
        if not sources or target_id in sources:
            return False
        if self.set_board_parents(sources, target_id):
            self.cancel_board_connection()
            return True
        return False

    def add_model_organogram(self):
        self._finish_page_interaction()
        self.save_snapshot()
        self._model_document = add_organogram(self._model_document)
        self.switch_model_page("organogram")
        self._pending_history_page_id = "organogram"
        self.save_snapshot()
        self._refresh_page_controls()

    def add_board_group(self, settings=None):
        if self._active_page_id != "organogram":
            return
        if settings is None:
            return self.edit_board_group(create=True)
        group = deepcopy(settings)
        pattern = re.escape(tr("Bloco {numero}")).replace(re.escape("{numero}"), r"(\d+)")
        used = {block_name_key(item.data["name"]) for item in self._board_items()}
        if group.get("name") == tr("Bloco") or (
                block_name_key(group.get("name")) in used and re.fullmatch(pattern, group.get("name", ""), re.IGNORECASE)):
            group["name"] = self._next_board_name()
        group["order"] = len(self._board_items())
        candidate = self._board_state()
        candidate["groups"].append(group)
        validate_organogram(candidate)
        self.scene.clearSelection()
        item = BoardGroupItem(self, group, self._board_card_preview)
        self.scene.addItem(item)
        item.setPos(item.pos())
        item.setSelected(True)
        self._update_board_extent()
        self.save_snapshot()
        return item

    def edit_board_group(self, item=None, *, create=False):
        if self._active_page_id != "organogram":
            return
        item = item or self._selected_board_group()
        if item is None and not create:
            return
        data = deepcopy(item.data) if item else new_group(self._model_document)
        if item is None:
            data["name"] = self._next_board_name()
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Adicionar bloco") if create else tr("Editar bloco"))
        form = QFormLayout(dialog)
        name = QLineEdit(data.get("name", tr("Bloco")))
        name.setObjectName("boardBlockName")
        form.addRow(tr("Nome do bloco"), name)
        controls = {}
        for key, label, minimum, maximum, value in (
            ("columns", tr("Colunas"), 1, 100, data["columns"]),
            ("rows", tr("Linhas"), 1, 100, data["rows"]),
            ("width", tr("Largura do cartão (mm)"), 1, 1000, data["card_w"] / UNITS_PER_MM),
            ("gap_x", tr("Espaçamento horizontal (mm)"), 0, 1000, data["gap_x"] / UNITS_PER_MM),
            ("gap_y", tr("Espaçamento vertical (mm)"), 0, 1000, data["gap_y"] / UNITS_PER_MM),
        ):
            control = QSpinBox() if key in ("columns", "rows") else QDoubleSpinBox()
            control.setRange(minimum, maximum)
            control.setValue(value)
            controls[key] = control
            form.addRow(label, control)
        hint = QLabel(tr("A altura acompanha a proporção da página 1. Use este nome na coluna Bloco da tabela para enviar os registros a este destino, na ordem das linhas. O nome deve ser único e não cria um título na arte."))
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        style_dialog_button_box(buttons)
        form.addRow(buttons)
        def accept_name():
            try:
                validate_block_name(name.text(), [group.data for group in self._board_items()],
                                    exclude_id=item.data["id"] if item else None)
            except ModelValidationError as error:
                QMessageBox.warning(dialog, tr("Nome de bloco inválido"), str(error))
                name.setFocus()
                name.selectAll()
                return
            dialog.accept()
        buttons.accepted.connect(accept_name)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        width = controls["width"].value() * UNITS_PER_MM
        canvas = self._model_document["canvas_size"]
        data.update(name=name.text().strip(),
                    columns=controls["columns"].value(), rows=controls["rows"].value(),
                    card_w=width, card_h=width * canvas["h"] / canvas["w"],
                    gap_x=controls["gap_x"].value() * UNITS_PER_MM,
                    gap_y=controls["gap_y"].value() * UNITS_PER_MM)
        if item is None:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            grid = self._board_grid_mm * UNITS_PER_MM
            bounds = group_rect(data)
            data.update(x=round(center.x() / grid) * grid - bounds.width() / 2,
                        y=round(center.y() / grid) * grid - bounds.height() / 2)
        else:
            center = item.pos() + item.rect().center()
            bounds = group_rect(data)
            data.update(x=center.x() - bounds.width() / 2, y=center.y() - bounds.height() / 2)
        candidate = self._board_state()
        candidate["groups"] = [data if group["id"] == data["id"] else group for group in candidate["groups"]]
        if item is None:
            candidate["groups"].append(data)
        try:
            validate_organogram(candidate)
            if item is None:
                self.add_board_group(data)
            else:
                old_center = item.rect().center() + item.pos()
                item.prepareGeometryChange()
                item.data = data
                rect = group_rect(data)
                item.setRect(0, 0, rect.width(), rect.height())
                self.scene._board_snap_suspended = True
                try:
                    item.setPos(old_center - item.rect().center())
                finally:
                    self.scene._board_snap_suspended = False
                item.update()
                self._update_board_connections()
                self._update_board_extent()
                self.save_snapshot()
        except ModelValidationError as error:
            QMessageBox.warning(self, tr("Bloco inválido"), str(error))

    def start_board_connection(self):
        if getattr(self, "_board_connection_sources", None):
            self.cancel_board_connection()
            return
        selected = [item for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)]
        if not selected or len(selected) == len(self._board_items()):
            self.organogram_panel.connection_hint.setText(tr("Selecione os blocos que receberão um superior e deixe um bloco disponível como destino."))
            return
        self._finish_page_interaction()
        self._board_connection_sources = {item.data["id"] for item in selected}
        self._board_connection_locked = [(item, item.opacity(), item.flags(), item.acceptedMouseButtons()) for item in selected]
        for item in selected:
            item.setOpacity(0.35)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        if not hasattr(self, "_board_cancel_shortcut"):
            self._board_cancel_shortcut = QShortcut(Qt.Key.Key_Escape, self)
            self._board_cancel_shortcut.activated.connect(self.cancel_board_connection)
        self._board_cancel_shortcut.setEnabled(True)
        self._board_connection_message = tr("Clique no bloco superior. Os blocos apagados estão bloqueados. Esc cancela.")
        self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.organogram_panel.refresh()

    def duplicate_board_selection(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)]
        if not selected:
            return False
        previous_board = getattr(self, "_board_clipboard", None)
        previous_objects = self._object_clipboard
        try:
            self.copy_board_selection()
            self.paste_board_selection()
        finally:
            self._board_clipboard = previous_board
            self._object_clipboard = previous_objects
        return True

    def copy_board_selection(self):
        groups = [deepcopy(item.data) for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)]
        if not groups:
            self._board_clipboard = None
            return False
        ids = {group["id"] for group in groups}
        self._board_clipboard = {
            "groups": groups,
            "connections": [edge for edge in self._board_connections_data()
                            if edge["source"] in ids and edge["target"] in ids],
        }
        self._object_clipboard = []
        return True

    def paste_board_selection(self):
        clipboard = getattr(self, "_board_clipboard", None)
        if not clipboard:
            return False
        if self._active_page_id != "organogram":
            return True
        board = self._board_state()
        copies = deepcopy(clipboard["groups"])
        identifiers = {group["id"]: f"block-{uuid4().hex}" for group in copies}
        names = {group["name"] for group in board["groups"]}
        for index, group in enumerate(copies, start=len(board["groups"])):
            name = self._next_board_name(group["name"], names)
            names.add(name)
            group.update(id=identifiers[group["id"]], order=index,
                         name=name,
                         x=group["x"] + self._board_grid_mm * UNITS_PER_MM,
                         y=group["y"] + self._board_grid_mm * UNITS_PER_MM)
        edges = [{**deepcopy(edge), "source": identifiers[edge["source"]], "target": identifiers[edge["target"]]}
                 for edge in clipboard["connections"]]
        board["groups"].extend(copies)
        board["connections"].extend(edges)
        try:
            validate_organogram(board)
        except ModelValidationError as error:
            QMessageBox.warning(self, tr("Bloco inválido"), str(error))
            return True
        self.scene.clearSelection()
        for group in copies:
            item = BoardGroupItem(self, group, self._board_card_preview)
            self.scene.addItem(item)
            item.setSelected(True)
        for edge in edges:
            self._add_board_edge(edge)
        self._update_board_connections()
        self._update_board_extent()
        self.save_snapshot()
        return True

    def refresh_board_context(self):
        active = self._active_page_id == "organogram"
        self.spin_phys_w.setEnabled(not active)
        self.spin_phys_h.setEnabled(not active)
        self.chk_doc_proporcao.setEnabled(not active)
        if not hasattr(self, "organogram_panel"):
            return
        self._organogram_section.setVisible(active)
        self._board_caption.setText(
            f'<b>{tr("Quadro")}</b><br><span style="font-size:9px">{tr("Blocos e conexões")}</span>' if active else
            f'<b>{tr("Assinatura")}</b><br><span style="font-size:9px">{tr("Imagem opcional")}</span>')
        self._board_button_icon.setPixmap(themed_svg_icon(object_icon_path("organogram" if active else "signature")).pixmap(20, 20))
        self._board_button_arrow.setPixmap(themed_svg_icon(navigation_icon_path("chevron-down")).pixmap(16, 16) if active else QPixmap())
        self.btn_add_sig.setMenu(self._board_tool_menu if active else None)
        self.btn_add_sig.setToolTip(tr("Blocos e conexões do quadro") if active else tr("Adicionar uma assinatura opcional ao modelo"))
        if active:
            self._update_board_extent()
            self.organogram_panel.refresh()
