"""Escolha visual de exemplos locais antes de iniciar uma nova composição."""
import math

from PySide6.QtCore import Qt, QSize, QSizeF, QRectF, QRect, QTimer, QEvent, QPoint, QLocale
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPageSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
                              QListView, QDialogButtonBox, QHBoxLayout, QSpinBox,
                              QStyledItemDelegate, QStyle)

from core.i18n import tr, current_locale
from core.themes import themed_style, theme_color
from core.dialog_buttons import style_dialog_button_box
from core.starter_templates import starter_catalog, model_from_starter, organogram_from_starter
from core.organogram import board_bounds, UNITS_PER_MM
from core.model_document import adapt_model_page, DEFAULT_NEW_MODEL_SIZE_MM
from features.generator.renderer import NativeRenderer
from features.generator.organogram import OrganogramRenderer


TEMPLATE_DIMENSIONS_ROLE = Qt.ItemDataRole.UserRole + 2


def starter_dimensions(document):
    """Medidas físicas em largura × altura, com formato de papel quando exato."""
    if document.get('organogram') is not None:
        bounds = board_bounds(document['organogram'])
        width, height = bounds.width() / UNITS_PER_MM, bounds.height() / UNITS_PER_MM
    else:
        width, height = document.get('target_w_mm'), document.get('target_h_mm')
    if width is None or height is None:
        return tr('Dimensões ajustáveis')
    decimal = QLocale(current_locale()).decimalPoint()
    def number(value):
        return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.', decimal)
    dimensions = f'{number(width)} × {number(height)} mm'
    # Ordenar apenas para reconhecer o formato; a legenda conserva a orientação.
    paper = QPageSize(QSizeF(min(width, height), max(width, height)),
                      QPageSize.Unit.Millimeter, '', QPageSize.SizeMatchPolicy.ExactMatch)
    if paper.id() != QPageSize.PageSizeId.Custom:
        dimensions += f' ({paper.name()})'
    return dimensions


def starter_thumbnail(document, provider=None):
    if document.get("organogram") is not None:
        # Usa a prévia completa para conservar camadas, textos e imagens do quadro.
        renderer = OrganogramRenderer(document, [], asset_provider=provider,
                                     layout_preview=True, fixed_layout=True)
        return QPixmap.fromImage(renderer.preview(max_side=320))
    renderer = NativeRenderer(adapt_model_page(document), asset_provider=provider)
    return renderer.render_to_pixmap(row_rich=None, max_side=320)


def thumbnail_icon(pixmap):
    """Área uniforme evita que o estilo do Qt recorte exemplos horizontais."""
    thumbnail = QPixmap(320, 232)
    thumbnail.fill(Qt.GlobalColor.transparent)
    fitted = pixmap.scaled(QSize(316, 228), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(thumbnail)
    painter.drawPixmap((320 - fitted.width()) // 2, (232 - fitted.height()) // 2, fitted)
    painter.end()
    return QIcon(thumbnail)


class StarterTileDelegate(QStyledItemDelegate):
    """Centraliza imagem e legenda em cada célula, mantendo as cores da arte."""

    def paint(self, painter, option, index):
        painter.save()
        try:
            painter.setClipRect(option.rect)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            offset = getattr(self.parent(), '_tile_offset', 0)
            tile = QRectF(option.rect).adjusted(12 + offset, 10, -12 + offset, -10)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
            if selected or hovered:
                painter.setBrush(QColor(theme_color('hover')))
                painter.setPen(QPen(QColor(theme_color('accent' if selected else 'border_strong')), 2 if selected else 1))
                painter.drawRoundedRect(tile, 7, 7)
            dimensions = str(index.data(TEMPLATE_DIMENSIONS_ROLE) or '')
            caption_height = option.fontMetrics.height() * 2
            dimensions_height = option.fontMetrics.height() if dimensions else 0
            dimensions_gap = 4 if dimensions else 0
            label_height = 10 + caption_height + dimensions_gap + dimensions_height
            image_size = QSize(320, 232).scaled(
                QSize(max(1, int(tile.width() - 24)), max(1, int(tile.height() - label_height - 16))),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            top = tile.center().y() - (image_size.height() + label_height) / 2
            image_rect = QRectF(tile.center().x() - image_size.width() / 2, top,
                                image_size.width(), image_size.height())
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QIcon):
                icon.paint(painter, image_rect.toRect(), Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Normal)
            painter.setFont(option.font)
            painter.setPen(QColor(theme_color('text')))
            caption = QRectF(tile.left() + 8, image_rect.bottom() + 10, tile.width() - 16, caption_height)
            title = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
            flags = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
            painter.drawText(caption, flags, title)
            if dimensions:
                actual_height = min(caption_height, option.fontMetrics.boundingRect(
                    QRect(0, 0, int(caption.width()), caption_height), flags, title).height())
                size_rect = QRectF(caption.left(), caption.top() + actual_height + dimensions_gap,
                                   caption.width(), dimensions_height)
                painter.setPen(QColor(theme_color('muted')))
                painter.drawText(size_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 option.fontMetrics.elidedText(dimensions, Qt.TextElideMode.ElideRight, int(size_rect.width())))
        finally:
            painter.restore()


class StarterGallery(QListWidget):
    """Divide o espaço visível igualmente; telas pequenas mantêm a rolagem."""

    def __init__(self):
        super().__init__()
        self.setItemDelegate(StarterTileDelegate(self))
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setMovement(QListView.Movement.Snap)
        self.setDragEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._distribute_tiles)
        self.model().rowsInserted.connect(lambda *_: self._layout_timer.start(0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_timer.start(0)

    def viewportEvent(self, event):
        result = super().viewportEvent(event)
        if event.type() == QEvent.Type.Resize and hasattr(self, '_layout_timer'):
            self._layout_timer.start(0)
        return result

    def _distribute_tiles(self):
        if not self.count():
            return
        viewport = self.viewport().size()
        # O QListView reserva espaço para a barra ao calcular a quebra de linha,
        # mesmo antes de exibi-la. Usar a área máxima evita alternar a grade
        # entre duas e três colunas durante o ajuste das barras de rolagem.
        maximum = self.maximumViewportSize()
        scrollbar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        width, height = max(1, maximum.width() - scrollbar - 4), max(1, maximum.height() - 4)
        max_columns = min(self.count(), max(1, width // 220))
        rows = math.ceil(self.count() / max_columns)
        columns = math.ceil(self.count() / rows)
        size = QSize(max(1, width // columns), max(190, height // rows))
        self._tile_offset = max(0, (viewport.width() - size.width() * columns) / 2)
        if self.gridSize() != size:
            self.setGridSize(size)
            for row in range(self.count()):
                self.item(row).setSizeHint(size)
            self.doItemsLayout()
        # Centraliza também uma última linha incompleta (por exemplo, três
        # estruturas na primeira linha e duas na segunda).
        last_count = self.count() % columns
        for index in range(self.count()):
            row, column = divmod(index, columns)
            offset = (columns - last_count) * size.width() // 2 if last_count and row == rows - 1 else 0
            self.setPositionForIndex(QPoint(column * size.width() + offset, row * size.height()),
                                     self.model().index(index, 0))
        self.viewport().update()


class StarterDialog(QDialog):
    def __init__(self, kind, parent=None, *, document=None):
        super().__init__(parent)
        self.kind, self.document = kind, document
        self.result_document = self.asset_provider = None
        self._templates = {}
        self.setWindowTitle(tr("Novo modelo") if kind == "model" else tr("Adicionar organograma"))
        self.resize(820, 620)
        self.setMinimumSize(620, 440)
        layout = QVBoxLayout(self)
        title = QLabel(tr("Escolha um ponto de partida"))
        themed_style(title, "font-size: 20px; font-weight: 700; color: @text@;")
        layout.addWidget(title)
        hint = QLabel(tr("Escolha um exemplo e personalize no editor.") if kind == "model" else
                      tr("Escolha uma estrutura. Todos os blocos usarão o cartão da Página 1."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.gallery = StarterGallery()
        self.gallery.setObjectName("starterGallery")
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setIconSize(QSize(200, 145))
        self.gallery.setGridSize(QSize(245, 210))
        self.gallery.setWordWrap(True)
        self.gallery.setUniformItemSizes(True)
        themed_style(self.gallery, "QListWidget { background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 8px; }")
        layout.addWidget(self.gallery, 1)
        blank = QPixmap(200, 145)
        blank.fill(Qt.GlobalColor.white)
        painter = QPainter(blank)
        painter.setPen(QColor("#aab7c1"))
        painter.drawRect(1, 1, 197, 142)
        painter.drawLine(90, 72, 110, 72)
        painter.drawLine(100, 62, 100, 82)
        painter.end()
        default_width, default_height = DEFAULT_NEW_MODEL_SIZE_MM
        blank_dimensions = (starter_dimensions({'target_w_mm': default_width, 'target_h_mm': default_height})
                            if kind == 'model' else tr('Dimensões ajustáveis'))
        self._add_tile(None, tr("Começar em branco"), tr("Crie sua própria composição no editor."), blank,
                       blank_dimensions)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.grid_controls = QHBoxLayout()
        self.columns, self.rows = QSpinBox(), QSpinBox()
        for spin, value in ((self.columns, 4), (self.rows, 10)):
            spin.setRange(1, 100)
            spin.setValue(value)
            spin.setKeyboardTracking(False)
        self.grid_labels = [QLabel(tr("Colunas")), QLabel(tr("Linhas"))]
        for label, control in zip(self.grid_labels, (self.columns, self.rows)):
            self.grid_controls.addWidget(label)
            self.grid_controls.addWidget(control)
        self.grid_controls.addStretch()
        layout.addLayout(self.grid_controls)
        self.error = QLabel()
        self.error.setWordWrap(True)
        themed_style(self.error, "color: @danger@;")
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Usar modelo") if kind == "model" else tr("Usar estrutura"))
        style_dialog_button_box(self.buttons)
        layout.addWidget(self.buttons)
        errors = []
        try:
            templates = starter_catalog(kind)
        except Exception as error:
            templates = ()
            errors.append(str(error))
        for template in templates:
            try:
                preview, provider = (model_from_starter(template) if kind == "model" else
                                     (organogram_from_starter(document, template), getattr(parent, "_fornax_asset_provider", None)))
                self._templates[template.id] = template
                self._add_tile(template.id, tr(template.title), tr(template.description), starter_thumbnail(preview, provider),
                               starter_dimensions(preview))
            except Exception as error:
                errors.append(f"{template.title}: {error}")
        self._catalog_error = "\n".join(errors)
        self.gallery.currentItemChanged.connect(self._selection_changed)
        self.gallery.itemDoubleClicked.connect(lambda *_: self.accept())
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._grid_timer = QTimer(self)
        self._grid_timer.setSingleShot(True)
        self._grid_timer.setInterval(100)
        self._grid_timer.timeout.connect(self._update_grid_preview)
        self.columns.valueChanged.connect(lambda *_: self._grid_timer.start())
        self.rows.valueChanged.connect(lambda *_: self._grid_timer.start())
        self.gallery.setCurrentRow(0)

    def _add_tile(self, identity, title, description, pixmap, dimensions):
        item = QListWidgetItem(thumbnail_icon(pixmap), title)
        item.setSizeHint(QSize(235, 200))
        item.setData(Qt.ItemDataRole.UserRole, identity)
        item.setData(Qt.ItemDataRole.UserRole + 1, description)
        self._set_tile_dimensions(item, dimensions)
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.gallery.addItem(item)

    def _set_tile_dimensions(self, item, dimensions):
        item.setData(TEMPLATE_DIMENSIONS_ROLE, dimensions)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, f'{item.text()}\n{dimensions}')
        item.setToolTip(f'{item.data(Qt.ItemDataRole.UserRole + 1)}\n{dimensions}')

    def _selection_changed(self, item, _previous):
        if item is None:
            return
        template = self._templates.get(item.data(Qt.ItemDataRole.UserRole))
        grid = bool(template and template.configurable_grid)
        for widget in (*self.grid_labels, self.columns, self.rows):
            widget.setVisible(grid)
        self.details.setText(item.data(Qt.ItemDataRole.UserRole + 1))
        self.error.setText(self._catalog_error)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        if grid:
            self._update_grid_preview()

    def _update_grid_preview(self):
        item = self.gallery.currentItem()
        template = self._templates.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        if not template or not template.configurable_grid:
            return
        try:
            preview = organogram_from_starter(self.document, template, columns=self.columns.value(), rows=self.rows.value())
            item.setIcon(thumbnail_icon(starter_thumbnail(preview, getattr(self.parent(), "_fornax_asset_provider", None))))
            self._set_tile_dimensions(item, starter_dimensions(preview))
            self.details.setText(tr("{colunas} × {linhas} · {quantidade} posições. Você poderá ajustar o bloco no editor.").format(colunas=self.columns.value(), linhas=self.rows.value(), quantidade=self.columns.value() * self.rows.value()))
            self.error.setText(self._catalog_error)
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        except Exception as error:
            self.error.setText(str(error))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def accept(self):
        item = self.gallery.currentItem()
        if item is None:
            return
        template = self._templates.get(item.data(Qt.ItemDataRole.UserRole))
        try:
            if self.kind == "model":
                self.result_document, self.asset_provider = model_from_starter(template) if template else (None, None)
            else:
                self.result_document = organogram_from_starter(self.document, template, columns=self.columns.value(), rows=self.rows.value())
            super().accept()
        except Exception as error:
            self.error.setText(str(error))
