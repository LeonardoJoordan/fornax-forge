"""Ferramentas de quadro integradas ao editor existente."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import math
import json
import re
from uuid import uuid4

from PySide6.QtCore import Qt, QPointF, QTimer, QRectF, QSignalBlocker, QEvent, QSize
from PySide6.QtGui import QColor, QPen, QPainterPath, QBrush, QPainter, QPixmap, QShortcut, QPainterPathStroker, QDrag, QMouseEvent, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QPushButton, QSpinBox,
    QDoubleSpinBox, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem,
    QDialog, QDialogButtonBox, QMessageBox, QGraphicsItem, QGraphicsRectItem,
    QGraphicsPathItem, QMenu, QGraphicsView, QColorDialog, QCheckBox, QGridLayout, QHBoxLayout,
    QStyleOptionGraphicsItem, QStyle,
)
from core.i18n import tr
from core.organogram import (
    UNITS_PER_MM, add_organogram, new_group, group_rect, slot_rect, board_bounds,
    validate_organogram, block_name_key, validate_block_name,
)
from core.board_connectors import (connector_style, connector_pen, connector_paths, connector_clip,
                                   MAX_CURVE_RADIUS_MM, validate_connector_style)
from core.board_routing import board_routes, SIDES
from core.board_borders import (border_style, bordered_group_bounds, paint_group_borders,
                                card_clip_path, APPEARANCE_KEYS)
from core.model_document import adapt_model_page, ModelValidationError
from core.dialog_buttons import style_dialog_button_box
from core.resources import object_icon_path, navigation_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import theme_color, theme_manager, themed_style
from shiboken6 import isValid
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
            with self.window()._board_visual_batch():
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
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setZValue(-10)
        window._board_item_refs[id(self)] = self

    def boundingRect(self):
        bounds = bordered_group_bounds(self.data).translated(-self.data["x"], -self.data["y"])
        return bounds.united(super().boundingRect())

    def itemChange(self, change, value):
        if self.scene() and change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            grid = getattr(self.scene(), "_board_grid", 0)
            if grid:
                return _snap_board_position(self, value)
        if self.scene() and change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data.update(x=self.pos().x(), y=self.pos().y())
            self.window._update_board_connections()
        return super().itemChange(change, value)

    def _visible_card_indices(self, painter, exposed):
        """Faixas da grade que alcançam a área exposta, inclusive contornos."""
        columns, rows = self.data["columns"], self.data["rows"]
        if exposed.isEmpty() or exposed.contains(self.boundingRect()):
            return range(columns * rows)
        inverse, invertible = painter.deviceTransform().inverted()
        if not invertible:
            return range(columns * rows)
        # Três pixels de folga incluem traços cosméticos e antialiasing em
        # qualquer zoom/DPI. A área chega em coordenadas locais do conjunto.
        pixel_bounds = inverse.mapRect(QRectF(0, 0, 3, 3))
        style = border_style(self.data, 'cards')
        margin = 0
        if style['cards'] and style['opacity'] > 0:
            fraction = {'inside': 0, 'center': .5, 'outside': 1}[style['cards_position']]
            margin = style['width_mm'] * UNITS_PER_MM * fraction
        exposed = exposed.adjusted(-margin - pixel_bounds.width(), -margin - pixel_bounds.height(),
                                   margin + pixel_bounds.width(), margin + pixel_bounds.height())
        width, height = self.data['card_w'], self.data['card_h']
        step_x, step_y = width + self.data['gap_x'], height + self.data['gap_y']
        first_column = max(0, math.ceil((exposed.left() - width) / step_x))
        last_column = min(columns - 1, math.floor(exposed.right() / step_x))
        first_row = max(0, math.ceil((exposed.top() - height) / step_y))
        last_row = min(rows - 1, math.floor(exposed.bottom() / step_y))
        return tuple(row * columns + column
                     for row in range(first_row, last_row + 1)
                     for column in range(first_column, last_column + 1))

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # O recorte é exclusivo da view. Renderizações de cena continuam
        # completas; a prévia/exportação usam o renderer compartilhado.
        indices = (self._visible_card_indices(painter, option.exposedRect)
                   if widget is not None else range(self.data["columns"] * self.data["rows"]))
        for index in indices:
            x = index % self.data["columns"] * (self.data["card_w"] + self.data["gap_x"])
            y = index // self.data["columns"] * (self.data["card_h"] + self.data["gap_y"])
            rect = QRectF(x, y, self.data["card_w"], self.data["card_h"])
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipPath(card_clip_path(self.data, rect), Qt.ClipOperation.IntersectClip)
            painter.drawImage(rect, self.preview)
            painter.restore()
            pen = QPen(QColor(theme_color("border_strong")), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(rect)
        local = {**self.data, "x": 0, "y": 0}
        paint_group_borders(painter, local, (slot_rect(local, index) for index in indices))
        if self.isSelected():
            pen = QPen(QColor(theme_color("accent")), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(self.rect())
        painter.restore()

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
        return self.window._board_cutouts()

    def shape(self):
        path = self.path()
        width = max(self.pen().widthF(), 12)
        revision = getattr(self.window, '_board_cutout_revision', 0)
        cached = getattr(self, '_shape_cache', None)
        if cached is not None and cached[:4] == (path, width, revision, bool(self.scene())):
            return QPainterPath(cached[4])
        stroker = QPainterPathStroker()
        stroker.setWidth(width)
        shape = stroker.createStroke(path)
        if self.scene():
            shape = shape.subtracted(self.cutouts())
        self._shape_cache = (path, width, revision, bool(self.scene()), shape)
        return QPainterPath(shape)

    def _paint_clip(self):
        bounds = self.boundingRect().adjusted(-12, -12, 12, 12)
        revision = getattr(self.window, '_board_cutout_revision', 0)
        cached = getattr(self, '_clip_cache', None)
        if cached is None or cached[:2] != (bounds, revision):
            cached = self._clip_cache = (bounds, revision, connector_clip(bounds, self.cutouts()))
        return cached[2]

    def boundingRect(self):
        # Inclui a tolerância de clique e o realce da seleção no índice da cena.
        return super().boundingRect().adjusted(-6, -6, 6, 6)

    def paint(self, painter, option, widget=None):
        painter.save()
        try:
            painter.setClipPath(self._paint_clip(), Qt.ClipOperation.IntersectClip)
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


class ConnectorSides(QWidget):
    """Quatro permissões espaciais em torno de uma representação do bloco."""
    def __init__(self, title, window, key):
        from .frontend import property_heading
        super().__init__()
        self.key = key
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        property_heading(layout, title)
        grid = QGridLayout()
        layout.addLayout(grid)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setSpacing(6)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.block_icon = QLabel()
        self.block_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.block_icon.setFixedSize(40, 40)
        self._refresh_icon()
        theme_manager().changed.connect(self._refresh_icon)
        grid.addWidget(self.block_icon, 1, 1, Qt.AlignmentFlag.AlignCenter)
        self.checks = {}
        for side, label, row, column in (("top", tr("Cima"), 0, 1), ("left", tr("Esquerda"), 1, 0),
                                         ("right", tr("Direita"), 1, 2), ("bottom", tr("Baixo"), 2, 1)):
            checkbox = QCheckBox()
            # A área do widget coincide com o indicador (14 px + borda),
            # evitando o deslocamento causado pelo espaço nativo da legenda.
            checkbox.setFixedSize(16, 16)
            checkbox.setStyleSheet('QCheckBox { spacing: 0; padding: 0; margin: 0; }')
            checkbox.setAccessibleName(f"{title}: {label}")
            checkbox.setToolTip(tr("Permitir por {lado}. Mantenha pelo menos um lado marcado.").format(lado=label.lower()))
            checkbox.clicked.connect(lambda _checked, side=side, checkbox=checkbox:
                                       window.change_board_ports(key, side, checkbox.checkState() == Qt.CheckState.Checked))
            grid.addWidget(checkbox, row, column, Qt.AlignmentFlag.AlignCenter)
            self.checks[side] = checkbox

    def _refresh_icon(self):
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self.block_icon.setPixmap(themed_svg_icon(object_icon_path("square-user-round")).pixmap(
            QSize(40, 40), mode))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and hasattr(self, 'block_icon'):
            self._refresh_icon()

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
        from .frontend import (
            column, field, row, property_heading, compact_sidebar_action,
            square_control, compact, centered_toggle_button,
            outline_controls, corner_radius_controls,
        )
        super().__init__()
        self.window = window
        self._syncing = False
        self._tree_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        property_heading(layout, tr("HIERARQUIA"))
        self.tree = StructureTree(window)
        self.tree.setObjectName("boardStructure")
        themed_style(self.tree, '''
            QTreeWidget#boardStructure {
                background: @surface@; border: 1px solid @border@;
                border-radius: 5px; padding: 3px; outline: none;
            }
            QTreeWidget#boardStructure::item { padding: 4px 5px; border: none; }
            QTreeWidget#boardStructure::item:selected { background: @selection@; color: @text@; }
            QTreeWidget#boardStructure::item:hover { background: @hover@; }
        ''')
        self.tree.setToolTip(tr("Arraste na árvore para mudar o superior. O centro dos blocos encaixa em 5 mm e o dos textos em 2,5 mm."))
        self.tree.setMinimumHeight(150)
        self.tree.setMaximumHeight(260)
        layout.addWidget(self.tree)
        self.tree.itemSelectionChanged.connect(self.select_from_tree)
        self.tree.itemDoubleClicked.connect(lambda *_: QTimer.singleShot(0, self, window.edit_board_group))
        self.tree.itemClicked.connect(self.click_tree_item)
        self.connect_button = QPushButton(tr("Conectar a elemento"))
        compact_sidebar_action(self.connect_button)
        self.connect_button.setToolTip(tr("Selecione os blocos, clique em conectar e escolha o superior no desenho ou na árvore."))
        self.connect_button.clicked.connect(window.start_board_connection)
        layout.addWidget(self.connect_button)
        self.connection_hint = QLabel()
        self.connection_hint.setWordWrap(True)
        layout.addWidget(self.connection_hint)
        self.parent_combo = QComboBox()
        self.parent_combo.activated.connect(self.change_parent)
        layout.addWidget(field(tr("Superior"), self.parent_combo))
        hint = QLabel(tr("Arraste os blocos na árvore para ajustar a hierarquia."))
        hint.setWordWrap(True)
        themed_style(hint, 'color: @disabled@; font-size: 10px;')
        layout.addWidget(hint)
        self.routing_hint = QLabel()
        self.routing_hint.setWordWrap(True)
        layout.addWidget(self.routing_hint)

        # Opções do documento e propriedades compartilham os mesmos controles;
        # o frontend encaixa cada conteúdo na seção existente do inspetor.
        self.output_settings, output_layout = column()
        self.output_settings.setObjectName("boardOutputSettings")
        output_layout.setContentsMargins(0, 0, 0, 0)
        property_heading(output_layout, tr("SAÍDA DO QUADRO"), separated=True)
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, 1000)
        self.margin.setSuffix(" mm")
        self.margin.setKeyboardTracking(False)
        self.margin.valueChanged.connect(self.change_margin)
        output_layout.addWidget(field(tr("Margem de saída"), self.margin))
        self.size_label = QLabel()
        self.size_label.setWordWrap(True)
        themed_style(self.size_label, 'color: @disabled@; font-size: 10px;')
        output_layout.addWidget(self.size_label)
        self.output_settings.hide()

        self.properties, properties_layout = column()
        self.properties.setObjectName("boardProperties")
        properties_layout.setContentsMargins(0, 0, 0, 0)
        self.properties.hide()
        self.group_settings, group_layout = column()
        group_layout.setContentsMargins(0, 0, 0, 0)
        property_heading(group_layout, tr("BLOCO / CONJUNTO"))
        self.edit = QPushButton(tr("Editar bloco selecionado"))
        compact_sidebar_action(self.edit)
        self.edit.clicked.connect(lambda: window.edit_board_group())
        group_layout.addWidget(self.edit)
        properties_layout.addWidget(self.group_settings)

        self.artwork_layers, artwork_form = column()
        artwork_form.setContentsMargins(0, 0, 0, 0)
        property_heading(artwork_form, tr("CAMADAS DO QUADRO"), separated=True)
        self.artwork_position = QComboBox()
        self.artwork_position.addItem(tr("À frente do organograma"), False)
        self.artwork_position.addItem(tr("Atrás do organograma"), True)
        self.artwork_position.activated.connect(
            lambda index: window.change_board_artwork_position(self.artwork_position.itemData(index)))
        artwork_form.addWidget(field(tr("Posição"), self.artwork_position))
        self.artwork_hint = QLabel(tr("Para uma imagem de fundo, escolha atrás do organograma."))
        self.artwork_hint.setWordWrap(True)
        themed_style(self.artwork_hint, 'color: @disabled@; font-size: 10px;')
        artwork_form.addWidget(self.artwork_hint)
        properties_layout.addWidget(self.artwork_layers)
        self.ports, ports_layout = column()
        ports_layout.setContentsMargins(0, 0, 0, 0)
        property_heading(ports_layout, tr("LADOS PERMITIDOS"), separated=True)
        self.entry_sides = ConnectorSides(tr("Entrada"), window, "entry_sides")
        self.exit_sides = ConnectorSides(tr("Saída"), window, "exit_sides")
        port_layout = row(ports_layout, self.entry_sides, self.exit_sides)
        port_layout.setStretch(0, 1)
        port_layout.setStretch(1, 1)
        properties_layout.addWidget(self.ports)
        self.borders, border_form = column()
        border_form.setContentsMargins(0, 0, 0, 0)
        self.border_corners = corner_radius_controls('board')
        for key, control in self.border_corners.spins.items():
            control.editingFinished.connect(lambda key=key: self.apply_border_corner(key))
        self.border_corners.sync.toggled.connect(self.toggle_border_corner_sync)
        border_form.addWidget(self.border_corners)
        property_heading(border_form, tr("CONTORNO"), separated=True)
        self.border_enabled = QPushButton(tr("Habilitar contorno"))
        self.border_enabled.setObjectName('boardOutlineEnabled')
        self.border_enabled.setCheckable(True)
        centered_toggle_button(border_form, self.border_enabled)
        self.border_enabled.clicked.connect(self.toggle_border)
        self.border_scope = QComboBox()
        self.border_scope.setObjectName('boardOutlineScope')
        self.border_scope.setPlaceholderText(tr("Contornos diferentes"))
        self.border_scope.addItem(tr("Em cada cartão"), 'cards')
        self.border_scope.addItem(tr("Ao redor do conjunto"), 'group')
        self.border_scope.addItem(tr("Cartões e conjunto"), 'both')
        self.border_scope.activated.connect(self.change_border_scope)
        self.border_scope.setToolTip(tr("Escolha onde mostrar o contorno. Cartão e conjunto mantêm suas cores e configurações ao alternar. A opção Cartões e conjunto mostra ambos."))
        border_form.addWidget(field(tr("Aplicar em"), self.border_scope))
        self.border_outline = outline_controls('boardBorder')
        self.border_color = self.border_outline.swatch
        self.border_color_hex = self.border_outline.color
        self.border_width = self.border_outline.spin_width
        self.border_opacity = self.border_outline.alpha
        self.border_position = self.border_outline.position
        self.border_position.setPlaceholderText(tr("Posições diferentes"))
        self.border_position.setToolTip(self.border_position.toolTip() + "\n" +
                                       tr("A posição escolhida vale somente para o contorno em edição."))
        self.border_position.activated.connect(
            lambda index: window.change_board_border_position(self.border_position.itemData(index)))
        self.border_color.clicked.connect(self.choose_border_color)
        self.border_color_hex.editingFinished.connect(lambda: self.apply_color_text(border=True))
        self.border_width.editingFinished.connect(lambda: window.change_board_border(width_mm=self.border_width.value()))
        self.border_opacity.editingFinished.connect(lambda: window.change_board_border(opacity=self.border_opacity.value() / 100))
        self.border_outline.join_straight.clicked.connect(lambda: window.change_board_border(join="miter"))
        self.border_outline.join_round.clicked.connect(lambda: window.change_board_border(join="round"))
        border_form.addWidget(self.border_outline)
        self.border_padding = QDoubleSpinBox()
        self.border_padding.setRange(0, 1000)
        self.border_padding.setDecimals(2)
        self.border_padding.setSingleStep(0.1)
        self.border_padding.setKeyboardTracking(False)
        self.border_padding.editingFinished.connect(
            lambda: window.change_board_border(padding_mm=self.border_padding.value()))
        self.border_padding.setToolTip(tr("Espaço entre os cartões e o limite do conjunto, antes da espessura do contorno."))
        self.border_padding_field = field(tr("Folga do conjunto"), compact('', self.border_padding, 'mm'))
        self.border_outline.layout().addWidget(self.border_padding_field)
        properties_layout.addWidget(self.borders)
        self.appearance, style_form = column()
        style_form.setContentsMargins(0, 0, 0, 0)
        self.connector_heading = property_heading(style_form, tr("CONECTORES"), separated=True)
        self.style_target = QLabel()
        self.style_target.setWordWrap(True)
        themed_style(self.style_target, 'color: @disabled@; font-size: 10px;')
        style_form.addWidget(self.style_target)
        self.color = QPushButton()
        square_control(self.color)
        self.color.setToolTip(tr("Escolher a cor do conector"))
        self.color.clicked.connect(self.choose_color)
        self.color_hex = QLineEdit()
        self.color_hex.setMaxLength(7)
        self.color_hex.setPlaceholderText("#RRGGBB")
        self.color_hex.editingFinished.connect(lambda: self.apply_color_text(border=False))
        connector_color_field, connector_color_layout = column()
        connector_color_layout.setContentsMargins(0, 0, 0, 0)
        row(connector_color_layout, self.color, self.color_hex).setStretch(1, 1)
        style_form.addWidget(field(tr("Cor"), connector_color_field))
        self.width = QDoubleSpinBox()
        self.width.setRange(0.05, 20)
        self.width.setDecimals(2)
        self.width.setSingleStep(0.1)
        self.width.setSuffix(" mm")
        self.width.setKeyboardTracking(False)
        self.width.valueChanged.connect(lambda value: window.change_board_connector_style(width_mm=value))
        self.transparency = QSpinBox()
        self.transparency.setRange(0, 100)
        self.transparency.setSuffix(" %")
        self.transparency.setKeyboardTracking(False)
        self.transparency.valueChanged.connect(lambda value: window.change_board_connector_style(opacity=1 - value / 100))
        connector_dimensions = row(style_form, field(tr("Espessura"), self.width),
                                   field(tr("Transparência"), self.transparency))
        connector_dimensions.setStretch(0, 1)
        connector_dimensions.setStretch(1, 1)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0, MAX_CURVE_RADIUS_MM)
        self.radius.setDecimals(2)
        self.radius.setSingleStep(0.5)
        self.radius.setSuffix(" mm")
        self.radius.setKeyboardTracking(False)
        self.radius.setToolTip(tr("0 mantém as quinas retas. O raio é limitado pelo comprimento dos trechos e pelo espaço entre os blocos."))
        self.radius.valueChanged.connect(lambda value: window.change_board_connector_style(radius_mm=value))
        style_form.addWidget(field(tr("Raio de curva"), self.radius))
        properties_layout.addWidget(self.appearance)

    def properties_available(self):
        window = self.window
        return window._active_page_id == "organogram" and (
            bool(getattr(window, "_board_connection_sources", None))
            or bool(window._board_selected_artwork())
            or any(isinstance(item, (BoardGroupItem, BoardConnectorItem)) for item in window.scene.selectedItems())
        )

    def show_connection_message(self, message):
        self.connection_hint.setText(message)
        self.connection_hint.setVisible(bool(message))

    def select_from_tree(self):
        if self._syncing or getattr(self.window, "_board_connection_sources", None):
            return
        identifiers = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()}
        self._syncing = True
        try:
            with self.window._selection_batch():
                self.window.scene.clearSelection()
                for item in self.window._board_items():
                    item.setSelected(item.data["id"] in identifiers)
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

    def choose_border_color(self):
        selected = self.window._selected_board_group()
        if selected is None:
            return
        color = QColorDialog.getColor(QColor(border_style(selected.data)["color"]), self, tr("Cor do contorno"))
        if color.isValid():
            self.window.change_board_border(color=color.name())

    def toggle_border(self, enabled):
        # Uma seleção mista conserva o destino particular de cada conjunto.
        self.window.change_board_border(_enabled=enabled)

    def change_border_scope(self, index):
        scope = self.border_scope.itemData(index)
        if scope is None:
            return
        self.window.change_board_border(_scope=scope)

    def apply_border_corner(self, key):
        # Como nas formas, vincular afeta a próxima edição, sem zerar cantos.
        value = self.border_corners.spins[key].value()
        linked = self.border_corners.sync.isChecked()
        changes = {key: value}
        if linked:
            changes = {corner: value for corner in self.border_corners.spins}
        self.window.change_board_corner_radii(changes, linked=linked)

    def toggle_border_corner_sync(self, linked):
        self.border_corners.refresh_sync_icon(linked)
        self.window.change_board_border(corner_radii_linked=linked)

    def apply_color_text(self, *, border):
        control = self.border_color_hex if border else self.color_hex
        value = control.text().strip()
        color = QColor(value)
        if len(value) == 7 and value.startswith("#") and color.isValid():
            change = self.window.change_board_border if border else self.window.change_board_connector_style
            change(color=color.name())
        else:
            self.refresh()

    def change_parent(self, index):
        selected = self.window._selected_board_group()
        if selected:
            self.window.set_board_parent(selected.data["id"], self.parent_combo.itemData(index))

    def change_margin(self, value):
        if self.window._active_page_id == "organogram":
            self.window._board_margin_mm = value
            self.window._update_board_extent()
            self.window.save_snapshot()

    def refresh(self, *, refresh_inspector=True):
        window = self.window
        if getattr(window, '_restoring_history', False):
            return  # A seleção final atualiza o painel ao concluir a restauração.
        active = window._active_page_id == "organogram"
        self.output_settings.setVisible(active)
        self.properties.setVisible(self.properties_available())
        if not active:
            if refresh_inspector and hasattr(window, "_refresh_board_inspector"):
                window._refresh_board_inspector()
            return
        if getattr(window, "_loading_board", False):
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
        artwork = window._board_selected_artwork() if not connecting else []
        self.group_settings.setVisible(bool(selected_ids))
        self.ports.setVisible(bool(selected_ids))
        self.borders.setVisible(bool(selected_ids))
        self.artwork_layers.setVisible(bool(artwork))
        self.artwork_layers.setEnabled(bool(artwork))
        explicit_connectors = any(isinstance(item, BoardConnectorItem) for item in window.scene.selectedItems())
        self.appearance.setVisible(connecting or explicit_connectors)
        self.connector_heading._section_separator.setVisible(bool(selected_ids or artwork))
        positions = {getattr(item, "board_behind", False) for item in artwork}
        with QSignalBlocker(self.artwork_position):
            self.artwork_position.setCurrentIndex(
                self.artwork_position.findData(next(iter(positions))) if len(positions) == 1 else -1)
        self.parent_combo.setEnabled(selected_id is not None and not connecting)
        self.edit.setEnabled(selected_id is not None and not connecting)
        chosen = [group for group in groups if group["id"] in selected_ids] if not connecting else []
        self.entry_sides.refresh(chosen)
        self.exit_sides.refresh(chosen)
        self.borders.setEnabled(bool(chosen))
        styles = [border_style(group) for group in chosen]
        border = styles[0] if styles else border_style({})
        scopes = {style['target'] for style in styles}
        with QSignalBlocker(self.border_scope):
            self.border_scope.setCurrentIndex(self.border_scope.findData(next(iter(scopes))) if len(scopes) == 1 else -1)
        enabled = any(style['cards'] or style['group'] for style in styles)
        with QSignalBlocker(self.border_enabled):
            self.border_enabled.setChecked(enabled)
        self.border_enabled.setText(tr('Desabilitar contorno') if enabled else tr('Habilitar contorno'))
        self.border_enabled.setToolTip(tr('Aplica a alteração a todos os blocos selecionados.'))
        self.border_outline.setVisible(enabled)
        with QSignalBlocker(self.border_corners.sync):
            self.border_corners.sync.setChecked(border.get('corner_radii_linked', True))
        self.border_corners.refresh_sync_icon(self.border_corners.sync.isChecked())
        radii = border.get('corner_radii_mm', {})
        for key, control in self.border_corners.spins.items():
            with QSignalBlocker(control):
                control.setValue(radii.get(key, border['radius_mm']))
        self.border_color_hex.setText(border["color"].upper())
        themed_style(self.border_color, f'background: {border["color"]}; border: 1px solid @border_strong@;')
        for control, value in ((self.border_width, border["width_mm"]),
                               (self.border_opacity, round(border["opacity"] * 100)),
                               (self.border_padding, border["padding_mm"])):
            with QSignalBlocker(control):
                control.setValue(value)
        positions = {style[key] for style in styles
                     for target, key in (("cards", "cards_position"), ("group", "group_position"))
                     if style[target] and style['target'] in (target, 'both')}
        with QSignalBlocker(self.border_position):
            self.border_position.setCurrentIndex(
                self.border_position.findData(next(iter(positions))) if len(positions) == 1 else -1)
        joins = {style["join"] for style in styles}
        self.border_outline.join_straight.setChecked(joins == {"miter"})
        self.border_outline.join_round.setChecked(joins == {"round"})
        self.border_outline.setEnabled(enabled)
        self.border_padding_field.setVisible(any(style['target'] in ('group', 'both') for style in styles))
        self.routing_hint.setText(tr("Algumas conexões não têm espaço livre. Afaste os blocos ou permita outros lados de entrada e saída.")
                                  if getattr(window, "_board_routes_crowded", False) else "")
        self.routing_hint.setVisible(bool(self.routing_hint.text()))
        self.connect_button.setEnabled(connecting or (bool(selected_ids) and len(groups) > len(selected_ids)))
        self.connect_button.setText(tr("Cancelar conexão") if connecting else tr("Conectar a elemento"))
        self.tree.setDragEnabled(not connecting)
        self.show_connection_message(getattr(window, "_board_connection_message", "") if connecting else "")
        style = window._board_style_for_selection()
        count = len(window._board_selected_connectors())
        self.style_target.setText(tr("Conexões selecionadas: {numero}").format(numero=count) if count else tr("Aparência das novas conexões"))
        self.color_hex.setText(style["color"].upper())
        themed_style(self.color, f'background: {style["color"]}; border: 1px solid @border_strong@;')
        for control, value in ((self.width, style["width_mm"]), (self.transparency, round((1 - style["opacity"]) * 100)),
                               (self.radius, style["radius_mm"])):
            with QSignalBlocker(control):
                control.setValue(value)
        self.margin.blockSignals(True)
        self.margin.setValue(window._board_margin_mm)
        self.margin.blockSignals(False)
        rect = window._board_geometry()[3]
        self.size_label.setText(tr("Tamanho sugerido: {largura:.1f} × {altura:.1f} mm").format(
            largura=rect.width() / UNITS_PER_MM, altura=rect.height() / UNITS_PER_MM))
        if refresh_inspector and hasattr(window, "_refresh_board_inspector"):
            window._refresh_board_inspector()


class OrganogramEditorMixin:
    def change_board_corner_radii(self, changes, *, linked):
        self.change_board_border(corner_radii_linked=linked, _corner_changes=changes)

    def change_board_border_position(self, position):
        self.change_board_border(_position=position)

    def _board_artwork_roots(self):
        from .table_item import TableItem
        from .canvas_items import DesignerBox, ImageItem, BackgroundItem, RectangleItem
        return [item for item in self.scene.items()
                if isinstance(item, (DesignerBox, ImageItem, TableItem)) and not isinstance(item, BackgroundItem)
                and not isinstance(item.parentItem(), RectangleItem)
                and not getattr(item, "is_document_background", False)]

    def _board_selected_artwork(self):
        from .canvas_items import RectangleItem
        roots = set(self._board_artwork_roots())
        selected = {item.parentItem() if isinstance(item.parentItem(), RectangleItem) else item
                    for item in self.scene.selectedItems()}
        return list(roots & selected)

    def _sync_board_artwork_layers(self):
        if self._active_page_id != "organogram":
            return
        roots = self._board_artwork_roots()
        self._invalidate_board_cutouts()
        # Preserva as subclasses Python enquanto o Qt usa a ordem da pilha.
        self._board_artwork_refs = roots
        # Cada plano mantém a ordem das camadas. O fundo fica acima do papel
        # (-200), abaixo dos conectores (-20) e dos cartões (-10).
        for behind in (True, False):
            items = sorted((item for item in roots if getattr(item, "board_behind", False) == behind),
                           key=lambda item: (item.zValue(), -(getattr(item, "layer_id", None) or 0)))
            for index, item in enumerate(items):
                item.setZValue(-30 + index / (len(items) + 1) if behind else index)

    def change_board_artwork_position(self, behind):
        if self._active_page_id != "organogram" or getattr(self, "_board_connection_sources", None):
            return
        selected = self._board_selected_artwork()
        if not selected:
            return
        for item in selected:
            item.board_behind = bool(behind)
        self.refresh_layer_list()
        for item in self.scene.items():
            if isinstance(item, BoardConnectorItem):
                item.update()
        self.save_snapshot()
        self.organogram_panel.refresh()

    def change_board_border(self, *, _corner_changes=None, _enabled=None, _position=None, _scope=None, **changes):
        if self._active_page_id != "organogram" or getattr(self, "_board_connection_sources", None):
            return
        selected = [item for item in self.scene.selectedItems() if isinstance(item, BoardGroupItem)]
        if not selected:
            return
        candidate = self._board_state()
        identifiers = {item.data["id"] for item in selected}
        updated = {}
        for group in candidate["groups"]:
            if group["id"] in identifiers:
                # Materializa os dois estilos antes de mudar a aparência comum
                # de um arquivo antigo; editar um nunca muda o outro.
                previous = border_style(group)
                appearances = {target: {key: deepcopy(value) for key, value in border_style(group, target).items()
                                        if key in APPEARANCE_KEYS}
                               for target in ('cards', 'group')}
                style = {**previous, **changes}
                if _scope is not None:
                    # A aplicação controla a exibição. As aparências individuais
                    # continuam guardadas, inclusive quando um contorno se oculta.
                    style['target'] = _scope
                    enabled = previous['cards'] or previous['group']
                    style['cards'] = enabled and _scope in ('cards', 'both')
                    style['group'] = enabled and _scope in ('group', 'both')
                if _enabled is not None:
                    for target in ('cards', 'group'):
                        style[target] = _enabled and style['target'] in (target, 'both')
                if 'target' not in changes and ('cards' in changes or 'group' in changes):
                    if style['cards'] or style['group']:
                        style['target'] = 'both' if style['cards'] and style['group'] else 'cards' if style['cards'] else 'group'
                edited_targets = ('cards', 'group') if style['target'] == 'both' else (style['target'],)
                if _position is not None:
                    for target in edited_targets:
                        style[target + '_position'] = _position
                for target in edited_targets:
                    appearance = appearances[target]
                    appearance.update({key: deepcopy(value) for key, value in changes.items() if key in APPEARANCE_KEYS})
                    if 'radius_mm' in changes:
                        appearance.pop('corner_radii_mm', None)
                    if _corner_changes is not None:
                        radii = {key: appearance.get('corner_radii_mm', {}).get(key, appearance['radius_mm'])
                                 for key in ('top_left', 'top_right', 'bottom_left', 'bottom_right')}
                        appearance['corner_radii_mm'] = {**radii, **_corner_changes}
                for target, appearance in appearances.items():
                    style[target + '_style'] = appearance
                # Conserva os atributos legados como representação dos controles
                # ativos. A pintura usa sempre os estilos individuais acima.
                for key in APPEARANCE_KEYS:
                    style.pop(key, None)
                style.update(deepcopy(appearances[edited_targets[0]]))
                group["border"] = style
                updated[group["id"]] = group["border"]
        validate_organogram(candidate)
        for item in selected:
            item.prepareGeometryChange()
            item.data["border"] = deepcopy(updated[item.data["id"]])
            item.update()
        self._update_board_connections()
        self._update_board_extent()
        self.save_snapshot()

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
                self.organogram_panel.show_connection_message(tr("Mantenha pelo menos um lado permitido em cada entrada e saída."))
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
        previous_snap = getattr(self.scene, '_board_snap_suspended', False)
        self.scene._board_snap_suspended = True
        try:
            with self._board_visual_batch():
                for item in movable:
                    item.moveBy(delta.x(), delta.y())
        finally:
            self.scene._board_snap_suspended = previous_snap

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
        self._board_path_cache = None
        self._board_bounds_cache = None
        self._invalidate_board_cutouts()
        self._board_grid_mm = data.get("__board_grid_mm", 5)
        self._board_margin_mm = data.get("__board_margin_mm", 10)
        self._board_connector_style = {**connector_style(), **data.get("__board_connector_style", {})}
        self.scene._board_grid = self._board_grid_mm * UNITS_PER_MM if self._active_page_id == "organogram" else 0
        if self._active_page_id != "organogram":
            self._board_artwork_refs = []
            return
        self._sync_board_artwork_layers()
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None
        template = adapt_model_page(self._model_document, "front")
        if self._current_model_dir:
            template["__model_dir"] = str(self._current_model_dir)
        self._board_card_preview = self._visual_cache.card_preview(
            template, self._editor_asset_provider,
            lambda provider: NativeRenderer(template, asset_provider=provider).render_preview_image(max_side=640),
        )
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

    def _update_board_extent(self, *, refresh_panel=True):
        if self._active_page_id != "organogram" or getattr(self, "_loading_board", False):
            return
        rect = self._board_geometry()[3]
        changed = rect != self._get_document_rect()
        if changed:
            self._set_document_rect(rect)
        elif refresh_panel or getattr(self, '_board_workspace_dirty', False):
            self._update_workspace_scene_rect()
        self._board_workspace_dirty = False
        if self.fallback_bg:
            if self.fallback_bg.rect() != rect:
                self.fallback_bg.setRect(rect)
            brush = QBrush(Qt.GlobalColor.white)
            if self.fallback_bg.brush() != brush:
                self.fallback_bg.setBrush(brush)
        for control, value in ((self.spin_phys_w, rect.width() / UNITS_PER_MM),
                               (self.spin_phys_h, rect.height() / UNITS_PER_MM)):
            with QSignalBlocker(control):
                control.setValue(value)
        panel = getattr(self, "organogram_panel", None)
        if panel and (refresh_panel or changed):
            panel.refresh()

    def _add_board_edge(self, edge):
        item = BoardConnectorItem(self, edge)
        self.scene.addItem(item)
        return item

    @contextmanager
    def _board_visual_batch(self):
        # O Qt move os itens selecionados um a um dentro do mesmo evento.
        # Concluir a rota antes de devolver o evento evita geometria pendente
        # na pintura, na soltura perdida, em Esc e nas capturas do histórico.
        previous = getattr(self, '_board_defer_connections', False)
        self._board_defer_connections = True
        try:
            yield
        finally:
            self._board_defer_connections = previous
            if not previous and getattr(self, '_board_connections_pending', False):
                self._board_connections_pending = False
                self._update_board_connections()

    def _board_geometry_state(self):
        # Somente dados geométricos: não serializar HTML, placeholders ou assets
        # para calcular limites ou mostrar o tamanho sugerido no painel.
        from .canvas_items import DesignerBox, ImageItem, BackgroundItem, RectangleItem
        from .table_item import TableItem
        items = self.scene.items()
        groups = sorted((item.data for item in items if isinstance(item, BoardGroupItem)),
                        key=lambda data: data.get('order', 0))
        identifiers = {group['id'] for group in groups}
        edges = sorted((item.board_edge for item in items if isinstance(item, BoardConnectorItem)
                        and item.board_edge['source'] in identifiers and item.board_edge['target'] in identifiers),
                       key=lambda edge: (edge['source'], edge['target']))
        board = {'groups': groups, 'connections': edges, 'connector_style': self._board_connector_style,
                 'margin_mm': self._board_margin_mm, 'boxes': [], 'images': [], 'shapes': [], 'tables': []}
        for item in items:
            if not isinstance(item, (DesignerBox, ImageItem, TableItem)) or isinstance(item, BackgroundItem):
                continue
            if isinstance(item, TableItem):
                # artwork_bounds expande o traço antes da rotação. Conserva
                # essa geometria sem copiar células/HTML ou acessar a edição.
                data = item.data
                width = max([data['border']['width'],
                             *(edge['style'].get('width', data['border']['width']) for edge in data['edges'])])
                board['tables'].append({'x': float(item.x()), 'y': float(item.y()),
                    'rotation': float(item.rotation()), 'visible': item.isVisible(),
                    'column_widths': tuple(data['column_widths']), 'row_heights': tuple(data['row_heights']),
                    'border': {'width': width}, 'edges': []})
                continue
            rect = item.rect()
            entry = {'x': round(float(item.pos().x()), 2), 'y': round(float(item.pos().y()), 2),
                     'w': round(float(rect.width()), 2), 'h': round(float(rect.height()), 2),
                     'rotation': round(float(item.rotation()), 2), 'visible': item.isVisible()}
            collection = 'boxes' if isinstance(item, DesignerBox) else 'images'
            if isinstance(item, RectangleItem):
                collection = 'shapes'
                entry['outline_width'] = item.outline_width
            board[collection].append(entry)
        return board

    def _build_board_paths(self, board):
        routes = board_routes(board)
        return connector_paths(board, routes=routes), any(crowded for _, crowded in routes.values())

    def _board_geometry(self):
        board = self._board_geometry_state()
        group_key = []
        for group in board['groups']:
            rect = bordered_group_bounds(group)
            group_key.append((group['id'], rect.x(), rect.y(), rect.width(), rect.height(),
                              tuple(group.get('entry_sides', ['bottom'])), tuple(group.get('exit_sides', ['top']))))
        edge_key = []
        for edge in board['connections']:
            style = connector_style(edge, board)
            edge_key.append((edge['source'], edge['target'], style['width_mm'], style['radius_mm']))
        path_key = (tuple(group_key), tuple(edge_key))
        cached = getattr(self, '_board_path_cache', None)
        if cached is None or cached[0] != path_key:
            paths, crowded = self._build_board_paths(board)
            cached = self._board_path_cache = (path_key, paths, crowded)
        table_key = tuple((entry['x'], entry['y'], entry['rotation'], entry['visible'],
                           entry['column_widths'], entry['row_heights'], entry['border']['width'])
                          for entry in board['tables'])
        bounds_key = (path_key, board['margin_mm'], tuple(tuple(tuple(sorted(entry.items()))
                      for entry in board[key]) for key in ('boxes', 'images', 'shapes')), table_key)
        extent = getattr(self, '_board_bounds_cache', None)
        if extent is None or extent[0] != bounds_key:
            extent = self._board_bounds_cache = (bounds_key, board_bounds(board, paths=cached[1]))
        return board, cached[1], cached[2], QRectF(extent[1])

    def _invalidate_board_cutouts(self):
        previous = getattr(self, '_board_cutouts_cache', None)
        self._board_cutouts_cache = None
        self._board_workspace_dirty = True
        self._board_cutout_revision = getattr(self, '_board_cutout_revision', 0) + 1
        if previous is not None and not previous.isEmpty():
            self.scene.update(previous.boundingRect())

    def _build_board_cutouts(self):
        from .table_item import TableItem
        from .canvas_items import DesignerBox
        result = QPainterPath()
        result.setFillRule(Qt.FillRule.WindingFill)
        for item in self.scene.items():
            if (isinstance(item, (DesignerBox, TableItem)) and item.isVisible() and item.opacity() > 0
                    and not getattr(item, 'board_behind', False)):
                rect = QPainterPath()
                rect.addPolygon(item.mapToScene(item.rect()))
                rect.closeSubpath()
                result.addPath(rect)
        return result

    def _board_cutouts(self):
        cached = getattr(self, '_board_cutouts_cache', None)
        if cached is None:
            cached = self._board_cutouts_cache = self._build_board_cutouts()
        # Mantém a semântica de um resultado que o chamador pode modificar.
        return QPainterPath(cached)

    def _update_board_connections(self):
        if getattr(self, "_board_defer_connections", False):
            self._board_connections_pending = True
            return
        self._board_connections_pending = False
        if self._active_page_id != 'organogram':
            return
        board, paths, crowded, _ = self._board_geometry()
        groups = {group['id'] for group in board['groups']}
        self._board_routes_crowded = crowded
        for item in list(self._board_item_refs.values()):
            if not isValid(item) or item.scene() is not self.scene or not isinstance(item, BoardConnectorItem):
                continue
            edge = item.board_edge
            if edge['source'] not in groups or edge['target'] not in groups:
                self.scene.removeItem(item)
                continue
            pen = connector_pen(connector_style(edge, board))
            if item.pen() != pen:
                item.setPen(pen)
                self._board_workspace_dirty = True
            path = paths[(edge['source'], edge['target'])]
            if item.path() != path:
                item.setPath(path)
                self._board_workspace_dirty = True
        self._board_item_refs = {key: item for key, item in self._board_item_refs.items()
                                 if isValid(item) and item.scene() is self.scene}

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
            self.organogram_panel.show_connection_message(str(error))
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

    def add_model_organogram(self, *, show_chooser=True):
        self._finish_page_interaction()
        self.save_snapshot()
        if show_chooser:
            from .starter_dialog import StarterDialog
            chooser = StarterDialog("organogram", self, document=self._model_document)
            if chooser.exec() != QDialog.DialogCode.Accepted:
                return
            self._model_document, _provider = chooser.take_result()
        else:
            self._model_document = add_organogram(self._model_document)
        self._pending_history_page_id = "organogram"
        self.switch_model_page("organogram")
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
            self.organogram_panel.show_connection_message(tr("Selecione os blocos que receberão um superior e deixe um bloco disponível como destino."))
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
        with self._selection_batch():
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
        else:
            self.organogram_panel.refresh()
