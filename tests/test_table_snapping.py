"""Magnetismo de tabelas segue o mesmo contrato de formas e imagens."""
from copy import deepcopy
import unittest

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

import test_table_interaction as interaction
from core.model_document import normalize_model_document, add_model_table
from core.table_model import new_table
from core.organogram import add_organogram
from features.editor.canvas_items import Guideline, RectangleItem
from features.editor.table_item import TableItem


class TableSnappingTest(unittest.TestCase):
    setUpClass = classmethod(interaction.TableInteractionTest.setUpClass.__func__)
    tearDownClass = classmethod(interaction.TableInteractionTest.tearDownClass.__func__)
    setUp = interaction.TableInteractionTest.setUp
    tearDown = interaction.TableInteractionTest.tearDown
    editor = interaction.TableInteractionTest.editor
    point = interaction.TableInteractionTest.point
    drag = interaction.TableInteractionTest.drag

    def setup_table(self):
        table = new_table(width=240, height=150)
        table.update(x=100, y=100)
        document = add_model_table(normalize_model_document({'canvas_size': {'w': 900, 'h': 650}}), table)
        return self.editor(document)

    def guides(self, w, x=300, y=300):
        for position, vertical in ((x, True), (y, False)):
            guide = Guideline(position, vertical)
            guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            w.scene.addItem(guide)

    def start(self, w, leader, *items):
        with w._selection_batch():
            w.scene.clearSelection()
            for item in items or (leader,):
                item.setSelected(True)
        leader._is_mouse_dragging = True
        w.scene._drag_start_positions = {i: QPointF(i.pos()) for i in items or (leader,)}
        w.scene._group_raw_delta = w.scene._board_drag_anchor = None

    def test_edges_and_center_snap_like_shapes_including_rotation(self):
        w, table = self.setup_table()
        shape = RectangleItem(240, 150)
        shape.layer_id = w._get_next_layer_id()
        w.scene.addItem(shape)
        self.guides(w)
        layout, documents = table.layout, [cell.document for cell in table.layout.cells]
        for rotation in (0, 30, 90):
            for anchor in ('first', 'center', 'last'):
                results = []
                for item in (table, shape):
                    with self.subTest(rotation=rotation, anchor=anchor, item=type(item).__name__):
                        item._is_mouse_dragging = False
                        item.setPos(100, 100)
                        item.setRotation(rotation)
                        bounds = item.mapRectToScene(item.rect())
                        target = {'first': bounds.topLeft(), 'center': bounds.center(),
                                  'last': bounds.bottomRight()}[anchor]
                        offset = target-item.pos()
                        self.start(w, item)
                        try:
                            item.setPos(QPointF(298, 298)-offset)
                            results.append(QPointF(item.pos()))
                            self.assertLess((item.pos()+offset-QPointF(300, 300)).manhattanLength(), .0001)
                        finally:
                            item._is_mouse_dragging = False
                            w.scene._group_raw_delta = None
                self.assertEqual(results[0], results[1])
        self.assertIs(table.layout, layout)
        self.assertEqual([cell.document for cell in table.layout.cells], documents)

    def test_real_drag_snaps_to_guides_and_undo_redo_retains_result(self):
        w, item = self.setup_table()
        self.guides(w)
        w.save_snapshot()
        before = deepcopy(w._capture_document_history_state()['document'])
        layout = item.layout
        start = self.point(w, item, 80, 60)
        end = w.view.mapFromScene(item.mapToScene(QPointF(80, 60))+QPointF(198, 198))
        self.drag(w, start, end)
        self.assertEqual(item.pos(), QPointF(300, 300))
        self.assertIs(item.layout, layout)
        self.assertFalse(item._is_mouse_dragging)
        self.assertIsNone(item.selected_range)
        final = deepcopy(w._capture_document_history_state()['document'])
        w.undo()
        self.assertEqual(w._capture_document_history_state()['document'], before)
        w.redo()
        self.assertEqual(w._capture_document_history_state()['document'], final)

    def test_mixed_drag_preserves_distance_with_table_or_shape_as_leader(self):
        w, table = self.setup_table()
        shape = RectangleItem(100, 100)
        shape.layer_id = w._get_next_layer_id()
        w.scene.addItem(shape)
        self.guides(w)
        for leader in (table, shape):
            with self.subTest(leader=type(leader).__name__):
                table.setPos(100, 100)
                shape.setPos(450, 100)
                offset = shape.pos()-table.pos()
                self.start(w, leader, table, shape)
                starts = dict(w.scene._drag_start_positions)
                for item in (leader, shape if leader is table else table):
                    item.setPos(starts[item]+QPointF(198, 198))
                self.assertEqual(table.pos(), QPointF(300, 300))
                self.assertEqual(shape.pos()-table.pos(), offset)
                leader._is_mouse_dragging = False
                w.scene._group_raw_delta = None

    def test_numeric_position_is_not_snapped_and_document_edges_are_targets(self):
        w, table = self.setup_table()
        self.guides(w)
        table.setPos(298, 298)
        self.assertEqual(table.pos(), QPointF(298, 298))
        self.start(w, table)
        table.setPos(2, 2)
        self.assertEqual(table.pos(), QPointF(0, 0))
        table._is_mouse_dragging = False

    def test_resize_handle_snaps_to_guide_without_moving_opposite_edge(self):
        w, item = self.setup_table()
        self.guides(w, x=440, y=550)
        item.keep_proportion = False
        item.setSelected(True)
        self.app.processEvents()
        fixed_edge = item.mapToScene(QPointF(0, 75))
        start = w.view.mapFromScene(item.resize_handles['right'].scenePos())
        end = w.view.mapFromScene(item.mapToScene(QPointF(338, 75)))
        self.drag(w, start, end)
        self.assertAlmostEqual(item.mapToScene(QPointF(item.rect().width(), 75)).x(), 440)
        self.assertEqual(item.mapToScene(QPointF(0, 75)), fixed_edge)
        self.assertAlmostEqual(item.rect().height(), 150)

    def test_organogram_keeps_center_grid_and_suspension(self):
        w, _ = self.setup_table()
        source = add_organogram(w._capture_document_history_state()['document'])
        source = add_model_table(source, new_table(width=240, height=150), 'organogram')
        w._load_document_into_scene(source)
        w.switch_model_page('organogram')
        item = next(i for i in w.scene.items() if isinstance(i, TableItem))
        self.start(w, item)
        item.setPos(137, 217)
        center = item.mapToScene(item.rect().center())
        step = w.scene._board_grid
        self.assertAlmostEqual(center.x()/step, round(center.x()/step))
        self.assertAlmostEqual(center.y()/step, round(center.y()/step))
        w.scene._board_snap_suspended = True
        try:
            item.setPos(137, 217)
            self.assertEqual(item.pos(), QPointF(137, 217))
        finally:
            item._is_mouse_dragging = False
            w.scene._board_snap_suspended = False


if __name__ == '__main__':
    unittest.main()
