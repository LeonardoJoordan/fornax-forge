"""Impede alterações acidentais em seletores durante a rolagem de painéis."""

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QComboBox, QWidget
from shiboken6 import isValid


class WheelFocusGuard(QObject):
    """Só permite que o último seletor clicado processe a roda."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armed = None

    @staticmethod
    def _selector_for(widget):
        while isinstance(widget, QWidget) and isValid(widget):
            if isinstance(widget, (QComboBox, QAbstractSpinBox)):
                return widget
            widget = widget.parentWidget()
        return None

    def _belongs_to_combo_popup(self, widget):
        # Editores de células são destruídos ao confirmar/cancelar a seleção.
        # A referência Python pode sobreviver ao controle nativo do Qt.
        if self._armed is not None and not isValid(self._armed):
            self._armed = None
        if not isinstance(self._armed, QComboBox):
            return False
        popup = self._armed.view()
        viewport = popup.viewport()
        while isinstance(widget, QWidget) and isValid(widget):
            if widget is popup or widget is viewport:
                return True
            widget = widget.parentWidget()
        return False

    def eventFilter(self, watched, event):
        if self._armed is not None and not isValid(self._armed):
            self._armed = None
        if not isValid(watched):
            return False
        kind = event.type()
        selector = self._selector_for(watched)
        if kind == QEvent.Type.Polish and selector is not None:
            selector.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        elif kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if selector is not None:
                self._armed = selector
            elif not self._belongs_to_combo_popup(watched):
                self._armed = None
        if kind != QEvent.Type.Wheel:
            return False
        if selector is None:
            return False
        watched = selector
        if self._armed is watched:
            return False

        # O controle está apenas sob o cursor. Aplicar a rolagem ao painel
        # ancestral conserva o comportamento esperado da barra lateral.
        scroll_area = watched.parentWidget()
        while scroll_area is not None and not isinstance(scroll_area, QAbstractScrollArea):
            scroll_area = scroll_area.parentWidget()
        if scroll_area is not None:
            horizontal = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            delta = event.angleDelta().x() if horizontal else event.angleDelta().y()
            bar = scroll_area.horizontalScrollBar() if horizontal else scroll_area.verticalScrollBar()
            if not delta and not event.pixelDelta().isNull():
                delta = event.pixelDelta().x() if horizontal else event.pixelDelta().y()
                step = 1
            else:
                step = max(1, bar.singleStep() * 3) / 120
            if delta:
                bar.setValue(round(bar.value() - delta * step))
        event.accept()
        return True


_guard = None


def install_wheel_focus_guard(app):
    """Instala uma única proteção para todos os seletores da aplicação."""
    global _guard
    if _guard is None:
        _guard = WheelFocusGuard(app)
        app.installEventFilter(_guard)
    return _guard
