"""Seleções coletivas: regras, foco, máscaras, painéis e aparência de referência."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent, QItemSelection, QItemSelectionModel, QRectF, QSignalBlocker
from PySide6.QtGui import QPainterPath, QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtTest import QTest
from features.editor.canvas_items import DesignerBox, RectangleItem, Guideline
from features.editor.organogram_editor import BoardConnectorItem, BoardGroupItem
import test_editor_performance_contracts as contracts


class SelectionBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def settle(self):
        for _ in range(4):
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def record(self, window, key):
        """Estado/pixels reais, fora do intervalo medido e com fonte/entrada fixa."""
        self.settle()
        def identity(item):
            if isinstance(item, BoardGroupItem):
                return 'block:' + item.data['id']
            if isinstance(item, BoardConnectorItem):
                return 'edge:' + item.board_edge['source'] + ':' + item.board_edge['target']
            return type(item).__name__ + ':' + str(getattr(item, 'layer_id', None))
        image = QImage(800, 600, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            window.scene.render(painter, QRectF(0, 0, 800, 600), window._get_document_rect())
        finally:
            painter.end()
        state = {'selected': sorted(identity(i) for i in window.scene.selectedItems()),
                 'document': window._document_with_active_page(),
                 'text_enabled': window.editor_texto_panel.isEnabled(),
                 'properties_enabled': window.caixa_texto_panel.isEnabled(),
                 'multi_handles': window.scene._multi_selection_active,
                 'pixels_sha256': sha256(bytes(image.constBits())).hexdigest()}
        output = os.environ.get('FORNAX_SELECTION_EVIDENCE')
        if output:
            path = Path(output)
            values = json.loads(path.read_text()) if path.exists() else {}
            values[key] = state
            path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
        return state

    def test_all_and_group_keep_masks_document_and_final_appearance(self):
        w = self.editor('mixed', 60)
        before = w._document_with_active_page()
        history = w.history._current_index
        w.select_all_items()
        self.assertEqual(before, w._document_with_active_page())
        self.assertEqual(history, w.history._current_index)
        for item in w.scene.selectedItems():
            self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.assertNotIsInstance(item, Guideline)
        self.record(w, 'all-mixed')
        w.select_group(1)
        self.assertEqual(set(w.scene.selectedItems()), set(w._group_members(1)))
        self.record(w, 'group-mixed')

    def test_canvas_selecting_member_completes_group_without_changing_document(self):
        w = self.editor('mixed', 60)
        member = w._group_members(1)[0]
        before = w._document_with_active_page()
        member.setSelected(True)
        self.assertEqual(set(w.scene.selectedItems()), set(w._group_members(1)))
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'group-from-member')

    def test_mask_badge_selects_parent_on_canvas_and_children_only_in_layers(self):
        w = self.editor('mixed', 60)
        shape = sorted((i for i in w.scene.items() if isinstance(i, RectangleItem) and i.masked_images()),
                       key=lambda i: i.layer_id)[0]
        before = w._document_with_active_page()
        w.select_mask_group(shape)
        self.assertEqual(w.scene.selectedItems(), [shape])
        self.assertEqual({row.data(Qt.ItemDataRole.UserRole) for row in w.layer_list.selectedItems()},
                         {shape, *shape.masked_images()})
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'mask-badge')

    def test_mask_badge_inside_group_preserves_existing_group_completion_rule(self):
        w = self.editor('mixed', 60)
        shape = next(i for i in w._group_members(1) if isinstance(i, RectangleItem) and i.masked_images())
        w.select_mask_group(shape)
        self.assertEqual(set(w.scene.selectedItems()), set(w._group_members(1)))
        self.assertEqual({row.data(Qt.ItemDataRole.UserRole) for row in w.layer_list.selectedItems()},
                         {shape, *shape.masked_images()})
        self.record(w, 'mask-badge-in-group')

    def test_select_all_commits_mask_edit_and_restores_flags(self):
        w = self.editor('mixed', 60)
        shape = sorted((i for i in w.scene.items() if isinstance(i, RectangleItem) and i.masked_images()),
                       key=lambda i: i.layer_id)[0]
        image = shape.masked_images()[0]
        before = w._document_with_active_page()
        self.assertTrue(w.begin_mask_edit(image))
        w.select_all_items()
        self.assertIsNone(w._mask_edit_session)
        self.assertFalse(shape._mask_editing)
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'all-after-mask-edit')

    def test_layer_selection_keeps_partial_group(self):
        w = self.editor('mixed', 60)
        member = w._group_members(1)[0]
        row = next(w.layer_list.item(i) for i in range(w.layer_list.count())
                   if w.layer_list.item(i).data(Qt.ItemDataRole.UserRole) is member)
        w.layer_list.setCurrentItem(row, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.assertEqual(w.scene.selectedItems(), [member])
        self.record(w, 'partial-group-layers')

    def test_guides_are_selected_alone_and_removed_from_mixed_selection(self):
        w = self.editor('mixed', 60)
        guide = next(i for i in w.scene.items() if isinstance(i, Guideline))
        guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        guide.setSelected(True)
        self.assertEqual(w.scene.selectedItems(), [guide])
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and not i.group_id and i.layer_id != 1)
        box.setSelected(True)
        self.assertEqual(w.scene.selectedItems(), [box])

    def test_tree_selects_multiple_blocks_and_keeps_document(self):
        w = self.editor('connected', 10)
        tree = w.organogram_panel.tree
        model = tree.model()
        selection = QItemSelection()
        for group in w._board_items()[:4]:
            index = tree.indexFromItem(w.organogram_panel._nodes[group.data['id']])
            selection.select(index, index)
        before = w._document_with_active_page()
        tree.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        expected = {node.data(0, Qt.ItemDataRole.UserRole) for node in tree.selectedItems()}
        self.assertEqual(len(expected), 4)
        self.assertEqual({i.data['id'] for i in w.scene.selectedItems()}, expected)
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'tree-blocks')

    def test_area_selection_keeps_blocks_and_connectors(self):
        w = self.editor('connected', 10)
        path = QPainterPath()
        path.addRect(w.scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
        before = w._document_with_active_page()
        w.scene.setSelectionArea(path, Qt.ItemSelectionOperation.ReplaceSelection, Qt.ItemSelectionMode.IntersectsItemShape)
        selected = w.scene.selectedItems()
        self.assertEqual(sum(isinstance(i, BoardGroupItem) for i in selected), 10)
        self.assertEqual(sum(isinstance(i, BoardConnectorItem) for i in selected), 9)
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'area-board')

    def test_ctrl_click_adds_and_removes_canvas_items(self):
        w = self.editor()
        w.resize(1280, 800)
        w.show()
        w._zoom_to_fit()
        self.settle()
        items = sorted((i for i in w.scene.items() if isinstance(i, DesignerBox) and i.isVisible()
                        and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable), key=lambda i: i.layer_id)
        first, second = items[:2]
        def click(item, modifier):
            point = w.view.mapFromScene(item.sceneBoundingRect().center())
            QTest.mouseClick(w.view.viewport(), Qt.MouseButton.LeftButton, modifier, point)
            self.settle()
        click(first, Qt.KeyboardModifier.NoModifier)
        self.assertEqual(w.scene.selectedItems(), [first])
        click(second, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(set(w.scene.selectedItems()), {first, second})
        click(second, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.scene.selectedItems(), [first])

    def test_ctrl_a_during_text_edit_selects_text_and_preserves_edit_session(self):
        w = self.editor()
        w.show()
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.layer_id == 2)
        w.canvas_edit.begin(box)
        self.settle()
        QTest.keyClick(w.view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertIs(w.canvas_edit.box, box)
        self.assertTrue(box.text_item.textCursor().hasSelection())
        self.assertEqual(w.scene.selectedItems(), [box])
        self.assertFalse(w.shortcut_select_all.isEnabled())

    def test_select_all_finishes_existing_text_edit_and_keeps_box_selected(self):
        w = self.editor()
        w.show()
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.layer_id == 2)
        w.canvas_edit.begin(box)
        w.select_all_items()
        self.assertIsNone(w.canvas_edit.box)
        self.assertTrue(box.isSelected())

    def test_changing_selection_commits_text_and_restores_shortcuts(self):
        w = self.editor()
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.layer_id == 2)
        other = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.layer_id == 3)
        w.canvas_edit.begin(box)
        box.text_item.textCursor().insertText(' completo')
        w.scene.clearSelection()
        other.setSelected(True)
        self.assertIsNone(w.canvas_edit.box)
        self.assertIn(' completo', box.state.html_content)
        self.assertTrue(w.shortcut_select_all.isEnabled())
        self.assertTrue(w.editor_texto_panel.isEnabled())


class SelectionWorkTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def observe(self, window):
        states = []
        def changed():
            states.append(set(window.scene.selectedItems()))
        window.scene.selectionChanged.connect(changed)
        self.addCleanup(lambda: window.scene.selectionChanged.disconnect(changed))
        return states

    # Executado separadamente apenas depois da otimização; não muda os contratos.
    def test_collective_selection_publishes_one_final_state(self):
        for fixture, size, action in (
            ('simple', 20, lambda w: w.select_all_items()),
            ('mixed', 60, lambda w: w.select_all_items()),
            ('mixed', 60, lambda w: w.select_group(1)),
        ):
            with self.subTest(action=fixture):
                w = self.editor(fixture, size)
                states = self.observe(w)
                with patch.object(w, '_groupable_items', wraps=w._groupable_items) as scans, \
                     patch.object(w.caixa_texto_panel, 'load_from_item', wraps=w.caixa_texto_panel.load_from_item) as text, \
                     patch.object(w.caixa_texto_panel, 'load_from_image', wraps=w.caixa_texto_panel.load_from_image) as image, \
                     patch.object(w, '_refresh_board_inspector', wraps=w._refresh_board_inspector) as inspector:
                    action(w)
                    self.assertEqual(states, [set(w.scene.selectedItems())])
                    self.assertLessEqual(text.call_count + image.call_count, 1)
                    self.assertLessEqual(scans.call_count, 2)
                    self.assertEqual(inspector.call_count, 1)

    def test_group_completion_has_one_panel_load_and_final_notification(self):
        w = self.editor('mixed', 60)
        states = self.observe(w)
        with patch.object(w, '_sync_selection_panels', wraps=w._sync_selection_panels) as panels:
            w._group_members(1)[0].setSelected(True)
        self.assertEqual(panels.call_count, 1)
        self.assertEqual(states, [set(w._group_members(1))])

    def test_batch_is_nested_and_preserves_external_signal_blocking(self):
        w = self.editor()
        boxes = sorted((i for i in w.scene.items() if isinstance(i, DesignerBox)), key=lambda i: i.layer_id)
        states = self.observe(w)
        with w._selection_batch():
            boxes[1].setSelected(True)
            with w._selection_batch():
                boxes[2].setSelected(True)
            self.assertEqual(states, [])
        self.assertEqual(states, [{boxes[1], boxes[2]}])
        states.clear()
        with QSignalBlocker(w.scene):
            w.select_all_items()
            self.assertTrue(w.scene.signalsBlocked())
        self.assertEqual(states, [])
        self.assertFalse(w.scene.signalsBlocked())

    def test_batch_restores_signals_after_error(self):
        w = self.editor()
        with self.assertRaises(ValueError):
            with w._selection_batch():
                raise ValueError('simulação')
        self.assertFalse(w.scene.signalsBlocked())
        self.assertEqual(w._selection_batch_depth, 0)

    def test_layer_and_tree_publish_one_final_selection(self):
        for fixture in ('mixed', 'connected'):
            with self.subTest(fixture=fixture):
                w = self.editor(fixture, 20)
                view = w.layer_list if fixture == 'mixed' else w.organogram_panel.tree
                model = view.model()
                selection = QItemSelection(model.index(0, 0), model.index(min(4, model.rowCount()-1), 0))
                states = self.observe(w)
                with patch.object(w, '_sync_selection_panels', wraps=w._sync_selection_panels) as panels:
                    view.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                self.assertEqual(states, [set(w.scene.selectedItems())])
                self.assertEqual(panels.call_count, 1)


if __name__ == '__main__':
    unittest.main()
