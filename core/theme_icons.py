"""Ícones de ferramentas seguem o tema; a marca e imagens da arte não mudam."""
from PySide6.QtGui import QIcon, QIconEngine, QPixmap, QPainter
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
from core.themes import theme_color


class ThemedSvgIconEngine(QIconEngine):
    """Renderiza um SVG externo usando a cor de ícone do tema atual."""

    def __init__(self, path, role='icon'):
        super().__init__()
        self.path = str(path)
        self.role = role

    def clone(self):
        return ThemedSvgIconEngine(self.path, self.role)

    def pixmap(self, size, mode, state):
        source = QPixmap(size)
        source.fill(Qt.GlobalColor.transparent)
        painter = QPainter(source)
        QSvgRenderer(self.path).render(painter, source.rect())
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(source.rect(), theme_color(
            'disabled' if mode == QIcon.Mode.Disabled else self.role
        ))
        painter.end()
        return source

    def paint(self, painter, rect, mode, state):
        painter.drawPixmap(rect, self.pixmap(rect.size(), mode, state))


def themed_svg_icon(path, role='icon'):
    return QIcon(ThemedSvgIconEngine(path, role))
