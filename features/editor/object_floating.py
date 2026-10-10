"""Atalhos mínimos para formas, agrupamento e conexão de blocos."""
from PySide6.QtCore import Qt, QSignalBlocker, QRect, QRectF, QObject, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDoubleSpinBox, QWidget, QHBoxLayout, QVBoxLayout, QWidgetAction, QGraphicsItem, QApplication, QLabel
from shiboken6 import isValid

from core.i18n import tr
from core.resources import action_icon_path, state_icon_path
from core.theme_icons import themed_svg_icon, tool_icon
from core.themes import themed_style
from .canvas_items import RectangleItem, DesignerBox, ImageItem, SignatureItem, BackgroundItem
from .organogram_editor import BoardGroupItem
from .table_item import TableItem
from .floating_bar import FloatingBar


class MaskImagePicker(QObject):
    """Intercepção temporária antes de selecionar, arrastar ou editar uma camada."""
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.shape = None
        self.hint = QLabel(bar.view.viewport())
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        themed_style(self.hint, 'background: @panel@; color: @text@; padding: 8px; border-radius: 6px;')
        self.hint.hide()

    def start(self, target):
        bar = self.bar
        shape = bar.selected()
        if (shape is None or bar.target_key(shape) != target
                or shape.dynamic_image_field or shape.masked_images()):
            return
        self.cancel(refresh=False)
        self.shape, self.target = shape, target
        self.scene = bar.window.scene
        self.cursor = bar.view.viewport().cursor()
        self.hint.setText(tr('Clique em uma imagem no canvas ou em Camadas. Esc cancela.'))
        self.hint.setMaximumWidth(max(1, bar.view.viewport().width()-16))
        self.hint.adjustSize()
        self.hint.move(max(0, (bar.view.viewport().width()-self.hint.width())//2), 8)
        self.hint.show(); self.hint.raise_()
        bar.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        QApplication.instance().installEventFilter(self)
        bar.refresh()
        bar.restore_focus()

    def valid_target(self):
        bar = self.bar
        return (self.shape is not None and isValid(self.shape)
                and self.scene is bar.window.scene and self.shape.scene() is self.scene
                and bar.target_key(self.shape) == self.target
                and not self.shape.dynamic_image_field and not self.shape.masked_images())

    def cancel(self, refresh=True):
        if self.shape is None:
            return
        self.shape = None
        QApplication.instance().removeEventFilter(self)
        self.hint.hide()
        self.bar.view.viewport().setCursor(self.cursor)
        if refresh:
            self.bar.refresh()

    def choose(self, image):
        valid = self.valid_target()
        target = self.target
        self.cancel()
        if valid and image is not None and isValid(image):
            self.bar.apply_mask(image, target)

    def eventFilter(self, source, event):
        if self.shape is None:
            return False
        w = self.bar.window
        if not self.valid_target():
            self.cancel()
            return False
        kind = event.type()
        if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
            event.accept()
            if kind == QEvent.Type.KeyPress:
                self.cancel()
            return True
        if source is w and kind in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate):
            self.cancel()
        if source is w.view.viewport() and kind == QEvent.Type.Resize:
            self.cancel()
        if kind not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return False
        # Eventos reais passam pelo QWindow antes de chegar ao QWidget sob o
        # mouse. Essa primeira passagem ainda não identifica o alvo do clique.
        if not isinstance(source, QWidget):
            return False
        canvas = source is w.view.viewport()
        layers = source is w.layer_list or w.layer_list.isAncestorOf(source)
        if event.button() != Qt.MouseButton.LeftButton:
            if canvas or layers:
                self.cancel()
                return True
            return False
        if canvas:
            image = w.view.itemAt(event.position().toPoint())
            # Alças/overlays não são imagens; não atravessar objetos sobrepostos.
        elif layers:
            point = w.layer_list.viewport().mapFromGlobal(event.globalPosition().toPoint())
            row = w.layer_list.itemAt(point)
            image = row.data(Qt.ItemDataRole.UserRole) if row else None
        else:
            self.cancel()
            return False
        self.choose(image if w._is_mask_image(image) else None)
        return True


class ObjectFloatingBar(FloatingBar):
    def __init__(self, window):
        self.window = window
        self.kind = None
        super().__init__(self)
        self.setObjectName('objectFloatingBar')
        # A orientação pertence à sessão de enquadramento; os demais contextos
        # mantêm a mesma linha de ferramentas, sem espaço reservado para texto.
        tools_row = QWidget(self)
        tools_row.setObjectName('objectFloatingTools')
        tools_row.setLayout(self._layout)
        themed_style(tools_row, 'QWidget#objectFloatingTools { background: transparent; border: none; }')
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.mask_edit_hint = QLabel(tr('Ajuste o enquadramento da imagem e clique em Concluir.'), self)
        self.mask_edit_hint.setObjectName('maskEditHint')
        self.mask_edit_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mask_edit_hint.setWordWrap(True)
        self.mask_edit_hint.setFixedWidth(260)
        self.mask_edit_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        themed_style(self.mask_edit_hint, 'QLabel#maskEditHint { background: transparent; color: @text@; '
                     'font-size: 12px; border: none; padding: 8px 8px 2px 8px; }')
        self.mask_edit_hint.hide()
        outer_layout.addWidget(self.mask_edit_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addWidget(tools_row, 0, Qt.AlignmentFlag.AlignHCenter)
        button = self.button('fill', '', tool_icon(
            '<path d="m12 3 8 8-9 9-8-8 9-9ZM3 12h17M8 2l5 5"/>'), tr('Cor do preenchimento'))
        button.clicked.connect(self.choose_fill)
        button = self.button('outline', '', tool_icon('<rect x="4" y="4" width="16" height="16"/>'),
                             tr('Habilitar contorno'))
        button.setCheckable(True)
        button.clicked.connect(lambda: self.invoke('outline'))
        opacity = self.button('opacity', '', themed_svg_icon(state_icon_path('opacity')), tr('Opacidade'))
        menu = self.menu(opacity)
        menu.setObjectName('tableFloatingAlignmentMenu')
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.alignment_menus['opacity'] = menu
        picker = QWidget(menu)
        picker.setObjectName('tableFloatingAlignmentPicker')
        layout = QHBoxLayout(picker); layout.setContentsMargins(5, 5, 5, 5)
        self.opacity_spin = QDoubleSpinBox(picker)
        self.opacity_spin.setRange(0, 100); self.opacity_spin.setDecimals(0)
        self.opacity_spin.setSuffix(' %'); self.opacity_spin.setKeyboardTracking(False)
        self.opacity_spin.setAccessibleName(tr('Opacidade'))
        layout.addWidget(self.opacity_spin)
        action = QWidgetAction(menu); action.setDefaultWidget(picker); menu.addAction(action)
        self.opacity_spin.editingFinished.connect(self.apply_opacity)
        mask = self.button('mask', '', tool_icon('<rect x="3" y="3" width="18" height="18"/><circle cx="12" cy="12" r="6"/>'),
                           tr('Usar como máscara'))
        mask.setCheckable(True)
        self.mask_menu = self.menu(mask)
        self.mask_picker = MaskImagePicker(self)
        button = self.button('group', '', themed_svg_icon(action_icon_path('unlock ratio')), tr('Agrupar'))
        button.clicked.connect(lambda: self.invoke('group'))
        button = self.button('connect', '', tool_icon('<rect x="3" y="3" width="6" height="6"/><rect x="15" y="15" width="6" height="6"/><path d="M6 9v9h9"/>'),
                             tr('Conectar a elemento'))
        button.clicked.connect(lambda: self.invoke('connect'))
        button = self.button('mask_cancel', tr('Cancelar'), tool_icon('<path d="m6 6 12 12M18 6 6 18"/>'),
                             tr('Cancelar'))
        button.clicked.connect(lambda: self.finish_mask(False))
        button = self.button('mask_finish', tr('Concluir'), tool_icon('<path d="m5 12 4 4L19 6"/>'),
                             tr('Concluir'))
        button.clicked.connect(lambda: self.finish_mask(True))
        self.finish_setup()
        controls = window._shape_quick_controls
        for signal in (controls['color'].editingFinished, controls['outline'].toggled,
                       window.caixa_texto_panel.spin_opacity.valueChanged):
            signal.connect(self.refresh)

    def selection(self):
        w = self.window
        if (not isValid(w) or not isValid(w.scene)
                or getattr(w, '_board_connection_sources', None)):
            return None, ()
        session = w._mask_edit_session
        if session:
            shape, image = session['shape'], session['image']
            if (isValid(shape) and isValid(image) and shape.scene() is w.scene
                    and image.scene() is w.scene and shape.isVisible()):
                return 'mask_edit', (shape,)
            return None, ()
        items = tuple(w.scene.selectedItems())
        if not items or any(not isValid(item) or not item.isVisible()
                            or not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                            for item in items):
            return None, ()
        if all(isinstance(item, BoardGroupItem) for item in items):
            return 'board', items
        if any(isinstance(item, (BoardGroupItem, BackgroundItem))
               or getattr(item, 'is_document_background', False) for item in items):
            return None, ()
        if (all(isinstance(item, (DesignerBox, ImageItem, SignatureItem, TableItem))
                and not isinstance(item.parentItem(), RectangleItem) for item in items)
                and (len(items) >= 2 or getattr(items[0], 'group_id', None) is not None)):
            return 'group', items
        if (len(items) == 1 and isinstance(items[0], RectangleItem)
                and items[0].shape_type in ('rectangle', 'ellipse', 'circle')):
            return 'shape', items
        return None, ()

    def selected(self):
        if self.mask_picker.shape is not None:
            return None
        kind, items = self.selection()
        return items[0] if kind else None

    def target_key(self, item):
        kind, items = self.selection()
        if kind == 'mask_edit':
            return self.window._active_page_id, kind, id(self.window._mask_edit_session)
        return self.window._active_page_id, kind, tuple(sorted(id(member) for member in items))

    def target_available(self, item):
        if self.kind == 'mask_edit':
            # A forma fica bloqueada durante o enquadramento, mas continua
            # sendo a referência fixa da barra enquanto a imagem se move.
            return item is not None and isValid(item) and item.isVisible()
        return super().target_available(item)

    def target_rectangle(self, item):
        _, items = self.selection()
        bounds = QRectF()
        for member in items:
            rectangle = member.mapToScene(member.rect()).boundingRect()
            bounds = rectangle if bounds.isNull() else bounds.united(rectangle)
        return self.view.mapFromScene(bounds).boundingRect() if items else QRect()

    def tool_keys(self):
        return {'shape': ('fill', 'outline', 'opacity', 'mask'),
                'group': ('group',), 'board': ('connect',),
                'mask_edit': ('mask_cancel', 'mask_finish')}.get(self.kind, ())

    def configure_orientation(self, side, compact, *, collapsed=None):
        editing = self.kind == 'mask_edit'
        super().configure_orientation(side, compact, collapsed=False if editing else collapsed)
        self.mask_edit_hint.setVisible(editing)
        self.grip.setVisible(not editing)
        if editing:
            self.mask_edit_hint.ensurePolished()
            self.mask_edit_hint.setFixedHeight(self.mask_edit_hint.heightForWidth(self.mask_edit_hint.width()))
            # As decisões da sessão ficam sempre acessíveis, mesmo quando a
            # barra normal estava recolhida; sua preferência é preservada.
            self.collapse_button.hide()
            for key in self.tool_keys():
                button = self.buttons[key]
                width = button.fontMetrics().horizontalAdvance(button.text()) + button.iconSize().width() + 28
                button.setFixedWidth(width)

    def finish_mask(self, commit):
        w = self.window
        session = w._mask_edit_session
        if not session:
            return
        shape = session['shape']
        key = w._item_selection_key(shape)
        page_id = w._active_page_id
        w.finish_mask_edit(commit)
        if w._active_page_id == page_id:
            # Cancelar pode reconstruir os objetos: procurar pela identidade
            # persistente em vez de reutilizar um wrapper Qt destruído.
            target = next((item for item in w.scene.items()
                           if key is not None and w._item_selection_key(item) == key), None)
            if target is not None:
                with w._selection_batch():
                    w.scene.clearSelection()
                    target.setSelected(True)
        self.refresh()
        self.restore_focus()

    def refresh(self, *_):
        if self.mask_picker.shape is not None and not self.mask_picker.valid_target():
            self.mask_picker.cancel(refresh=False)
        self.kind, items = self.selection()
        if self.kind == 'shape':
            item = items[0]
            outline = self.buttons['outline']
            outline.setChecked(item.outline_enabled)
            outline.setToolTip(tr('Desabilitar contorno') if item.outline_enabled else tr('Habilitar contorno'))
            mask = self.buttons['mask']
            masked = bool(item.masked_images()) or bool(item.dynamic_image_field)
            mask.setChecked(masked)
            mask.setEnabled(True)
            mask.setToolTip(tr('Remover máscara') if masked else tr('Usar como máscara'))
            with QSignalBlocker(self.opacity_spin):
                self.opacity_spin.setValue(item.opacity()*100)
            themed_style(self.buttons['fill'], 'border: 1px solid '+item.fill_color+';')
        elif self.kind == 'group':
            source = self.window.btn_group_layer
            self.buttons['group'].setIcon(source.icon())
            self.buttons['group'].setToolTip(source.toolTip())
            self.buttons['group'].setEnabled(source.isEnabled())
        elif self.kind == 'board':
            self.buttons['connect'].setEnabled(self.window.organogram_panel.connect_button.isEnabled())
        for button in self.buttons.values():
            button.setAccessibleName(button.toolTip())
        self.reposition()

    def reposition(self):
        # O timer também acompanha mudanças de seleção/bloqueio durante um menu.
        if self.mask_picker.shape is not None and not self.mask_picker.valid_target():
            self.mask_picker.cancel(refresh=False)
        self.kind, _ = self.selection()
        super().reposition()

    def invoke(self, operation):
        kind, items = self.selection()
        if operation == 'outline' and kind == 'shape':
            self.window._shape_quick_controls['outline'].click()
        elif operation == 'group' and kind == 'group':
            self.window.btn_group_layer.click()
        elif operation == 'connect' and kind == 'board':
            self.window.organogram_panel.connect_button.click()
        self.refresh()
        self.restore_focus()

    def choose_fill(self):
        kind, items = self.selection()
        if kind != 'shape':
            return
        target = self.target_key(items[0])
        color = QColorDialog.getColor(QColor(items[0].fill_color), self.window, tr('Cor do preenchimento'))
        current = self.selected()
        if color.isValid() and current is not None and self.target_key(current) == target:
            control = self.window._shape_quick_controls['color']
            control.setText(color.name()); control.editingFinished.emit()
        self.refresh()
        self.restore_focus()

    def popup(self, button, menu):
        kind, items = self.selection()
        if kind != 'shape':
            return
        target = self.target_key(items[0])
        if menu is self.mask_menu:
            # Abrir o menu não ativa uma máscara nem altera seu indicador.
            button.setChecked(bool(items[0].masked_images()) or bool(items[0].dynamic_image_field))
            if items[0].masked_images():
                self.window.remove_mask(selected=items[0])
                self.refresh(); self.restore_focus()
                return
            if items[0].dynamic_image_field:
                self.window._shape_quick_controls['dynamic'].click()
                self.refresh(); self.restore_focus()
                return
            menu.clear()
            action = menu.addAction(tr('Selecionar imagem no canvas ou em Camadas'))
            action.setEnabled(bool(self.window._free_mask_images()))
            action.triggered.connect(lambda _=False: self.mask_picker.start(target))
            action = menu.addAction(tr('Imagem variável'))
            action.triggered.connect(lambda _=False: self.use_dynamic_image(target))
        super().popup(button, menu)
        if menu is self.alignment_menus['opacity']:
            self.opacity_spin.setFocus(Qt.FocusReason.PopupFocusReason)
            self.opacity_spin.selectAll()

    def use_dynamic_image(self, target):
        shape = self.selected()
        if shape is None or self.target_key(shape) != target or shape.masked_images():
            return
        controls = self.window._shape_quick_controls
        if not shape.dynamic_image_field:
            controls['dynamic'].click()
        self.refresh()
        self.restore_focus()

    def apply_mask(self, image, target):
        kind, items = self.selection()
        if (kind == 'shape' and self.target_key(items[0]) == target and isValid(image)
                and image.scene() is self.window.scene and image in self.window._free_mask_images()):
            self.window.create_mask(image, items[0])
        self.refresh()

    def apply_opacity(self):
        kind, items = self.selection()
        if kind != 'shape' or self.target_key(items[0]) != self._menu_target:
            return
        value = self.opacity_spin.value()
        if abs(items[0].opacity()*100-value) > .0001:
            control = self.window.caixa_texto_panel.spin_opacity
            control.setValue(value); control.editingFinished.emit()
        self.alignment_menus['opacity'].close()
        self.refresh(); self.restore_focus()
