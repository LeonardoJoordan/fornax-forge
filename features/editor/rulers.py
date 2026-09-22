"""Réguas leves em coordenadas de documento, sem alterar a cena ao arrastar."""
import math
from PySide6.QtCore import Qt, QEvent, QPoint, QRect
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QRubberBand
from .canvas_items import mm_to_px
from core.themes import theme_color, themed_style, theme_manager
from core.i18n import tr


class Ruler(QWidget):
    def __init__(self, window, horizontal, parent):
        super().__init__(parent)
        self.window = window
        self.horizontal = horizontal
        theme_manager().changed.connect(self.update)
        self.dragging = False
        self.preview = QRubberBand(QRubberBand.Shape.Line, window.view.viewport())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SplitVCursor if horizontal else Qt.CursorShape.SplitHCursor)
        self.setToolTip(tr('Arraste para criar uma guia horizontal') if horizontal else tr('Arraste para criar uma guia vertical'))
        if horizontal:
            self.setFixedHeight(26)
        else:
            self.setFixedWidth(26)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme_color('panel')))
        painter.setFont(QFont('sans-serif', 8))
        view = self.window.view
        doc = self.window._get_document_rect()
        transform = view.viewportTransform()
        scale = abs(transform.m11() if self.horizontal else transform.m22())
        if scale <= 0:
            return
        offset = self.mapFromGlobal(view.viewport().mapToGlobal(QPoint(0, 0)))
        origin = transform.map(doc.topLeft())
        zero = (origin.x() + offset.x()) if self.horizontal else (origin.y() + offset.y())
        pixels_per_mm = mm_to_px(1) * scale
        # 1/2/5 intervals keep labels readable at every zoom level.
        target = 60 / pixels_per_mm
        decade = 10 ** math.floor(math.log10(target))
        major = next(n * decade for n in (1, 2, 5, 10) if n * decade >= target)
        minor = major / 5
        step = minor * pixels_per_mm
        length = self.width() if self.horizontal else self.height()
        start = math.floor(-zero / step)
        end = math.ceil((length - zero) / step)
        for index in range(start, end + 1):
            position = round(zero + index * step)
            large = index % 5 == 0
            painter.setPen(QColor(theme_color('muted' if large else 'border_strong')))
            tick = 9 if large else 4
            if self.horizontal:
                painter.drawLine(position, 26 - tick, position, 25)
            else:
                painter.drawLine(26 - tick, position, 25, position)
            if large:
                label = f'{index * minor:g}'
                if self.horizontal:
                    painter.drawText(position + 3, 12, label)
                else:
                    painter.save()
                    painter.translate(11, position - 3)
                    painter.rotate(-90)
                    painter.drawText(0, 0, label)
                    painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.setFocus()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            viewport = self.window.view.viewport()
            point = viewport.mapFromGlobal(event.globalPosition().toPoint())
            if viewport.rect().contains(point):
                self.preview.setGeometry(QRect(0, point.y(), viewport.width(), 1) if self.horizontal else QRect(point.x(), 0, 1, viewport.height()))
                self.preview.show()
            else:
                self.preview.hide()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            self.preview.hide()
            view = self.window.view
            point = view.viewport().mapFromGlobal(event.globalPosition().toPoint())
            if view.viewport().rect().contains(point):
                position = view.mapToScene(point)
                self.window.add_guide(not self.horizontal, position.y() if self.horizontal else position.x())
            view.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dragging = False
            self.preview.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


class RulerWorkspace(QWidget):
    def __init__(self, window):
        super().__init__()
        self.top = Ruler(window, True, self)
        self.left = Ruler(window, False, self)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        corner = QLabel('mm')
        corner.setFixedSize(26, 26)
        corner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        themed_style(corner, 'background: @panel@; color: @disabled@; font-size: 9px;')
        layout.addWidget(corner, 0, 0)
        layout.addWidget(self.top, 0, 1)
        layout.addWidget(self.left, 1, 0)
        layout.addWidget(window.view, 1, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)
        window.view.viewport().installEventFilter(self)
        for bar in (window.view.horizontalScrollBar(), window.view.verticalScrollBar()):
            bar.valueChanged.connect(self.refresh)

    def refresh(self, *_):
        self.top.update()
        self.left.update()

    def eventFilter(self, source, event):
        if event.type() in (QEvent.Type.Paint, QEvent.Type.Resize):
            self.refresh()
        return False
