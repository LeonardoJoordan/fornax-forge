"""Atalhos para dimensões físicas; os objetos conservam sua geometria."""
from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QPushButton, QSizePolicy, QMessageBox, QButtonGroup

from core.i18n import tr
from core.resources import object_icon_path
from core.theme_icons import themed_svg_icon
from core.model_document import validate_canvas_dimensions, ModelValidationError
from .canvas_items import mm_to_px


PRESETS = {
    'A1': (594.0, 841.0), 'A2': (420.0, 594.0), 'A3': (297.0, 420.0),
    'A4': (210.0, 297.0), 'A5': (148.0, 210.0), 'A6': (105.0, 148.0),
    'A7': (74.0, 105.0), 'letter': (215.9, 279.4),
    'business-card': (50.0, 90.0), 'square': (100.0, 100.0),
}


def matching_preset(width, height):
    dimensions = sorted((width, height))
    return next((key for key, size in PRESETS.items()
                 if all(abs(a - b) < 0.005 for a, b in zip(dimensions, size))), 'custom')


def supported_size(width, height):
    try:
        validate_canvas_dimensions(int(mm_to_px(width)), int(mm_to_px(height)))
        return True
    except ModelValidationError:
        return False


class DocumentSizeControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setObjectName('documentSizePreset')
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setToolTip(tr('Escolher o tamanho da página'))
        for key in PRESETS:
            label = {'letter': tr('Carta'), 'business-card': tr('Cartão de visita'),
                     'square': tr('Quadrado — 100 × 100 mm')}.get(key, key)
            self.combo.addItem(label, key)
            if not supported_size(*PRESETS[key]):
                self.combo.model().item(self.combo.count() - 1).setEnabled(False)
                self.combo.setItemData(self.combo.count() - 1,
                    tr('Cada dimensão do documento deve ser de até 10.000 mm. A exportação permanece em 300 DPI; os limites de pixels são definidos em Limite de exportação.'),
                    Qt.ItemDataRole.ToolTipRole)
        self.combo.addItem(tr('Personalizado'), 'custom')
        layout.addWidget(self.combo, 1)
        self.portrait = QPushButton()
        self.landscape = QPushButton()
        self.square = QPushButton()
        self.orientation_group = QButtonGroup(self)
        self.orientation_group.setExclusive(True)
        from .frontend import square_control
        for button, tooltip in (
            (self.portrait, tr('Orientação vertical')),
            (self.landscape, tr('Orientação horizontal')),
            (self.square, tr('Formato quadrado (1:1)')),
        ):
            button.setObjectName('documentOrientation')
            button.setCheckable(True)
            square_control(button)
            button.setIconSize(QSize(20, 20))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            self.orientation_group.addButton(button)
            layout.addWidget(button)
        self.refresh_icons()
        from .frontend import _connect_theme_callback
        _connect_theme_callback(self, lambda: self.refresh_icons())
        self.combo.activated.connect(self.choose_preset)
        self.portrait.clicked.connect(lambda: self.orient(False))
        self.landscape.clicked.connect(lambda: self.orient(True))
        self.restore({})

    def refresh_icons(self):
        self.portrait.setIcon(themed_svg_icon(object_icon_path('portrait')))
        self.landscape.setIcon(themed_svg_icon(object_icon_path('landscape')))
        self.square.setIcon(themed_svg_icon(object_icon_path('1.1')))

    def restore(self, state):
        w = self.window
        width, height = w.spin_phys_w.value(), w.spin_phys_h.value()
        detected = matching_preset(width, height)
        requested = state.get('document_size_preset', detected)
        w._document_size_preset = requested if requested in ('custom', detected) else detected
        self.refresh()

    def manual_change(self):
        self.window._document_size_preset = 'custom'

    def refresh(self):
        w = self.window
        width, height = w.spin_phys_w.value(), w.spin_phys_h.value()
        preset = getattr(w, '_document_size_preset', 'custom')
        if preset != 'custom' and preset != matching_preset(width, height):
            preset = w._document_size_preset = 'custom'
        with QSignalBlocker(self.combo):
            self.combo.setCurrentIndex(self.combo.findData(preset))
        with QSignalBlocker(self.portrait), QSignalBlocker(self.landscape), QSignalBlocker(self.square):
            self.portrait.setChecked(height > width)
            self.landscape.setChecked(width > height)
            self.square.setChecked(width == height)
        enabled = w._active_page_id != 'organogram'
        self.combo.setEnabled(enabled)
        self.portrait.setEnabled(enabled and width != height)
        self.landscape.setEnabled(enabled and width != height)
        self.square.setEnabled(enabled and width == height)
        if enabled and supported_size(width, height):
            self._last_dimensions = (width, height)
            self._last_preset = preset
            self._last_aspect_ratio = getattr(w, '_doc_aspect_ratio', width / height)

    def reject_invalid_dimensions(self):
        """Recusa medidas manuais antes de alterar a cena ou o histórico."""
        w = self.window
        if w._active_page_id == 'organogram' or supported_size(w.spin_phys_w.value(), w.spin_phys_h.value()):
            return False
        width, height = self._last_dimensions
        with QSignalBlocker(w.spin_phys_w), QSignalBlocker(w.spin_phys_h):
            w.spin_phys_w.setValue(width)
            w.spin_phys_h.setValue(height)
        w._document_size_preset = self._last_preset
        w._doc_aspect_ratio = self._last_aspect_ratio
        self.refresh()
        QMessageBox.warning(w, tr('Tamanho acima do limite'),
            tr('Cada dimensão do documento deve ser de até 10.000 mm. A exportação permanece em 300 DPI; os limites de pixels são definidos em Limite de exportação.'))
        return True

    def choose_preset(self, index):
        key = self.combo.itemData(index)
        w = self.window
        if w._active_page_id == 'organogram' or key not in (*PRESETS, 'custom'):
            return
        if key == 'custom':
            w.save_snapshot()
            w._document_size_preset = 'custom'
            self.refresh()
            w.save_snapshot()
            return
        width, height = PRESETS[key]
        if w.spin_phys_w.value() > w.spin_phys_h.value():
            width, height = height, width
        self.apply(key, width, height)

    def orient(self, landscape):
        w = self.window
        width, height = sorted((w.spin_phys_w.value(), w.spin_phys_h.value()))
        if landscape:
            width, height = height, width
        self.apply(w._document_size_preset, width, height)

    def apply(self, key, width, height):
        w = self.window
        if w._active_page_id == 'organogram':
            return
        if not supported_size(width, height):
            self.refresh()
            QMessageBox.warning(w, tr('Tamanho acima do limite'),
                tr('Cada dimensão do documento deve ser de até 10.000 mm. A exportação permanece em 300 DPI; os limites de pixels são definidos em Limite de exportação.'))
            return
        w.save_snapshot()
        with QSignalBlocker(w.spin_phys_w), QSignalBlocker(w.spin_phys_h):
            w.spin_phys_w.setValue(width)
            w.spin_phys_h.setValue(height)
        w._document_size_preset = key
        w._doc_aspect_ratio = width / height
        w._on_physical_size_changed()
        w.save_snapshot()
