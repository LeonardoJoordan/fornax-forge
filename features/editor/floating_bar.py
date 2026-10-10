"""Estrutura compartilhada das barras flutuantes do editor."""
from PySide6.QtCore import Qt, QEvent, QTimer, QSize, QPoint, QRect, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QBoxLayout, QLayout, QWidget,
                              QPushButton, QMenu, QGraphicsItem, QGraphicsOpacityEffect)
from shiboken6 import isValid

from core.i18n import tr
from core.theme_icons import tool_icon
from core.themes import themed_style, theme_color, theme_manager


class FloatingBarGrip(QWidget):
    """Alça de pontos; captura somente o arraste da barra, sem tocar a cena."""
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.setObjectName('tableFloatingGrip')
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(tr('Arraste para reposicionar a barra'))
        self.setAccessibleName(self.toolTip())
        themed_style(self, 'QWidget#tableFloatingGrip { background: transparent; border: none; }')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme_color('muted')))
        vertical = self.bar.dock_side in ('left', 'right')
        for column in range(3 if vertical else 2):
            for row in range(2 if vertical else 3):
                x = self.width()/2 + (column-(1 if vertical else .5))*5
                y = self.height()/2 + (row-(.5 if vertical else 1))*5
                painter.drawEllipse(QRectF(x-1.2, y-1.2, 2.4, 2.4))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.bar.begin_dock_drag(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self.bar._dragging:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self.bar.end_dock_drag()
            else:
                self.bar.move_dock_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.bar._dragging:
            self.bar.end_dock_drag(event.globalPosition().toPoint())
            event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.UngrabMouse and self.bar._dragging:
            self.bar.end_dock_drag(restore_focus=False)
        return super().event(event)


class FloatingBar(QWidget):
    def __init__(self, controller):
        self.controller = controller
        self.view = controller.window.view
        super().__init__(self.view.viewport())
        self.setObjectName('tableFloatingBar')
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.buttons, self.actions, self.menus = {}, {}, []
        self.alignment_choices = {}
        self.alignment_menus = {}
        self.alignment_layouts = {}
        self._menu_target = None
        self.dock_side = 'top'
        self.collapsed = False
        self._dragging = False
        self._dock_targets = {}
        self._size_cache = {}
        self._orientation = None
        self._separators = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.reposition)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        self._layout = layout
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.grip = FloatingBarGrip(self)

    def finish_setup(self):
        self.collapse_button = self.button('collapse', '', tool_icon('<path d="M5 12h14"/>'),
                                           self.collapse_tooltip(False))
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        self._layout.addWidget(self.grip)
        self.refresh_surface_style()
        theme_manager().changed.connect(self.refresh_surface_style)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self.controller.window.installEventFilter(self)
        for scroll in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            scroll.valueChanged.connect(self.schedule)
        self.hide()

    def refresh_surface_style(self):
        # Transparência só na superfície; os controles mantêm contraste integral.
        def surface_color(role):
            color = QColor(theme_color(role))
            return f'rgba({color.red()}, {color.green()}, {color.blue()}, 191)'

        themed_style(self, '''
            QWidget#tableFloatingBar { background: SURFACE; border: 1px solid OUTLINE; border-radius: 8px; }
            QWidget#tableFloatingBar QPushButton { background: @button@; color: @text@;
                border: 1px solid transparent; border-radius: 5px; padding: 4px 6px;
                min-height: 24px; font-size: 12px; }
            QWidget#tableFloatingBar QPushButton:hover { background: @hover@; border-color: @border_strong@; }
            QWidget#tableFloatingBar QPushButton:checked { background: @selection@; border-color: @accent@; }
            QWidget#tableFloatingBar QPushButton:disabled { color: @disabled@; background: @panel@; }
            QWidget#tableFloatingBar QFrame#tableFloatingSeparator { background: @border@; border: none; }
        '''.replace('SURFACE', surface_color('panel'))
            .replace('OUTLINE', surface_color('border_strong'))
            .replace('tableFloatingBar', self.objectName()))
        for menu in self.alignment_menus.values():
            themed_style(menu, '''
                QMenu#tableFloatingAlignmentMenu {
                    background: SURFACE; border: 1px solid OUTLINE;
                    border-radius: 8px; padding: 0px; margin: 0px;
                }
                QMenu#tableFloatingAlignmentMenu::item {
                    background: transparent; border: none; padding: 0px; margin: 0px;
                }
                QMenu#tableFloatingAlignmentMenu::item:selected { background: transparent; }
                QWidget#tableFloatingAlignmentPicker { background: transparent; border: none; }
            '''.replace('SURFACE', surface_color('panel'))
                .replace('OUTLINE', surface_color('border_strong')))

    def button(self, key, text, icon, tooltip):
        button = QPushButton(text, self)
        button.setObjectName('tableFloating_'+key)
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if not text:
            button.setFixedWidth(32)
        self._layout.addWidget(button)
        self.buttons[key] = button
        return button

    def separator(self):
        separator = QFrame(self)
        separator.setObjectName('tableFloatingSeparator')
        separator.setFixedSize(1, 22)
        opacity = QGraphicsOpacityEffect(separator)
        opacity.setOpacity(.75)
        separator.setGraphicsEffect(opacity)
        self._separators.append(separator)
        self._layout.addWidget(separator)

    def menu(self, button):
        menu = QMenu(self)
        self.menus.append(menu)
        button.clicked.connect(lambda: self.popup(button, menu))
        return menu

    def target_key(self, item):
        return item.data['object_id']

    def target_rectangle(self, item):
        return self.view.mapFromScene(item.mapToScene(item.rect())).boundingRect()

    def target_available(self, item):
        return (item is not None and getattr(item, 'overlays_enabled', True)
                and item.isVisible()
                and bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable))

    def tool_keys(self):
        return tuple(key for key in self.buttons if key != 'collapse')

    def collapse_tooltip(self, collapsed):
        return tr('Expandir barra de ferramentas') if collapsed else tr('Recolher barra de ferramentas')

    def popup(self, button, menu):
        item = self.controller.selected()
        if item is None:
            return
        self._menu_target = self.target_key(item)
        self.show_menu(button, menu)

    def show_menu(self, button, menu):
        menu.adjustSize()
        if self.dock_side == 'left':
            position = QPoint(button.width()+4, 0)
        elif self.dock_side == 'right':
            position = QPoint(-menu.sizeHint().width()-4, 0)
        elif self.dock_side == 'bottom':
            position = QPoint(0, -menu.sizeHint().height()-4)
        else:
            position = QPoint(0, button.height()+4)
        menu.popup(button.mapToGlobal(position))

    def restore_focus(self):
        self.view.setFocus(Qt.FocusReason.OtherFocusReason)

    def schedule(self, *_args):
        if not self._timer.isActive():
            self._timer.start(0)

    def toggle_collapsed(self):
        self.end_dock_drag(restore_focus=False)
        for menu in self.menus:
            menu.close()
        self.collapsed = not self.collapsed
        self.reposition()
        self.restore_focus()

    def eventFilter(self, source, event):
        if self._dragging:
            if event.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.Hide):
                self.end_dock_drag(restore_focus=False)
            elif event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
                if event.key() == Qt.Key.Key_Escape:
                    if event.type() == QEvent.Type.KeyPress:
                        self.end_dock_drag()
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.Resize:
                self.end_dock_drag(restore_focus=False)
        if event.type() in (QEvent.Type.Paint, QEvent.Type.Resize, QEvent.Type.Show):
            self.schedule()
        return False

    def configure_orientation(self, side, compact, *, collapsed=None):
        collapsed = self.collapsed if collapsed is None else collapsed
        vertical = side in ('left', 'right')
        labels = (tr('Linhas'), tr('Colunas'))
        state = vertical, compact, labels, collapsed, self.tool_keys()
        if state == self._orientation:
            return
        self._orientation = state
        self._layout.setDirection(QBoxLayout.Direction.TopToBottom if vertical
                                  else QBoxLayout.Direction.LeftToRight)
        self._layout.setContentsMargins(*( (6, 8, 6, 8) if vertical else
                                           (6, 6, 6, 6) if compact else (8, 6, 8, 6) ))
        self._layout.setSpacing(1 if compact and not vertical else 4)
        self.grip.setFixedSize(32, 16) if vertical else self.grip.setFixedSize(16, 32)
        for key, button in self.buttons.items():
            button.setVisible(key == 'collapse' or (not collapsed and key in self.tool_keys()))
            if key in ('rows', 'columns'):
                button.setText('' if vertical or compact else labels[0 if key == 'rows' else 1])
            if vertical or compact or key not in ('rows', 'columns'):
                button.setFixedWidth(28 if compact and not vertical else 32)
            else:
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
        for separator in self._separators:
            separator.setVisible(not collapsed)
            separator.setFixedSize(22, 1) if vertical else separator.setFixedSize(1, 22)
        self.collapse_button.setIcon(tool_icon('<path d="M5 12h14M12 5v14"/>' if collapsed
                                               else '<path d="M5 12h14"/>'))
        self.collapse_button.setToolTip(tr('Expandir barra da tabela') if collapsed
                                       else self.collapse_tooltip(False))
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
        self._layout.invalidate()
        self.grip.update()

    def dock_geometries(self, rectangle, available, *, collapsed=None):
        collapsed = self.collapsed if collapsed is None else collapsed
        compact = available.width() < 420
        key = compact, tr('Linhas'), tr('Colunas'), self.tool_keys()
        if key not in self._size_cache:
            sizes = []
            for size_collapsed in (False, True):
                self.configure_orientation('top', compact, collapsed=size_collapsed)
                horizontal = QSize(self.sizeHint())
                self.configure_orientation('left', compact, collapsed=size_collapsed)
                vertical = QSize(self.sizeHint())
                sizes.append((horizontal, vertical))
            self._size_cache[key] = sizes
        self.configure_orientation(self.dock_side, compact)
        expanded = self._size_cache[key][0]
        horizontal, vertical = self._size_cache[key][int(collapsed)]
        geometries = {}
        for side, size in (('top', horizontal), ('bottom', horizontal),
                           ('left', vertical), ('right', vertical)):
            width, height = size.width(), size.height()
            if width > available.width() or height > available.height():
                continue
            # Recolher preserva a extremidade onde ficam o botão e a alça.
            full_size = expanded[0 if side in ('top', 'bottom') else 1]
            full_width, full_height = full_size.width(), full_size.height()
            if side in ('top', 'bottom'):
                x = rectangle.center().x()-full_width//2
                y = rectangle.top()-height-16 if side == 'top' else rectangle.bottom()+17
                x = max(available.left(), min(x, available.right()-full_width+1))
                x += full_width-width
            else:
                x = rectangle.left()-width-16 if side == 'left' else rectangle.right()+17
                y = rectangle.center().y()-full_height//2
                y = max(available.top(), min(y, available.bottom()-full_height+1))
                y += full_height-height
            x = max(available.left(), min(x, available.right()-width+1))
            y = max(available.top(), min(y, available.bottom()-height+1))
            geometries[side] = QRect(x, y, width, height)
        return geometries

    def dock_target_geometries(self, rectangle, available):
        # Só os destaques são encurtados; o encaixe continua usando a barra inteira.
        geometries = self.dock_geometries(rectangle, available, collapsed=False)
        for side, geometry in geometries.items():
            if side in ('top', 'bottom'):
                width = min(geometry.width(), max(1, rectangle.width()))
                geometry.setWidth(width)
                x = rectangle.center().x()-width//2
                geometry.moveLeft(max(available.left(), min(x, available.right()-width+1)))
            else:
                height = min(geometry.height(), max(1, rectangle.height()))
                geometry.setHeight(height)
                y = rectangle.center().y()-height//2
                geometry.moveTop(max(available.top(), min(y, available.bottom()-height+1)))
        return geometries

    def begin_dock_drag(self, global_position):
        item = self.controller.selected()
        if item is None or self.isHidden():
            return
        available = self.parentWidget().rect().adjusted(8, 8, -8, -8)
        rectangle = self.target_rectangle(item)
        # Os destinos acompanham os limites da tabela também com a barra recolhida.
        self._drag_geometries = self.dock_target_geometries(rectangle, available)
        self._drag_target_id = self.target_key(item)
        self._drag_offset = self.parentWidget().mapFromGlobal(global_position)-self.pos()
        self._dragging = True
        self.grip.setCursor(Qt.CursorShape.ClosedHandCursor)
        for menu in self.menus:
            menu.close()
        for side, geometry in self._drag_geometries.items():
            if side == self.dock_side:
                continue
            if side not in self._dock_targets:
                target = QFrame(self.parentWidget())
                target.setObjectName('tableDockTarget')
                target.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                target.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                opacity = QGraphicsOpacityEffect(target)
                opacity.setOpacity(.5)
                target.setGraphicsEffect(opacity)
                self._dock_targets[side] = target
            target = self._dock_targets[side]
            self.style_target(target, False)
            target.setGeometry(geometry)
            target.show()
            target.raise_()
        self.raise_()

    @staticmethod
    def style_target(target, active):
        if target.property('active') == active:
            return
        target.setProperty('active', active)
        # Com o efeito de 50%, estes alphas resultam em ~35% / 50%.
        themed_style(target, 'QFrame#tableDockTarget { background: rgba(160, 164, 171, '+
                     ('255' if active else '179')+'); border: '+
                     ('2px solid @accent@' if active else '1px dashed @border_strong@')+
                     '; border-radius: 8px; }')

    def target_at(self, point):
        candidates = [side for side, rect in self._drag_geometries.items()
                      if rect.adjusted(-20, -20, 20, 20).contains(point)]
        return min(candidates, key=lambda side: (self._drag_geometries[side].center()-point).manhattanLength()) if candidates else None

    def move_dock_drag(self, global_position):
        if not self._dragging:
            return
        point = self.parentWidget().mapFromGlobal(global_position)
        position = point-self._drag_offset
        available = self.parentWidget().rect().adjusted(8, 8, -8, -8)
        position.setX(max(available.left(), min(position.x(), available.right()-self.width()+1)))
        position.setY(max(available.top(), min(position.y(), available.bottom()-self.height()+1)))
        self.move(position)
        chosen = self.target_at(point)
        for side, target in self._dock_targets.items():
            if target.isVisible():
                self.style_target(target, chosen == side)

    def end_dock_drag(self, global_position=None, *, restore_focus=True, reposition=True):
        if not self._dragging:
            return
        item = self.controller.selected()
        if (global_position is not None and item is not None
                and self.target_key(item) == self._drag_target_id):
            side = self.target_at(self.parentWidget().mapFromGlobal(global_position))
            if side is not None:
                self.dock_side = side
        self._dragging = False
        self.grip.setCursor(Qt.CursorShape.OpenHandCursor)
        for target in self._dock_targets.values():
            target.hide()
        if QWidget.mouseGrabber() is self.grip:
            self.grip.releaseMouse()
        if reposition:
            self.reposition()
        if restore_focus:
            self.restore_focus()

    def reposition(self):
        if not isValid(self.view) or not isValid(self.controller.window):
            return
        item = self.controller.selected()
        available = self.parentWidget().rect().adjusted(8, 8, -8, -8)
        if not self.target_available(item) or not self.view.isVisible():
            self.dismiss()
            return
        if self.target_key(item) != self._menu_target:
            for menu in self.menus:
                if menu.isVisible():
                    menu.close()
        rectangle = self.target_rectangle(item)
        if not rectangle.intersects(available):
            self.dismiss()
            return
        if self._dragging:
            if self.target_key(item) == self._drag_target_id:
                return
            self.end_dock_drag(restore_focus=False, reposition=False)
        geometry = self.dock_geometries(rectangle, available).get(self.dock_side)
        if geometry is None:
            self.dismiss()
            return
        if geometry != self.geometry():
            self.setGeometry(geometry)
        if self.isHidden():
            self.show()
            self.raise_()

    def dismiss(self):
        self.end_dock_drag(restore_focus=False, reposition=False)
        for menu in self.menus:
            if menu.isVisible():
                menu.close()
        if not self.isHidden():
            self.hide()
