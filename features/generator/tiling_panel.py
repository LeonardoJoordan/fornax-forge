"""Configuração do ladrilhamento integrada à seção de geração."""
from PySide6.QtCore import Qt, QRectF, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QLabel, QComboBox, QCheckBox, QGroupBox, QPushButton,
                              QScrollArea)

from core.custom_widgets import MathDoubleSpinBox
from core.i18n import tr
from core.themes import themed_style, theme_color
from core.tiling import build_tile_plan, UNITS_PER_MM


class TileMap(QWidget):
    tileClicked = Signal(int)
    dragged = Signal(float, float)

    def __init__(self, bounds, parent=None):
        super().__init__(parent)
        self.bounds = QRectF(bounds)
        self.image = None
        self.plan = None
        self.selected = 0
        self.sheet = False
        self._drag_position = None
        self._drag_scene = None
        self._moved = False
        self.setMinimumSize(280, 300)
        self.setToolTip(tr("Arraste o desenho para ajustar sua posição nas folhas."))

    def scene_bounds(self):
        if self._drag_scene is not None:
            return self._drag_scene
        if not self.plan or self.sheet:
            return self.bounds
        result = QRectF(self.plan.drawing_bounds)
        for tile in self.plan.tiles:
            result = result.united(self.sheet_rect(tile))
        return result

    def sheet_rect(self, tile):
        margin = self.plan.margin_mm * UNITS_PER_MM
        return QRectF(tile.region.left() - margin, tile.region.top() - margin,
                      self.plan.paper[0] * UNITS_PER_MM, self.plan.paper[1] * UNITS_PER_MM)

    def image_rect(self):
        area = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        scene = self.scene_bounds()
        ratio = self.image.width() / self.image.height() if self.sheet and self.image else scene.width() / scene.height()
        width = min(area.width(), area.height() * ratio)
        height = width / ratio
        return QRectF(area.center().x() - width / 2, area.center().y() - height / 2, width, height)

    def map_rect(self, rect):
        target, scene = self.image_rect(), self.scene_bounds()
        return QRectF(target.left() + (rect.left() - scene.left()) * target.width() / scene.width(),
                      target.top() + (rect.top() - scene.top()) * target.height() / scene.height(),
                      rect.width() * target.width() / scene.width(),
                      rect.height() * target.height() / scene.height())

    def tile_rect(self, tile):
        return self.map_rect(self.sheet_rect(tile))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme_color('panel')))
        if self.image is None:
            painter.setPen(QColor(theme_color('muted')))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Carregando prévia…"))
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.sheet or self.plan is None:
            painter.drawPixmap(self.image_rect(), self.image, QRectF(self.image.rect()))
            return
        for tile in self.plan.tiles:
            painter.fillRect(self.tile_rect(tile), QColor('white'))
        painter.drawPixmap(self.map_rect(self.plan.drawing_bounds), self.image, QRectF(self.image.rect()))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index, tile in enumerate(self.plan.tiles):
            rect = self.tile_rect(tile)
            pen = QPen(QColor(theme_color('accent') if index == self.selected else '#596575'), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            if rect.width() >= 22 and rect.height() >= 20:
                label = QRectF(rect.left() + 3, rect.top() + 3,
                               min(rect.width() - 6, painter.fontMetrics().horizontalAdvance(tile.name) + 10), 20)
                painter.fillRect(label, QColor('#ffffff'))
                painter.setPen(QColor('#20242a'))
                painter.drawText(label, Qt.AlignmentFlag.AlignCenter, tile.name)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.plan and not self.sheet and self.image:
            if self.map_rect(self.plan.drawing_bounds).contains(event.position()):
                self._drag_scene = self.scene_bounds()
                self._drag_position = event.position()
                self._moved = False
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            self.select_at(event.position())
        super().mousePressEvent(event)

    def select_at(self, point):
        if self.plan:
            for index, tile in enumerate(self.plan.tiles):
                if self.tile_rect(tile).contains(point):
                    self.tileClicked.emit(index)
                    break

    def mouseMoveEvent(self, event):
        if self._drag_position is not None:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self.end_drag()
                return
            delta = event.position() - self._drag_position
            self._drag_position = event.position()
            target = self.image_rect()
            scene = self.scene_bounds()
            self._moved = self._moved or delta.manhattanLength() > 0
            self.dragged.emit(delta.x() * scene.width() / target.width(),
                              delta.y() * scene.height() / target.height())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_position is not None:
            if not self._moved:
                self.select_at(event.position())
            self.end_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def end_drag(self):
        self._drag_position = None
        self._drag_scene = None
        self.unsetCursor()
        self.update()

    def focusOutEvent(self, event):
        self.end_drag()
        super().focusOutEvent(event)


class TilingPanel(QWidget):
    changed = Signal()
    def __init__(self, renderer, parent=None, *, initial=None, imposition_settings=None):
        super().__init__(parent)
        self.renderer = renderer
        self.plan = None
        self._base_image = None
        self._closing = False
        self._preview_error = ''
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(80)
        self._preview_timer.timeout.connect(self._render_preview)
        initial, presets = initial or {}, imposition_settings or {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tiling = QCheckBox(tr("Habilitar impressão em ladrilhos"))
        self.tiling.setChecked(bool(initial.get("tiling", False)))
        outer.addWidget(self.tiling)
        self.details = QWidget()
        body = QHBoxLayout(self.details)
        body.setContentsMargins(0, 0, 0, 0)
        self.details.setMinimumHeight(490)
        outer.addWidget(self.details, 1)
        controls = QWidget()
        controls.setMinimumWidth(270)
        settings_layout = QVBoxLayout(controls)
        settings_layout.setContentsMargins(0, 0, 10, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(controls)
        body.addWidget(scroll, 2)
        size = renderer.bounds
        size_label = QLabel(tr("Original: {largura:.1f} × {altura:.1f} mm").format(
            largura=size.width() / UNITS_PER_MM, altura=size.height() / UNITS_PER_MM,
            quantidade=len(renderer.slots)))
        size_label.setWordWrap(True)
        settings_layout.addWidget(size_label)
        self.target_width, self.target_height = self.measure(1, 50000), self.measure(1, 50000)
        target_width = initial.get("target_size_mm", [size.width() / UNITS_PER_MM, size.height() / UNITS_PER_MM])[0]
        self.target_width.setValue(target_width)
        self.target_height.setValue(target_width * size.height() / size.width())
        dimensions = QFormLayout()
        dimensions.addRow(tr("Largura final"), self.target_width)
        dimensions.addRow(tr("Altura final"), self.target_height)
        self.restore_size = QPushButton(tr("Restaurar tamanho original"))
        self.restore_size.clicked.connect(self._restore_original_size)
        dimensions.addRow(self.restore_size)
        self.dpi = QComboBox()
        self.dpi.addItem('150 dpi', 150)
        self.dpi.addItem('300 dpi', 300)
        self.dpi.setCurrentIndex(max(0, self.dpi.findData(initial.get('dpi', 150))))
        dimensions.addRow(tr('Resolução do PNG'), self.dpi)
        settings_layout.addLayout(dimensions)
        self.paper_group = QGroupBox(tr("Folhas para impressão"))
        form = QFormLayout(self.paper_group)
        self.paper = QComboBox()
        for name, size in (('A4', (210, 297)), ('A3', (297, 420)), ('A5', (148, 210)),
                           ('Carta', (215.9, 279.4)), ('Personalizado', None)):
            self.paper.addItem(tr(name), size)
        preset_paper = presets.get('sheet_w_mm', 210), presets.get('sheet_h_mm', 297)
        default_index = next((index for index in range(4)
                              if tuple(sorted(self.paper.itemData(index))) == tuple(sorted(preset_paper))), 4)
        self.paper.setCurrentIndex(max(0, min(4, int(initial.get('paper_index', default_index)))))
        self.orientation = QComboBox()
        self.orientation.addItems([tr('Retrato'), tr('Paisagem'), tr('Automática — menos folhas')])
        self.orientation.setCurrentIndex(2 if initial.get('auto_orientation', True) else int(bool(initial.get('landscape', preset_paper[0] > preset_paper[1]))))
        self.width, self.height = self.measure(10, 5000), self.measure(10, 5000)
        self.width.setValue(initial.get('paper', preset_paper)[0])
        self.height.setValue(initial.get('paper', preset_paper)[1])
        form.addRow(tr('Papel'), self.paper)
        form.addRow(tr('Orientação'), self.orientation)
        form.addRow(tr('Largura'), self.width)
        form.addRow(tr('Altura'), self.height)
        self.margin_enabled = QCheckBox(tr('Habilitar margem na folha'))
        self.margin_enabled.setChecked(initial.get('margin_enabled', presets.get('bleed_margin', False)))
        self.margin = self.measure(0, 2000)
        self.margin.setValue(initial.get('margin_value', 5))
        form.addRow(self.margin_enabled)
        form.addRow(tr('Margem da folha'), self.margin)
        self.crop_marks = QCheckBox(tr('Habilitar marcas de corte'))
        self.crop_marks.setChecked(initial.get('crop_marks', presets.get('crop_marks', False)))
        form.addRow(self.crop_marks)
        self.overlap = self.measure(0, 1000)
        self.overlap.setValue(initial.get('overlap_mm', 0))
        form.addRow(tr('Sobreposição'), self.overlap)
        self.offset_x, self.offset_y = self.measure(0, 5000), self.measure(0, 5000)
        self.offset_x.setValue(initial.get('offset_mm', [0, 0])[0])
        self.offset_y.setValue(initial.get('offset_mm', [0, 0])[1])
        form.addRow(tr('Posição horizontal'), self.offset_x)
        form.addRow(tr('Posição vertical'), self.offset_y)
        self.optimize = QPushButton(tr('Otimizar disposição'))
        self.optimize.clicked.connect(self._optimize)
        form.addRow(self.optimize)
        settings_layout.addWidget(self.paper_group)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        settings_layout.addWidget(self.summary)
        self.hint = QLabel(tr('Arraste o desenho para ajustar os cortes. A proporção é preservada. Imprima em tamanho real (100%). '
                             'As divisões seguem colunas A, B, C e linhas 1, 2, 3. '
                             'Com sobreposição, as marcas indicam o recorte para encaixar sem repetir conteúdo.'))
        self.hint.setWordWrap(True)
        themed_style(self.hint, 'color: @muted@;')
        settings_layout.addWidget(self.hint)
        settings_layout.addStretch(1)
        right = QVBoxLayout()
        body.addLayout(right, 3)
        self.view_mode = QComboBox()
        self.view_mode.addItems([tr('Mapa das folhas'), tr('Folha selecionada')])
        right.addWidget(self.view_mode)
        self.preview = TileMap(renderer.bounds)
        right.addWidget(self.preview, 1)
        self.position = QComboBox()
        self.position.setMaxVisibleItems(12)
        right.addWidget(self.position)
        self.error = QLabel()
        self.error.setWordWrap(True)
        themed_style(self.error, 'color: @warning@;')
        outer.addWidget(self.error)
        self.paper.currentIndexChanged.connect(self._paper_changed)
        self.orientation.currentIndexChanged.connect(self._orientation_changed)
        for widget in (self.width, self.height, self.margin, self.overlap, self.offset_x, self.offset_y):
            widget.valueChanged.connect(self.refresh_plan)
        for widget in (self.tiling, self.margin_enabled, self.crop_marks):
            widget.toggled.connect(self.refresh_plan)
        self.target_width.valueChanged.connect(self._target_width_changed)
        self.target_height.valueChanged.connect(self._target_height_changed)
        self.preview.dragged.connect(self._move_drawing)
        self.position.currentIndexChanged.connect(self._select_tile)
        self.view_mode.currentIndexChanged.connect(self._view_changed)
        self.preview.tileClicked.connect(self.position.setCurrentIndex)
        self._paper_changed()

    @staticmethod
    def measure(minimum, maximum):
        widget = MathDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(2)
        widget.setSuffix(' mm')
        widget.setKeyboardTracking(False)
        return widget

    def _paper_changed(self, *_):
        paper = self.paper.currentData()
        self.width.setEnabled(paper is None)
        self.height.setEnabled(paper is None)
        if paper is not None:
            if self.orientation.currentIndex() == 1:
                paper = tuple(reversed(paper))
            with QSignalBlocker(self.width), QSignalBlocker(self.height):
                self.width.setValue(paper[0])
                self.height.setValue(paper[1])
        self.refresh_plan()

    def _orientation_changed(self, *_):
        if self.paper.currentData() is None and self.orientation.currentIndex() != 2:
            width, height = sorted((self.width.value(), self.height.value()), reverse=self.orientation.currentIndex() == 1)
            with QSignalBlocker(self.width), QSignalBlocker(self.height):
                self.width.setValue(width)
                self.height.setValue(height)
        self._paper_changed()

    def configuration(self):
        return dict(tiling=self.tiling.isChecked(), auto_orientation=self.orientation.currentIndex() == 2,
                    target_size_mm=list(self._target_size_mm()),
                    offset_mm=[self.offset_x.value(), self.offset_y.value()], paper_index=self.paper.currentIndex(),
                    landscape=self.orientation.currentIndex() == 1, paper=[self.width.value(), self.height.value()],
                    margin_enabled=self.margin_enabled.isChecked(), margin_value=self.margin.value(),
                    crop_marks=self.crop_marks.isChecked(), overlap_mm=self.overlap.value(), dpi=self.dpi.currentData())

    def tiling_options(self):
        if not self.tiling.isChecked():
            return None
        return dict(paper=(self.width.value(), self.height.value()),
                    margin_mm=self.margin.value() if self.margin_enabled.isChecked() else 0,
                    overlap_mm=self.overlap.value(), crop_marks=self.crop_marks.isChecked(),
                    target_size_mm=self._target_size_mm(),
                    offset_mm=(self.offset_x.value(), self.offset_y.value()),
                    auto_orientation=self.orientation.currentIndex() == 2)

    def refresh_plan(self, *_):
        self.details.setVisible(self.tiling.isChecked())

        self.margin.setEnabled(self.margin_enabled.isChecked())
        self.view_mode.setEnabled(self.tiling.isChecked())
        self.position.setEnabled(self.tiling.isChecked())
        self.plan = None
        error = ''
        previous = self.position.currentText()
        try:
            if self.tiling.isChecked():
                self.plan = build_tile_plan(self.renderer.bounds, **self.tiling_options())
                if self.orientation.currentIndex() == 2:
                    with QSignalBlocker(self.width), QSignalBlocker(self.height):
                        self.width.setValue(self.plan.paper[0])
                        self.height.setValue(self.plan.paper[1])
                self.summary.setText(tr('{colunas} colunas × {linhas} linhas — {folhas} folhas').format(
                    colunas=self.plan.columns, linhas=self.plan.rows, folhas=len(self.plan.tiles)) +
                    tr(' · {orientacao}').format(orientacao=tr('Paisagem') if self.plan.paper[0] > self.plan.paper[1] else tr('Retrato')))
            else:
                self.summary.setText(tr('Um arquivo no tamanho completo do quadro.'))
        except ValueError as problem:
            error = str(problem)
            self.summary.clear()
        self.error.setText(error or self._preview_error)
        self._plan_error = error
        self.changed.emit()
        with QSignalBlocker(self.position):
            self.position.clear()
            if self.plan:
                self.position.addItems([tile.name for tile in self.plan.tiles])
                self.position.setCurrentIndex(max(0, self.position.findText(previous)))
        self.preview.plan = self.plan
        self.preview.selected = max(0, self.position.currentIndex())
        self.preview.update()
        self._request_preview()

    def _select_tile(self, *_):
        self.preview.selected = max(0, self.position.currentIndex())
        self.preview.update()
        self._request_preview()

    def _view_changed(self, *_):
        self._request_preview()

    def _request_preview(self, *_):
        if self._closing or self._preview_error or not self.tiling.isChecked():
            return
        sheet = bool(self.plan and self.tiling.isChecked() and self.view_mode.currentIndex())
        self.preview.sheet = sheet
        if self._base_image is not None and not sheet:
            self._preview_timer.stop()
            self.preview.image = self._base_image
            self.preview.update()
            return
        self.preview.image = None
        self.preview.update()
        self._preview_timer.start()

    def _render_preview(self):
        # A prévia mantém documentos de texto e widgets no contexto da interface.
        # O mapa é pintado uma vez; mudanças rápidas usam somente a última escolha.
        if self._closing:
            return
        try:
            if self.preview.sheet and self.plan:
                tile = self.plan.tiles[max(0, self.position.currentIndex())]
                scale = 900 / (max(self.plan.paper) * UNITS_PER_MM)
                image = self.renderer.tile_image(self.plan, tile, scale=scale)
                self.preview.image = QPixmap.fromImage(image)
            else:
                if self._base_image is None:
                    self._base_image = QPixmap.fromImage(self.renderer.preview(max_side=1000))
                self.preview.image = self._base_image
            self.preview.update()
        except Exception as error:
            self._preview_error = tr('Não foi possível gerar a prévia: {erro}').format(erro=error)
            self.error.setText(self._preview_error)
            self.changed.emit()

    @property
    def valid(self):
        return not self.tiling.isChecked() or (self.plan is not None and not self._preview_error)

    def interpret_controls(self):
        for control in (self.width, self.height, self.margin, self.overlap,
                        self.target_width, self.target_height, self.offset_x, self.offset_y):
            control.interpretText()
        self.refresh_plan()

    def stop_preview(self):
        self._closing = True
        self._preview_timer.stop()
        self.preview.end_drag()

    def _target_width_changed(self):
        with QSignalBlocker(self.target_height):
            self.target_height.setValue(self.target_width.value() * self.renderer.bounds.height() / self.renderer.bounds.width())
        self.refresh_plan()

    def _target_size_mm(self):
        original = (self.renderer.bounds.width() / UNITS_PER_MM,
                    self.renderer.bounds.height() / UNITS_PER_MM)
        current = (self.target_width.value(), self.target_height.value())
        # Os campos mostram duas casas; a restauração mantém a escala exata.
        if current == tuple(round(value, 2) for value in original):
            return original
        return current

    def _restore_original_size(self):
        with QSignalBlocker(self.target_width), QSignalBlocker(self.target_height):
            self.target_width.setValue(self.renderer.bounds.width() / UNITS_PER_MM)
            self.target_height.setValue(self.renderer.bounds.height() / UNITS_PER_MM)
        self.refresh_plan()

    def _target_height_changed(self):
        with QSignalBlocker(self.target_width):
            self.target_width.setValue(self.target_height.value() * self.renderer.bounds.width() / self.renderer.bounds.height())
        self.refresh_plan()

    def _move_drawing(self, dx, dy):
        with QSignalBlocker(self.offset_x), QSignalBlocker(self.offset_y):
            self.offset_x.setValue(max(0, self.offset_x.value() + dx / UNITS_PER_MM))
            self.offset_y.setValue(max(0, self.offset_y.value() + dy / UNITS_PER_MM))
        self.refresh_plan()

    def _optimize(self):
        with QSignalBlocker(self.orientation), QSignalBlocker(self.offset_x), QSignalBlocker(self.offset_y):
            self.orientation.setCurrentIndex(2)
            self.offset_x.setValue(0)
            self.offset_y.setValue(0)
        self._paper_changed()
