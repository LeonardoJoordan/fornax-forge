"""Seletor de luz: a direção persistida continua sendo a projeção da sombra."""
import math

from PySide6.QtCore import Qt, Signal, QPointF, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from core.i18n import tr
from core.themes import theme_color, theme_manager


class ShadowDirectionDial(QWidget):
    valueChanged = Signal(float)
    editingFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 45.
        self._dragging = False
        self._key_active = False
        self._gesture_start = self._value
        self.setObjectName('textShadowAngle')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(96, 96)
        self.setAccessibleName(tr('Posição da luz'))
        self.setToolTip(tr('Posicione a luz no círculo. A sombra aparece no lado oposto. Use as setas para ajustar o ângulo.'))
        theme_manager().changed.connect(self.update)

    def sizeHint(self):
        return QSize(96, 96)

    def value(self):
        """Ângulo da sombra, em graus no sentido horário, a partir da direita."""
        return self._value

    def lightAngle(self):
        """Ângulo da luz: 0° à direita, 90° acima (convenção do círculo)."""
        return (180 - self._value) % 360

    def setLightAngle(self, value):
        self.setValue(180 - value)

    def setValue(self, value):
        value = float(value) % 360
        if math.isfinite(value) and not math.isclose(value, self._value, abs_tol=1e-9):
            self._value = value
            self.update()
            self.valueChanged.emit(value)

    def _circle(self):
        center = QPointF(self.width() / 2, self.height() / 2)
        return center, max(1., min(self.width(), self.height()) / 2 - 12)

    def lightPosition(self):
        center, radius = self._circle()
        angle = math.radians(self._value + 180)
        return center + QPointF(math.cos(angle) * radius, math.sin(angle) * radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = self._circle()
        painter.setPen(QPen(QColor(theme_color('border_strong')), 1.2))
        painter.setBrush(QColor(theme_color('surface')))
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for degrees in (0, 90, 180, 270):
            angle = math.radians(degrees)
            direction = QPointF(math.cos(angle), math.sin(angle))
            painter.drawLine(center + direction * (radius - 5), center + direction * (radius - 1))
        accent = QColor(theme_color('accent' if self.isEnabled() else 'disabled'))
        sun = self.lightPosition()
        painter.setPen(QPen(accent, 1.5))
        painter.drawLine(center, sun)
        painter.setBrush(accent)
        painter.drawEllipse(center, 2, 2)
        # Sol desenhado pelo Qt: mesma geometria e cores em todos os sistemas.
        painter.setPen(QPen(QColor(theme_color('surface')), 3))
        painter.drawEllipse(sun, 4.5, 4.5)
        painter.setPen(QPen(accent, 1.5))
        for degrees in range(0, 360, 45):
            angle = math.radians(degrees)
            direction = QPointF(math.cos(angle), math.sin(angle))
            painter.drawLine(sun + direction * 7, sun + direction * 9)

    def _point_angle(self, position):
        center, _ = self._circle()
        delta = position - center
        if math.hypot(delta.x(), delta.y()) >= 3:
            # O mouse escolhe a luz; o documento guarda sua projeção oposta.
            self.setValue(round(math.degrees(math.atan2(delta.y(), delta.x())) + 180) % 360)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._gesture_start = self.value()
            self._dragging = True
            self._point_angle(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._point_angle(event.position())
            else:
                self._finish()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._point_angle(event.position())
            self._finish()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and (self._dragging or self._key_active):
            self._dragging = self._key_active = False
            self.setValue(self._gesture_start)
            event.accept()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            if not self._key_active:
                self._gesture_start = self.value()
                self._key_active = True
            step = 15 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            sign = -1 if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
            self.setValue(self.value() + sign * step)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._key_active and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            if not event.isAutoRepeat():
                self._finish()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def _finish(self):
        active = self._dragging or self._key_active
        self._dragging = self._key_active = False
        if active and not math.isclose(self.value(), self._gesture_start, abs_tol=1e-9):
            self.editingFinished.emit()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        self._finish()
        super().focusOutEvent(event)
        self.update()

    def event(self, event):
        if event.type() in (QEvent.Type.UngrabMouse, QEvent.Type.Hide, QEvent.Type.WindowDeactivate):
            self._finish()
        return super().event(event)
