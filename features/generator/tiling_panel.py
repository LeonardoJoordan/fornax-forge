"""Configuração de folhas e ladrilhamento com uma prévia interativa compartilhada."""
from copy import deepcopy
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QLabel, QComboBox, QCheckBox, QGroupBox, QPushButton,
                              QScrollArea, QButtonGroup)

from core.custom_widgets import MathDoubleSpinBox
from core.i18n import tr
from core.themes import themed_style, theme_color
from core.tiling import (build_tile_plan, tile_sheet_rect, tile_crop_mark_segments, UNITS_PER_MM,
                        BLEED_MARGIN_MM, sheet_margins, reserved_margin_mm)
from .imposition import DPI
from .output_layout import resolve_output_layout


class TileMap(QWidget):
    tileClicked = Signal(int)
    dragged = Signal(float, float)
    dragFinished = Signal()

    def __init__(self, bounds, parent=None):
        super().__init__(parent)
        self.bounds = QRectF(bounds)
        self.image = None
        self.message = ''
        self.plan = None
        self.assembler = None
        self.selected = 0
        self.sheet = False
        self.bleed_mm = 0
        self._drag_position = None
        self._drag_scene = None
        self._moved = False
        self._translation = QPointF()
        self.setMinimumSize(280, 300)
        self.setToolTip(tr("Arraste o desenho para ajustar sua posição nas folhas."))

    def scene_bounds(self):
        if self._drag_scene is not None:
            return self._drag_scene
        if not self.has_layout or self.sheet:
            return self.bounds
        drawing = self.drawing_bounds()
        result = QRectF(drawing)
        for rect, _ in self.paper_rects():
            result = result.united(rect)
        # Após soltar, o desenho volta ao centro, sem deslocar as folhas no arraste.
        center = drawing.center()
        half_w = max(center.x() - result.left(), result.right() - center.x())
        half_h = max(center.y() - result.top(), result.bottom() - center.y())
        return QRectF(center.x() - half_w, center.y() - half_h, half_w * 2, half_h * 2)

    @property
    def has_layout(self):
        return self.plan is not None or self.assembler is not None

    def drawing_rects(self):
        if self.assembler:
            a = self.assembler
            return [QRectF((a.margin_left_mm + col * a.target_w_mm) * UNITS_PER_MM,
                           (a.margin_top_mm + row * a.target_h_mm) * UNITS_PER_MM,
                           a.target_w_mm * UNITS_PER_MM, a.target_h_mm * UNITS_PER_MM)
                    for row in range(a.rows) for col in range(a.cols)]
        return [self.plan.drawing_bounds] if self.plan else [self.bounds]

    def drawing_bounds(self):
        if self.assembler:
            a = self.assembler
            return QRectF(a.margin_left_mm * UNITS_PER_MM, a.margin_top_mm * UNITS_PER_MM,
                          a.cols * a.target_w_mm * UNITS_PER_MM, a.rows * a.target_h_mm * UNITS_PER_MM)
        return self.plan.drawing_bounds if self.plan else self.bounds

    def paper_rects(self):
        if self.assembler:
            return [(QRectF(0, 0, self.assembler.sheet_w_mm * UNITS_PER_MM,
                           self.assembler.sheet_h_mm * UNITS_PER_MM), 'A1')]
        return [(self.sheet_rect(tile), tile.name) for tile in self.plan.tiles] if self.plan else []

    def sheet_rect(self, tile):
        return tile_sheet_rect(self.plan, tile)

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

    def content_rects(self):
        if self.has_layout:
            reserve = self.assembler.edge_reserve_mm if self.assembler else self.plan.margin_mm
            inset = reserve * UNITS_PER_MM
            # During dragging the sheets stay fixed. A tile's region is trimmed
            # to the original artwork extent, so it cannot delimit blank paper
            # that the moving artwork may now occupy.
            return [paper.adjusted(inset, inset, -inset, -inset) for paper, _ in self.paper_rects()]
        return [self.bounds]

    def _paint_bleed(self, painter):
        # É uma indicação de segurança da prévia, nunca parte da arte exportada.
        if not self.bleed_mm or not self.has_layout:
            return
        if self.sheet:
            paper_w = self.assembler.sheet_w_mm if self.assembler else self.plan.paper[0]
            paper_h = self.assembler.sheet_h_mm if self.assembler else self.plan.paper[1]
            outer = self.image_rect()
            dx, dy = outer.width() * self.bleed_mm / paper_w, outer.height() * self.bleed_mm / paper_h
            rings = [(outer, outer.adjusted(dx, dy, -dx, -dy))]
        else:
            inset = self.bleed_mm * UNITS_PER_MM
            rings = [(self.map_rect(paper), self.map_rect(paper.adjusted(inset, inset, -inset, -inset)))
                     for paper, _ in self.paper_rects()]
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for outer, inner in rings:
            path.addRect(outer)
            cutout = QPainterPath()
            cutout.addRect(inner)
            path.addPath(cutout.toReversed())
        color = QColor('#ff0000')
        color.setAlphaF(.30)
        painter.fillPath(path, color)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme_color('panel')))
        if self.message:
            painter.setPen(QColor(theme_color('warning')))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            return
        if self.image is None:
            painter.setPen(QColor(theme_color('muted')))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Carregando prévia…"))
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.sheet or not self.has_layout:
            painter.drawPixmap(self.image_rect(), self.image, QRectF(self.image.rect()))
            self._paint_bleed(painter)
            return
        for rect, _ in self.paper_rects():
            painter.fillRect(self.map_rect(rect), QColor('white'))
        painter.save()
        content = QPainterPath()
        content.setFillRule(Qt.FillRule.WindingFill)
        for rect in self.content_rects():
            content.addRect(self.map_rect(rect))
        painter.setClipPath(content)
        for rect in self.drawing_rects():
            painter.drawPixmap(self.map_rect(rect.translated(self._translation)), self.image, QRectF(self.image.rect()))
        painter.restore()
        self._paint_bleed(painter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.assembler and self.assembler.crop_marks:
            # A mesma geometria da geração; as marcas acompanham os cartões no
            # arraste, enquanto a folha e o seu limite de recorte ficam parados.
            target, scene = self.image_rect(), self.scene_bounds()
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setClipRect(self.map_rect(self.paper_rects()[0][0]))
            painter.translate(target.topLeft())
            painter.scale(target.width() / scene.width(), target.height() / scene.height())
            painter.translate(-scene.left(), -scene.top())
            painter.translate(self._translation)
            self.assembler._draw_crop_marks(painter, self.assembler.cols, self.assembler.rows, preview=True)
            painter.restore()
        elif self.plan and self.plan.crop_marks:
            pen = QPen(QColor('black'), 1)
            pen.setCosmetic(True)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(pen)
            drawing = self.plan.drawing_bounds.translated(self._translation)
            for tile in self.plan.tiles:
                for x1, y1, x2, y2 in tile_crop_mark_segments(self.plan, tile, drawing_bounds=drawing):
                    start = self.map_rect(QRectF(x1, y1, 0, 0)).topLeft()
                    end = self.map_rect(QRectF(x2, y2, 0, 0)).topLeft()
                    painter.drawLine(start, end)
            painter.restore()
        for index, (paper, name) in enumerate(self.paper_rects()):
            rect = self.map_rect(paper)
            pen = QPen(QColor(theme_color('accent') if index == self.selected else '#596575'), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            # Na folha única, o rótulo A1 poderia cobrir as marcas de corte.
            if not self.assembler and not self.plan.crop_marks and rect.width() >= 22 and rect.height() >= 20:
                label = QRectF(rect.left() + 3, rect.top() + 3,
                               min(rect.width() - 6, painter.fontMetrics().horizontalAdvance(name) + 10), 20)
                painter.fillRect(label, QColor('#ffffff'))
                painter.setPen(QColor('#20242a'))
                painter.drawText(label, Qt.AlignmentFlag.AlignCenter, name)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.has_layout and not self.sheet and self.image:
            if self.map_rect(self.drawing_bounds()).contains(event.position()):
                self._drag_scene = self.scene_bounds()
                self._drag_position = event.position()
                self._moved = False
                self._translation = QPointF()
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
        dragging = self._drag_position is not None
        self._drag_position = None
        self._drag_scene = None
        self._translation = QPointF()
        self.unsetCursor()
        if dragging:
            self.dragFinished.emit()
        self.update()

    def focusOutEvent(self, event):
        self.end_drag()
        super().focusOutEvent(event)


class TilingPanel(QWidget):
    changed = Signal()
    def __init__(self, renderer, parent=None, *, initial=None, imposition_settings=None, automatic=False):
        super().__init__(parent)
        self.renderer = renderer
        self.automatic = automatic
        self.repeat = renderer.document.get('organogram') is None
        self.assembler = None
        self.output_layout = None
        self._loading = False
        settings = initial or {}
        self._mode = self._configuration_mode(settings)
        self._mode_settings = deepcopy(settings.get('mode_settings', {}))
        self._positioned = bool(settings.get('positioned', settings.get('tiling', False)
                                            and settings.get('layout_mode') != 'auto'))
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
        self.tiling = QCheckBox(tr("Dividir em ladrilhos"))
        self.tiling.setChecked(bool(initial.get('enabled', initial.get("tiling", False))))
        if automatic:
            self.mode_buttons = QButtonGroup(self)
            mode_row = QHBoxLayout()
            self.items_button = self._mode_button(tr('Itens por folha'), 'imposition')
            self.tiles_button = self._mode_button(tr('Ladrilhos'), 'tiles')
            mode_row.addWidget(self.items_button)
            mode_row.addWidget(self.tiles_button)
            outer.addLayout(mode_row)
            self.tiling.hide()
            self._check_mode_button()
        else:
            outer.addWidget(self.tiling)
        self.details = QWidget()
        body = QHBoxLayout(self.details)
        body.setContentsMargins(0, 0, 0, 0)
        self.details.setMinimumHeight(360)
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
        settings_layout.addLayout(dimensions)
        self.paper_group = QGroupBox(tr("Folha de saída"))
        form = self.paper_form = QFormLayout(self.paper_group)
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
        self.margin_enabled = self._option_button(tr('Margem de sangria')) if automatic else QCheckBox(tr('Habilitar margem na folha'))
        self.margin_enabled.setChecked(initial.get('margin_enabled', presets.get('bleed_margin', False)))
        self.margin = self.measure(0, 2000)
        self.margin.setValue(BLEED_MARGIN_MM if automatic else initial.get('margin_value', 5))
        form.addRow(self.margin_enabled)
        if automatic:
            self.margin.hide()
        else:
            form.addRow(tr('Margem da folha'), self.margin)
        self.margin_enabled.setToolTip(tr('Reserva 5 mm em cada lado da folha. A faixa vermelha é mostrada apenas na prévia.'))
        self.crop_marks = self._option_button(tr('Marcas de corte')) if automatic else QCheckBox(tr('Habilitar marcas de corte'))
        self.crop_marks.setChecked(initial.get('crop_marks', presets.get('crop_marks', False)))
        self.crop_marks.setToolTip(tr('Reserva mais 5 mm em cada lado: marcas de 3 mm, separadas do item por 2 mm.'))
        form.addRow(self.crop_marks)
        # Older standalone settings may contain repeated artwork for assembly.
        # The current UI uses only each sheet's own margin, without extra overlap.
        self._legacy_overlap_mm = initial.get('overlap_mm', 0)
        self.offset_x, self.offset_y = self.measure(0, 5000), self.measure(0, 5000)
        self.offset_x.setValue(initial.get('offset_mm', [0, 0])[0])
        self.offset_y.setValue(initial.get('offset_mm', [0, 0])[1])
        # Keep the saved displacement and drag state, without numeric position
        # controls in the interface. Placement is adjusted directly on the map.
        self.offset_x.hide()
        self.offset_y.hide()
        self.optimize = QPushButton(tr('Otimizar disposição'))
        self.optimize.clicked.connect(self._optimize)
        form.addRow(self.optimize)
        settings_layout.addWidget(self.paper_group)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        themed_style(self.summary, 'color: @text@; font-weight: bold; padding: 4px 0;')
        outer.insertWidget(1, self.summary)
        self.hint = QLabel(tr('O tamanho final é preservado: itens menores são distribuídos na folha; '
                             'desenhos maiores são divididos em ladrilhos A1, B1, A2… '
                             'Arraste o desenho sobre as folhas para ajustar a posição. '
                             'Depois de gerar, imprima os arquivos em tamanho real (100%).'))
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
        for widget in (self.width, self.height, self.margin, self.offset_x, self.offset_y):
            widget.valueChanged.connect(self.refresh_plan)
        for widget in (self.tiling, self.margin_enabled, self.crop_marks):
            widget.toggled.connect(self.refresh_plan)
        self.target_width.valueChanged.connect(self._target_width_changed)
        self.target_height.valueChanged.connect(self._target_height_changed)
        self.preview.dragged.connect(self._move_drawing)
        self.preview.dragFinished.connect(self._finish_drag)
        self.position.currentIndexChanged.connect(self._select_tile)
        self.view_mode.currentIndexChanged.connect(self._view_changed)
        self.preview.tileClicked.connect(self.position.setCurrentIndex)
        self._paper_changed()

    def _configuration_mode(self, settings):
        if settings.get('mode') in ('imposition', 'tiles'):
            return settings['mode']
        if settings.get('tiling') and settings.get('layout_mode') != 'auto':
            return 'tiles'
        if settings.get('layout_mode') == 'auto' and settings.get('enabled'):
            try:
                layout = resolve_output_layout(settings, self.renderer.bounds, repeat=self.repeat)
                return 'imposition' if layout.assembler else 'tiles'
            except ValueError:
                pass
        return 'tiles' if not self.repeat else 'imposition'

    def _mode_button(self, text, mode):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setMinimumHeight(32)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        themed_style(button, '''QPushButton { background: @button@; color: @text@;
            border: 1px solid @border@; border-radius: 4px; padding: 4px 12px; }
            QPushButton:hover { background: @hover@; }
            QPushButton:checked { background: @success@; color: @field@; border-color: @success@; }''')
        self.mode_buttons.addButton(button)
        button.clicked.connect(lambda: self._switch_mode(mode))
        return button

    @staticmethod
    def _option_button(text):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setFixedHeight(33)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        themed_style(button, '''QPushButton { background: @button@; color: @muted@;
            border: 1px solid @border@; border-radius: 4px; padding: 0 10px;
            min-height: 31px; max-height: 31px; }
            QPushButton:hover { background: @hover@; }
            QPushButton:checked { background: @selection@; color: @text@; border-color: @accent@; }''')
        return button

    def _check_mode_button(self):
        if not self.automatic:
            return
        self.mode_buttons.setExclusive(False)
        self.items_button.setChecked(self.tiling.isChecked() and self._mode == 'imposition')
        self.tiles_button.setChecked(self.tiling.isChecked() and self._mode == 'tiles')
        self.mode_buttons.setExclusive(True)

    def _switch_mode(self, mode):
        if self._mode != mode:
            current = self.configuration(include_modes=False)
            self._mode_settings[self._mode] = current
            next_settings = deepcopy(self._mode_settings.get(mode, current))
            next_settings.update(mode=mode, enabled=True, tiling=mode == 'tiles')
            if mode not in self._mode_settings:
                next_settings.update(positioned=False, offset_mm=[0, 0], overlap_mm=0)
            self.apply_configuration(next_settings, keep_modes=True)
        else:
            self.tiling.setChecked(True)
            self._check_mode_button()
            self.refresh_plan()

    def _mode_controls(self):
        if not self.automatic:
            return
        tiled = self._mode == 'tiles'
        self.optimize.setVisible(tiled)
        self.margin.setEnabled(self.margin_enabled.isChecked())
        self.orientation.setItemText(2, tr('Automática — menos folhas') if tiled else tr('Automática — melhor aproveitamento'))
        self.position.setVisible(tiled)
        self.view_mode.setVisible(tiled)
        self.hint.setText(tr('Divida o desenho em folhas A1, B1, A2… Arraste para ajustar a posição. '
                             'Imprima os arquivos em tamanho real (100%).') if tiled else
                          tr('Distribua os itens na folha sem alterar a proporção. '
                             'As marcas de corte podem ser usadas com ou sem margem de sangria.'))

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

    def configuration(self, *, include_modes=True):
        settings = dict(tiling=self.tiling.isChecked(), auto_orientation=self.orientation.currentIndex() == 2,
                    target_size_mm=list(self._target_size_mm()),
                    offset_mm=[self.offset_x.value(), self.offset_y.value()], paper_index=self.paper.currentIndex(),
                    landscape=self.orientation.currentIndex() == 1, paper=[self.width.value(), self.height.value()],
                    margin_enabled=self.margin_enabled.isChecked(), margin_value=self.margin.value(),
                    crop_marks=self.crop_marks.isChecked(),
                    overlap_mm=0 if self.automatic else self._legacy_overlap_mm, dpi=DPI)
        if self.automatic:
            settings.update(layout_mode='auto', enabled=self.tiling.isChecked(), positioned=self._positioned)
            settings.update(margin_policy='separate', margin_value=BLEED_MARGIN_MM)
            settings.update(mode=self._mode, tiling=self.tiling.isChecked() and self._mode == 'tiles')
            if include_modes:
                settings['mode_settings'] = deepcopy(self._mode_settings)
                settings['mode_settings'][self._mode] = self.configuration(include_modes=False)
        return settings

    def apply_configuration(self, settings, *, keep_modes=False):
        self._loading = True
        try:
            self._mode = self._configuration_mode(settings)
            if not keep_modes:
                self._mode_settings = deepcopy(settings.get('mode_settings', {}))
            self._positioned = bool(settings.get('positioned', False))
            self.tiling.setChecked(bool(settings.get('enabled', settings.get('tiling', False))))
            self.paper.setCurrentIndex(settings.get('paper_index', 4))
            self.orientation.setCurrentIndex(2 if settings.get('auto_orientation', True)
                                             else int(bool(settings.get('landscape'))))
            paper = settings.get('paper', (210, 297))
            self.width.setValue(paper[0])
            self.height.setValue(paper[1])
            target = settings.get('target_size_mm', (self.renderer.bounds.width() / UNITS_PER_MM,))
            with QSignalBlocker(self.target_width), QSignalBlocker(self.target_height):
                self.target_width.setValue(target[0])
                self.target_height.setValue(target[0] * self.renderer.bounds.height() / self.renderer.bounds.width())
            self.margin_enabled.setChecked(settings.get('margin_enabled', False))
            self.margin.setValue(BLEED_MARGIN_MM if self.automatic else settings.get('margin_value', 5))
            self.crop_marks.setChecked(settings.get('crop_marks', False))
            self._legacy_overlap_mm = settings.get('overlap_mm', 0)
            offset = settings.get('offset_mm', (0, 0))
            self.offset_x.setValue(offset[0])
            self.offset_y.setValue(offset[1])
            self._check_mode_button()
        finally:
            self._loading = False
        self._paper_changed()

    def tiling_options(self):
        if not self.tiling.isChecked():
            return None
        return dict(paper=(self.width.value(), self.height.value()),
                    margin_mm=reserved_margin_mm(self.configuration()),
                    overlap_mm=self.configuration()['overlap_mm'], crop_marks=self.crop_marks.isChecked(),
                    target_size_mm=self._target_size_mm(),
                    offset_mm=(self.offset_x.value(), self.offset_y.value()),
                    auto_orientation=self.orientation.currentIndex() == 2)

    def refresh_plan(self, *_):
        if self._loading or self._closing:
            return
        if self.sender() in (self.offset_x, self.offset_y):
            self._positioned = True
        self._mode_controls()
        self.details.setVisible(self.tiling.isChecked())

        self.margin.setEnabled(self.margin_enabled.isChecked())
        self.view_mode.setEnabled(self.tiling.isChecked())
        self.position.setEnabled(self.tiling.isChecked())
        self.plan = None
        self.assembler = None
        self.output_layout = None
        error = ''
        previous = self.position.currentText()
        try:
            if self.tiling.isChecked():
                if self.automatic:
                    self.output_layout = resolve_output_layout(self.configuration(), self.renderer.bounds, repeat=self.repeat)
                    self.plan, self.assembler = self.output_layout.plan, self.output_layout.assembler
                else:
                    self.plan = build_tile_plan(self.renderer.bounds, **self.tiling_options())
                paper = self.plan.paper if self.plan else (self.assembler.sheet_w_mm, self.assembler.sheet_h_mm)
                if self.orientation.currentIndex() == 2:
                    with QSignalBlocker(self.width), QSignalBlocker(self.height):
                        self.width.setValue(paper[0])
                        self.height.setValue(paper[1])
                if self.assembler:
                    self.summary.setText(tr('Até {itens} itens por folha ({colunas} × {linhas})').format(
                        itens=self.assembler.capacity, colunas=self.assembler.cols, linhas=self.assembler.rows))
                else:
                    self.summary.setText(tr('{colunas} colunas × {linhas} linhas — {folhas} folhas').format(
                        colunas=self.plan.columns, linhas=self.plan.rows, folhas=len(self.plan.tiles)))
                if self.automatic and not self._positioned:
                    offset = ((self.assembler.margin_left_mm - self.assembler.edge_reserve_mm,
                               self.assembler.margin_top_mm - self.assembler.edge_reserve_mm)
                              if self.assembler else self.plan.offset_mm)
                    with QSignalBlocker(self.offset_x), QSignalBlocker(self.offset_y):
                        self.offset_x.setValue(offset[0])
                        self.offset_y.setValue(offset[1])
            else:
                self.summary.setText(tr('Um item por página, no tamanho original do modelo.'))
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
        self.preview.assembler = self.assembler
        self.preview.bleed_mm = sheet_margins(self.configuration())[0]
        if self.assembler:
            with QSignalBlocker(self.position):
                self.position.addItem('A1')
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
        if self._closing or not self.tiling.isChecked():
            self._preview_timer.stop()
            return
        self.preview.message = self._plan_error or self._preview_error
        if self.preview.message:
            # Não substituir uma folha inválida pelo cartão isolado: isso faria
            # o cartão parecer ser a folha, escondendo a falta de margem.
            self._preview_timer.stop()
            self.preview.image = None
            self.preview.update()
            return
        sheet = bool((self.plan or self.assembler) and self.tiling.isChecked() and self.view_mode.currentIndex())
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
        if self._closing or self._plan_error or self._preview_error or not self.tiling.isChecked():
            return
        try:
            if self._base_image is None:
                self._base_image = QPixmap.fromImage(self.renderer.preview(max_side=1000))
            if self.preview.sheet and self.assembler:
                a = self.assembler
                scale = 900 / max(a.sheet_w, a.sheet_h)
                image = QImage(max(1, round(a.sheet_w * scale)), max(1, round(a.sheet_h * scale)), QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.white)
                painter = QPainter(image)
                try:
                    painter.scale(scale, scale)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    for rect in self.preview.drawing_rects():
                        painter.drawPixmap(rect, self._base_image, QRectF(self._base_image.rect()))
                    if a.crop_marks:
                        a._draw_crop_marks(painter, a.cols, a.rows)
                finally:
                    painter.end()
                self.preview.image = QPixmap.fromImage(image)
            elif self.preview.sheet and self.plan:
                tile = self.plan.tiles[max(0, self.position.currentIndex())]
                scale = 900 / (max(self.plan.paper) * UNITS_PER_MM)
                image = self.renderer.tile_image(self.plan, tile, scale=scale)
                self.preview.image = QPixmap.fromImage(image)
            else:
                self.preview.image = self._base_image
            self.preview.update()
        except Exception as error:
            self._preview_error = tr('Não foi possível gerar a prévia: {erro}').format(erro=error)
            self.error.setText(self._preview_error)
            self._request_preview()
            self.changed.emit()

    @property
    def valid(self):
        return not self.tiling.isChecked() or (bool(self.plan or self.assembler) and not self._plan_error and not self._preview_error)

    def interpret_controls(self):
        for control in (self.width, self.height, self.margin,
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
        return current[0], current[0] * self.renderer.bounds.height() / self.renderer.bounds.width()

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
        old_x, old_y = self.offset_x.value(), self.offset_y.value()
        with QSignalBlocker(self.offset_x), QSignalBlocker(self.offset_y):
            self.offset_x.setValue(max(0, self.offset_x.value() + dx / UNITS_PER_MM))
            self.offset_y.setValue(max(0, self.offset_y.value() + dy / UNITS_PER_MM))
        self._positioned = True
        if self.preview._drag_position is not None:
            self.preview._translation += QPointF((self.offset_x.value() - old_x) * UNITS_PER_MM,
                                                 (self.offset_y.value() - old_y) * UNITS_PER_MM)
            self.preview.update()
        else:
            self.refresh_plan()

    def _finish_drag(self):
        if not self._closing:
            self.refresh_plan()

    def _optimize(self):
        self._positioned = False
        with QSignalBlocker(self.orientation), QSignalBlocker(self.offset_x), QSignalBlocker(self.offset_y):
            self.orientation.setCurrentIndex(2)
            self.offset_x.setValue(0)
            self.offset_y.setValue(0)
        self._paper_changed()
