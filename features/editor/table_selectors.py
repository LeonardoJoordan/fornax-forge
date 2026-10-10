"""Cabeçalhos temporários de seleção: controles do viewport, nunca da arte."""
from math import atan2, degrees, hypot

from PySide6.QtCore import QObject, QEvent, QTimer, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QPainter, QRegion
from PySide6.QtWidgets import QPushButton, QGraphicsItem
from shiboken6 import isValid

from core.i18n import tr
from core.resources import object_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import theme_manager


class TableSelectorButton(QPushButton):
    SIZE = 24
    ICON_SIZE = 15

    def __init__(self, owner, axis, index):
        super().__init__(owner.view.viewport())
        self.owner, self.axis, self.index = owner, axis, index
        self.angle = 0
        self._additive = False
        self._press_target = None
        self.setObjectName('tableSelector_'+axis+'_'+str(index))
        # A área de clique é maior que o SVG, mas não desenha fundo ou caixa.
        self.setStyleSheet('QPushButton { min-width: 0px; min-height: 0px; padding: 0px; '
                          'border: none; background: transparent; }')
        asset = {'row': 'arrow-right', 'column': 'arrow-down', 'all': 'arrow-down-right'}[axis]
        self.setIcon(themed_svg_icon(object_icon_path(asset), role='canvas_selection'))
        label = {'row': tr('Selecionar linha {number}'),
                 'column': tr('Selecionar coluna {number}'),
                 'all': tr('Selecionar todas as células')}[axis].format(number=index+1)
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.clicked.connect(self.select)
        self.hide()

    def select(self):
        additive, self._additive = self._additive, False
        target, self._press_target = self._press_target, None
        if target is not None and target is not self.owner._target:
            return
        self.owner.select(self.axis, self.index, additive=additive)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(QRectF(self.rect()).center())
        painter.rotate(self.angle)
        size = min(self.ICON_SIZE, self.width()-4, self.height()-4)
        self.icon().paint(painter, QRect(-size//2, -size//2, size, size))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self._press_target = self.owner._target
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._additive = False
        self._press_target = None


class TableSelectors(QObject):
    # Distância e tamanho em pixels de tela, independentes do zoom da arte.
    # O SVG tem margens internas: centro a 10 px deixa o traço a ~5 px da tabela.
    DISTANCE = 10
    BAR_GAP = 20

    def __init__(self, controller):
        super().__init__(controller.window.view)
        self.controller = controller
        self.view = controller.window.view
        self.buttons = {}
        self._target = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.reposition)
        self.view.installEventFilter(self)
        self.view.viewport().installEventFilter(self)
        self.view.scene().selectionChanged.connect(self.schedule)
        self.view.scene().changed.connect(self.schedule)
        for scroll in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            scroll.valueChanged.connect(self.schedule)
        theme_manager().changed.connect(self.refresh_theme)

    def refresh_theme(self):
        for button in self.buttons.values():
            button.update()
        self.schedule()

    def schedule(self, *_args):
        if not self._timer.isActive():
            self._timer.start(0)

    def eventFilter(self, source, event):
        if event.type() in (QEvent.Type.Paint, QEvent.Type.Resize, QEvent.Type.Show,
                            QEvent.Type.Hide):
            self.schedule()
        return False

    def select(self, axis, index, *, additive=False):
        item = self.controller.selected()
        if (item is None or item is not self._target or not item.overlays_enabled
                or not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
            return
        self.controller.window.table_edit.finish()
        self.controller.window.canvas_edit.finish()
        item.finish_cell_selection_gesture()
        cells = item.data['cells']
        if axis in ('row', 'column'):
            count = item.data['rows' if axis == 'row' else 'columns']
            if not 0 <= index < count:
                return
            span = axis+'_span'
            cells = [c for c in cells if c[axis] <= index < c[axis]+c[span]]
        identities = {c['id'] for c in cells}
        if additive and item.selected_range is not None:
            identities.update(c['id'] for c in item.selected_cells())
        self.view.setFocus(Qt.FocusReason.MouseFocusReason)
        item.set_cell_selection(identities)

    def reposition(self):
        if not isValid(self.view):
            return
        item = self.controller.selected()
        available = (item is not None and item.overlays_enabled and item.isVisible()
                     and self.view.isVisible()
                     and bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable))
        self._target = item if available else None
        positions = {}
        blocked = QRegion()
        if available:
            # A área invisível de clique não intercepta o corpo da tabela nem
            # suas alças verdes, mesmo estando próxima da borda.
            blocked = QRegion(self.view.mapFromScene(item.mapToScene(item.rect())))
            for handle in item.resize_handles.values():
                if handle.isVisible():
                    blocked |= QRegion(self.view.mapFromScene(handle.sceneBoundingRect()).boundingRect())
            # viewportTransform mantém precisão subpixel e inclui rotação/pan.
            transform = item.deviceTransform(self.view.viewportTransform())
            origin = transform.map(QPointF())
            x_axis = transform.map(QPointF(1, 0))-origin
            y_axis = transform.map(QPointF(0, 1))-origin
            x_scale, y_scale = hypot(x_axis.x(), x_axis.y()), hypot(y_axis.x(), y_axis.y())
            if x_scale > 0 and y_scale > 0:
                angle = degrees(atan2(x_axis.y(), x_axis.x()))
                top = -y_axis/y_scale*self.DISTANCE
                left = -x_axis/x_scale*self.DISTANCE
                positions['all', 0] = (origin+top+left, TableSelectorButton.SIZE, TableSelectorButton.SIZE, angle)
                for axis, tracks, centers, offset, scale in (
                    ('column', item.data['column_widths'], item.layout.x, top, x_scale),
                    ('row', item.data['row_heights'], item.layout.y, left, y_scale)):
                    for index, length in enumerate(tracks):
                        local = QPointF(centers[index]+length/2, 0) if axis == 'column' else QPointF(0, centers[index]+length/2)
                        # Em zoom muito baixo, a área acompanha o espaço real
                        # da linha/coluna para não interceptar o seletor vizinho.
                        if length*scale < 8:
                            continue  # Aumentar o zoom torna esses seletores acessíveis.
                        extent = min(TableSelectorButton.SIZE, int(length*scale))
                        width = extent if axis == 'column' else TableSelectorButton.SIZE
                        height = extent if axis == 'row' else TableSelectorButton.SIZE
                        if abs(x_axis.y()) > abs(x_axis.x()):
                            width, height = height, width
                        positions[axis, index] = (transform.map(local)+offset, width, height, angle)
        for key, button in self.buttons.items():
            if key not in positions:
                button.hide()
        viewport = self.view.viewport().rect()
        bar = self.controller.floating_bar
        if bar.isVisible():
            blocked |= QRegion(bar.geometry())
        for key, (center, width, height, angle) in positions.items():
            geometry = QRect(0, 0, width, height)
            geometry.moveCenter(center.toPoint())
            visible = viewport.contains(geometry)
            if not visible and key not in self.buttons:
                continue
            button = self.buttons.get(key)
            if button is None:
                button = self.buttons[key] = TableSelectorButton(self, *key)
            if button.geometry() != geometry:
                button.setGeometry(geometry)
            hit_area = QRegion(button.rect())-blocked.translated(-geometry.x(), -geometry.y())
            visible = visible and not hit_area.isEmpty()
            if button.mask() != hit_area:
                button.setMask(hit_area)
            if button.angle != angle:
                button.angle = angle
                button.update()
            if button.isHidden() == visible:
                button.setVisible(visible)
                if visible:
                    button.raise_()
