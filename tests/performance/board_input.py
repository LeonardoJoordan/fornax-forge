"""Arraste real da seleção através da view, sem mover cada bloco por Python."""
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.organogram import UNITS_PER_MM


def start_board_drag(window, count):
    groups = window._board_items()[:count]
    with window._selection_batch():
        window.scene.clearSelection()
        for item in groups:
            item.setSelected(True)
    QApplication.processEvents()
    window._zoom_to_fit()
    QApplication.processEvents()
    start = window.view.mapFromScene(groups[0].mapToScene(groups[0].rect().center()))
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    if window.scene.mouseGrabberItem() is not groups[0]:
        raise AssertionError('O ponteiro não atingiu o bloco previsto para o arraste.')
    return start


def move_board_drag(window, start, distance_mm, *, release=True, buttons=Qt.MouseButton.LeftButton):
    view = window.view
    end = view.mapFromScene(view.mapToScene(start) + QPointF(distance_mm * UNITS_PER_MM, 0))
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end),
                        QPointF(view.viewport().mapToGlobal(end)),
                        Qt.MouseButton.NoButton, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), event)
    if release:
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    return end
