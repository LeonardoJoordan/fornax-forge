from core.themes import themed_style, theme_color, theme_manager
"""Composição visual da interface Qt Widgets do editor."""
from pathlib import Path
from core.resources import (
    action_icon_path, align_icon_path, navigation_icon_path, object_icon_path,
    state_icon_path,
)
from core.theme_icons import themed_svg_icon
from core.i18n import tr
from PySide6.QtCore import (
    Qt, QSize, QObject, QEvent, QPoint, QTimer, QPropertyAnimation, QEasingCurve,
    QAbstractAnimation,
)
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter
from .canvas_items import RectangleItem, mm_to_px, px_to_mm
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSplitter, QFrame, QLineEdit, QAbstractSpinBox, QColorDialog,
    QDoubleSpinBox, QComboBox, QMenu, QSizePolicy, QListView,
    QGridLayout, QButtonGroup,
)
from shiboken6 import isValid


STYLE = """
QWidget { background: @surface@; color: @text@; font-size: 12px; }
QMainWindow, QWidget#root { background: @window@; }
QFrame#footer { background: @window@; border: none; }
QLabel { background: transparent; }
QMenu {
 background: @button@; color: @text@; font-size: 12px;
 border: 1px solid @border_strong@; border-radius: 8px; padding: 6px;
}
QMenu::item {
 min-height: 18px; padding: 2px 28px; border: 1px solid transparent;
 border-radius: 5px; background: transparent;
}
QMenu::item:selected { background: @selection@; border-color: @accent@; }
QMenu::item:disabled { color: @disabled@; }
QMenu::separator { height: 1px; background: @border_strong@; margin: 6px 8px; }
QMenu#shapeMenu::item { padding-left: 36px; }
QMenu#shapeMenu::icon { left: 10px; }
QListView#editorComboOptions {
 background: @button@; color: @text@; font-size: 12px;
 border: 1px solid @border_strong@; border-radius: 8px;
 padding: 6px; outline: none; selection-background-color: transparent;
}
QListView#editorComboOptions::item {
 min-height: 18px; padding: 2px 12px; border: 1px solid transparent;
 border-radius: 5px; background: transparent;
}
QListView#editorComboOptions::item:selected,
QListView#editorComboOptions::item:hover {
 background: @selection@; border-color: @accent@; color: @text@;
}
QListView#editorComboOptions::item:disabled { color: @disabled@; }

QLabel#muted { color: @muted@; }
QFrame#bar { background: @panel@; border-bottom: 1px solid @border@; }
QFrame#compact { background: @field@; border: 1px solid @border@; border-radius: 6px; }
QFrame#compact QAbstractSpinBox { border: none; background: transparent; padding: 0; min-height: 0; font-size: 11px; }
QFrame#compact QLabel { color: @disabled@; font-size: 10px; }
QPushButton { background: @button@; border: 1px solid @border@;
 border-radius: 6px; padding: 6px 10px; min-height: 20px; }
QPushButton:hover { background: @hover@; border-color: @border_strong@; }
QPushButton:checked { background: @selection@; border-color: @accent@; }
QPushButton:disabled { color: @disabled@; background: @surface@; }
QPushButton#primary { background: @accent@; color: @on_accent@; border: none; }
QFrame#pageSelector { background: transparent; }
QFrame#pageButton { background: transparent; border: 1px solid @border@; border-radius: 6px; }
QFrame#pageButton QPushButton { border: none; border-radius: 0; background: @button@; }
QFrame#pageButton QPushButton#pageMain { border-top-left-radius: 5px; border-bottom-left-radius: 5px; }
QFrame#pageButton QPushButton#pageMore { border-left: 1px solid @border@; border-top-right-radius: 5px; border-bottom-right-radius: 5px; padding: 0; }
QFrame#pageButton[active="true"] { border-color: @accent@; }
QFrame#pageButton[active="true"] QPushButton { background: @selection@; }
QFrame#saveButtonGroup { background: @accent@; border: 1px solid @accent@; border-radius: 6px; }
QFrame#saveButtonGroup QPushButton { background: @accent@; color: @on_accent@; border: none; border-radius: 0; }
QFrame#saveButtonGroup QPushButton:hover { background: @accent_hover@; }
QFrame#saveButtonGroup QPushButton#saveMain { border-top-left-radius: 5px; border-bottom-left-radius: 5px; }
QFrame#saveButtonGroup QPushButton#saveSecurity { border-left: 1px solid @on_accent@; border-top-right-radius: 5px; border-bottom-right-radius: 5px; padding: 0; }
QPushButton[squareControl="true"] {
 padding: 0; min-width: 28px; max-width: 28px;
 min-height: 28px; max-height: 28px; border: 1px solid @border@;
}
QPushButton#section { text-align: left; background: @panel@;
 border: none; border-bottom: 1px solid @border@; border-radius: 0;
 padding: 12px; font-weight: 600; }
QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit { background: @field@;
 border: 1px solid @border@; border-radius: 5px; padding: 5px; min-height: 20px;
 selection-background-color: @selection@; }
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QTextEdit:focus { border-color: @accent@; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
 subcontrol-origin: border; subcontrol-position: top right; width: 20px;
 background: @border@; border-left: 1px solid @border_strong@; border-bottom: 1px solid @border_strong@;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
 subcontrol-origin: border; subcontrol-position: bottom right; width: 20px;
 background: @border@; border-left: 1px solid @border_strong@;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: @selection@; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(@spin_up@); width: 10px; height: 6px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(@spin_down@); width: 10px; height: 6px; }
QSpinBox::up-button:disabled, QDoubleSpinBox::up-button:disabled,
QSpinBox::down-button:disabled, QDoubleSpinBox::down-button:disabled { background: @surface@; }
QWidget:disabled { color: @disabled@; }
QListWidget { background: @surface@; border: none; outline: none; }
QListWidget::item { padding: 7px; border-bottom: 1px solid @border@; }
QListWidget::item:selected { background: @selection@; color: @text@; }
QListWidget#layers {
 background: @surface@; border: 1px solid @border@; border-radius: 5px;
 padding: 3px; outline: none;
}
QListWidget#layers::item { padding: 0; border: none; }
QListWidget#layers QWidget { background: transparent; }
QScrollArea { border: none; }
QScrollBar:vertical { background: @scroll_track@; width: 8px; margin: 0; }
QScrollBar:horizontal { background: @scroll_track@; height: 8px; margin: 0; }
QScrollBar::handle:vertical {
 background: @scroll_handle@; min-height: 24px; border-radius: 2px;
}
QScrollBar::handle:horizontal {
 background: @scroll_handle@; min-width: 24px; border-radius: 2px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: @scroll_hover@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QAbstractScrollArea::corner { background: @scroll_track@; border: none; }
QSplitter::handle { background: @border@; width: 1px; }
QToolTip { background: @button@; color: @text@; border: 1px solid @border_strong@; padding: 6px; }
"""


def icon(path):
    from core.theme_icons import tool_icon
    return tool_icon(path)


def _connect_theme_callback(owner, callback):
    """Mantém callbacks locais ligados ao tema somente enquanto o widget existir."""
    manager = theme_manager()
    manager.changed.connect(callback)

    def disconnect(*_):
        if not isValid(manager):
            return
        try:
            manager.changed.disconnect(callback)
        except (RuntimeError, TypeError):
            pass

    owner.destroyed.connect(disconnect)


def column():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)
    return widget, layout


def square_control(button):
    button.setProperty('squareControl', True)
    button.setFixedSize(30, 30)


def row(layout, *widgets):
    line = QHBoxLayout()
    line.setSpacing(8)
    for widget in widgets:
        line.addWidget(widget)
    layout.addLayout(line)
    return line


def field(name, control):
    widget, layout = column()
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    label = QLabel(name)
    label.setObjectName('muted')
    layout.addWidget(label)
    layout.addWidget(control)
    return widget


def compact(name, control, suffix='', width=100, accessible_name=None):
    widget = QFrame()
    widget.setObjectName('compact')
    widget.setFixedHeight(30)
    if width is not None:
        widget.setFixedWidth(width)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(8, 0, 7, 0)
    layout.setSpacing(5)
    if isinstance(name, Path):
        label = QLabel()
        label.setFixedSize(16, 20)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        def refresh_icon():
            label.setPixmap(themed_svg_icon(name).pixmap(14, 14))
        refresh_icon()
        _connect_theme_callback(label, refresh_icon)
    else:
        label = QLabel(name)
    layout.addWidget(label)
    control.setMinimumWidth(0)
    control.setMaximumWidth(16777215)
    control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    control.setAlignment(Qt.AlignmentFlag.AlignRight)
    control.setAccessibleName(accessible_name or (name if isinstance(name, str) else 'Valor'))
    layout.addWidget(control, 1)
    if suffix:
        layout.addWidget(QLabel(suffix))
    return widget


class FooterSaveAlignment(QObject):
    """Alinha salvar ao inspetor e páginas ao centro do canvas."""
    def __init__(self, window, sidebar, canvas, footer_bar, footer_layout, button, pages):
        super().__init__(window)
        self.window = window
        self.sidebar = sidebar
        self.canvas = canvas
        self.footer_bar = footer_bar
        self.footer_layout = footer_layout
        self.button = button
        self.pages = pages
        self._update_pending = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.align)
        for watched in (window, sidebar, canvas, footer_bar, pages):
            watched.installEventFilter(self)

    def schedule(self):
        if self._update_pending:
            return
        self._update_pending = True
        self._timer.start(0)

    def align(self):
        self._update_pending = False
        widgets = (
            self.sidebar, self.canvas, self.footer_bar, self.button, self.pages,
        )
        if any(not isValid(widget) for widget in widgets):
            return
        if not self.sidebar.isVisible() or self.footer_bar.width() <= 0:
            return
        sidebar_center_global = self.sidebar.mapToGlobal(
            QPoint(self.sidebar.width() // 2, 0)
        )
        sidebar_center = self.footer_bar.mapFromGlobal(sidebar_center_global).x()
        right_margin = round(
            self.footer_bar.width() - sidebar_center - self.button.width() / 2
        )
        self.footer_layout.setContentsMargins(14, 5, max(14, right_margin), 5)
        self.footer_layout.activate()
        canvas_center_global = self.canvas.mapToGlobal(QPoint(self.canvas.width() // 2, 0))
        canvas_center = self.footer_bar.mapFromGlobal(canvas_center_global).x()
        self.pages.move(
            round(canvas_center - self.pages.width() / 2),
            round((self.footer_bar.height() - self.pages.height()) / 2),
        )
        self.pages.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Destroy:
            self._timer.stop()
            self._update_pending = False
            return False
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.schedule()
        return False


class SectionReveal(QWidget):
    """Recorta o conteúdo sem comprimir seus controles durante a animação."""
    def __init__(self, content):
        super().__init__()
        self.content = content
        self._content_hint = content.sizeHint()
        self._sync_pending = False
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_content_hint)
        content.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        content.installEventFilter(self)

    def sizeHint(self):
        return self._content_hint

    def minimumSizeHint(self):
        return QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_content()

    def _position_content(self):
        target = self.content.geometry()
        target.setRect(0, 0, self.width(), self._content_hint.height())
        if self.content.geometry() != target:
            self.content.setGeometry(target)

    def _sync_content_hint(self):
        self._sync_pending = False
        hint = self.content.sizeHint()
        if hint != self._content_hint:
            self._content_hint = hint
            self.updateGeometry()
        self._position_content()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Show) and not self._sync_pending:
            self._sync_pending = True
            self._sync_timer.start(0)
        return False


class Section(QWidget):
    def __init__(self, title, content, expanded=False):
        super().__init__()
        self._content = content
        self._reveal = SectionReveal(content)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._animation = QPropertyAnimation(self._reveal, b'maximumHeight', self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = QPushButton()
        self.header.setObjectName('section')
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.header)
        layout.addWidget(self._reveal)

        def refresh_header(opened):
            from core.theme_icons import themed_svg_icon
            self.header.setText(title.upper())
            self.header.setIcon(themed_svg_icon(navigation_icon_path(
                'chevron-up' if opened else 'chevron-down'
            )))
            self.header.setIconSize(QSize(13, 13))

        def finish_animation():
            if self.header.isChecked():
                self._reveal.setMaximumHeight(16777215)
            else:
                self._reveal.hide()

        def toggle(opened):
            refresh_header(opened)
            if self._animation.state() == QAbstractAnimation.State.Running:
                self._animation.stop()
            current_height = self._reveal.height() if self._reveal.isVisible() else 0
            if opened:
                self._reveal.show()
                target_height = max(1, content.sizeHint().height())
                self._reveal.setMaximumHeight(current_height)
            else:
                target_height = 0
                self._reveal.setMaximumHeight(current_height)
            self._animation.setStartValue(current_height)
            self._animation.setEndValue(target_height)
            self._animation.start()

        self._animation.finished.connect(finish_animation)
        self.header.toggled.connect(toggle)
        refresh_header(expanded)
        content.show()
        self._reveal.setVisible(expanded)
        self._reveal.setMaximumHeight(16777215 if expanded else 0)


def install_frontend(w):
    # A janela fornece diretamente a cena e os controles funcionais usados aqui.
    themed_style(w, STYLE)
    w.resize(1500, 930)
    root, outer = column()
    root.setObjectName('root')
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    w.setCentralWidget(root)

    header = QFrame()
    header.setObjectName('bar')
    header.setFixedHeight(64)
    h = QHBoxLayout(header)
    h.addStretch()
    model_title = QLabel(w._current_model_name or tr('Novo modelo'))
    model_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    themed_style(model_title, 'font-size: 16px; font-weight: 600;')
    w.windowTitleChanged.connect(
        lambda _, label=model_title: label.setText(w._current_model_name or tr('Novo modelo'))
    )
    h.addWidget(model_title)
    h.addStretch()
    w.btn_save.setObjectName('primary')
    outer.addWidget(header)

    p = w.caixa_texto_panel
    toolbar = QFrame()
    toolbar.setObjectName('bar')
    tools = QHBoxLayout(toolbar)
    tools.setContentsMargins(14, 8, 14, 8)
    tools.setSpacing(8)
    selection = QLabel(tr('SELEÇÃO') + '\n' + tr('Nenhum objeto'))
    selection.setFixedWidth(138)
    themed_style(selection, 'color: @muted@; font-size: 10px;')
    tools.addWidget(selection)
    def toolbar_separator():
        # O layout já fornece 8 px externamente; os 12 px internos completam
        # os 20 px de respiro desejados em cada lado da linha de 1 px.
        spacing = QWidget()
        spacing.setFixedSize(25, 24)
        themed_style(spacing, 'background: transparent;')
        separator = QFrame(spacing)
        separator.setObjectName('toolbarSeparator')
        separator.setGeometry(12, 0, 1, 24)
        themed_style(separator, 'QFrame#toolbarSeparator { background: @border@; border: none; }')
        tools.addWidget(spacing)
    moved = [
        p.spin_w, p.spin_h, p.chk_proporcao, p.spin_rot, p.spin_opacity,
        p.btn_rot_minus_90, p.btn_rot_plus_90,
    ]
    for name, control in [('X', w.spin_pos_x), ('Y', w.spin_pos_y), ('L', p.spin_w), ('A', p.spin_h)]:
        if name == 'L':
            toolbar_separator()
        tools.addWidget(compact(name, control, 'mm'))
    p.chk_proporcao.setText('')
    p.chk_proporcao.setToolTip(tr('Manter proporção ao redimensionar'))
    p.chk_proporcao.setFixedSize(30, 30)
    p._refresh_proportion_button(p.isEnabled())
    tools.addWidget(p.chk_proporcao)
    toolbar_separator()
    for button, asset_name, tip in (
        (p.btn_rot_minus_90, 'rotate-left', tr('Girar 90° no sentido anti-horário')),
        (p.btn_rot_plus_90, 'rotate-right', tr('Girar 90° no sentido horário')),
    ):
        button.setText('')
        button.setIcon(themed_svg_icon(action_icon_path(asset_name)))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tip)
        button.setGraphicsEffect(None)
        themed_style(button, 'padding: 0;')
        button.setFixedSize(30, 30)
        tools.addWidget(button)
    tools.addWidget(compact(state_icon_path('rotate'), p.spin_rot, '°', 78))
    tools.addWidget(compact(
        state_icon_path('opacity'), p.spin_opacity, '%', 88, tr('Opacidade')
    ))
    toolbar_separator()
    guide_label = QLabel(tr('GUIAS'))
    guide_label.setObjectName('muted')
    tools.addWidget(guide_label)
    for vertical, label, asset_name in [
        (False, tr('Adicionar guia horizontal'), 'h.guide'),
        (True, tr('Adicionar guia vertical'), 'v.guide'),
    ]:
        button = QPushButton()
        button.setIcon(themed_svg_icon(state_icon_path(asset_name)))
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(30, 30)
        themed_style(button, 'padding: 0;')
        button.setToolTip(label)
        button.clicked.connect(lambda checked=False, v=vertical: w.add_guide(v))
        tools.addWidget(button)
    for button, asset_name, tip in (
        (w.btn_toggle_guides, 'eye' if w.btn_toggle_guides.isChecked() else 'eye-off', tr('Exibir ou ocultar guias')),
        (w.btn_lock_guides, 'lock' if w.btn_lock_guides.isChecked() else 'unlock', tr('Bloquear ou desbloquear a movimentação das guias')),
    ):
        button.setText('')
        button.setIcon(themed_svg_icon(state_icon_path(asset_name)))
        button.setIconSize(QSize(20, 20))
        button.setToolTip(tip)
        themed_style(button, 'QPushButton { padding: 0; min-width: 28px; max-width: 28px; '
                            'min-height: 28px; max-height: 28px; font-size: 14px; }')
        button.setFixedSize(30, 30)
        tools.addWidget(button)
    toolbar_separator()
    for button, asset_name, tip in (
        (w.btn_undo, 'undo', tr('Desfazer')),
        (w.btn_redo, 'redo', tr('Refazer')),
    ):
        button.setText('')
        button.setIcon(themed_svg_icon(action_icon_path(asset_name)))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tip)
        button.setMinimumSize(0, 0)
        button.setMaximumSize(16777215, 16777215)
        themed_style(button, 'padding: 0; font-size: 16px;')
        button.setFixedSize(30, 30)
        tools.addWidget(button)
    tools.addStretch()
    fit = QPushButton(tr('Ajustar à janela'))
    fit.setFixedSize(116, 34)
    fit.clicked.connect(w._zoom_to_fit)
    tools.addWidget(fit)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(toolbar)
    scroll.setFixedHeight(54)
    outer.addWidget(scroll)

    split = QSplitter(Qt.Orientation.Horizontal)
    outer.addWidget(split, 1)
    left, ll = column()
    left.setMinimumWidth(220)
    ll.addWidget(QLabel(tr('ADICIONAR AO MODELO')))
    forms = QPushButton(tr('Formas'))
    from .draw_shapes import ShapeDrawing
    w.shape_drawing = ShapeDrawing(w)
    forms.setToolTip(tr('Escolha uma forma e arraste no canvas. Shift restringe proporções ou ângulo; Esc cancela.'))
    shape_menu = QMenu(forms)
    shape_menu.setObjectName('shapeMenu')
    shape_menu.aboutToShow.connect(lambda: shape_menu.setMinimumWidth(forms.width()))
    for name, kind, asset_name in (
        (tr('Quadrado'), 'rectangle', 'square'),
        (tr('Círculo'), 'ellipse', 'circle'),
        (tr('Linha'), 'line', 'line'),
    ):
        action = shape_menu.addAction(themed_svg_icon(object_icon_path(asset_name)), name)
        action.triggered.connect(lambda checked=False, k=kind: w.shape_drawing.activate(k))
    forms.setMenu(shape_menu)
    for button, label, detail, tooltip, path, asset_name, object_name in [
        (w.btn_add, tr('Texto'), tr('Campo dinâmico'), tr('Adicionar uma caixa de texto ao modelo'), '<path d="M4 5h16M12 5v15M8 20h8"/>', 'text', 'Texto'),
        (forms, tr('Formas'), tr('Preenchimento e borda'), forms.toolTip(), '<rect x="4" y="4" width="16" height="16" rx="3"/>', 'shapes', 'Formas'),
        (w.btn_add_img, tr('Imagens'), tr('Foto, logo ou QR'), tr('Adicionar uma imagem ao modelo'), '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m3 16 5-5 5 5 3-3 5 5"/>', 'image', 'Imagens'),
        (w.btn_add_sig, tr('Assinatura'), tr('Imagem opcional'), tr('Adicionar uma assinatura opcional ao modelo'), '<path d="m4 17 3-1L19 4l2 2L9 18l-5 1zM4 22h16"/>', 'signature', 'Assinatura')]:
        button.setText('')
        button.setToolTip(tooltip)
        contents = QHBoxLayout(button)
        contents.setContentsMargins(12, 3, 8, 3)
        contents.setSpacing(10)
        leading_icon = QLabel()
        leading_icon.setFixedSize(20, 20)
        leading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        leading_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        def refresh_leading_icon(target=leading_icon, name=asset_name):
            target.setPixmap(themed_svg_icon(object_icon_path(name)).pixmap(20, 20))
        refresh_leading_icon()
        _connect_theme_callback(leading_icon, refresh_leading_icon)
        contents.addWidget(leading_icon)
        caption = QLabel(f'<b>{label}</b><br><span style="font-size:9px">{detail}</span>')
        caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        contents.addWidget(caption)
        contents.addStretch(1)
        trailing_icon = QLabel()
        trailing_icon.setFixedSize(20, 20)
        trailing_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trailing_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if button is forms:
            def refresh_shape_arrow(target=trailing_icon):
                target.setPixmap(
                    themed_svg_icon(navigation_icon_path('chevron-down')).pixmap(16, 16)
                )
            refresh_shape_arrow()
            _connect_theme_callback(trailing_icon, refresh_shape_arrow)
        contents.addWidget(trailing_icon)
        button.setIcon(QIcon())
        button.setObjectName('add' + object_name)
        # QSS mede a área de conteúdo: 36 + 12 de padding + 2 de borda = 50.
        # Fixar também no estilo evita que o polish restaure o mínimo global.
        themed_style(button, 'QPushButton#' + button.objectName() + ' { '
                            'text-align: left; padding: 6px 10px 6px 12px; '
                            'min-height: 36px; max-height: 36px; } '
                            'QPushButton#' + button.objectName() + '::menu-indicator { image: none; }')
        button.setFixedHeight(50)
        ll.addWidget(button)
    layer_heading = QHBoxLayout()
    layer_heading.addWidget(QLabel(tr('CAMADAS')), 1)
    for b, label, asset_name in [
        (w.btn_ren_layer, tr('Renomear'), 'edit'),
        (w.btn_dup_layer, tr('Duplicar'), 'duplicate'),
        (w.btn_group_layer, tr('Agrupar'), 'unlock ratio'),
        (w.btn_del_layer, tr('Excluir'), 'delete'),
    ]:
        b.setText('')
        b.setToolTip(label)
        b.setMinimumSize(0, 0)
        b.setMaximumSize(16777215, 16777215)
        themed_style(b, '')
        square_control(b)
        b.setIcon(themed_svg_icon(action_icon_path(asset_name)))
        b.setIconSize(QSize(18, 18))
        layer_heading.addWidget(b)
    ll.addLayout(layer_heading)
    w.layer_list.setObjectName('layers')
    w.layer_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    ll.addWidget(w.layer_list, 1)
    split.addWidget(left)
    def update_canvas_theme():
        w.view.setBackgroundBrush(QColor(theme_color('canvas')))
        from .canvas_items import Guideline, ResizeHandle
        for item in w.scene.items():
            if isinstance(item, Guideline):
                pen = item.pen()
                pen.setColor(QColor(theme_color('warning' if item.isSelected() else 'guide')))
                item.setPen(pen)
            elif isinstance(item, ResizeHandle):
                item.setBrush(QColor(theme_color('handle')))
        w.view.viewport().update()
    _connect_theme_callback(w, update_canvas_theme)
    update_canvas_theme()
    w.view.setFrameShape(QFrame.Shape.NoFrame)
    from .rulers import RulerWorkspace
    w.ruler_workspace = RulerWorkspace(w)
    split.addWidget(w.ruler_workspace)

    inspector, il = column()
    il.setContentsMargins(0, 0, 0, 0)
    il.setSpacing(1)
    props, pl = column()
    def property_heading(layout, title, *, separated=False):
        separator = None
        if separated:
            separator = QFrame()
            separator.setObjectName('propertySectionSeparator')
            separator.setFixedHeight(1)
            themed_style(
                separator,
                'QFrame#propertySectionSeparator { background: @border@; border: none; margin: 0; }',
            )
            layout.addWidget(separator)
        heading = QLabel(title)
        heading.setObjectName('propertySectionHeading')
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        themed_style(heading, 'color: @icon@; font-size: 11px; font-weight: 600;')
        heading._section_separator = separator
        layout.addWidget(heading)
        return heading

    def centered_toggle_button(layout, button):
        """Mantém o botão em 65% da largura útil e centralizado."""
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper.setFixedHeight(22)
        themed_style(
            button,
            'QPushButton { padding: 0 10px; min-height: 0; max-height: 20px; }',
        )
        button.setFixedHeight(22)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wrapper_layout.addStretch(175)
        wrapper_layout.addWidget(button, 650)
        wrapper_layout.addStretch(175)
        layout.addWidget(wrapper)
        return wrapper

    def compact_sidebar_action(button):
        content_height = 22 if button.objectName() == 'primary' else 20
        themed_style(
            button,
            f'QPushButton {{ padding: 0 10px; min-height: {content_height}px; '
            f'max-height: {content_height}px; }}',
        )
        button.setFixedHeight(22)

    shape_color = QLineEdit('#ffffff')
    shape_color.setMaxLength(7)
    fill_alpha = QDoubleSpinBox()
    fill_alpha.setObjectName('shapeFillAlpha')
    fill_alpha.setRange(0, 100)
    fill_alpha.setDecimals(0)
    fill_alpha.setKeyboardTracking(False)
    shape_swatch = QPushButton()
    shape_swatch.setObjectName('shapeFillSwatch')
    square_control(shape_swatch)
    shape_controls, shape_layout = column()
    shape_controls.setObjectName('shapeControls')
    shape_layout.setContentsMargins(0, 0, 0, 0)
    fill_controls, fill_layout = column()
    fill_layout.setContentsMargins(0, 0, 0, 0)
    fill_heading = property_heading(fill_layout, tr('PREENCHIMENTO'))
    fill_row = row(fill_layout, shape_swatch, shape_color, compact(
        state_icon_path('opacity'), fill_alpha, '%', 85, tr('Opacidade do preenchimento')
    ))
    fill_row.setStretch(1, 1)
    shape_layout.addWidget(fill_controls)
    pl.addWidget(shape_controls)
    def set_shape_color(value):
        from .canvas_items import RectangleItem
        color = QColor(value)
        selected = w.scene.selectedItems()
        if color.isValid() and len(selected) == 1 and isinstance(selected[0], RectangleItem):
            selected[0].fill_color = color.name()
            selected[0].fill_opacity = fill_alpha.value() / 100
            selected[0].update()
            selected[0].refresh_mask_structure()
            shape_color.setText(color.name())
            themed_style(shape_swatch, f'background: {color.name()};')
            w.save_snapshot()
    def choose_shape_color():
        color = QColorDialog.getColor(QColor(shape_color.text()), w, tr('Cor do preenchimento'))
        if color.isValid():
            set_shape_color(color.name())
    shape_swatch.clicked.connect(choose_shape_color)
    shape_color.editingFinished.connect(lambda: set_shape_color(shape_color.text()))
    fill_alpha.editingFinished.connect(lambda: set_shape_color(shape_color.text()))
    outline_enabled = QPushButton(tr('Habilitar contorno'))
    outline_enabled.setObjectName('shapeOutlineEnabled')
    outline_enabled.setCheckable(True)
    outline_toggle_container = centered_toggle_button(shape_layout, outline_enabled)
    outline_color = QLineEdit('#000000')
    outline_color.setMaxLength(7)
    outline_alpha = QDoubleSpinBox()
    outline_alpha.setObjectName('shapeOutlineAlpha')
    outline_alpha.setRange(0, 100)
    outline_alpha.setDecimals(0)
    outline_alpha.setKeyboardTracking(False)
    outline_swatch = QPushButton()
    outline_swatch.setObjectName('shapeOutlineSwatch')
    square_control(outline_swatch)
    outline_width = QDoubleSpinBox()
    outline_width.setObjectName('shapeOutlineWidth')
    outline_width.setDecimals(2)
    outline_width.setRange(0.01, 1000)
    outline_width.setSingleStep(0.1)
    outline_width.setKeyboardTracking(False)
    outline_position = QComboBox()
    outline_position.setObjectName('shapeOutlinePosition')
    for title, value in [(tr('Interno'), 'inside'), (tr('Centralizado'), 'center'), (tr('Externo'), 'outside')]:
        outline_position.addItem(title, value)
    outline_position.setToolTip(tr('Interno: para dentro. Externo: para fora. Centralizado: metade para cada lado.'))
    outline_details, outline_details_layout = column()
    outline_details_layout.setContentsMargins(0, 0, 0, 0)
    outline_color_row = row(outline_details_layout, outline_swatch, outline_color, compact(
        state_icon_path('opacity'), outline_alpha, '%', 85, tr('Opacidade do contorno')
    ))
    outline_color_row.setStretch(1, 1)
    outline_join, join_layout = column()
    join_layout.setContentsMargins(0, 0, 0, 0)
    outline_join.setObjectName('shapeOutlineJoin')
    join_buttons = QWidget()
    join_buttons_layout = QHBoxLayout(join_buttons)
    join_buttons_layout.setContentsMargins(0, 0, 0, 0)
    join_buttons_layout.setSpacing(6)
    join_group = QButtonGroup(outline_join)
    join_group.setExclusive(True)
    join_straight = QPushButton()
    join_straight.setObjectName('outlineJoinStraight')
    join_straight.setCheckable(True)
    join_straight.setToolTip(tr('Cantos retos'))
    join_straight.setAccessibleName(tr('Cantos retos'))
    square_control(join_straight)
    join_round = QPushButton()
    join_round.setObjectName('outlineJoinRound')
    join_round.setCheckable(True)
    join_round.setToolTip(tr('Cantos arredondados'))
    join_round.setAccessibleName(tr('Cantos arredondados'))
    square_control(join_round)
    join_group.addButton(join_straight, 0)
    join_group.addButton(join_round, 1)
    join_buttons_layout.addStretch(1)
    join_buttons_layout.addWidget(join_straight)
    join_buttons_layout.addWidget(join_round)
    join_buttons_layout.addStretch(1)
    join_layout.addWidget(join_buttons)
    def refresh_outline_join_icons():
        join_straight.setIcon(themed_svg_icon(align_icon_path('straight_edge')))
        join_round.setIcon(themed_svg_icon(align_icon_path('curved_edge')))
        join_straight.setIconSize(QSize(18, 18))
        join_round.setIconSize(QSize(18, 18))
    refresh_outline_join_icons()
    _connect_theme_callback(outline_join, refresh_outline_join_icons)
    join_field = field(tr('Cantos do contorno'), outline_join)
    outline_details_layout.addWidget(join_field)
    rectangle_radius, rectangle_radius_layout = column()
    rectangle_radius_layout.setContentsMargins(0, 0, 0, 0)
    radius_heading = property_heading(
        rectangle_radius_layout, tr('ARREDONDAMENTO DE BORDAS'), separated=True
    )
    sync_radii = QPushButton()
    sync_radii.setObjectName('syncCornerRadii')
    sync_radii.setCheckable(True)
    sync_radii.setChecked(True)
    sync_radii.setToolTip(tr('Sincronizar o arredondamento dos quatro cantos'))
    square_control(sync_radii)
    def refresh_radius_sync_icon(checked):
        asset_name = 'lock ratio' if checked else 'unlock ratio'
        sync_radii.setIcon(themed_svg_icon(action_icon_path(asset_name)))
        sync_radii.setIconSize(QSize(20, 20))
    refresh_radius_sync_icon(sync_radii.isChecked())
    corner_grid = QGridLayout()
    corner_grid.setContentsMargins(0, 0, 0, 0)
    corner_grid.setHorizontalSpacing(7)
    corner_grid.setVerticalSpacing(8)
    corner_spins = {}
    corner_icon_labels = []
    for index, (key, title, asset_name) in enumerate((
        ('top_left', tr('Sup. esquerdo'), 'sup_esq'),
        ('top_right', tr('Sup. direito'), 'sup_dir'),
        ('bottom_left', tr('Inf. esquerdo'), 'inf_esq'),
        ('bottom_right', tr('Inf. direito'), 'inf_dir'),
    )):
        spin = QDoubleSpinBox()
        spin.setObjectName('shapeCornerRadius_' + key)
        spin.setDecimals(2)
        spin.setRange(0, 1000)
        spin.setSingleStep(0.1)
        spin.setKeyboardTracking(False)
        spin.setToolTip(title)
        icon_label = QLabel()
        icon_label.setObjectName('cornerRadiusIcon_' + key)
        icon_label.setFixedSize(22, 30)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setToolTip(title)
        icon_label.setPixmap(themed_svg_icon(align_icon_path(asset_name)).pixmap(18, 18))
        value_box = compact('', spin, 'mm', None)
        row_index = index // 2
        is_left = key.endswith('left')
        if is_left:
            corner_grid.addWidget(value_box, row_index, 0)
            corner_grid.addWidget(icon_label, row_index, 1)
        else:
            corner_grid.addWidget(icon_label, row_index, 3)
            corner_grid.addWidget(value_box, row_index, 4)
        corner_spins[key] = spin
        corner_icon_labels.append((icon_label, asset_name))
    def refresh_corner_radius_icons():
        for label, asset_name in corner_icon_labels:
            label.setPixmap(themed_svg_icon(align_icon_path(asset_name)).pixmap(18, 18))
    _connect_theme_callback(rectangle_radius, refresh_corner_radius_icons)
    corner_grid.setColumnStretch(0, 1)
    corner_grid.setColumnStretch(4, 1)
    corner_grid.addWidget(
        sync_radii, 0, 2, 2, 1, Qt.AlignmentFlag.AlignCenter,
    )
    rectangle_radius_layout.addLayout(corner_grid)
    shape_layout.insertWidget(shape_layout.indexOf(outline_toggle_container), rectangle_radius)

    outline_heading_container, outline_heading_layout = column()
    outline_heading_layout.setContentsMargins(0, 0, 0, 0)
    outline_heading = property_heading(outline_heading_layout, tr('CONTORNO'), separated=True)
    shape_layout.insertWidget(shape_layout.indexOf(outline_toggle_container), outline_heading_container)

    updating_radii = {'active': False}
    def apply_corner_radius(changed_key):
        if updating_radii['active']:
            return
        selected = w.scene.selectedItems()
        if len(selected) != 1 or getattr(selected[0], 'shape_type', '') != 'rectangle':
            return
        updating_radii['active'] = True
        try:
            if sync_radii.isChecked():
                value = corner_spins[changed_key].value()
                for spin in corner_spins.values():
                    spin.setValue(value)
            item = selected[0]
            item.corner_radii = {key: mm_to_px(spin.value()) for key, spin in corner_spins.items()}
            item.corner_radii_linked = sync_radii.isChecked()
            item.corner_radius = item.corner_radii['top_left']
            item.update()
            item.refresh_mask_structure()
            w.save_snapshot()
        finally:
            updating_radii['active'] = False
    for key, spin in corner_spins.items():
        spin.editingFinished.connect(lambda key=key: apply_corner_radius(key))
    def toggle_radius_sync(checked):
        refresh_radius_sync_icon(checked)
        if updating_radii['active']:
            return
        selected = w.scene.selectedItems()
        if len(selected) == 1 and getattr(selected[0], 'shape_type', '') == 'rectangle':
            selected[0].corner_radii_linked = checked
            # Ativar o vínculo define apenas o comportamento das próximas
            # edições. Os valores atuais permanecem intactos até que o
            # operador altere explicitamente um dos cantos.
            w.save_snapshot()
    sync_radii.toggled.connect(toggle_radius_sync)
    position_field = field(tr('Posição'), outline_position)
    thickness_row = row(outline_details_layout, field(tr('Espessura'), compact('', outline_width, 'mm')), position_field)
    thickness_row.setStretch(0, 1)
    thickness_row.setStretch(1, 1)
    for layout_index in range(outline_details_layout.count()):
        if outline_details_layout.itemAt(layout_index).layout() is thickness_row:
            outline_details_layout.takeAt(layout_index)
            break
    outline_details_layout.insertLayout(0, thickness_row)
    shape_layout.insertWidget(shape_layout.indexOf(outline_toggle_container) + 1, outline_details)
    background_outline_hint = QLabel(tr('No plano de fundo, o contorno cresce sempre para dentro da página.'))
    background_outline_hint.setWordWrap(True)
    background_outline_hint.setObjectName('muted')
    shape_layout.addWidget(background_outline_hint)
    def apply_outline(*_):
        from .canvas_items import RectangleItem
        selected = w.scene.selectedItems()
        if len(selected) != 1 or not isinstance(selected[0], RectangleItem):
            return
        item = selected[0]
        color = QColor(outline_color.text())
        if not color.isValid():
            outline_color.setText(item.outline_color)
            return
        item.prepareGeometryChange()
        is_line = item.shape_type == 'line'
        item.outline_enabled = outline_enabled.isChecked()
        item.outline_color = color.name()
        item.outline_opacity = outline_alpha.value() / 100
        item.outline_join = 'miter' if join_straight.isChecked() else 'round'
        # Não arredondar a medida original ao alterar apenas cor/posição.
        if outline_width.value() != round(px_to_mm(item.outline_width), 2):
            item.outline_width = mm_to_px(outline_width.value())
        item.outline_position = 'center' if is_line else ('inside' if getattr(item, 'is_document_background', False) else outline_position.currentData())
        item.update()
        item.refresh_mask_structure()
        themed_style(outline_swatch, f'background: {color.name()};')
        for control in (outline_color, outline_swatch, outline_width, outline_position, outline_alpha, outline_join):
            control.setEnabled(item.outline_enabled)
        w.save_snapshot()
    def choose_outline_color():
        color = QColorDialog.getColor(QColor(outline_color.text()), w, tr('Cor do contorno'))
        if color.isValid():
            outline_color.setText(color.name())
            apply_outline()
    outline_swatch.clicked.connect(choose_outline_color)
    outline_color.editingFinished.connect(apply_outline)
    def update_outline_label(enabled):
        outline_enabled.setText(tr('Desabilitar contorno') if enabled else tr('Habilitar contorno'))
    outline_enabled.toggled.connect(update_outline_label)
    outline_enabled.toggled.connect(outline_details.setVisible)
    outline_enabled.toggled.connect(apply_outline)
    outline_width.editingFinished.connect(apply_outline)
    outline_position.activated.connect(apply_outline)
    join_straight.clicked.connect(apply_outline)
    join_round.clicked.connect(apply_outline)
    outline_alpha.editingFinished.connect(apply_outline)
    p.btn_restore.setText(tr('Restaurar original'))
    p.btn_restore.setMinimumSize(0, 0)
    p.btn_restore.setMaximumSize(16777215, 16777215)
    p.chk_link.setText(tr('Habilitar link'))
    p.chk_link.setToolTip(tr('Adiciona ao objeto um link clicável nos arquivos PDF.'))
    restore_controls, restore_layout = column()
    restore_controls.setObjectName('restoreControls')
    restore_layout.setContentsMargins(0, 0, 0, 0)
    restore_layout.setSpacing(6)
    restore_heading = property_heading(restore_layout, tr('ARQUIVO ORIGINAL'))
    restore_button_container = centered_toggle_button(restore_layout, p.btn_restore)
    pl.addWidget(restore_controls)

    link_controls, link_layout = column()
    link_controls.setObjectName('linkControls')
    link_layout.setContentsMargins(0, 0, 0, 0)
    link_layout.setSpacing(6)
    link_heading = property_heading(link_layout, tr('LINK'), separated=True)
    link_toggle_container = centered_toggle_button(link_layout, p.chk_link)
    link_details, link_details_layout = column()
    link_details.setObjectName('linkDetails')
    link_details_layout.setContentsMargins(0, 0, 0, 0)
    link_field = QLineEdit()
    link_field.setObjectName('linkField')
    link_field.setPlaceholderText(tr('Ex.: Link'))
    link_details_layout.addWidget(field(tr('Campo da tabela'), link_field))
    link_layout.addWidget(link_details)
    updating_link = {'active': False}

    def _selected_link_owner():
        session = w._mask_edit_session
        if session and session.get('inspector_item') is not None:
            item = session['inspector_item']
        else:
            selected = w.scene.selectedItems()
            if len(selected) != 1:
                return None, None
            item = selected[0]
        owner = item.state if hasattr(item, 'state') else item
        return item, owner

    def _default_link_field():
        existing = set(w.get_all_model_placeholders())
        candidate = tr('Link')
        suffix = 2
        while candidate in existing:
            candidate = tr('Link {numero}').format(numero=suffix)
            suffix += 1
        return candidate

    def apply_link_field(save=False):
        if updating_link['active']:
            return
        item, owner = _selected_link_owner()
        if owner is None:
            return
        enabled = p.chk_link.isChecked()
        value = link_field.text().strip()
        if enabled and not value:
            value = _default_link_field()
            link_field.setText(value)
        owner.link_key = value if enabled else ''
        link_details.setVisible(enabled)
        w.sync_placeholders_list()
        w.refresh_layer_list()
        if save:
            w.save_snapshot()

    p.chk_link.toggled.connect(lambda _checked: apply_link_field(False))
    link_field.editingFinished.connect(lambda: apply_link_field(True))

    dynamic_controls, dynamic_layout = column()
    dynamic_controls.setObjectName('dynamicImageControls')
    dynamic_layout.setContentsMargins(0, 0, 0, 0)
    dynamic_layout.setSpacing(6)
    dynamic_heading = property_heading(dynamic_layout, tr('IMAGEM VARIÁVEL'), separated=True)
    dynamic_enabled = QPushButton(tr('Usar imagem variável'))
    dynamic_enabled.setObjectName('dynamicImageEnabled')
    dynamic_enabled.setCheckable(True)
    dynamic_toggle_container = centered_toggle_button(dynamic_layout, dynamic_enabled)
    dynamic_details, dynamic_details_layout = column()
    dynamic_details_layout.setContentsMargins(0, 0, 0, 0)
    dynamic_field = QLineEdit()
    dynamic_field.setObjectName('dynamicImageField')
    dynamic_field.setPlaceholderText(tr('Ex.: Foto'))
    dynamic_fit = QComboBox()
    dynamic_fit.setObjectName('dynamicImageFit')
    dynamic_fit.addItem(tr('Preencher e cortar'), 'cover')
    dynamic_fit.addItem(tr('Ajustar imagem inteira'), 'contain')
    dynamic_details_layout.addWidget(field(tr('Campo da tabela'), dynamic_field))
    dynamic_details_layout.addWidget(field(tr('Enquadramento'), dynamic_fit))
    dynamic_hint = QLabel(tr('A pasta das imagens é escolhida na tela principal.'))
    dynamic_hint.setObjectName('muted')
    dynamic_hint.setWordWrap(True)
    dynamic_details_layout.addWidget(dynamic_hint)
    dynamic_layout.addWidget(dynamic_details)

    updating_dynamic = {'active': False}

    def _default_dynamic_field():
        existing = set(w.get_all_model_placeholders())
        candidate = tr('Imagem')
        suffix = 2
        while candidate in existing:
            candidate = tr('Imagem {numero}').format(numero=suffix)
            suffix += 1
        return candidate

    def apply_dynamic_image():
        if updating_dynamic['active']:
            return
        selected = w.scene.selectedItems()
        if len(selected) != 1 or not isinstance(selected[0], RectangleItem):
            return
        item = selected[0]
        enabled = dynamic_enabled.isChecked()
        value = dynamic_field.text().strip()
        if enabled and not value:
            value = _default_dynamic_field()
            dynamic_field.setText(value)
        if enabled:
            item.dynamic_image_field = value
        else:
            item.dynamic_image_field = ''
            dynamic_field.clear()
        item.dynamic_image_fit = dynamic_fit.currentData() or 'cover'
        dynamic_details.setVisible(enabled)
        w.sync_placeholders_list()
        w.save_snapshot()
        refresh_mask_controls()

    dynamic_enabled.toggled.connect(apply_dynamic_image)
    dynamic_field.editingFinished.connect(apply_dynamic_image)
    dynamic_fit.activated.connect(apply_dynamic_image)

    mask_controls, mask_layout = column()
    mask_controls.setObjectName('maskControls')
    mask_layout.setContentsMargins(0, 0, 0, 0)
    mask_layout.setSpacing(6)
    mask_heading = property_heading(mask_layout, tr('MÁSCARA'), separated=True)
    mask_enabled = QPushButton(tr('Usar como máscara'))
    mask_enabled.setObjectName('maskEnabled')
    mask_enabled.setCheckable(True)
    mask_toggle_container = centered_toggle_button(mask_layout, mask_enabled)
    mask_details, mask_details_layout = column()
    mask_details.setObjectName('maskDetails')
    mask_details_layout.setContentsMargins(0, 0, 0, 0)
    mask_details_layout.setSpacing(6)
    mask_status = QLabel()
    mask_status.setObjectName('muted')
    mask_status.setWordWrap(True)
    mask_details_layout.addWidget(mask_status)
    mask_add_image = QPushButton(tr('+ Imagem'))
    mask_add_image.setObjectName('maskAddImage')
    mask_add_image.setCheckable(True)
    mask_add_image_container = centered_toggle_button(mask_details_layout, mask_add_image)
    mask_insert_controls, mask_insert_layout = column()
    mask_insert_controls.setObjectName('maskInsertControls')
    mask_insert_layout.setContentsMargins(0, 0, 0, 0)
    mask_insert_layout.setSpacing(6)
    mask_target = QComboBox()
    mask_target.setObjectName('maskTarget')
    mask_insert_layout.addWidget(mask_target)
    mask_create = QPushButton()
    mask_create.setObjectName('maskCreate')
    mask_create_container = centered_toggle_button(mask_insert_layout, mask_create)
    mask_details_layout.addWidget(mask_insert_controls)
    mask_child = QComboBox()
    mask_child.setObjectName('maskChild')
    mask_details_layout.addWidget(mask_child)
    mask_actions = row(mask_details_layout)
    mask_edit = QPushButton(tr('Editar máscara'))
    mask_remove = QPushButton(tr('Remover máscara'))
    mask_edit.setObjectName('maskEdit')
    mask_remove.setObjectName('maskRemove')
    mask_actions.addWidget(mask_edit, 1)
    mask_actions.addWidget(mask_remove, 1)
    mask_session_actions = row(mask_details_layout)
    mask_cancel = QPushButton(tr('Cancelar'))
    mask_finish = QPushButton(tr('Concluir'))
    mask_cancel.setObjectName('maskCancel')
    mask_finish.setObjectName('primary')
    for button in (mask_edit, mask_remove, mask_cancel, mask_finish):
        compact_sidebar_action(button)
    mask_session_actions.addWidget(mask_cancel, 1)
    mask_session_actions.addWidget(mask_finish, 1)
    mask_layout.addWidget(mask_details)
    # Ordem visual estável das propriedades de formas:
    # preenchimento, arredondamento, contorno, máscara, link e imagem variável.
    pl.addWidget(mask_controls)
    pl.addWidget(link_controls)
    pl.addWidget(dynamic_controls)

    updating_mask = {'active': False}

    def set_mask_checkbox(checked, enabled=True):
        updating_mask['active'] = True
        try:
            mask_enabled.setEnabled(enabled)
            mask_enabled.setChecked(checked)
        finally:
            updating_mask['active'] = False

    def refresh_mask_controls():
        from .canvas_items import RectangleItem
        selected = w.scene.selectedItems()
        item = selected[0] if len(selected) == 1 else None
        session = w._mask_edit_session
        mask_controls.setVisible(bool(session) or item is not None)
        mask_enabled.setVisible(False)
        mask_enabled.setToolTip('')
        mask_details.setVisible(False)
        mask_add_image.setVisible(False)
        mask_add_image_container.setVisible(False)
        mask_add_image.blockSignals(True)
        mask_add_image.setChecked(False)
        mask_add_image.blockSignals(False)
        mask_insert_controls.setVisible(False)
        mask_create_container.setVisible(False)
        for control in (mask_target, mask_create, mask_child, mask_edit,
                        mask_remove, mask_cancel, mask_finish):
            control.setVisible(False)
        if session:
            shape = session['shape']
            image = session['image']
            mask_status.setText(tr('Editando {image} dentro de {shape}').format(
                image=w._generate_layer_name(image.layer_id, image),
                shape=w._generate_layer_name(shape.layer_id, shape),
            ))
            mask_enabled.setVisible(True)
            mask_enabled.setText(tr('Máscara ativa'))
            set_mask_checkbox(True, enabled=False)
            mask_details.setVisible(True)
            mask_cancel.setVisible(True)
            mask_finish.setVisible(True)
            return
        mask_status.clear()
        if item is None:
            mask_controls.setVisible(False)
            return
        if w._is_mask_image(item):
            parent = item.parentItem()
            mask_enabled.setVisible(True)
            if isinstance(parent, RectangleItem):
                mask_enabled.setText(tr('Máscara ativa'))
                set_mask_checkbox(True, enabled=False)
                mask_details.setVisible(True)
                mask_status.setText(tr('Imagem vinculada a {shape}').format(
                    shape=w._generate_layer_name(parent.layer_id, parent)))
                mask_edit.setVisible(True)
                mask_remove.setVisible(True)
            else:
                shapes = sorted(w._mask_shapes(), key=lambda value: value.custom_name.casefold())
                mask_enabled.setText(tr('Aplicar máscara'))
                set_mask_checkbox(False, enabled=bool(shapes))
                if not shapes:
                    mask_enabled.setToolTip(tr('Crie uma forma fechada para utilizá-la como máscara.'))
                    return
                mask_enabled.setToolTip('')
                mask_target.clear()
                for shape in shapes:
                    mask_target.addItem(w._generate_layer_name(shape.layer_id, shape), shape)
                mask_target.setVisible(True)
                mask_insert_controls.setVisible(True)
                mask_create.setText(tr('Aplicar'))
                mask_create_container.setVisible(True)
                mask_create.setVisible(True)
            return
        if isinstance(item, RectangleItem):
            children = item.masked_images()
            mask_available = (
                item.shape_type in ('rectangle', 'ellipse', 'circle')
                and not getattr(item, 'is_document_background', False)
                and not bool(item.dynamic_image_field)
            )
            mask_enabled.setVisible(True)
            if not mask_available:
                mask_enabled.setText(tr('Usar como máscara'))
                set_mask_checkbox(bool(children), enabled=False)
                return
            free_images = sorted(w._free_mask_images(), key=lambda value: value.custom_name.casefold())
            mask_enabled.setText(tr('Máscara ativa') if children else tr('Usar como máscara'))
            set_mask_checkbox(bool(children), enabled=not children and bool(free_images))
            mask_details.setVisible(bool(children))
            if free_images:
                mask_target.clear()
                for image in free_images:
                    mask_target.addItem(w._generate_layer_name(image.layer_id, image), image)
                mask_target.setVisible(True)
                mask_create.setText(tr('Inserir imagem'))
                mask_create_container.setVisible(True)
                mask_create.setVisible(True)
                if children:
                    mask_add_image_container.setVisible(True)
                    mask_add_image.setVisible(True)
                else:
                    mask_insert_controls.setVisible(True)
            if children:
                mask_child.clear()
                for image in reversed(children):
                    mask_child.addItem(w._generate_layer_name(image.layer_id, image), image)
                mask_child.setVisible(True)
                mask_edit.setVisible(True)
                mask_remove.setVisible(True)
                mask_status.setText(tr('{count} imagem(ns) vinculada(s)').format(count=len(children)))
            elif not free_images:
                mask_enabled.setToolTip(tr('Não há imagens disponíveis para mascaramento.'))
            else:
                mask_enabled.setToolTip('')
            return
        mask_controls.setVisible(False)

    def toggle_mask_panel(checked):
        if updating_mask['active']:
            return
        selected = w.scene.selectedItems()
        item = selected[0] if len(selected) == 1 else None
        if item is None:
            return
        mask_details.setVisible(checked)

    def create_selected_mask():
        selected = w.scene.selectedItems()
        if len(selected) != 1:
            return
        item = selected[0]
        target = mask_target.currentData()
        if w._is_mask_image(item):
            w.create_mask(item, target)
        elif isinstance(item, RectangleItem):
            w.create_mask(target, item)

    def edit_selected_mask():
        selected = w.scene.selectedItems()
        if len(selected) != 1:
            return
        item = selected[0]
        image = item if w._is_mask_image(item) else mask_child.currentData()
        if image is not None:
            w.begin_mask_edit(image)

    mask_create.clicked.connect(create_selected_mask)
    mask_edit.clicked.connect(edit_selected_mask)
    mask_remove.clicked.connect(lambda: w.remove_mask())
    mask_cancel.clicked.connect(lambda: w.finish_mask_edit(False))
    mask_finish.clicked.connect(lambda: w.finish_mask_edit(True))
    mask_enabled.toggled.connect(toggle_mask_panel)
    mask_add_image.toggled.connect(mask_insert_controls.setVisible)
    w._refresh_mask_controls = refresh_mask_controls

    prop_section = Section(tr('Propriedades'), props)
    il.addWidget(prop_section)
    t = w.editor_texto_panel
    t.cbo_font.setToolTip(tr('Selecionar a família da fonte'))
    t.spin_size.setToolTip(tr('Alterar o tamanho da fonte'))
    t.btn_bold.setToolTip(tr('Negrito (Ctrl+B)'))
    t.btn_italic.setToolTip(tr('Itálico (Ctrl+I)'))
    t.btn_underline.setToolTip(tr('Sublinhado (Ctrl+U)'))
    t.btn_color.setToolTip(tr('Selecionar a cor do texto'))
    square_control(t.btn_color)
    text_body, tl = column()
    hint = QLabel(tr('Duplo clique no texto para editar no canvas.'))
    hint.setWordWrap(True)
    hint.setObjectName('muted')
    tl.addWidget(hint)
    typography_heading = property_heading(tl, tr('TIPOGRAFIA'))
    font_row = row(tl, field(tr('Fonte'), t.cbo_font), field(tr('Tamanho'), t.spin_size))
    font_row.setStretch(0, 3)
    font_row.setStretch(1, 1)
    styles = row(tl, t.btn_bold, t.btn_italic, t.btn_underline)
    styles.setSpacing(6)
    for button in (t.btn_bold, t.btn_italic, t.btn_underline):
        themed_style(button, 'QPushButton { padding: 0; min-width: 28px; max-width: 28px; '
                            'min-height: 28px; max-height: 28px; }')
        button.setFixedSize(30, 30)
    styles.addStretch()
    t.color_hex = QLineEdit('#000000')
    t.color_hex.setMaxLength(7)
    t.color_hex.setPlaceholderText('#RRGGBB')
    text_alpha = QDoubleSpinBox()
    text_alpha.setObjectName('textColorAlpha')
    text_alpha.setRange(0, 100)
    text_alpha.setDecimals(0)
    text_alpha.setValue(100)
    text_alpha.setKeyboardTracking(False)
    color_row, color_layout = column()
    color_layout.setContentsMargins(0, 0, 0, 0)
    text_color_row = row(color_layout, t.btn_color, t.color_hex, compact(
        state_icon_path('opacity'), text_alpha, '%', 85, tr('Opacidade do texto')
    ))
    text_color_row.setStretch(1, 1)
    tl.addWidget(field(tr('Cor'), color_row))
    def apply_hex():
        value = t.color_hex.text().strip()
        color = QColor(value)
        if len(value) == 7 and value.startswith('#') and color.isValid():
            themed_style(t.btn_color, f'background: {color.name()}; border: 1px solid @border_strong@;')
            color.setAlphaF(text_alpha.value()/100)
            t.fontColorChanged.emit(color.name(QColor.NameFormat.HexArgb))
            t.snapshotRequested.emit()
        else:
            t.color_hex.setText(t.color_hex.property('lastColor') or '#000000')
    t.color_hex.editingFinished.connect(apply_hex)
    text_alpha.editingFinished.connect(apply_hex)
    def color_changed(value):
        color = QColor(value)
        t.color_hex.setText(color.name())
        t.color_hex.setProperty('lastColor', color.name())
        text_alpha.setValue(round(color.alphaF()*100))
    t.fontColorChanged.connect(color_changed)
    alignment_heading = property_heading(tl, tr('ALINHAMENTO'), separated=True)
    for control in (t.spin_lh, t.spin_indent, t.spin_size):
        selector = 'QComboBox' if isinstance(control, QComboBox) else 'QAbstractSpinBox'
        themed_style(control, selector + ' { min-height: 18px; max-height: 18px; padding-top: 5px; padding-bottom: 5px; }')
        control.setFixedHeight(30)
        control.setMinimumWidth(0)
    t.cbo_align.hide()
    t.cbo_valign.hide()
    alignment_widget = QWidget()
    t.alignment_widget = alignment_widget
    alignment_layout = QHBoxLayout(alignment_widget)
    alignment_layout.setContentsMargins(0, 0, 0, 0)
    alignment_layout.setSpacing(0)
    horizontal_widget = QWidget()
    horizontal_layout = QHBoxLayout(horizontal_widget)
    horizontal_layout.setContentsMargins(0, 0, 0, 0)
    horizontal_layout.setSpacing(0)
    vertical_widget = QWidget()
    vertical_layout = QHBoxLayout(vertical_widget)
    vertical_layout.setContentsMargins(0, 0, 0, 0)
    vertical_layout.setSpacing(0)
    horizontal_group = QButtonGroup(t)
    vertical_group = QButtonGroup(t)
    horizontal_group.setExclusive(True)
    vertical_group.setExclusive(True)
    t.alignment_buttons = []
    alignment_icon_specs = []
    alignment_value_icons = []

    def alignment_button(asset_name, tooltip, group, combo, index, target_layout):
        button = QPushButton()
        button.setObjectName('textAlign_' + asset_name)
        button.setCheckable(True)
        button.setIcon(themed_svg_icon(align_icon_path(asset_name)))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        square_control(button)
        group.addButton(button, index)
        button.clicked.connect(lambda _checked=False, i=index: combo.setCurrentIndex(i))
        button.clicked.connect(t.snapshotRequested.emit)
        if target_layout.count():
            target_layout.addStretch(1)
        target_layout.addWidget(button)
        t.alignment_buttons.append(button)
        alignment_icon_specs.append((button, asset_name))
        return button

    horizontal_buttons = [
        alignment_button('left-align', tr('Alinhar texto à esquerda'), horizontal_group, t.cbo_align, 0, horizontal_layout),
        alignment_button('center-align', tr('Centralizar texto'), horizontal_group, t.cbo_align, 1, horizontal_layout),
        alignment_button('right-align', tr('Alinhar texto à direita'), horizontal_group, t.cbo_align, 2, horizontal_layout),
        alignment_button('justify', tr('Justificar texto'), horizontal_group, t.cbo_align, 3, horizontal_layout),
    ]
    alignment_layout.addWidget(horizontal_widget, 4)
    align_separator = QFrame()
    align_separator.setObjectName('textAlignmentSeparator')
    align_separator.setFixedSize(1, 22)
    themed_style(align_separator, 'QFrame#textAlignmentSeparator { background: @border_strong@; border: none; }')
    alignment_layout.addSpacing(10)
    alignment_layout.addWidget(align_separator)
    alignment_layout.addSpacing(10)
    vertical_buttons = [
        alignment_button('top-alignment', tr('Alinhar texto ao topo'), vertical_group, t.cbo_valign, 0, vertical_layout),
        alignment_button('mid-alignment', tr('Alinhar texto ao meio'), vertical_group, t.cbo_valign, 1, vertical_layout),
        alignment_button('bot-alignment', tr('Alinhar texto à base'), vertical_group, t.cbo_valign, 2, vertical_layout),
    ]
    alignment_layout.addWidget(vertical_widget, 3)

    def sync_alignment_buttons():
        horizontal_index = t.cbo_align.currentIndex()
        vertical_index = t.cbo_valign.currentIndex()
        for index, button in enumerate(horizontal_buttons):
            button.setChecked(index == horizontal_index)
        for index, button in enumerate(vertical_buttons):
            button.setChecked(index == vertical_index)

    t.cbo_align.currentIndexChanged.connect(sync_alignment_buttons)
    t.cbo_valign.currentIndexChanged.connect(sync_alignment_buttons)
    sync_alignment_buttons()
    tl.addWidget(alignment_widget)

    def icon_value_field(asset_name, tooltip, control):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        icon_label = QLabel()
        icon_label.setPixmap(themed_svg_icon(align_icon_path(asset_name)).pixmap(20, 20))
        icon_label.setFixedSize(22, 30)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setToolTip(tooltip)
        control.setToolTip(tooltip)
        alignment_value_icons.append((icon_label, asset_name))
        layout.addWidget(icon_label)
        layout.addWidget(control, 1)
        return widget

    spacing = row(
        tl,
        icon_value_field('line-space', tr('Entrelinha'), t.spin_lh),
        icon_value_field('paragraph', tr('Recuo da primeira linha'), t.spin_indent),
    )
    t.spin_indent.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
    spacing.setStretch(0, 1)
    spacing.setStretch(1, 1)
    def refresh_alignment_icons():
        for button, asset_name in alignment_icon_specs:
            button.setIcon(themed_svg_icon(align_icon_path(asset_name)))
        for label, asset_name in alignment_value_icons:
            label.setPixmap(themed_svg_icon(align_icon_path(asset_name)).pixmap(20, 20))
    _connect_theme_callback(text_body, refresh_alignment_icons)
    text_section = Section(tr('Texto'), text_body)
    w._text_section = text_section
    il.addWidget(text_section)
    doc, dl = column()
    dimensions_heading = property_heading(dl, tr('DIMENSÕES'))
    w.chk_doc_proporcao.setText('')
    w.chk_doc_proporcao.setToolTip(tr('Manter a proporção do documento'))
    w.chk_doc_proporcao.setFixedSize(30, 30)
    w._refresh_doc_proportion_button()
    dimensions = row(dl, compact('L', w.spin_phys_w, 'mm', None),
                     compact('A', w.spin_phys_h, 'mm', None), w.chk_doc_proporcao)
    dimensions.setStretch(0, 1)
    dimensions.setStretch(1, 1)
    table_fields_heading = property_heading(dl, tr('CAMPOS DA TABELA'), separated=True)
    order_hint = QLabel(tr('Segure e arraste para ajustar a ordem'))
    order_hint.setWordWrap(True)
    themed_style(order_hint, 'color: @disabled@; font-size: 10px;')
    dl.addWidget(order_hint)
    w.lst_placeholders.setObjectName('tableFields')
    themed_style(w.lst_placeholders, '''
        QListWidget#tableFields {
            background: @surface@; border: 1px solid @border@;
            border-radius: 5px; padding: 3px; outline: none;
        }
        QListWidget#tableFields::item { padding: 4px 5px; border: none; }
        QListWidget#tableFields::item:selected { background: @selection@; color: @text@; }
        QListWidget#tableFields::item:hover { background: @hover@; }
    ''')
    w.lst_placeholders.setFixedHeight(180)
    w.lst_placeholders.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    dl.addWidget(w.lst_placeholders)
    document_section = Section(tr('Documento'), doc, True)
    il.insertWidget(0, document_section)
    il.addStretch()
    right = QScrollArea()
    right.setObjectName('inspectorScroll')
    right.setWidgetResizable(True)
    right.setWidget(inspector)
    right.setMinimumWidth(322)
    split.addWidget(right)
    split.setSizes([262, 916, 322])
    split.setStretchFactor(1, 1)
    split.setChildrenCollapsible(False)
    footer_bar = QFrame()
    footer_bar.setObjectName('footer')
    footer_bar.setFixedHeight(44)
    footer = QHBoxLayout(footer_bar)
    footer.setContentsMargins(14, 5, 14, 5)
    footer.addStretch()
    save_group = QFrame(footer_bar)
    save_group.setObjectName('saveButtonGroup')
    save_layout = QHBoxLayout(save_group)
    save_layout.setContentsMargins(0, 0, 0, 0)
    save_layout.setSpacing(0)
    w.btn_save.setObjectName('saveMain')
    w.btn_save.setText(tr('Salvar modelo'))
    w.btn_save.setMinimumSize(0, 0)
    w.btn_save.setMaximumSize(16777215, 16777215)
    w.btn_save.setFixedSize(116, 34)
    save_layout.addWidget(w.btn_save)
    w.btn_save_security = QPushButton(save_group)
    w.btn_save_security.setObjectName('saveSecurity')
    w.btn_save_security.setFixedSize(34, 34)
    w.btn_save_security.setIconSize(QSize(16, 16))
    protection_menu = QMenu(w.btn_save_security)
    protection_actions = {}
    for mode, label in (
        ('none', tr('Sem proteção')),
        ('signatures', tr('Proteger assinaturas')),
        ('full', tr('Proteger modelo inteiro')),
    ):
        action = protection_menu.addAction(label)
        action.setCheckable(True)
        action.triggered.connect(
            lambda _checked=False, selected=mode: w.request_protection_mode(selected)
        )
        protection_actions[mode] = action
    protection_menu.addSeparator()
    change_password = protection_menu.addAction(tr('Alterar senha'))
    change_password.triggered.connect(w.change_fornax_password)
    protection_menu.aboutToShow.connect(w.refresh_protection_control)
    w.protection_actions = protection_actions
    w.action_change_password = change_password
    w.protection_menu = protection_menu
    w.btn_save_security.clicked.connect(
        lambda: protection_menu.exec(
            w.btn_save_security.mapToGlobal(QPoint(0, w.btn_save_security.height()))
        )
    )
    save_layout.addWidget(w.btn_save_security)
    footer.addWidget(save_group)
    w.save_button_group = save_group
    w.refresh_protection_control()
    page_selector = QFrame(footer_bar)
    page_selector.setObjectName('pageSelector')
    page_layout = QHBoxLayout(page_selector)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.setSpacing(6)

    def show_page_menu(page_id, anchor):
        menu = QMenu(anchor)
        clear_action = menu.addAction(tr('Limpar página'))
        clear_action.triggered.connect(lambda: w.clear_model_page(page_id))
        if w._model_document and len(w._model_document.get('pages', [])) > 1:
            remove_action = menu.addAction(tr('Remover página'))
            remove_action.triggered.connect(lambda: w.remove_model_page(page_id))
        menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    def rebuild_page_selector():
        while page_layout.count():
            item = page_layout.takeAt(0)
            old_widget = item.widget()
            if old_widget:
                old_widget.hide()
                old_widget.setParent(None)
                old_widget.deleteLater()
        document = w._model_document
        page_ids = [page['page_id'] for page in document.get('pages', [])] if document else ['front']
        for index, page_id in enumerate(page_ids, start=1):
            group = QFrame(page_selector)
            group.setObjectName('pageButton')
            group.setProperty('active', page_id == w._active_page_id)
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(0)
            main = QPushButton(tr('Página {numero}').format(numero=index), group)
            main.setObjectName('pageMain')
            main.setFixedHeight(34)
            main.setMinimumWidth(82)
            main.setAccessibleName(tr('Página {numero}').format(numero=index))
            main.setToolTip(tr('Exibir a página {numero} no editor').format(numero=index))
            main.clicked.connect(lambda _checked=False, target=page_id: w.switch_model_page(target))
            more = QPushButton(group)
            more.setObjectName('pageMore')
            more.setFixedSize(28, 34)
            more.setIcon(themed_svg_icon(action_icon_path('more-vertical')))
            more.setIconSize(QSize(14, 14))
            more.setToolTip(tr('Ações da página'))
            more.setAccessibleName(tr('Ações da página {numero}').format(numero=index))
            more.clicked.connect(lambda _checked=False, target=page_id, anchor=more: show_page_menu(target, anchor))
            group_layout.addWidget(main)
            group_layout.addWidget(more)
            page_layout.addWidget(group)
        if len(page_ids) < 2:
            add_page = QPushButton(tr('+ Página'), page_selector)
            add_page.setFixedHeight(34)
            add_page.setMinimumWidth(82)
            add_page.setToolTip(tr('Adicionar o verso ao modelo'))
            add_page.setAccessibleName(tr('Adicionar o verso ao modelo'))
            add_page.clicked.connect(w.add_model_page)
            page_layout.addWidget(add_page)
        page_layout.invalidate()
        page_layout.activate()
        widgets = [page_layout.itemAt(i).widget() for i in range(page_layout.count())]
        width = sum(widget.sizeHint().width() for widget in widgets)
        width += page_layout.spacing() * max(0, len(widgets) - 1)
        height = max((widget.sizeHint().height() for widget in widgets), default=34)
        page_selector.resize(width, height)
        if hasattr(w, '_footer_save_alignment'):
            w._footer_save_alignment.schedule()

    w._update_page_controls = rebuild_page_selector
    rebuild_page_selector()
    outer.addWidget(footer_bar)
    w._footer_save_alignment = FooterSaveAlignment(
        w, right, split.widget(1), footer_bar, footer, save_group, page_selector
    )
    split.splitterMoved.connect(lambda *_: w._footer_save_alignment.schedule())
    w._footer_save_alignment.schedule()

    selection_state = {'kind': None}

    def clear_text_presentation():
        """Limpa somente os controles visuais; o texto continua no item da cena."""
        controls = (
            t.txt_content, t.cbo_font, t.spin_size, t.btn_bold,
            t.btn_italic, t.btn_underline, t.cbo_align, t.cbo_valign,
            *t.alignment_buttons,
            t.spin_lh, t.spin_indent, t.btn_color, t.color_hex, text_alpha,
        )
        previous = [(control, control.blockSignals(True)) for control in controls]
        try:
            t.txt_content.clear()
            t.cbo_font.setCurrentIndex(-1)
            t.spin_size.lineEdit().clear()
            t.btn_bold.setChecked(False)
            t.btn_italic.setChecked(False)
            t.btn_underline.setChecked(False)
            t.cbo_align.setCurrentIndex(-1)
            t.cbo_valign.setCurrentIndex(-1)
            sync_alignment_buttons()
            t.spin_lh.lineEdit().clear()
            t.spin_indent.lineEdit().clear()
            t.color_hex.clear()
            text_alpha.lineEdit().clear()
            themed_style(t.btn_color, 'background: @field@; border: 1px solid @border@; border-radius: 5px;')
        finally:
            for control, was_blocked in previous:
                control.blockSignals(was_blocked)

    def sync_enabled():
        from shiboken6 import isValid
        if not all(isValid(obj) for obj in (w.scene, p, props, t, text_body)):
            return
        for control in moved:
            if isValid(control):
                control.setEnabled(p.isEnabled())
        props.setEnabled(p.isEnabled())
        text_available = t.isEnabled()
        properties_available = p.isEnabled()
        prop_section.setEnabled(properties_available)
        text_section.setEnabled(text_available)
        text_body.setEnabled(t.isEnabled())
        selected = w.scene.selectedItems()
        current_kind = 'text' if text_available else ('object' if selected else 'none')
        if current_kind != selection_state['kind']:
            # Undo/Redo reconstrói a cena e produz transições temporárias de
            # seleção. Elas não representam uma escolha nova do operador.
            if not getattr(w, '_restoring_history', False):
                if current_kind != 'text':
                    clear_text_presentation()
                prop_section.header.setChecked(bool(properties_available))
                text_section.header.setChecked(bool(text_available))
                selection_state['kind'] = current_kind
        from .canvas_items import RectangleItem, ImageItem, BackgroundItem, SignatureItem
        mask_session = w._mask_edit_session
        inspector_item = (
            mask_session.get('inspector_item')
            if mask_session else (selected[0] if len(selected) == 1 else None)
        )
        # Durante a edição de uma máscara a imagem precisa ser a seleção real
        # do canvas. O inspetor, porém, conserva o objeto pelo qual o operador
        # iniciou o fluxo para que a lateral não troque de estrutura.
        is_shape = isinstance(inspector_item, RectangleItem)
        background_selected = bool(
            inspector_item is not None
            and getattr(inspector_item, 'is_document_background', False)
        )
        restore_visible = (
            isinstance(inspector_item, SignatureItem)
            or (
                isinstance(inspector_item, ImageItem)
                and not isinstance(inspector_item, (RectangleItem, BackgroundItem))
            )
        )
        if background_selected:
            for control in (w.spin_pos_x, w.spin_pos_y, p.spin_w, p.spin_h, p.spin_rot, p.chk_proporcao):
                control.setEnabled(False)
        w.btn_dup_layer.setEnabled(bool(selected) and not background_selected)
        w.btn_del_layer.setEnabled(bool(selected) and not background_selected)
        shape_controls.setVisible(is_shape)
        restore_controls.setVisible(restore_visible)
        p.btn_restore.setVisible(restore_visible)
        link_controls.setVisible(inspector_item is not None)
        dynamic_controls.setVisible(False)
        # A seleção técnica da imagem durante o enquadramento não deve alterar
        # nem apagar visualmente o inspetor que o operador já estava usando.
        # Os próprios manipuladores ignoram ações incompatíveis com o item
        # ativo, portanto os blocos podem conservar sua apresentação normal.
        for controls in (shape_controls, restore_controls, link_controls, dynamic_controls):
            controls.setEnabled(True)
        masked_image_selected = bool(
            isinstance(inspector_item, ImageItem)
            and not isinstance(inspector_item, RectangleItem)
            and isinstance(inspector_item.parentItem(), RectangleItem)
        )
        link_available = inspector_item is not None and not (
            background_selected or masked_image_selected
        )
        link_controls.setEnabled(link_available)
        p.set_link_available(link_available)
        if is_shape:
            item = inspector_item
            is_line = item.shape_type == 'line'
            dynamic_available = (
                not is_line
                and not background_selected
                and not item.masked_images()
                and item.shape_type in ('rectangle', 'ellipse', 'circle')
            )
            # Os submenus permanecem estáveis para qualquer forma. Recursos
            # incompatíveis continuam visíveis, porém bloqueados.
            dynamic_controls.setVisible(True)
            updating_dynamic['active'] = True
            try:
                dynamic_enabled.setEnabled(dynamic_available or bool(item.dynamic_image_field))
                dynamic_enabled.setChecked(bool(item.dynamic_image_field))
                dynamic_field.setText(item.dynamic_image_field)
                dynamic_fit.setCurrentIndex(max(0, dynamic_fit.findData(item.dynamic_image_fit)))
                dynamic_details.setVisible(bool(item.dynamic_image_field))
            finally:
                updating_dynamic['active'] = False
            fill_controls.setVisible(True)
            fill_controls.setEnabled(True)
            outline_heading_container.setVisible(True)
            outline_enabled.setVisible(True)
            outline_enabled.setEnabled(True)
            position_field.setVisible(not is_line)
            join_field.setVisible(item.shape_type == 'rectangle')
            rectangle_radius.setVisible(item.shape_type == 'rectangle')
            rectangle_radius.setEnabled(item.shape_type == 'rectangle')
            if item.shape_type == 'rectangle':
                stored_radii = dict(getattr(item, 'corner_radii', {}) or {})
                fallback = getattr(item, 'corner_radius', 0)
                updating_radii['active'] = True
                try:
                    sync_radii.setChecked(getattr(item, 'corner_radii_linked', True))
                    refresh_radius_sync_icon(sync_radii.isChecked())
                    for key, spin in corner_spins.items():
                        spin.setValue(px_to_mm(stored_radii.get(key, fallback)))
                finally:
                    updating_radii['active'] = False
            if is_line:
                p.spin_rot.blockSignals(True)
                p.spin_rot.setValue((-item.rotation()) % 360)
                p.spin_rot.blockSignals(False)
            outline_enabled.blockSignals(True)
            outline_enabled.setChecked(item.outline_enabled)
            outline_enabled.blockSignals(False)
            update_outline_label(item.outline_enabled)
            outline_details.setVisible(item.outline_enabled)
            outline_color.setText(item.outline_color)
            fill_alpha.setValue(item.fill_opacity * 100)
            outline_alpha.setValue(item.outline_opacity * 100)
            join_straight.setChecked(item.outline_join == 'miter')
            join_round.setChecked(item.outline_join != 'miter')
            themed_style(outline_swatch, f'background: {item.outline_color};')
            outline_width.setValue(px_to_mm(item.outline_width))
            for index in range(outline_position.count()):
                outline_position.model().item(index).setEnabled(
                    not background_selected or outline_position.itemData(index) == 'inside')
            outline_position.setCurrentIndex(max(0, outline_position.findData(item.outline_position)))
            for control in (outline_color, outline_swatch, outline_width, outline_position, outline_alpha, outline_join):
                control.setEnabled(item.outline_enabled)
            background_outline_hint.setVisible(background_selected)
            shape_color.setText(item.fill_color)
            themed_style(shape_swatch, f'background: {item.fill_color};')
            p.btn_restore.setEnabled(False)
        link_item = inspector_item
        link_owner = (
            inspector_item.state
            if inspector_item is not None and hasattr(inspector_item, 'state')
            else inspector_item
        )
        updating_link['active'] = True
        try:
            link_enabled = bool(link_owner and getattr(link_owner, 'has_link', False))
            if not link_available:
                link_enabled = False
            link_field.setText(
                w._link_key_for_item(link_item) if link_enabled else ''
            )
            link_details.setVisible(link_enabled)
        finally:
            updating_link['active'] = False
        refresh_mask_controls()
        if mask_session and not prop_section.header.isChecked():
            prop_section.header.setChecked(True)
        if mask_heading._section_separator is not None:
            mask_heading._section_separator.setVisible(is_shape or restore_visible)
        if link_heading._section_separator is not None:
            link_heading._section_separator.setVisible(
                is_shape or restore_visible or mask_controls.isVisible()
            )
        selection.setText(
            tr('SELEÇÃO') + '\n' + (
                getattr(inspector_item, 'layer_name', '') or tr('Objeto selecionado')
                if inspector_item is not None else tr('Nenhum objeto')
            )
        )
        if t.isEnabled() and len(selected) == 1:
            color_changed(getattr(selected[0].state, 'font_color', '#000000'))
            if hasattr(w, 'canvas_edit'):
                w.canvas_edit.sync_panel()
    w.scene.selectionChanged.connect(sync_enabled)
    # O seletor de camadas bloqueia os sinais da cena enquanto seleciona pela lista.
    # Atualizar depois dele também cobre o único acesso ao plano de fundo.
    w.layer_list.itemSelectionChanged.connect(sync_enabled)
    # O editor sempre começa no contexto geral do documento. As seções de
    # objeto só são habilitadas quando o usuário faz uma seleção explícita.
    w.scene.clearSelection()
    sync_enabled()
    w._inspector_sections = {
        'document': document_section,
        'properties': prop_section,
        'text': text_section,
    }

    def restore_inspector_state(saved_state):
        """Restaura preferências visuais após uma reconstrução do histórico."""
        selected = w.scene.selectedItems()
        text_available = t.isEnabled()
        properties_available = p.isEnabled()
        current_kind = 'text' if text_available else ('object' if selected else 'none')
        selection_state['kind'] = current_kind
        if current_kind != 'text':
            clear_text_presentation()
        document_section.header.setChecked(saved_state.get('document', True))
        prop_section.header.setChecked(
            saved_state.get('properties', False) if properties_available else False
        )
        text_section.header.setChecked(
            saved_state.get('text', False) if text_available else False
        )

    w._restore_inspector_state = restore_inspector_state

    # QListView permite que os popups usem as mesmas métricas do workspace.
    # O seletor de fontes conserva seu delegate de prévia tipográfica.
    from PySide6.QtWidgets import QFontComboBox
    for combo in w.findChildren(QComboBox):
        if isinstance(combo, QFontComboBox):
            popup = combo.view()
        else:
            popup = QListView(combo)
            combo.setView(popup)
        popup.setObjectName('editorComboOptions')
        popup.setMouseTracking(True)
        popup.setUniformItemSizes(True)
        combo.setMaxVisibleItems(12)
