"""Pintura real da view e leitura do backing store, sem forçar um render ao capturar."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsView

from core.model_document import normalize_model_document, persistent_model_document
from core.organogram import UNITS_PER_MM
from editor_scenarios import Scenario, make_document


@dataclass(frozen=True)
class PaintCase:
    id: str
    operation: str
    fixture: str = 'grid'
    size: int = 400
    near: bool = True


def cases():
    result = [PaintCase(f'paint_{view}-{size}', 'repaint', size=size, near=view == 'near')
              for size in (40, 400, 2500) for view in ('near', 'full')]
    result += [PaintCase('paint_local-2500', 'local', size=2500),
               PaintCase('paint_select-40', 'select', 'connected', 40),
               PaintCase('paint_drag-40', 'drag', 'connected', 40),
               PaintCase('paint_text-400', 'text'),
               PaintCase('paint_scroll-2500', 'scroll', size=2500),
               PaintCase('paint_pan-2500', 'pan', size=2500),
               PaintCase('paint_zoom-2500', 'zoom', size=2500),
               PaintCase('paint_page_local-60', 'local', 'mixed', 60),
               PaintCase('paint_page_rotate-60', 'rotate', 'mixed', 60)]
    return tuple(result)


def document(case):
    doc, provider = make_document(Scenario('paint', 'paint_near', case.fixture, case.size))
    if case.fixture in ('grid', 'connected'):
        board = doc['organogram']
        for group in board['groups']:
            group['border'] = {'cards': True, 'group': True, 'color': '#426b91',
                               'width_mm': .5, 'opacity': .85, 'radius_mm': 2,
                               'padding_mm': 5, 'cards_position': 'outside'}
        board['boxes'] = [{'layer_id': 501, 'object_id': 'text:501', 'x': 70, 'y': 90,
                           'w': 300, 'h': 90, 'html': '<p>Equipe <b>{Nome}</b></p>',
                           'font_size': 16, 'rich_text_version': 1, 'z_value': 10}]
        board['layer_order'] = ['text:501']
    else:
        for shape in doc['pages'][0]['shapes']:
            shape.update(outline_width=20, outline_position='outside', fill_opacity=.5)
    return normalize_model_document(doc), provider


def settle(app=None):
    app = app or QApplication.instance()
    for _ in range(6):
        app.sendPostedEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def screen_image(window, *, workspace=False):
    """QScreen.grabWindow lê os pixels já pintados; QWidget.grab repintaria tudo."""
    target = window.ruler_workspace if workspace else window.view.viewport()
    image = window.screen().grabWindow(window.winId()).toImage()
    if image.isNull():
        raise AssertionError('O backend não oferece captura do backing store.')
    point = target.mapTo(window, QPoint())
    ratio = image.devicePixelRatio()
    rect = QRectF(point.x() * ratio, point.y() * ratio,
                  target.width() * ratio, target.height() * ratio).toAlignedRect()
    result = image.copy(rect)
    if result.isNull():
        raise AssertionError('Captura vazia da área do editor.')
    return result


def image_hash(image):
    return sha256(bytes(image.constBits())).hexdigest()


class PaintSession:
    def __init__(self, window, case, app):
        self.window, self.case, self.app = window, case, app
        self.document, self.provider = document(case)
        window.load_starter_document(self.document, self.provider)
        window.resize(1280, 800)
        window.show()
        window._autosave_timer.stop()
        self.restore()

    def restore(self):
        from features.editor.canvas_items import DesignerBox
        from board_input import start_board_drag
        w, case = self.window, self.case
        w._finish_page_interaction()
        if (hasattr(self, '_initial_transform')
                and case.operation in ('repaint', 'local', 'scroll', 'pan', 'zoom')):
            # Casos sem mutação mantêm a cena aquecida; restauram somente a
            # posição/escala da view, fora do intervalo medido.
            w.scene.clearSelection()
            w.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if case.operation == 'pan'
                               else QGraphicsView.DragMode.RubberBandDrag)
            w.view.setTransform(self._initial_transform)
            w.view.horizontalScrollBar().setValue(self._initial_scroll[0])
            w.view.verticalScrollBar().setValue(self._initial_scroll[1])
            settle(self.app)
            self.before_transform = w.view.transform()
            self.before_scroll = self._initial_scroll
            return
        w._load_document_into_scene(deepcopy(self.document))
        if case.fixture in ('grid', 'connected'):
            w.switch_model_page('organogram')
        w.scene.clearSelection()
        w.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        w._zoom_to_fit()
        settle(self.app)
        self.groups = w._board_items()
        self.box = min((i for i in w.scene.items() if isinstance(i, DesignerBox)
                        and i.isVisible() and i.layer_id != 1),
                       key=lambda i: (i.sceneBoundingRect().center() - QPointF(300, 240)).manhattanLength())
        if case.near:
            w.view.resetTransform()
            w.view.scale(.7, .7)
            w.view.centerOn(QPointF(300, 240))
        if case.operation == 'text':
            self.box.setSelected(True)
            w.canvas_edit.begin(self.box)
        elif case.operation == 'drag':
            self.drag_start = start_board_drag(w, 1)
            self.drag_before = QPointF(self.groups[0].pos())
        elif case.operation == 'pan':
            w.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        settle(self.app)
        self.before_scroll = (w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value())
        self.before_transform = w.view.transform()
        self._initial_transform = w.view.transform()
        self._initial_scroll = self.before_scroll
        # Não captura o documento aqui: isso encerraria a sessão textual/arraste.

    def perform(self):
        from board_input import move_board_drag
        w, op = self.window, self.case.operation
        if op == 'repaint':
            w.scene.update(w.view.mapToScene(w.view.viewport().rect()).boundingRect())
        elif op == 'local':
            w.scene.update(QRectF(160, 180, 12, 12))
        elif op == 'select':
            self.groups[0].setSelected(True)
        elif op == 'drag':
            move_board_drag(w, self.drag_start, 10)
        elif op == 'text':
            QTest.keyClicks(w.view.viewport(), ' equipe')
        elif op == 'scroll':
            w.view.verticalScrollBar().setValue(self.before_scroll[1] + 120)
        elif op == 'pan':
            viewport = w.view.viewport()
            # Inicia em área vazia: sobre um cartão o Qt arrastaria o conjunto.
            start = w.view.mapFromScene(QPointF(-70, -70))
            if not viewport.rect().contains(start):
                raise AssertionError('O ponto vazio do pan está fora da view.')
            end = start + QPoint(-60, -40)
            QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
            event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end),
                               QPointF(viewport.mapToGlobal(end)), Qt.MouseButton.NoButton,
                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(viewport, event)
            QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
        elif op == 'zoom':
            w._apply_zoom(1.15)
        elif op == 'rotate':
            self.box.setRotation(17)
        else:
            raise AssertionError(op)

    def verify(self):
        w, op = self.window, self.case.operation
        if op == 'text' and not self.box.text_item.toPlainText().endswith(' equipe'):
            raise AssertionError('Texto incompleto na operação de pintura.')
        if op == 'drag' and self.groups[0].pos() == self.drag_before:
            raise AssertionError('Arraste não moveu o conjunto.')
        if op in ('pan', 'scroll') and self.before_scroll == (
                w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value()):
            raise AssertionError('Rolagem/pan sem efeito.')
        if op == 'zoom' and w.view.transform() == self.before_transform:
            raise AssertionError('Zoom sem efeito.')
        if op == 'select' and not self.groups[0].isSelected():
            raise AssertionError('Seleção sem efeito.')
        if op == 'rotate' and self.box.rotation() != 17:
            raise AssertionError('Rotação sem efeito.')
        image = screen_image(w)
        return {'pixels_sha256': image_hash(image), 'image_size': [image.width(), image.height()],
                'scene_items': len(w.scene.items()), 'selected_items': len(w.scene.selectedItems()),
                'scroll': [w.view.horizontalScrollBar().value(), w.view.verticalScrollBar().value()],
                'transform': [w.view.transform().m11(), w.view.transform().m22()],
                'document': persistent_model_document(w._document_with_active_page())}


def close_window(window, app):
    window._finish_page_interaction()
    window._last_saved_state = window.get_current_scene_state()
    window._last_saved_document_state = window._capture_document_history_state()
    window._autosave_timer.stop()
    window.close()
    window.deleteLater()
    settle(app)
