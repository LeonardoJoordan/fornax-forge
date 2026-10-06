"""Seleção parcial de linhas e raio compartilhado entre editor e saída."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPointF, QRectF, QEvent
from PySide6.QtGui import QMouseEvent, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtTest import QTest

from core.board_connectors import connector_style, connector_path, MAX_CURVE_RADIUS_MM
from core.model_document import normalize_model_document, ModelValidationError
from core.organogram import group_rect, new_group, UNITS_PER_MM
from features.editor.editor_window import EditorWindow
from features.editor.organogram_editor import BoardConnectorItem, BoardGroupItem
from features.generator.organogram import OrganogramRenderer
import test_organogram as fixtures


class BoardConnectorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def chart(self, document=None):
        window = EditorWindow()
        window._load_document_into_scene(document or fixtures.board_document(1, 1))
        window.switch_model_page('organogram')
        def cleanup():
            window._finish_page_interaction()
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def linked_chart(self):
        window = self.chart()
        parent = window._board_items()[0]
        children = [window.add_board_group(new_group(window._model_document, columns=1, rows=1,
                                                     x=x, y=2000)) for x in (-1000, 1000)]
        window.set_board_parents([item.data['id'] for item in children], parent.data['id'])
        window.scene.clearSelection()
        window.show()
        self.app.processEvents()
        window._zoom_to_fit()
        return window, parent, children

    def connectors(self, window):
        return [item for item in window.scene.items() if isinstance(item, BoardConnectorItem)]

    def rubber_band(self, window, rect, modifiers=Qt.NoModifier):
        view = window.view
        start, end = view.mapFromScene(rect.topLeft()), view.mapFromScene(rect.bottomRight())
        QTest.mousePress(view.viewport(), Qt.LeftButton, modifiers, start)
        event = QMouseEvent(QEvent.MouseMove, QPointF(end),
                            QPointF(view.viewport().mapToGlobal(end)),
                            Qt.NoButton, Qt.LeftButton, modifiers)
        self.app.sendEvent(view.viewport(), event)
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, modifiers, end)
        self.app.processEvents()

    def connector_band(self, window, parent, children):
        bounds = QRectF()
        for connector in self.connectors(window):
            bounds = bounds.united(connector.boundingRect())
        y = (group_rect(parent.data).bottom() + min(group_rect(i.data).top() for i in children)) / 2
        return QRectF(bounds.left() - 50, y - 30, bounds.width() + 100, 60)

    def test_rubber_band_crosses_only_part_of_lines_and_selects_both(self):
        window, parent, children = self.linked_chart()
        band = self.connector_band(window, parent, children)
        self.assertTrue(all(not band.contains(i.boundingRect()) for i in self.connectors(window)))
        self.rubber_band(window, band)
        self.assertEqual(set(window.scene.selectedItems()), set(self.connectors(window)))
        self.assertFalse(any(isinstance(item, BoardGroupItem) for item in window.scene.selectedItems()))
        self.assertIn('2', window.organogram_panel.style_target.text())
        self.assertIn('2 conectores', window.findChild(QLabel, 'selectionSummary').text())
        self.assertTrue(window.view.rubberBandRect().isNull())

    def test_selected_lines_receive_radius_and_appearance_together_with_one_undo(self):
        window, parent, children = self.linked_chart()
        self.rubber_band(window, self.connector_band(window, parent, children))
        previous = window.history._current_index
        window.organogram_panel.radius.setValue(8.5)
        self.assertEqual(window.history._current_index, previous + 1)
        self.assertTrue(all(item.board_edge['style']['radius_mm'] == 8.5 for item in self.connectors(window)))
        self.assertEqual(window._board_connector_style['radius_mm'], 0)
        window.undo()
        self.assertTrue(all(item.board_edge['style']['radius_mm'] == 0 for item in self.connectors(window)))
        window.redo()
        self.assertTrue(all(item.board_edge['style']['radius_mm'] == 8.5 for item in self.connectors(window)))
        for item in self.connectors(window):
            item.setSelected(True)
        window.change_board_connector_style(color='#ff3322', width_mm=1.2, opacity=0.35)
        self.assertTrue(all(item.board_edge['style'] == {
            'radius_mm': 8.5, 'color': '#ff3322', 'width_mm': 1.2, 'opacity': 0.35
        } for item in self.connectors(window)))
        renderer = OrganogramRenderer(window._model_document, [{'Nome': 'A'}, {'Nome': 'B'}, {'Nome': 'C'}])
        for item in self.connectors(window):
            edge = item.board_edge
            self.assertEqual(item.path(), renderer.paths[(edge['source'], edge['target'])])

    def test_control_rubber_band_adds_another_connector_without_losing_first(self):
        window, _, _ = self.linked_chart()
        first, second = self.connectors(window)
        first.setSelected(True)
        point = second.path().pointAtPercent(0.85)
        band = QRectF(point.x() - 35, point.y() - 35, 70, 70)
        self.assertFalse(band.intersects(first.shape().boundingRect()) and first.shape().intersects(band))
        self.rubber_band(window, band, Qt.ControlModifier)
        self.assertEqual(set(window.scene.selectedItems()), {first, second})

    def test_radius_zero_is_square_and_positive_values_use_requested_millimeters(self):
        points = [QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000)]
        square = connector_path({}, {}, connector_style(), points=points, obstacles=[])
        self.assertTrue(all(square.elementAt(i).type != QPainterPath.CurveToElement
                            for i in range(square.elementCount())))
        paths = []
        for millimeters in (1, 5, 25):
            path = connector_path({}, {}, connector_style({'style': {'radius_mm': millimeters}}),
                                  points=points, obstacles=[])
            paths.append(path)
            self.assertAlmostEqual(path.elementAt(1).x, 2000 - millimeters * UNITS_PER_MM)
            self.assertAlmostEqual(path.elementAt(4).y, millimeters * UNITS_PER_MM)
            self.assertEqual(path.pointAtPercent(0), points[0])
            self.assertEqual(path.pointAtPercent(1), points[-1])
        self.assertNotEqual(paths[0], paths[1])
        self.assertNotEqual(paths[1], paths[2])

    def test_large_radius_is_limited_by_segments_and_neighboring_blocks(self):
        points = [QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000)]
        style = connector_style({'style': {'radius_mm': MAX_CURVE_RADIUS_MM}})
        path = connector_path({}, {}, style, points=points, obstacles=[])
        self.assertAlmostEqual(path.elementAt(1).x, 1000)
        self.assertAlmostEqual(path.elementAt(4).y, 1000)
        obstacle = QRectF(1800, 50, 100, 100)
        style = connector_style({'style': {'radius_mm': 25}})
        unrestricted = connector_path({}, {}, style, points=points, obstacles=[])
        limited = connector_path({}, {}, style, points=points, obstacles=[obstacle])
        stroker = QPainterPathStroker()
        stroker.setWidth(style['width_mm'] * UNITS_PER_MM)
        self.assertTrue(stroker.createStroke(unrestricted).intersects(obstacle))
        self.assertFalse(stroker.createStroke(limited).intersects(obstacle))
        self.assertGreater(limited.elementAt(1).x, unrestricted.elementAt(1).x)

    def test_saved_legacy_formats_open_with_equivalent_radius_controls(self):
        for mode, radius in (('square', 0), ('rounded', 5), ('curved', MAX_CURVE_RADIUS_MM)):
            with self.subTest(mode=mode):
                doc = fixtures.board_document(1, 1)
                doc['organogram']['connector_style'] = {'mode': mode, 'width_mm': 0.6}
                window = self.chart(doc)
                self.assertEqual(window.organogram_panel.radius.value(), radius)
                self.assertEqual(window._board_connector_style['radius_mm'], radius)
                self.assertEqual(window._board_connector_style['width_mm'], 0.6)
        self.assertEqual(connector_style({'style': {'mode': 'rounded'}},
                                        {'connector_style': {'radius_mm': 30}})['radius_mm'], 5)
        self.assertEqual(connector_style({'style': {'radius_mm': 2, 'mode': 'curved'}})['radius_mm'], 2)

    def test_invalid_saved_radii_are_rejected(self):
        for radius in (-1, True, math.inf, math.nan, MAX_CURVE_RADIUS_MM + 1, '5'):
            with self.subTest(radius=radius):
                doc = deepcopy(fixtures.board_document(1, 1))
                doc['organogram']['connector_style']['radius_mm'] = radius
                with self.assertRaises(ModelValidationError):
                    normalize_model_document(doc)


if __name__ == '__main__':
    unittest.main()
