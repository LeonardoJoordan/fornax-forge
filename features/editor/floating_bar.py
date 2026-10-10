"""Estrutura compartilhada das barras flutuantes do editor."""
from dataclasses import dataclass
from PySide6.QtCore import Qt, QEvent, QTimer, QSize, QPoint, QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QAction
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QBoxLayout, QLayout, QWidget,
                              QPushButton, QMenu, QGraphicsItem, QGraphicsOpacityEffect,
                              QLabel, QWidgetAction, QAbstractSpinBox, QComboBox)
from shiboken6 import isValid

from core.i18n import tr
from core.resources import state_icon_path
from core.theme_icons import tool_icon, themed_svg_icon
from core.themes import themed_style, theme_color, theme_manager


@dataclass(frozen=True)
class BarPresentation:
    """O contexto escolhe o conteúdo; o componente cuida de toda a apresentação."""
    tools: tuple
    hint: str = ''
    dockable: bool = True
    collapsible: bool = True


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
        vertical = self.bar.is_vertical
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
    """Registrar botões/menus e suas ações basta para compor uma nova barra.

    `presentation()` declara ferramentas, orientação textual e disponibilidade
    de arraste/recolhimento. Os contextos só fornecem seleção, estado e ações;
    não precisam implementar layouts, medidas, temas ou ancoragens.
    """
    DOCK_GAP = 20
    DOCK_SEPARATION = 30
    DOCK_SIDES = tuple(side + suffix for side in ('top', 'bottom', 'left', 'right')
                       for suffix in ('', '_far'))

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
        self._popup_focus = {}
        self._button_labels = {}
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
        # Todas as barras usam a mesma árvore visual, inclusive quando há
        # orientação acima dos botões (por exemplo, durante o enquadramento).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.hint = QLabel(self)
        self.hint.setObjectName('floatingHint')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setFixedWidth(260)
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        themed_style(self.hint, 'QLabel#floatingHint { background: transparent; color: @text@; '
                     'font-size: 12px; border: none; padding: 8px 8px 2px 8px; }')
        self.hint.hide()
        self.tools_row = QWidget(self)
        self.tools_row.setObjectName('floatingTools')
        themed_style(self.tools_row, 'QWidget#floatingTools { background: transparent; border: none; }')
        outer.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.tools_row, 0, Qt.AlignmentFlag.AlignHCenter)
        layout = QHBoxLayout(self.tools_row)
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
        self._size_cache.clear()
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
        self.schedule()

    def button(self, key, text, icon, tooltip, *, label_mode='compact'):
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
        self._button_labels[key] = (text, label_mode)
        return button

    def color_button(self, key, tooltip):
        return self.button(key, '', themed_svg_icon(state_icon_path('palette')), tooltip)

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

    def picker(self, key):
        """Popup de controles com a mesma superfície e opacidade da barra."""
        menu = self.menu(self.buttons[key])
        menu.setObjectName('tableFloatingAlignmentMenu')
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.alignment_menus[key] = menu
        picker = QWidget(menu)
        picker.setObjectName('tableFloatingAlignmentPicker')
        layout = QHBoxLayout(picker)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        action = QWidgetAction(menu)
        action.setDefaultWidget(picker)
        menu.addAction(action)
        return picker, layout

    def choice_menu(self, key, choices, callback):
        """Escolhas (valor, ícone, legenda), orientadas junto com a barra."""
        picker, layout = self.picker(key)
        menu = self.alignment_menus[key]
        self.alignment_layouts[key] = layout
        self.alignment_choices[key] = {}
        for value, icon, label in choices:
            action = QAction(icon, label, menu)
            action.setCheckable(True)
            self.actions[key+'_'+value] = action
            choice = QPushButton(icon, '', picker)
            choice.setObjectName('tableFloatingChoice_'+key+'_'+value)
            choice.setFixedSize(32, 34)
            choice.setIconSize(QSize(18, 18))
            choice.setToolTip(label)
            choice.setAccessibleName(label)
            choice.setCheckable(True)
            layout.addWidget(choice)
            self.alignment_choices[key][value] = choice
            choice.clicked.connect(lambda _=False, m=menu, a=action: (m.close(), a.trigger()))
            action.triggered.connect(lambda _=False, v=value: callback(v))
        return menu

    def set_popup_focus(self, key, widget):
        self._popup_focus[self.alignment_menus[key]] = widget

    def presentation(self):
        return BarPresentation(self.tool_keys())

    @staticmethod
    def dock_edge(side):
        return side.removesuffix('_far')

    @property
    def is_vertical(self):
        return self.dock_edge(self.dock_side) in ('left', 'right')

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
        axis = next((key for key in self.alignment_layouts
                     if self.alignment_menus[key] is menu), None)
        if axis is not None:
            layout = self.alignment_layouts[axis]
            direction = (QBoxLayout.Direction.TopToBottom if self.is_vertical
                         else QBoxLayout.Direction.LeftToRight)
            changed = layout.direction() != direction
            layout.setDirection(direction)
            layout.activate()
            layout.parentWidget().adjustSize()
            if changed:
                # QMenu guarda as medidas do QWidgetAction entre aberturas.
                action = menu.actions()[0]
                action.setVisible(False)
                action.setVisible(True)
        menu.adjustSize()
        edge = self.dock_edge(self.dock_side)
        if edge == 'left':
            position = QPoint(button.width()+4, 0)
        elif edge == 'right':
            position = QPoint(-menu.sizeHint().width()-4, 0)
        elif edge == 'bottom':
            position = QPoint(0, -menu.sizeHint().height()-4)
        else:
            position = QPoint(0, button.height()+4)
        menu.popup(button.mapToGlobal(position))
        focus = self._popup_focus.get(menu)
        if axis is not None:
            choices = list(self.alignment_choices[axis].values())
            focus = next((choice for choice in choices if choice.isChecked()), choices[0])
        if focus is not None:
            focus.setFocus(Qt.FocusReason.PopupFocusReason)
            if isinstance(focus, QAbstractSpinBox) or isinstance(focus, QComboBox) and focus.isEditable():
                focus.lineEdit().selectAll()

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
        presentation = self.presentation()
        collapsed = (self.collapsed if collapsed is None else collapsed) and presentation.collapsible
        vertical = self.dock_edge(side) in ('left', 'right')
        state = vertical, compact, collapsed, presentation
        if state == self._orientation:
            return
        self._orientation = state
        self.hint.setVisible(bool(presentation.hint))
        if presentation.hint:
            self.hint.setText(presentation.hint)
            self.hint.ensurePolished()
            self.hint.setFixedHeight(self.hint.heightForWidth(self.hint.width()))
        self.grip.setVisible(presentation.dockable)
        self._layout.setDirection(QBoxLayout.Direction.TopToBottom if vertical
                                  else QBoxLayout.Direction.LeftToRight)
        self._layout.setContentsMargins(*( (6, 8, 6, 8) if vertical else
                                           (6, 6, 6, 6) if compact else (8, 6, 8, 6) ))
        self._layout.setSpacing(1 if compact and not vertical else 4)
        self.grip.setFixedSize(32, 16) if vertical else self.grip.setFixedSize(16, 32)
        for key, button in self.buttons.items():
            button.setVisible(presentation.collapsible if key == 'collapse'
                              else not collapsed and key in presentation.tools)
            label, label_mode = self._button_labels[key]
            if label_mode == 'horizontal':
                button.setText('' if vertical or compact else label)
            if label_mode == 'always':
                width = button.fontMetrics().horizontalAdvance(button.text()) + button.iconSize().width() + 28
                button.setFixedWidth(width)
            elif vertical or compact or label_mode != 'horizontal':
                button.setFixedWidth(28 if compact and not vertical else 32)
            else:
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
        for separator in self._separators:
            separator.setVisible(not collapsed)
            separator.setFixedSize(22, 1) if vertical else separator.setFixedSize(1, 22)
        self.collapse_button.setIcon(tool_icon('<path d="M5 12h14M12 5v14"/>' if collapsed
                                               else '<path d="M5 12h14"/>'))
        self.collapse_button.setToolTip(self.collapse_tooltip(collapsed))
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
        self._layout.invalidate()
        # A medição das variantes é síncrona. Invalidar também os contêineres
        # evita reusar a largura horizontal ao recolher ou encaixar na lateral.
        self.tools_row.updateGeometry()
        self.layout().invalidate()
        self.grip.update()

    def dock_gap(self, edge):
        return self.DOCK_GAP

    def dock_geometries(self, rectangle, available, *, collapsed=None):
        collapsed = self.collapsed if collapsed is None else collapsed
        compact = available.width() < 420
        key = compact, self.presentation()
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
        for side in self.DOCK_SIDES:
            edge = self.dock_edge(side)
            size = horizontal if edge in ('top', 'bottom') else vertical
            full_size = expanded[0 if edge in ('top', 'bottom') else 1]
            thickness = full_size.height() if edge in ('top', 'bottom') else full_size.width()
            # A segunda posição começa depois da barra na primeira posição,
            # deixando 30 px livres entre elas, também quando recolhida.
            gap = self.dock_gap(edge) + (thickness + self.DOCK_SEPARATION if side.endswith('_far') else 0)
            width, height = size.width(), size.height()
            if width > available.width() or height > available.height():
                continue
            # Recolher preserva a extremidade onde ficam o botão e a alça.
            full_width, full_height = full_size.width(), full_size.height()
            if edge in ('top', 'bottom'):
                x = rectangle.center().x()-full_width//2
                y = rectangle.top()-height-gap if edge == 'top' else rectangle.bottom()+gap+1
                x = max(available.left(), min(x, available.right()-full_width+1))
                x += full_width-width
            else:
                x = rectangle.left()-width-gap if edge == 'left' else rectangle.right()+gap+1
                y = rectangle.center().y()-full_height//2
                y = max(available.top(), min(y, available.bottom()-full_height+1))
                y += full_height-height
            x = max(available.left(), min(x, available.right()-width+1))
            y = max(available.top(), min(y, available.bottom()-height+1))
            geometries[side] = QRect(x, y, width, height)
        return geometries

    def dock_target_geometries(self, rectangle, available):
        # O destaque conserva a espessura da barra. Só seu comprimento é
        # limitado pelo objeto, como nas quatro ancoragens originais.
        geometries = self.dock_geometries(rectangle, available, collapsed=False)
        for side, geometry in geometries.items():
            if self.dock_edge(side) in ('top', 'bottom'):
                width = min(geometry.width(), max(1, rectangle.width()))
                geometry.setWidth(width)
                x = rectangle.center().x()-width//2
                geometry.moveLeft(max(available.left(), min(x, available.right()-width+1)))
            else:
                height = min(geometry.height(), max(1, rectangle.height()))
                geometry.setHeight(height)
                y = rectangle.center().y()-height//2
                geometry.moveTop(max(available.top(), min(y, available.bottom()-height+1)))
        # O limite do viewport pode fazer dois destinos coincidirem por inteiro.
        # Sobreposição parcial mantém ambas as opções disponíveis.
        distinct = {}
        for side, geometry in geometries.items():
            if geometry not in distinct.values():
                distinct[side] = geometry
        return distinct

    def begin_dock_drag(self, global_position):
        item = self.controller.selected()
        if item is None or self.isHidden() or not self.presentation().dockable:
            return
        available = self.parentWidget().rect().adjusted(8, 8, -8, -8)
        rectangle = self.target_rectangle(item)
        # Os destinos acompanham os limites do objeto também com a barra recolhida.
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
        exact = [side for side, rect in self._drag_geometries.items() if rect.contains(point)]
        # Destinos próximos podem se sobrepor: prevalece aquele cujo centro
        # estiver mais perto do ponteiro, mantendo ambas as ancoragens acessíveis.
        candidates = exact or [side for side, rect in self._drag_geometries.items()
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
