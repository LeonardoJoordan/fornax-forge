"""Equivalência de rotas, limites, recortes e entradas reais do organograma."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QRectF, QPointF, QEvent
from PySide6.QtGui import QImage, QPainter, QPainterPath
from PySide6.QtTest import QTest
from core.organogram import board_bounds
from core.board_connectors import connector_paths
from features.editor.canvas_items import DesignerBox
from features.editor.organogram_editor import BoardConnectorItem
import test_editor_performance_contracts as contracts
from board_input import start_board_drag, move_board_drag


class BoardUpdateBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def chart(self, text=False):
        w = self.editor('connected', 12)
        if text:
            w.add_new_box()
            box = next(i for i in w.scene.selectedItems() if isinstance(i, DesignerBox))
            box.setRect(0, 0, 800, 90)
            box.state.html_content = '<p>Responsáveis</p>'
            box.apply_state()
            box.setPos(250, 400)
        w.show()
        self.app.processEvents()
        w._zoom_to_fit()
        self.app.processEvents()
        return w

    def edges(self, w):
        return [i for i in w.scene.items() if isinstance(i, BoardConnectorItem)]

    def expected_cutouts(self, w):
        result = QPainterPath()
        result.setFillRule(Qt.FillRule.WindingFill)
        for i in w.scene.items():
            if isinstance(i, DesignerBox) and i.isVisible() and i.opacity() > 0 and not getattr(i, 'board_behind', False):
                p = QPainterPath()
                p.addPolygon(i.mapToScene(i.rect()))
                p.closeSubpath()
                result.addPath(p)
        return result

    def check_geometry(self, w):
        board = w._board_state()
        paths = connector_paths(board)
        for edge in self.edges(w):
            self.assertEqual(edge.path(), paths[(edge.board_edge['source'], edge.board_edge['target'])])
            self.assertEqual(edge.cutouts(), self.expected_cutouts(w))
        self.assertEqual(w._get_document_rect(), board_bounds(board))

    def record(self, w, name):
        for _ in range(4):
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.check_geometry(w)
        image = QImage(800, 500, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            w.scene.render(painter, QRectF(0, 0, 800, 500), w._get_document_rect())
        finally:
            painter.end()
        routes = {}
        for edge in self.edges(w):
            path = edge.path()
            routes[edge.board_edge['target']] = [[path.elementAt(i).x, path.elementAt(i).y,
                                                path.elementAt(i).type.value] for i in range(path.elementCount())]
        rect = w._get_document_rect()
        value = json.loads(json.dumps({'document': w._document_with_active_page(), 'routes': routes,
                                      'bounds': [rect.x(), rect.y(), rect.width(), rect.height()],
                                      'pixels': sha256(bytes(image.constBits())).hexdigest()}).replace(str(self.root), '__TEST_ROOT__'))
        output = os.environ.get('FORNAX_BOARD_EVIDENCE')
        if output:
            p = Path(output)
            data = json.loads(p.read_text()) if p.exists() else {}
            data[name] = value
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')

    def test_native_drag_moves_whole_selection_and_final_geometry(self):
        for count in (1, 4, 10):
            with self.subTest(count=count):
                w = self.chart()
                initial = [QPointF(i.pos()) for i in w._board_items()]
                start = start_board_drag(w, count)
                move_board_drag(w, start, 10)
                deltas = [i.pos()-p for i,p in zip(w._board_items(), initial)]
                self.assertNotEqual(deltas[0], QPointF())
                self.assertTrue(all(d == deltas[0] for d in deltas[:count]))
                self.assertTrue(all(d == QPointF() for d in deltas[count:]))
                self.record(w, f'drag-{count}')

    def test_styles_keep_output_geometry_and_undo_redo(self):
        w = self.chart()
        self.edges(w)[0].setSelected(True)
        for name,changes in [('color', {'color': '#aa3344'}), ('opacity', {'opacity': .63}),
                             ('width', {'width_mm': 1.6}), ('radius', {'radius_mm': 5})]:
            index = w.history._current_index
            w.change_board_connector_style(**changes)
            self.assertEqual(w.history._current_index, index+1)
            self.record(w, name)
        document = w._document_with_active_page()
        w.undo()
        self.check_geometry(w)
        w.redo()
        self.assertEqual(w._document_with_active_page(), document)
        self.record(w, 'style-redo')

    def test_ports_borders_and_unconnected_obstacles(self):
        w = self.chart()
        w._board_items()[0].setSelected(True)
        for name, changes in [('border-color', {'color': '#aa3344'}), ('border-opacity', {'opacity': .63}),
                              ('border-width', {'width_mm': 1.6}), ('border-radius', {'radius_mm': 5})]:
            w.change_board_border(cards=True, group=True, **changes)
            self.record(w, name)
        w.change_board_ports('entry_sides', 'right', True)
        self.record(w, 'ports')
        # Um bloco sem conexão continua sendo obstáculo para as outras rotas.
        w.set_board_parent(w._board_items()[-1].data['id'], None)
        w._board_items()[-1].setPos(500, 500)
        w._update_board_extent()
        self.record(w, 'obstacle')

    def test_cutouts_follow_text_geometry_visibility_and_layer_immediately(self):
        w = self.chart(text=True)
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
        for name, change in [('text-move', lambda: box.moveBy(100, 0)),
                             ('text-rotation', lambda: box.setRotation(25)),
                             ('text-resize', lambda: box.setRect(0, 0, 500, 160)),
                             ('text-hidden', lambda: box.setVisible(False)),
                             ('text-transparent', lambda: (box.setVisible(True), box.setOpacity(0))),
                             ('text-behind', lambda: (box.setOpacity(1), setattr(box, 'board_behind', True), w._sync_board_artwork_layers()))]:
            self.edges(w)[0].cutouts()  # Já há um recorte anterior a invalidar.
            change()
            for edge in self.edges(w):
                self.assertEqual(edge.cutouts(), self.expected_cutouts(w))
            w._update_board_extent()
            self.record(w, name)

    def test_text_edit_keeps_content_and_connector_selection_excludes_cutout(self):
        w = self.chart(text=True)
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
        w.canvas_edit.begin(box)
        box.text_item.textCursor().insertText(' texto completo')
        w.canvas_edit.finish()
        self.assertIn('texto completo', box.state.html_content)
        edge = self.edges(w)[0]
        point = edge.path().pointAtPercent(.5)
        w.scene._board_snap_suspended = True
        box.setRotation(0)
        box.setPos(point-QPointF(50, 50))
        box.setRect(0, 0, 100, 100)
        w.scene._board_snap_suspended = False
        self.assertFalse(edge.shape().contains(point))
        box.setVisible(False)
        self.assertTrue(edge.shape().contains(point))
        w._update_board_extent()
        self.record(w, 'text-edit-selection')

    def test_missing_release_and_escape_finish_routes_and_history(self):
        for escape in (False, True):
            with self.subTest(escape=escape):
                w = self.chart()
                initial = [QPointF(i.pos()) for i in w._board_items()]
                start = start_board_drag(w, 4)
                move_board_drag(w, start, 10, release=False)
                if escape:
                    QTest.keyClick(w.view.viewport(), Qt.Key.Key_Escape)
                else:
                    move_board_drag(w, start, 10, release=False, buttons=Qt.MouseButton.NoButton)
                self.assertIsNone(w.scene.mouseGrabberItem())
                self.record(w, 'escape' if escape else 'missing-release')
                w.undo()
                self.assertEqual([i.pos() for i in w._board_items()], initial)
                self.check_geometry(w)


class BoardUpdateWorkTest(unittest.TestCase):
    setUpClass = BoardUpdateBehaviorTest.__dict__['setUpClass']
    setUp = BoardUpdateBehaviorTest.setUp
    editor = BoardUpdateBehaviorTest.editor
    chart = BoardUpdateBehaviorTest.chart
    edges = BoardUpdateBehaviorTest.edges
    expected_cutouts = BoardUpdateBehaviorTest.expected_cutouts
    check_geometry = BoardUpdateBehaviorTest.check_geometry

    def test_color_and_opacity_skip_geometry_and_repeat_panel_work(self):
        w = self.chart()
        self.edges(w)[0].setSelected(True)
        w._board_geometry()
        with patch.object(w, '_build_board_paths', wraps=w._build_board_paths) as paths, \
             patch.object(w, '_set_document_rect', wraps=w._set_document_rect) as extent, \
             patch.object(w.organogram_panel, 'refresh', wraps=w.organogram_panel.refresh) as panel:
            w.change_board_connector_style(color='#aa3344')
            w.change_board_connector_style(opacity=.63)
        paths.assert_not_called()
        extent.assert_not_called()
        self.assertEqual(panel.call_count, 2)
        self.check_geometry(w)

    def test_native_drag_builds_one_final_geometry(self):
        w = self.chart()
        start = start_board_drag(w, 10)
        with patch.object(w, '_build_board_paths', wraps=w._build_board_paths) as paths:
            move_board_drag(w, start, 10)
        self.assertEqual(paths.call_count, 1)
        self.check_geometry(w)

    def test_width_radius_ports_and_outer_border_invalidate_geometry(self):
        w = self.chart()
        self.edges(w)[0].setSelected(True)
        with patch.object(w, '_build_board_paths', wraps=w._build_board_paths) as paths:
            w.change_board_connector_style(width_mm=1.6)
            w.change_board_connector_style(radius_mm=5)
            w.scene.clearSelection()
            w._board_items()[0].setSelected(True)
            w.change_board_ports('entry_sides', 'right', True)
            w.change_board_border(cards=True, group=True, _position='outside', width_mm=3)
        self.assertEqual(paths.call_count, 4)
        self.check_geometry(w)

    def test_cutouts_are_shared_and_results_can_be_modified_safely(self):
        w = self.chart(text=True)
        w._invalidate_board_cutouts()
        with patch.object(w, '_build_board_cutouts', wraps=w._build_board_cutouts) as build:
            for edge in self.edges(w):
                edge.shape()
                edge.cutouts()
                edge._paint_clip()
            self.assertEqual(build.call_count, 1)
            box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
            box.moveBy(100, 0)
            for edge in self.edges(w):
                self.assertEqual(edge.cutouts(), self.expected_cutouts(w))
            self.assertEqual(build.call_count, 2)
        copy = self.edges(w)[0].cutouts()
        copy.addRect(QRectF(-10000, -10000, 100, 100))
        self.assertEqual(self.edges(w)[0].cutouts(), self.expected_cutouts(w))

    def test_larger_native_drag_matches_fresh_output_paths(self):
        w = self.editor('connected', 40)
        w.show()
        self.app.processEvents()
        start = start_board_drag(w, 10)
        move_board_drag(w, start, 10)
        self.check_geometry(w)

    def test_nested_batch_exception_flushes_and_restores_external_flags(self):
        w = self.chart()
        with patch.object(w, '_build_board_paths', wraps=w._build_board_paths) as paths:
            with self.assertRaises(ValueError):
                with w._board_visual_batch():
                    w._board_items()[0].moveBy(100, 0)
                    with w._board_visual_batch():
                        w._board_items()[1].moveBy(100, 0)
                        raise ValueError('interrompido')
        self.assertEqual(paths.call_count, 1)
        self.assertFalse(w._board_defer_connections)
        self.assertFalse(w._board_connections_pending)
        w._update_board_extent()
        self.check_geometry(w)
        w.scene._board_snap_suspended = True
        w._move_board_items(w._board_items()[:2], QPointF(100, 0))
        self.assertTrue(w.scene._board_snap_suspended)
        w.scene._board_snap_suspended = False

    def test_text_removal_and_new_scene_discard_cached_cutouts(self):
        from shiboken6 import delete
        w = self.chart(text=True)
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
        self.assertFalse(self.edges(w)[0].cutouts().isEmpty())
        delete(box)
        self.assertTrue(self.edges(w)[0].cutouts().isEmpty())
        document = w._document_with_active_page()
        w._load_document_into_scene(document)
        w.switch_model_page('organogram')
        self.assertTrue(self.edges(w)[0].cutouts().isEmpty())
        self.check_geometry(w)


if __name__ == '__main__':
    unittest.main()
