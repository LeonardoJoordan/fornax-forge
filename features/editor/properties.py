from core.themes import themed_style
from PySide6.QtWidgets import (QWidget, QSpinBox, QTextEdit, QFontComboBox,
                               QPushButton, QComboBox, QDoubleSpinBox, QColorDialog,
                               QGraphicsOpacityEffect, QMessageBox)
from PySide6.QtCore import Qt, Signal, QMimeData, QSize
from PySide6.QtGui import QFont, QTextCursor, QTextBlockFormat, QTextCharFormat, QIcon
import re

from .canvas_items import DesignerBox, ImageItem, BackgroundItem, px_to_mm
from core.custom_widgets import MathDoubleSpinBox
from core.html_utils import normalize_text_decoration
from core.text_layout import PLACEHOLDER_PATTERN
from core.resources import action_icon_path, align_icon_path
from core.theme_icons import themed_svg_icon
from core.i18n import tr


class CleanTextEdit(QTextEdit):
    """Campo de texto customizado que intercepta o Ctrl+V e purifica o HTML."""
    editingFinished = Signal()
    
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()

    def insertFromMimeData(self, source: QMimeData):
        if source.hasHtml():
            raw = source.html()
            # Exterminador no momento exato da colagem
            clean = re.sub(r"font-family\s*:[^;\"]+;?", "", raw)
            clean = re.sub(r"font-size\s*:[^;\"]+;?", "", clean)
            clean = re.sub(r"color\s*:[^;\"]+;?", "", clean)
            clean = re.sub(r"background-color\s*:[^;\"]+;?", "", clean)
            clean = normalize_text_decoration(clean)
            clean = re.sub(r"line-height\s*:[^;\"]+;?", "", clean)
            clean = re.sub(r"(?i)<a\b[^>]*>", "", clean)
            clean = re.sub(r"(?i)</a>", "", clean)
            clean = re.sub(r"(?i)<h[1-6]([^>]*)>", r"<p\1>", clean)
            clean = re.sub(r"(?i)</h[1-6]>", "</p>", clean)
            
            new_mime = QMimeData()
            new_mime.setHtml(clean)
            new_mime.setText(source.text())
            super().insertFromMimeData(new_mime)
        else:
            super().insertFromMimeData(source)

class CaixaDeTextoPanel(QWidget):
    ENABLED_OPACITY = 1.0
    DISABLED_OPACITY = 0.4
    PROPORTION_OFF_BACKGROUND = "rgba(220, 53, 69, 102)"
    PROPORTION_OFF_HOVER_BACKGROUND = "rgba(220, 53, 69, 130)"

    widthChanged = Signal(float)
    heightChanged = Signal(float)
    rotationChanged = Signal(float)
    proportionToggled = Signal(bool) # Novo sinal para a Checkbox
    linkToggled = Signal(bool)
    restoreRequested = Signal()
    opacityChanged = Signal(float)
    snapshotRequested = Signal()

    def __init__(self):
        super().__init__()
        # Este widget conserva o estado e os sinais dos controles. A interface
        # atual é montada exclusivamente em frontend.py, que assume a
        # propriedade visual dos controles abaixo.
        self._aspect_ratio = 1.0
        self._group_mode = False
        self._restore_available = False
        self._link_available = False

        self.spin_w = MathDoubleSpinBox(self)
        self.spin_w.setRange(1.0, 5000.0)
        self.spin_w.setDecimals(2)
        self.spin_w.setKeyboardTracking(False)
        self.spin_w.valueChanged.connect(self._on_w_changed)

        self.spin_h = MathDoubleSpinBox(self)
        self.spin_h.setRange(1.0, 5000.0)
        self.spin_h.setDecimals(2)
        self.spin_h.setKeyboardTracking(False)
        self.spin_h.valueChanged.connect(self._on_h_changed)

        self.chk_proporcao = self._make_tool_button(
            "",
            "<b>MANTER PROPORÇÃO</b><br><br>Preserva a relação entre largura e altura durante o redimensionamento.",
            checkable=True,
        )
        self.chk_proporcao.setChecked(True)
        self.op_proporcao = QGraphicsOpacityEffect(self.chk_proporcao)
        self.chk_proporcao.setGraphicsEffect(self.op_proporcao)
        self.op_proporcao.setOpacity(1.0)
        self.chk_proporcao.toggled.connect(self._on_proportion_toggled)

        self.btn_restore = self._make_tool_button(
            "🔄",
            "<b>RESTAURAR ORIGINAL</b><br><br>Restaura tamanho e rotação nativos do arquivo.",
        )
        self.op_restore = QGraphicsOpacityEffect(self.btn_restore)
        self.btn_restore.setGraphicsEffect(self.op_restore)
        self.op_restore.setOpacity(1.0)
        self.btn_restore.clicked.connect(self.restoreRequested.emit)

        self.spin_rot = MathDoubleSpinBox(self)
        self.spin_rot.setRange(0.0, 359.9)
        self.spin_rot.setDecimals(1)
        self.spin_rot.setWrapping(True)
        self.spin_rot.valueChanged.connect(self.rotationChanged.emit)

        self.btn_rot_minus_90 = self._make_tool_button("", "Gira o objeto 90° anti-horário.")
        self.btn_rot_plus_90 = self._make_tool_button("", "Gira o objeto 90° horário.")
        for button, asset_name in (
            (self.btn_rot_minus_90, "rotate-left"),
            (self.btn_rot_plus_90, "rotate-right"),
        ):
            button.setIcon(themed_svg_icon(action_icon_path(asset_name)))
            button.setIconSize(QSize(18, 18))
        self.op_rot_minus = QGraphicsOpacityEffect(self.btn_rot_minus_90)
        self.btn_rot_minus_90.setGraphicsEffect(self.op_rot_minus)
        self.op_rot_plus = QGraphicsOpacityEffect(self.btn_rot_plus_90)
        self.btn_rot_plus_90.setGraphicsEffect(self.op_rot_plus)
        self.btn_rot_minus_90.clicked.connect(lambda: self._apply_rotation_delta(-90))
        self.btn_rot_plus_90.clicked.connect(lambda: self._apply_rotation_delta(90))

        self.spin_opacity = MathDoubleSpinBox(self)
        self.spin_opacity.setRange(0.0, 100.0)
        self.spin_opacity.setDecimals(0)
        self.spin_opacity.setValue(100.0)
        self.spin_opacity.valueChanged.connect(self._on_opacity_changed)

        self.chk_link = QPushButton(tr("Habilitar link"), self)
        self.chk_link.setCheckable(True)
        self.chk_link.setFixedHeight(22)
        self.chk_link.setToolTip(
            "<b>HABILITAR LINK (URL)</b><br><br>Cria uma área clicável no PDF exportado."
        )
        self.chk_link.toggled.connect(self.linkToggled.emit)
        self.op_link = QGraphicsOpacityEffect(self.chk_link)
        self.chk_link.setGraphicsEffect(self.op_link)
        self.op_link.setOpacity(self.DISABLED_OPACITY)

        self.spin_w.editingFinished.connect(self.snapshotRequested.emit)
        self.spin_h.editingFinished.connect(self.snapshotRequested.emit)
        self.spin_rot.editingFinished.connect(self.snapshotRequested.emit)
        self.spin_opacity.editingFinished.connect(self.snapshotRequested.emit)
        self.chk_proporcao.clicked.connect(self.snapshotRequested.emit)
        self.chk_link.clicked.connect(self.snapshotRequested.emit)
        self.clear_selection_state()

    def _tool_button_style(self):
        return """
            QPushButton { 
                background-color: transparent; 
                border: none; 
                border-radius: 4px; 
                font-size: 16px; 
            }
            QPushButton:hover { background-color: @hover@; }
            QPushButton:pressed { background-color: @selection@; }
            QPushButton:disabled { color: @disabled@; }
        """

    @staticmethod
    def _proportion_button_style(active: bool):
        return """
            QPushButton {
                padding: 0; min-width: 28px; max-width: 28px;
                min-height: 28px; max-height: 28px;
                background-color: @button@; border: 1px solid @border@;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: @hover@; border-color: @border_strong@; }
            QPushButton:checked { background-color: @selection@; border-color: @accent@; }
            QPushButton:disabled { background-color: @surface@; color: @disabled@; }
        """

    def _make_tool_button(self, text, tooltip="", checkable=False):
        btn = QPushButton(text)
        btn.setFixedSize(26, 26) # Tamanho padrão dos seus ícones de guia
        btn.setCheckable(checkable)
        themed_style(btn, self._tool_button_style())
        btn.setToolTip(tooltip)
        return btn

    def _normalize_rotation(self, value):
        return round(value % 360.0, 1)

    def _apply_rotation_delta(self, delta):
        self.spin_rot.setValue(self._normalize_rotation(self.spin_rot.value() + delta))
        self.snapshotRequested.emit()

    def _on_proportion_toggled(self, checked):
        # Altera visualmente a opacidade
        self._refresh_proportion_button(not self._group_mode and self.isEnabled())
        # Emite o sinal original para o editor_window atualizar o item
        self.proportionToggled.emit(checked)

    def _opacity_effect_for(self, widget):
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        return effect

    def _set_widget_available(self, widget, available: bool, enabled_opacity=None):
        widget.setEnabled(available)
        opacity = enabled_opacity if available and enabled_opacity is not None else self.ENABLED_OPACITY
        if not available:
            opacity = self.DISABLED_OPACITY
        self._opacity_effect_for(widget).setOpacity(opacity)

    def _set_widgets_available(self, widgets, available: bool, enabled_opacity=None):
        for widget in widgets:
            self._set_widget_available(widget, available, enabled_opacity)

    def _refresh_proportion_button(self, available: bool):
        checked = self.chk_proporcao.isChecked()
        asset_name = "lock ratio" if checked else "unlock ratio"
        self.chk_proporcao.setIcon(themed_svg_icon(action_icon_path(asset_name)))
        self.chk_proporcao.setIconSize(QSize(20, 20))
        self.chk_proporcao.setEnabled(available)
        themed_style(self.chk_proporcao, self._proportion_button_style(available and checked))
        if not available:
            opacity = self.DISABLED_OPACITY
        elif not checked:
            opacity = 0.2
        else:
            opacity = self.ENABLED_OPACITY
        self.op_proporcao.setOpacity(opacity)

    def _set_size_controls_available(self, available: bool):
        self._set_widgets_available((self.spin_w, self.spin_h), available)
        self._refresh_proportion_button(available)

    def _set_rotation_controls_available(self, available: bool):
        self._set_widgets_available(
            (
                self.spin_rot,
                self.btn_rot_minus_90,
                self.btn_rot_plus_90,
            ),
            available,
        )

    def _set_restore_available(self, available: bool):
        self._set_widget_available(self.btn_restore, available)

    def _set_link_available(self, available: bool):
        self._set_widget_available(self.chk_link, available)

    def set_link_available(self, available: bool):
        self._link_available = available
        self._set_link_available(available)

    def _set_opacity_controls_available(self, available: bool):
        self._set_widget_available(self.spin_opacity, available)

    def _on_opacity_changed(self, val):
        clamped = max(0.0, min(100.0, val))
        if val != clamped:
            self.spin_opacity.blockSignals(True)
            self.spin_opacity.setValue(clamped)
            self.spin_opacity.blockSignals(False)
        self.opacityChanged.emit(clamped / 100.0)
    
    def clear_selection_state(self):
        self._group_mode = False
        self._restore_available = False
        self._link_available = False
        self._set_size_controls_available(False)
        self._set_restore_available(False)
        self._set_rotation_controls_available(False)
        self._set_opacity_controls_available(False)
        self._set_link_available(False)

    def set_group_mode(self, enabled: bool):
        self._group_mode = enabled

        item_controls_enabled = not enabled
        self._set_size_controls_available(item_controls_enabled)
        self._set_rotation_controls_available(True)
        self._set_restore_available(self._restore_available and item_controls_enabled)
        self._set_opacity_controls_available(True)
        self._set_link_available(self._link_available)

    def load_from_item(self, box: DesignerBox):
        self.blockSignals(True) 
        self._restore_available = False
        self._link_available = True
        rect = box.rect()
        self.spin_h.setMinimum(1.0)
        self.spin_w.setValue(px_to_mm(rect.width()))
        self.spin_h.setValue(px_to_mm(rect.height()))
        self.spin_rot.setValue(self._normalize_rotation(box.rotation()))
        if rect.height() > 0: self._aspect_ratio = rect.width() / rect.height()
        self.spin_opacity.setValue(box.opacity() * 100.0)
        
        self.chk_proporcao.blockSignals(True)
        is_proportional = getattr(box, 'keep_proportion', True) # Use img se estiver na load_from_image
        self.chk_proporcao.setChecked(is_proportional)
        self.chk_proporcao.blockSignals(False)
        self._refresh_proportion_button(not self._group_mode and self.isEnabled())
        self.chk_link.blockSignals(True)
        self.chk_link.setChecked(getattr(box.state, 'has_link', False))
        self.chk_link.blockSignals(False)
        # Desativa o botão restaurar para Textos
        self._set_restore_available(False)
        self._set_link_available(True)
        self.blockSignals(False)

    def load_from_image(self, img):
        self.blockSignals(True)
        self._restore_available = True
        self._link_available = isinstance(img, ImageItem) and not isinstance(img, BackgroundItem)
        rect = img.rect() if hasattr(img, 'rect') else img.pixmap().rect()
        self.spin_h.setMinimum(0.01 if getattr(img, 'shape_type', '') == 'line' else 1.0)
        self.spin_w.setValue(px_to_mm(rect.width()))
        self.spin_h.setValue(px_to_mm(rect.height()))
        self.spin_rot.setValue(self._normalize_rotation(img.rotation()))
        if rect.height() > 0: self._aspect_ratio = rect.width() / rect.height()
        self.spin_opacity.setValue(img.opacity() * 100.0)
        
        self.chk_proporcao.blockSignals(True)
        self.chk_proporcao.setChecked(getattr(img, 'keep_proportion', True))
        self.chk_proporcao.blockSignals(False)
        self._refresh_proportion_button(not self._group_mode and self.isEnabled())
        self.chk_link.blockSignals(True)
        self.chk_link.setChecked(getattr(img, 'has_link', False))
        self.chk_link.blockSignals(False)
        # Ativa o botão restaurar para Imagens
        self._set_restore_available(True)
        self._set_link_available(self._link_available)
        self.blockSignals(False)

    def _on_w_changed(self, val):
        if self.chk_proporcao.isChecked() and self._aspect_ratio > 0:
            new_h = val / self._aspect_ratio
            self.spin_h.blockSignals(True)
            self.spin_h.setValue(new_h)
            self.spin_h.blockSignals(False)
            self.widthChanged.emit(val)
            self.heightChanged.emit(new_h)
        else:
            self.widthChanged.emit(val)

    def _on_h_changed(self, val):
        if self.chk_proporcao.isChecked() and self._aspect_ratio > 0:
            new_w = val * self._aspect_ratio
            self.spin_w.blockSignals(True)
            self.spin_w.setValue(new_w)
            self.spin_w.blockSignals(False)
            self.heightChanged.emit(val)
            self.widthChanged.emit(new_w)
        else:
            self.heightChanged.emit(val)

    
class EditorDeTextoPanel(QWidget):
    htmlChanged = Signal(str)
    fontFamilyChanged = Signal(QFont)
    fontSizeChanged = Signal(int)
    fontColorChanged = Signal(str)
    boldChanged = Signal(bool) 
    alignChanged = Signal(str)
    verticalAlignChanged = Signal(str)
    indentChanged = Signal(float)
    lineHeightChanged = Signal(float)
    snapshotRequested = Signal()

    def __init__(self):
        super().__init__()
        # Controlador sem layout próprio. frontend.py monta e exibe estes
        # controles na árvore visual definitiva do editor.
        self.txt_content = CleanTextEdit(self)
        self.txt_content.setMinimumHeight(160)
        themed_style(
            self.txt_content,
            "background-color: @field@; color: @text@; border: 1px solid @border@; "
            "font-family: 'Inter 18pt', sans-serif; font-size: 11pt;",
        )
        self.txt_content.textChanged.connect(self._emit_clean_html)

        self.cbo_font = QFontComboBox(self)
        self.cbo_font.setToolTip("Selecionar a família tipográfica.")
        self.cbo_font.currentFontChanged.connect(self.set_font_family)

        self.spin_size = QSpinBox(self)
        self.spin_size.setRange(1, 999)
        self.spin_size.setToolTip("Alterar o tamanho da fonte.")
        self.spin_size.valueChanged.connect(self.set_font_size)

        self.btn_bold = QPushButton(self)
        self.btn_italic = QPushButton(self)
        self.btn_underline = QPushButton(self)
        for button, asset_name, tooltip in (
            (self.btn_bold, "bold", "Negrito (Ctrl+B)"),
            (self.btn_italic, "italic", "Itálico (Ctrl+I)"),
            (self.btn_underline, "underline", "Sublinhado (Ctrl+U)"),
        ):
            button.setFixedWidth(30)
            button.setIcon(themed_svg_icon(align_icon_path(asset_name)))
            button.setIconSize(QSize(14, 14))
            button.setCheckable(True)
            button.setToolTip(tooltip)
        self.btn_bold.clicked.connect(lambda: self.set_format_attribute("bold"))
        self.btn_italic.clicked.connect(lambda: self.set_format_attribute("italic"))
        self.btn_underline.clicked.connect(lambda: self.set_format_attribute("underline"))

        self.btn_color = QPushButton("", self)
        self.btn_color.setFixedWidth(30)
        self.btn_color.setToolTip("Selecionar a cor do texto.")
        themed_style(
            self.btn_color,
            "background-color: #000000; border: 1px solid @border_strong@; border-radius: 3px;",
        )
        self.btn_color.clicked.connect(self._choose_color)

        # Os combos mantêm o estado e os sinais usados pelos botões de ícone
        # da interface atual; não são elementos visuais do painel legado.
        self.cbo_align = QComboBox(self)
        self.cbo_align.addItems([tr("Esquerda"), tr("Centro"), tr("Direita"), tr("Justificado")])
        self._align_map = ["left", "center", "right", "justify"]
        self.cbo_align.currentIndexChanged.connect(
            lambda idx: self.alignChanged.emit(self._align_map[idx])
        )
        self.cbo_valign = QComboBox(self)
        self.cbo_valign.addItems([tr("Topo"), tr("Meio"), tr("Base")])
        self._valign_map = ["top", "center", "bottom"]
        self.cbo_valign.currentIndexChanged.connect(
            lambda idx: self.verticalAlignChanged.emit(self._valign_map[idx])
        )

        self.spin_indent = MathDoubleSpinBox(self)
        self.spin_indent.setRange(0, 500)
        self.spin_indent.valueChanged.connect(self._on_indent_changed)
        self.spin_lh = MathDoubleSpinBox(self)
        self.spin_lh.setRange(0.5, 5.0)
        self.spin_lh.setSingleStep(0.05)
        self.spin_lh.setValue(1.15)
        self.spin_lh.valueChanged.connect(self.lineHeightChanged.emit)

        self.txt_content.cursorPositionChanged.connect(self.update_buttons_state)
        self.txt_content.editingFinished.connect(self.snapshotRequested.emit)
        self.cbo_font.activated.connect(lambda _: self.snapshotRequested.emit())
        self.spin_size.editingFinished.connect(self.snapshotRequested.emit)
        self.btn_bold.clicked.connect(self.snapshotRequested.emit)
        self.btn_italic.clicked.connect(self.snapshotRequested.emit)
        self.btn_underline.clicked.connect(self.snapshotRequested.emit)
        self.cbo_align.activated.connect(lambda _: self.snapshotRequested.emit())
        self.cbo_valign.activated.connect(lambda _: self.snapshotRequested.emit())
        self.spin_indent.editingFinished.connect(self.snapshotRequested.emit)
        self.spin_lh.editingFinished.connect(self.snapshotRequested.emit)

    def load_from_item(self, box: DesignerBox):
        self.blockSignals(True)
        self.txt_content.blockSignals(True)

        state = box.state

        # 1. Limpeza Retroativa UI: Remove links/cores antigas do JSON antes de jogar no painel
        clean_html = re.sub(r"font-family\s*:[^;\"]+;?", "", state.html_content)
        clean_html = re.sub(r"font-size\s*:[^;\"]+;?", "", clean_html)
        clean_html = re.sub(r"color\s*:[^;\"]+;?", "", clean_html)
        clean_html = re.sub(r"background-color\s*:[^;\"]+;?", "", clean_html)
        clean_html = normalize_text_decoration(clean_html)
        clean_html = re.sub(r"line-height\s*:[^;\"]+;?", "", clean_html)
        clean_html = re.sub(r"(?i)<a\b[^>]*>", "", clean_html)
        clean_html = re.sub(r"(?i)</a>", "", clean_html)
        clean_html = re.sub(r"(?i)<h[1-6]([^>]*)>", r"<p\1>", clean_html)
        clean_html = re.sub(r"(?i)</h[1-6]>", "</p>", clean_html)

        # Carrega o conteúdo purificado no editor e força fonte padrão UI
        self.txt_content.setHtml(clean_html)

        cursor = self.txt_content.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.txt_content.setTextCursor(cursor)

        # 2. Preenche os controles com os metadados puros da Fonte da Verdade
        font_signals_blocked = self.cbo_font.blockSignals(True)
        try:
            self.cbo_font.setCurrentFont(QFont(state.font_family))
        finally:
            self.cbo_font.blockSignals(font_signals_blocked)
        self.spin_size.setValue(state.font_size)
        
        color_hex = getattr(state, 'font_color', '#000000')
        themed_style(self.btn_color, f"background-color: {color_hex}; border: 1px solid @border_strong@; border-radius: 3px;")
        
        self.update_buttons_state()

        if state.align == "right": self.cbo_align.setCurrentIndex(2)
        elif state.align == "center": self.cbo_align.setCurrentIndex(1)
        elif state.align == "justify": self.cbo_align.setCurrentIndex(3)
        else: self.cbo_align.setCurrentIndex(0)

        if state.vertical_align == "center": self.cbo_valign.setCurrentIndex(1)
        elif state.vertical_align == "bottom": self.cbo_valign.setCurrentIndex(2)
        else: self.cbo_valign.setCurrentIndex(0)

        self.spin_indent.setValue(state.indent_px)
        self.spin_lh.setValue(state.line_height)

        # Refletir o recuo no próprio editor de texto para feedback visual
        cursor_block = QTextCursor(self.txt_content.document())
        cursor_block.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setTextIndent(state.indent_px)
        cursor_block.mergeBlockFormat(fmt)

        self.txt_content.blockSignals(False)
        self.blockSignals(False)
    
    def update_buttons_state(self):
        fmt = self.txt_content.currentCharFormat()
        
        self.btn_bold.blockSignals(True)
        self.btn_italic.blockSignals(True)
        self.btn_underline.blockSignals(True)

        self.btn_bold.setChecked(fmt.fontWeight() == QFont.Weight.Bold)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_underline.setChecked(fmt.fontUnderline())

        self.btn_bold.blockSignals(False)
        self.btn_italic.blockSignals(False)
        self.btn_underline.blockSignals(False)

    def set_font_family(self, font):
        self.fontFamilyChanged.emit(font)
        self.txt_content.setFocus()

    def set_font_size(self, size):
        self.fontSizeChanged.emit(size)

    def set_format_attribute(self, attr_type):
        controller = getattr(self.window(), 'canvas_edit', None)
        button = getattr(self, 'btn_' + attr_type)
        if controller and controller.format(attr_type, button.isChecked()):
            controller.checkpoint()
            return
        cursor = self.txt_content.textCursor()

        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)

        fmt = QTextCharFormat()

        if attr_type == "bold":
            desired_on = self.btn_bold.isChecked()
            fmt.setFontWeight(QFont.Weight.Bold if desired_on else QFont.Weight.Normal)
        elif attr_type == "italic":
            desired_on = self.btn_italic.isChecked()
            fmt.setFontItalic(desired_on)
        elif attr_type == "underline":
            desired_on = self.btn_underline.isChecked()
            fmt.setFontUnderline(desired_on)

        cursor.mergeCharFormat(fmt)
        self.txt_content.mergeCurrentCharFormat(fmt)
        self.txt_content.setFocus()

    def _choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            alpha_control = self.window().findChild(QDoubleSpinBox, 'textColorAlpha')
            if alpha_control:
                color.setAlphaF(alpha_control.value()/100)
                hex_color = color.name(color.NameFormat.HexArgb)
            themed_style(self.btn_color, f"background-color: {hex_color}; border: 1px solid @border_strong@; border-radius: 3px;")
            self.fontColorChanged.emit(hex_color)
            self.snapshotRequested.emit()
            self.txt_content.setFocus()

    def _on_indent_changed(self, val):
        self.indentChanged.emit(val)
        # Atualiza o feedback visual do espaçamento em tempo real enquanto digita
        cursor = QTextCursor(self.txt_content.document())
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setTextIndent(val)
        cursor.mergeBlockFormat(fmt)

    def _emit_clean_html(self):
        raw_html = self.txt_content.toHtml()
        
        # FAXINA GERAL: Remove fontes, tamanhos, cores, fundos e decorações indesejadas do Ctrl+V
        clean_html = re.sub(r"font-family\s*:[^;\"]+;?", "", raw_html)
        clean_html = re.sub(r"font-size\s*:[^;\"]+;?", "", clean_html)
        clean_html = re.sub(r"color\s*:[^;\"]+;?", "", clean_html)
        clean_html = re.sub(r"background-color\s*:[^;\"]+;?", "", clean_html)
        clean_html = normalize_text_decoration(clean_html)
        clean_html = re.sub(r"line-height\s*:[^;\"]+;?", "", clean_html)
        
        # Extermina Hiperlinks fantasmas (tags <a>) mantendo apenas o texto limpo
        clean_html = re.sub(r"(?i)<a\b[^>]*>", "", clean_html)
        clean_html = re.sub(r"(?i)</a>", "", clean_html)
        
        # Rebaixa tags de título (h1, h2...) para parágrafos comuns (p)
        clean_html = re.sub(r"(?i)<h[1-6]([^>]*)>", r"<p\1>", clean_html)
        clean_html = re.sub(r"(?i)</h[1-6]>", "</p>", clean_html)
        
        self.htmlChanged.emit(clean_html)

    def make_placeholder(self):
        if not self.isVisible() or not self.isEnabled(): 
            return
            
        cursor = self.txt_content.textCursor()
        if not cursor.hasSelection():
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione uma palavra primeiro para transformá-la em variável."))
            return
            
        selected_text = cursor.selectedText()
        if not re.fullmatch(r"[\w]+", selected_text):
            QMessageBox.warning(self, tr("Caracteres inválidos"), tr("A variável só pode conter letras, números e subtraços (_). Remova espaços ou símbolos."))
            return
            
        cursor.insertText(f"{{{selected_text}}}")
        self.snapshotRequested.emit()
        self.txt_content.setFocus()

    def make_optional_section(self):
        if not self.isVisible() or not self.isEnabled(): 
            return
            
        cursor = self.txt_content.textCursor()
        if not cursor.hasSelection():
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um trecho de texto para transformá-lo em opcional."))
            return
            
        selected_text = cursor.selectedText()
        if not re.search(PLACEHOLDER_PATTERN, selected_text):
            QMessageBox.warning(self, tr("Ausência de variável"), tr("Um trecho opcional precisa conter pelo menos uma variável válida (ex.: {Nome}) para funcionar."))
            return
            
        cursor.insertText(f"|{selected_text}|")
        self.snapshotRequested.emit()
        self.txt_content.setFocus()
