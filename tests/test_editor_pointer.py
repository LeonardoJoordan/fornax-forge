"""Eventos de soltura perdidos não podem manter seleção/arraste ativos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
import gc
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView
from PySide6.QtTest import QTest

from core.model_document import normalize_model_document
from core.organogram import add_organogram, new_group
from features.editor.canvas_items import RectangleItem, DesignerBox
from features.editor.editor_window import EditorWindow


class EditorPointerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.enterContext(patch('core.paths._data_home', return_value=Path(temporary.name)))
        self.window = EditorWindow()
        self.addCleanup(self.close_editor)
        self.document = normalize_model_document({
            'canvas_size': {'w': 1000, 'h': 1000},
            'shapes': [{'x': 150, 'y': 150, 'width': 300, 'height': 200,
                        'shape_type': 'rectangle', 'fill_color': '#dcecf4',
                        'layer_id': 1}],
            'boxes': [], 'images': [], 'signatures': [],
        })
        self.window._load_document_into_scene(self.document)
        self.window.show()
        self.app.processEvents()
        self.window._zoom_to_fit()
        self.viewport = self.window.view.viewport()
        self.item = self.rectangle()

    def close_editor(self):
        # Normalize também o estado de botão do QTest entre os cenários.
        QTest.mouseRelease(self.viewport, Qt.LeftButton)
        QTest.mouseRelease(self.viewport, Qt.MiddleButton)
        self.window._finish_page_interaction()
        self.window._last_saved_state = self.window.get_current_scene_state()
        self.window._last_saved_document_state = self.window._capture_document_history_state()
        self.window.close()
        self.app.processEvents()

    def rectangle(self):
        return next(item for item in self.window.scene.items()
                    if isinstance(item, RectangleItem) and item.layer_id == 1)

    def point(self, item):
        return self.window.view.mapFromScene(item.mapToScene(item.rect().center()))

    def move(self, point, buttons=Qt.LeftButton):
        # Aqui não usamos mouseRelease: simulamos justamente a sua ausência.
        event = QMouseEvent(QEvent.MouseMove, QPointF(point),
                            QPointF(self.viewport.mapToGlobal(point)),
                            Qt.NoButton, buttons, Qt.NoModifier)
        self.app.sendEvent(self.viewport, event)

    def start_drag(self, item=None):
        start = self.point(item or self.item)
        end = start + QPoint(45, 25)
        QTest.mousePress(self.viewport, Qt.LeftButton, pos=start)
        self.move(end)
        return end

    def assert_released(self):
        self.assertEqual(self.window.view._pointer_buttons, Qt.NoButton)
        self.assertIsNone(self.window.scene.mouseGrabberItem())
        self.assertTrue(self.window.view.rubberBandRect().isNull())
        self.assertFalse(getattr(self.item, '_is_mouse_dragging', False))

    def test_missing_release_stops_item_drag_and_preserves_undo(self):
        initial = QPointF(self.item.pos())
        end = self.start_drag()
        moved = QPointF(self.item.pos())
        self.assertNotEqual(moved, initial)
        self.move(end + QPoint(40, 40), Qt.NoButton)
        self.assert_released()
        self.move(end + QPoint(70, 70), Qt.NoButton)
        self.assertEqual(self.item.pos(), moved)
        self.window.undo()
        self.item = self.rectangle()
        self.assertEqual(self.item.pos(), initial)

    def test_missing_release_closes_rubber_band_and_next_drag_works(self):
        start = self.window.view.mapFromScene(QPointF(700, 700))
        end = start + QPoint(60, 40)
        QTest.mousePress(self.viewport, Qt.LeftButton, pos=start)
        self.move(end)
        self.assertFalse(self.window.view.rubberBandRect().isNull())
        self.move(end + QPoint(30, 30), Qt.NoButton)
        self.assert_released()
        QTest.mouseRelease(self.viewport, Qt.LeftButton, pos=end)
        initial = QPointF(self.item.pos())
        end = self.start_drag()
        QTest.mouseRelease(self.viewport, Qt.LeftButton, pos=end)
        self.assertNotEqual(self.item.pos(), initial)

    def test_focus_deactivation_and_lost_grab_end_drag(self):
        for source, event_type in ((self.window.view, QEvent.FocusOut),
                                   (self.window, QEvent.WindowDeactivate),
                                   (self.viewport, QEvent.UngrabMouse)):
            with self.subTest(event=event_type):
                self.window.view.setFocus()
                end = self.start_drag()
                self.app.sendEvent(source, QEvent(event_type))
                self.app.processEvents()
                self.assert_released()
                QTest.mouseRelease(self.viewport, Qt.LeftButton, pos=end)

    def test_escape_releases_selection_even_if_button_still_reported_pressed(self):
        self.start_drag()
        position = QPointF(self.item.pos())
        QTest.keyClick(self.viewport, Qt.Key_Escape)
        self.assert_released()
        self.assertEqual(self.item.pos(), position)

    def test_delayed_ungrab_of_previous_gesture_does_not_cancel_new_drag(self):
        end = self.start_drag()
        self.app.sendEvent(self.viewport, QEvent(QEvent.UngrabMouse))
        QTest.mouseRelease(self.viewport, Qt.LeftButton, pos=end)
        self.start_drag()
        self.app.processEvents()
        self.assertEqual(self.window.view._pointer_buttons, Qt.LeftButton)
        self.assertTrue(self.item._is_mouse_dragging)

    def test_page_interaction_ends_drag_before_rebuilding_scene(self):
        end = self.start_drag()
        position = QPointF(self.item.pos())
        self.window._finish_page_interaction()
        self.assert_released()
        self.move(end + QPoint(40, 40), Qt.NoButton)
        self.assertEqual(self.item.pos(), position)

    def test_middle_pan_stops_when_move_reports_button_released(self):
        start = self.point(self.item)
        QTest.mousePress(self.viewport, Qt.MiddleButton, pos=start)
        self.move(start + QPoint(25, 25), Qt.MiddleButton)
        bars = (self.window.view.horizontalScrollBar(), self.window.view.verticalScrollBar())
        values = tuple(bar.value() for bar in bars)
        self.move(start + QPoint(60, 60), Qt.NoButton)
        self.assertFalse(self.window._is_middle_panning)
        self.assertEqual(tuple(bar.value() for bar in bars), values)

    def test_space_pan_can_be_interrupted_without_leaving_items_locked(self):
        buttons = self.item.acceptedMouseButtons()
        QTest.keyPress(self.viewport, Qt.Key_Space)
        self.assertEqual(self.item.acceptedMouseButtons(), Qt.NoButton)
        self.start_drag()
        QTest.keyClick(self.viewport, Qt.Key_Escape)
        self.assert_released()
        self.assertEqual(self.window.view.dragMode(), QGraphicsView.RubberBandDrag)
        self.assertEqual(self.item.acceptedMouseButtons(), buttons)
        QTest.keyRelease(self.viewport, Qt.Key_Space)

    def test_resize_finishes_on_missing_release_without_losing_size(self):
        self.item.setSelected(True)
        self.app.processEvents()
        handle = self.item.handle_br
        start = self.window.view.mapFromScene(handle.scenePos())
        QTest.mousePress(self.viewport, Qt.LeftButton, pos=start)
        self.move(start + QPoint(40, 25))
        self.assertTrue(handle._is_resizing)
        size = self.item.rect().size()
        self.move(start + QPoint(70, 70), Qt.NoButton)
        self.assertFalse(handle._is_resizing)
        self.assert_released()
        self.assertEqual(self.item.rect().size(), size)

    def test_chart_drag_recovers_and_keeps_the_snapped_position(self):
        document = add_organogram(self.document)
        document['organogram']['groups'] = [new_group(document, columns=1, rows=1)]
        self.window._load_document_into_scene(document)
        self.window.switch_model_page('organogram')
        self.item = self.window._board_items()[0]
        self.window._zoom_to_fit()
        self.window.view.centerOn(self.item)
        end = self.start_drag()
        position = QPointF(self.item.pos())
        self.move(end + QPoint(40, 40), Qt.NoButton)
        self.assert_released()
        self.assertEqual(self.item.pos(), position)
        self.assertIsNone(self.window.scene._board_drag_anchor)

    def test_recovery_keeps_python_text_item_and_its_saved_content(self):
        box = DesignerBox(500, 150, 300, 100, 'Texto preservado')
        self.window.scene.addItem(box)
        self.item.setSelected(True)
        box.setSelected(True)
        end = self.start_drag()
        QTest.mouseRelease(self.viewport, Qt.LeftButton, pos=end)
        del box
        gc.collect()
        self.window._finish_canvas_pointer_interaction(leave_pan=True)
        self.app.processEvents()
        gc.collect()
        texts = [item for item in self.window.scene.items() if isinstance(item, DesignerBox)]
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text_item.toPlainText(), 'Texto preservado')
        self.assertEqual(len(self.window.get_current_scene_state()['boxes']), 1)

    def test_text_selection_escape_also_releases_mouse_grab(self):
        box = DesignerBox(500, 150, 300, 100, 'Texto para selecionar')
        self.window.scene.addItem(box)
        self.window.canvas_edit.begin(box)
        start = self.window.view.mapFromScene(box.text_item.sceneBoundingRect().center())
        QTest.mousePress(self.viewport, Qt.LeftButton, pos=start)
        self.move(start + QPoint(35, 0))
        QTest.keyClick(self.viewport, Qt.Key_Escape)
        self.assert_released()
        self.assertIsNone(self.window.canvas_edit.box)

    def test_missing_release_cancels_unfinished_shape_preview(self):
        self.window.shape_drawing.activate('rectangle')
        start = self.window.view.mapFromScene(QPointF(600, 600))
        QTest.mousePress(self.viewport, Qt.LeftButton, pos=start)
        self.move(start + QPoint(40, 40))
        self.assertIsNotNone(self.window.shape_drawing.preview)
        self.move(start + QPoint(60, 60), Qt.NoButton)
        self.assertIsNone(self.window.shape_drawing.preview)
        self.assertIsNone(self.window.shape_drawing.start)
        self.assertIsNone(self.window.shape_drawing.kind)


if __name__ == '__main__':
    unittest.main()
