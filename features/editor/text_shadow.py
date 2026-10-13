"""Controles da sombra externa da caixa inteira, com prévia e um undo por gesto."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QDoubleSpinBox, QAbstractSpinBox, QSizePolicy

from core.color_dialog import get_color
from core.i18n import tr
from core.resources import state_icon_path
from core.themes import themed_style
from core.text_effects import normalize_shadow
from .canvas_items import DesignerBox, px_to_mm, mm_to_px
from .live_opacity import connect_live_opacity
from .shadow_direction import ShadowDirectionDial


class TextShadowControls(QWidget):
    def __init__(self, window):
        super().__init__()
        from .frontend import property_heading, centered_toggle_button, column, row, field, compact, square_control
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        property_heading(layout, tr('SOMBRA EXTERNA'), separated=True)
        self.enabled = QPushButton(tr('Habilitar sombra'))
        self.enabled.setObjectName('textShadowEnabled')
        self.enabled.setCheckable(True)
        centered_toggle_button(layout, self.enabled)
        self.details, body = column()
        body.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.details)
        self.color = QLineEdit('#000000')
        self.color.setMaxLength(7)
        self.color.setAccessibleName(tr('Cor da sombra'))
        self.swatch = QPushButton()
        self.swatch.setToolTip(tr('Cor da sombra'))
        square_control(self.swatch)
        self.opacity = self.spin('textShadowOpacity', 100, 0, tr('Opacidade da sombra'))
        colors = row(body, self.swatch, self.color, compact(
            state_icon_path('opacity'), self.opacity, '%', 85, tr('Opacidade da sombra')))
        colors.setStretch(1, 1)
        self.angle = ShadowDirectionDial()
        self.light_angle = self.spin('textShadowLightAngle', 360, 1, tr('Ângulo da luz'))
        self.light_angle.setSuffix('°')
        self.light_angle.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.light_angle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.light_angle.setFixedSize(56, 22)
        self.light_angle.setToolTip(tr('Ângulo da luz. 0°: direita; 90°: acima; 180°: esquerda; 270°: abaixo.'))
        themed_style(self.light_angle,
            'QDoubleSpinBox { background: transparent; border: 1px solid transparent; '
            'border-radius: 4px; padding: 0 3px; min-height: 0; font-size: 11px; color: @muted@; } '
            'QDoubleSpinBox:hover { border-color: @border@; } '
            'QDoubleSpinBox:focus { background: @field@; border-color: @accent@; color: @text@; }')
        light_controls = QWidget()
        light_layout = QHBoxLayout(light_controls)
        light_layout.setContentsMargins(0, 0, 0, 0)
        light_layout.setSpacing(4)
        light_layout.addWidget(self.angle)
        light_layout.addWidget(self.light_angle, 0, Qt.AlignmentFlag.AlignVCenter)
        self.distance = self.spin('textShadowDistance', px_to_mm(240), 2, tr('Distância da sombra'))
        self.blur = self.spin('textShadowBlur', px_to_mm(120), 2, tr('Desfoque da sombra'))
        for spin in (self.distance, self.blur):
            spin.setSuffix(' mm')
            spin.setSingleStep(.05)
        measures, measures_layout = column()
        measures_layout.setContentsMargins(0, 0, 0, 0)
        measures_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        measures_layout.addWidget(field(tr('Distância'), self.distance))
        measures_layout.addWidget(field(tr('Desfoque'), self.blur))
        light_field = field(tr('Posição da luz'), light_controls)
        light_field.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        light_field.setFixedWidth(self.angle.width()+light_layout.spacing()+self.light_angle.width())
        direction_row = row(body, light_field, measures)
        direction_row.setStretch(1, 1)
        self.enabled.clicked.connect(self.commit)
        self.color.editingFinished.connect(self.commit)
        self.swatch.clicked.connect(self.choose_color)
        for spin in (self.opacity, self.angle, self.distance, self.blur):
            connect_live_opacity(window, spin, lambda _: self.apply(), available=lambda: self.isEnabled())
            spin.editingFinished.connect(self.commit)
        self.angle.valueChanged.connect(self.sync_light_angle)
        connect_live_opacity(window, self.light_angle, self.angle.setLightAngle,
                             available=lambda: self.isEnabled())
        self.light_angle.editingFinished.connect(self.commit)
        self.sync()

    def spin(self, name, maximum, decimals, label):
        spin = QDoubleSpinBox()
        spin.setObjectName(name)
        spin.setRange(0, maximum)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        spin.setAccessibleName(label)
        spin.setToolTip(label)
        return spin

    def selected(self):
        items = self.window.scene.selectedItems()
        return items[0] if len(items) == 1 and isinstance(items[0], DesignerBox) else None

    @staticmethod
    def typing_spin(control):
        # O Qt pode limpar isModified mesmo antes de confirmar a digitação.
        return isinstance(control, QDoubleSpinBox) and control.hasFocus() and (
            control.lineEdit().isModified() or control.cleanText() != control.textFromValue(control.value()))

    def sync(self):
        box = self.selected()
        self.setVisible(box is not None)
        self.setEnabled(box is not None)
        if box is None:
            return
        shadow = normalize_shadow(box.state.shadow)
        for control, value in ((self.enabled, shadow['enabled']), (self.opacity, shadow['opacity'] * 100),
                               (self.angle, shadow['angle']), (self.distance, px_to_mm(shadow['distance'])),
                               (self.blur, px_to_mm(shadow['blur']))):
            # A sincronização da cena não pode interromper a digitação no spin.
            if self.typing_spin(control):
                continue
            with QSignalBlocker(control):
                if control is self.enabled:
                    control.setChecked(value)
                else:
                    control.setValue(value)
        self.sync_light_angle()
        if not self.color.hasFocus():
            self.color.setText(shadow['color'])
        self.presentation(shadow)

    def sync_light_angle(self, *_):
        if self.typing_spin(self.light_angle):
            return
        with QSignalBlocker(self.light_angle):
            self.light_angle.setValue(self.angle.lightAngle())

    def presentation(self, shadow):
        self.enabled.setText(tr('Desabilitar sombra') if shadow['enabled'] else tr('Habilitar sombra'))
        self.details.setVisible(shadow['enabled'])
        themed_style(self.swatch, f"background: {shadow['color']}; border: 1px solid @border_strong@; border-radius: 5px;")

    def apply(self):
        box = self.selected()
        if box is None:
            return
        color = QColor(self.color.text())
        if not color.isValid():
            self.color.setText(normalize_shadow(box.state.shadow)['color'])
            return
        shadow = normalize_shadow(dict(enabled=self.enabled.isChecked(), color=color.name(),
            opacity=self.opacity.value()/100, angle=self.angle.value(),
            distance=mm_to_px(self.distance.value()), blur=mm_to_px(self.blur.value())))
        box.set_shadow(shadow)
        self.presentation(shadow)

    def commit(self, *_):
        self.apply()
        self.window.save_snapshot()

    def choose_color(self):
        box = self.selected()
        if box is None:
            return
        color = get_color(QColor(self.color.text()), self.window, tr('Cor da sombra'))
        if color.isValid() and self.selected() is box:
            self.color.setText(color.name())
            self.commit()
