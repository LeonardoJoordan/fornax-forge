"""Criação por gesto: uma única entrada no histórico ao soltar o mouse."""
import math
from PySide6.QtCore import QObject, QEvent, Qt, QRectF, QPointF
from PySide6.QtGui import QPainterPath, QPen, QColor
from PySide6.QtWidgets import QGraphicsPathItem
from core.themes import theme_color
from .canvas_items import RectangleItem, mm_to_px


class ShapeDrawing(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.kind = None
        self.start = None
        self.preview = None
        window.view.viewport().installEventFilter(self)
        window.view.installEventFilter(self)

    def activate(self, kind):
        self.cancel()
        self.w.canvas_edit.finish()
        self.kind = kind
        self.w.view.setFocus()
        self.w.view.viewport().setCursor(Qt.CrossCursor)

    def cancel(self):
        if self.preview:
            self.w.scene.removeItem(self.preview)
        self.preview = None
        self.start = None
        self.kind = None
        self.w.view.viewport().unsetCursor()

    def geometry(self, point, shift):
        delta = point - self.start
        if shift:
            if self.kind == 'line':
                length = math.hypot(delta.x(), delta.y())
                angle = round(math.atan2(delta.y(), delta.x()) / (math.pi/4)) * math.pi/4
                delta = QPointF(length * math.cos(angle), length * math.sin(angle))
            else:
                side = max(abs(delta.x()), abs(delta.y()))
                delta = QPointF(math.copysign(side, delta.x()), math.copysign(side, delta.y()))
        return self.start + delta

    def eventFilter(self, source, event):
        if not self.kind:
            return False
        if event.type() == QEvent.ShortcutOverride:
            event.accept()
            return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.cancel()
            return True
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
            return True
        if source is not self.w.view.viewport():
            return False
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.start = self.w.view.mapToScene(event.position().toPoint())
            self.preview = QGraphicsPathItem()
            pen = QPen(QColor(theme_color('accent')), 1)
            pen.setCosmetic(True)
            self.preview.setPen(pen)
            self.preview.setZValue(1e6)
            self.w.scene.addItem(self.preview)
            return True
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonRelease) and self.start is not None:
            end = self.geometry(self.w.view.mapToScene(event.position().toPoint()), bool(event.modifiers() & Qt.ShiftModifier))
            rect = QRectF(self.start, end).normalized()
            path = QPainterPath()
            if self.kind == 'line':
                path.moveTo(self.start)
                path.lineTo(end)
            elif self.kind == 'ellipse':
                path.addEllipse(rect)
            else:
                path.addRect(rect)
            self.preview.setPath(path)
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                distance = math.hypot(end.x()-self.start.x(), end.y()-self.start.y())
                if distance * self.w.view.transform().m11() >= 3 and (self.kind == 'line' or min(rect.width(), rect.height()) > 0):
                    height = mm_to_px(0.25) if self.kind == 'line' else rect.height()
                    item = RectangleItem(distance if self.kind == 'line' else rect.width(), height, '#d9d9d9')
                    item.shape_type = self.kind
                    base_name = {'rectangle': 'Quadrado', 'ellipse': 'Círculo', 'line': 'Linha'}[self.kind]
                    item.custom_name = self.w._unique_layer_name(base_name)
                    if self.kind == 'line':
                        center = (self.start + end)/2
                        item.setPos(center.x()-distance/2, center.y()-height/2)
                        item.setRotation(math.degrees(math.atan2(end.y()-self.start.y(), end.x()-self.start.x())))
                        item.fill_color = '#000000'
                        item.keep_proportion = False
                        item.outline_position = 'center'
                    else:
                        item.setPos(rect.topLeft())
                    item.setZValue(self.w._next_object_z())
                    self.w.scene.addItem(item)
                    self.w.scene.clearSelection()
                    item.setSelected(True)
                    self.w.refresh_layer_list()
                    self.w.save_snapshot()
                self.cancel()
            return True
        return False
