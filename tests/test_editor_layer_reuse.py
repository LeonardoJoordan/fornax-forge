"""Camadas: estado, aparência, ordem, máscaras e referências de callbacks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QEvent, QSignalBlocker, QSize, QModelIndex
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QPushButton, QGraphicsRectItem
from shiboken6 import isValid
from core.themes import theme_manager
from features.editor.editor_window import ElidedLayerLabel, LayerGroupBadge, _BOARD_LAYER_ROLE
from features.editor.canvas_items import DesignerBox, RectangleItem
import test_editor_performance_contracts as contracts


class LayerBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def rows(self, w):
        return {row.data(Qt.ItemDataRole.UserRole): row for row in
                (w.layer_list.item(i) for i in range(w.layer_list.count()))
                if row.data(Qt.ItemDataRole.UserRole) is not None}

    def box(self, w):
        return next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.layer_id == 6)

    def settle(self):
        for _ in range(4):
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def record(self, w, key):
        self.settle()
        result = []
        for index in range(w.layer_list.count()):
            row = w.layer_list.item(index)
            widget = w.layer_list.itemWidget(row)
            item = row.data(Qt.ItemDataRole.UserRole)
            widget.resize(280, max(24, widget.sizeHint().height()))
            image = QImage(widget.size(), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            try:
                widget.render(painter, widget.rect().topLeft())
            finally:
                painter.end()
            result.append({'layer_id': getattr(item, 'layer_id', None),
                           'type': type(item).__name__, 'board': bool(row.data(_BOARD_LAYER_ROLE)),
                           'name': [label._full_text for label in widget.findChildren(ElidedLayerLabel)],
                           'badges': [badge.text() for badge in widget.findChildren(LayerGroupBadge)],
                           'flags': row.flags().value,
                           'pixels': sha256(bytes(image.constBits())).hexdigest()})
        state = json.loads(json.dumps({'rows': result, 'document': w._document_with_active_page()}).replace(str(self.root), '__TEST_ROOT__'))
        output = os.environ.get('FORNAX_LAYER_EVIDENCE')
        if output:
            path = Path(output)
            values = json.loads(path.read_text()) if path.exists() else {}
            values[key] = state
            path.write_text(json.dumps(values, indent=2, ensure_ascii=False)+'\n')
        return state

    def test_refresh_preserves_document_order_masks_and_appearance(self):
        w = self.editor('mixed', 60)
        before = w._document_with_active_page()
        w.refresh_layer_list()
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'refresh')

    def test_rename_and_text_edit_use_actual_editor_commands(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        with patch('features.editor.editor_window.dialog_get_text', return_value=('Nome completo', True)):
            w.rename_layer(self.rows(w)[box])
        self.assertEqual(box.custom_name, 'Nome completo')
        w.canvas_edit.begin(box)
        box.text_item.textCursor().insertText(' texto completo')
        w.canvas_edit.finish()
        self.assertIn(' texto completo', box.state.html_content)
        self.record(w, 'rename-text')

    def test_visibility_and_lock_controls_change_their_own_object(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        widget = w.layer_list.itemWidget(self.rows(w)[box])
        buttons = widget.findChildren(QPushButton)
        buttons[0].click()
        self.assertFalse(box.isVisible())
        buttons[-1].click()
        self.assertFalse(box.flags() & box.GraphicsItemFlag.ItemIsMovable)
        self.record(w, 'hidden-locked')

    def test_add_and_delete_restore_content_and_order(self):
        w = self.editor('mixed', 60)
        before = w._document_with_active_page()
        w.add_new_box()
        w.delete_selected_items()
        self.assertEqual(before, w._document_with_active_page())
        self.record(w, 'add-delete')

    def test_group_and_ungroup_keep_original_layer_order(self):
        w = self.editor('mixed', 60)
        boxes = [i for i in w.scene.items() if isinstance(i, DesignerBox) and not i.group_id
                 and i.isVisible() and i.layer_id != 1][:2]
        for box in boxes:
            box.setSelected(True)
        before = list(self.rows(w))
        self.assertTrue(w.group_selected_items())
        self.assertEqual(list(self.rows(w)), before)
        self.record(w, 'group')
        self.assertTrue(w.ungroup_selected_items())
        self.assertEqual(list(self.rows(w)), before)
        self.record(w, 'ungroup')

    def test_reorder_is_reflected_in_document_and_rows(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        row = self.rows(w)[box]
        self.assertTrue(w.layer_list.model().moveRows(QModelIndex(), w.layer_list.row(row), 1, QModelIndex(), 0))
        self.assertIs(w.layer_list.item(0).data(Qt.ItemDataRole.UserRole), box)
        self.record(w, 'reorder')

    def test_board_marker_and_artwork_keep_planes_and_order(self):
        import test_organogram_layers as fixtures
        helper = fixtures.OrganogramLayersTest()
        helper.root = self.root
        w = self.editor('connected', 4)
        document = helper.document()
        document['organogram']['groups'][0]['id'] = 'bloco-referencia'
        w._load_document_into_scene(document)
        w.switch_model_page('organogram')
        w.refresh_layer_list()
        self.assertEqual(sum(bool(w.layer_list.item(i).data(_BOARD_LAYER_ROLE))
                             for i in range(w.layer_list.count())), 1)
        self.record(w, 'board')

    def test_undo_and_redo_callbacks_target_current_scene_objects(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        box.setSelected(True)
        w.add_new_box()
        w.undo()
        w.redo()
        for item, row in self.rows(w).items():
            self.assertIs(item.scene(), w.scene)
            self.assertTrue(isValid(item))
        self.record(w, 'history')


class LayerReuseTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor
    rows = LayerBehaviorTest.rows
    box = LayerBehaviorTest.box
    settle = LayerBehaviorTest.settle
    def test_unchanged_refresh_creates_no_rows_and_keeps_scroll_selection(self):
        w = self.editor('mixed', 60)
        w.show()
        self.settle()
        box = self.box(w)
        w.layer_list.setCurrentItem(self.rows(w)[box])
        w.layer_list.verticalScrollBar().setValue(100)
        self.settle()
        scroll = w.layer_list.verticalScrollBar().value()
        old = {item: (row, w.layer_list.itemWidget(row)) for item,row in self.rows(w).items()}
        with patch.object(ElidedLayerLabel, '__init__', side_effect=AssertionError('Nova linha indevida')):
            w.refresh_layer_list()
        self.assertEqual(w.layer_list.verticalScrollBar().value(), scroll)
        self.assertIs(w.layer_list.currentItem(), old[box][0])
        self.assertTrue(old[box][0].isSelected())
        for item, (row, widget) in old.items():
            self.assertIs(self.rows(w)[item], row)
            self.assertIs(w.layer_list.itemWidget(row), widget)

    def test_rename_visibility_lock_and_text_keep_row_widgets(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        row = self.rows(w)[box]
        widget = w.layer_list.itemWidget(row)
        box.custom_name = 'Outro nome'
        box.state.html_content = '<p>Texto editado</p>'
        box.apply_state()
        box.setVisible(False)
        box.setFlag(box.GraphicsItemFlag.ItemIsMovable, False)
        w.refresh_layer_list()
        self.assertIs(self.rows(w)[box], row)
        self.assertIs(w.layer_list.itemWidget(row), widget)
        self.assertEqual(widget.findChildren(ElidedLayerLabel)[0]._full_text, 'Outro nome')
        self.assertEqual(widget.findChildren(QPushButton)[0].graphicsEffect().opacity(), .15)
        self.assertEqual(widget.findChildren(QPushButton)[-1].graphicsEffect().opacity(), 1)

    def test_add_delete_keep_unaffected_widgets(self):
        w = self.editor()
        old = {item: w.layer_list.itemWidget(row) for item,row in self.rows(w).items()}
        w.add_new_box()
        w.delete_selected_items()
        for item,widget in old.items():
            self.assertIs(w.layer_list.itemWidget(self.rows(w)[item]), widget)

    def test_reorder_keeps_widgets_and_badge_references(self):
        w = self.editor('mixed', 60)
        old = {item: (row,w.layer_list.itemWidget(row)) for item,row in self.rows(w).items()}
        box = self.box(w)
        row = old[box][0]
        w.layer_list.model().moveRows(QModelIndex(),w.layer_list.row(row),1,QModelIndex(),0)
        for item,(row,widget) in old.items():
            self.assertIs(w.layer_list.itemWidget(row),widget)
        badge = next(b for _,widget in old.values() for b in widget.findChildren(LayerGroupBadge)
                     if b.toolTip().startswith('Grupo'))
        badge.click()
        self.assertEqual(set(w.scene.selectedItems()),set(w._group_members(1)))

    def test_controls_invalidate_visual_state_before_external_restore(self):
        w = self.editor()
        box = self.box(w)
        widget = w.layer_list.itemWidget(self.rows(w)[box])
        buttons = widget.findChildren(QPushButton)
        buttons[0].click()
        buttons[-1].click()
        box.setVisible(True)
        box.setFlag(box.GraphicsItemFlag.ItemIsMovable, True)
        w.refresh_layer_list()
        self.assertEqual(buttons[0].graphicsEffect().opacity(), 1)
        self.assertEqual(buttons[-1].graphicsEffect().opacity(), .15)

    def test_detached_widget_callback_cannot_modify_removed_object(self):
        w = self.editor()
        box = self.box(w)
        widget = w.layer_list.itemWidget(self.rows(w)[box])
        button = widget.findChildren(QPushButton)[0]
        w.scene.removeItem(box)
        visible = box.isVisible()
        with patch.object(w,'save_snapshot') as save:
            button.click()
        self.assertEqual(box.isVisible(),visible)
        save.assert_not_called()

    def test_rebuilt_scene_never_reuses_callbacks_to_old_objects(self):
        w = self.editor()
        old = list(self.rows(w))
        document = w._document_with_active_page()
        w._load_document_into_scene(document)
        current = list(self.rows(w))
        self.assertTrue(all(new is not previous for new in current for previous in old))
        box = self.box(w)
        w.layer_list.itemWidget(self.rows(w)[box]).findChildren(QPushButton)[0].click()
        self.assertFalse(box.isVisible())


    def test_deleted_cpp_object_does_not_poison_remaining_rows(self):
        from shiboken6 import delete
        w = self.editor()
        box = self.box(w)
        remaining = {item: w.layer_list.itemWidget(row) for item,row in self.rows(w).items()
                     if item is not box}
        w.layer_list.setCurrentItem(self.rows(w)[box])
        delete(box)
        w.refresh_layer_list()
        self.assertNotIn(box, self.rows(w))
        for item,widget in remaining.items():
            self.assertIs(w.layer_list.itemWidget(self.rows(w)[item]), widget)

    def test_pasted_row_controls_only_the_new_object(self):
        w = self.editor()
        original = self.box(w)
        original_id = original.layer_id
        original.setSelected(True)
        w.copy_selected_items()
        w.paste_copied_items()
        # A colagem atual reconstrói a cena; a otimização dela é a etapa 05.
        original = next(item for item in w.scene.items() if isinstance(item, DesignerBox)
                        and item.layer_id == original_id)
        pasted = next(item for item in w.scene.selectedItems() if isinstance(item, DesignerBox))
        self.assertIsNot(pasted, original)
        w.layer_list.itemWidget(self.rows(w)[pasted]).findChildren(QPushButton)[0].click()
        self.assertFalse(pasted.isVisible())
        self.assertTrue(original.isVisible())

    def test_failed_reconciliation_rebuilds_safe_rows(self):
        w = self.editor()
        box = self.box(w)
        box.setZValue(w._next_object_z())
        with patch.object(w.layer_list.model(), 'moveRows', return_value=False):
            w.refresh_layer_list()
        self.assertIs(w.layer_list.item(0).data(Qt.ItemDataRole.UserRole), box)
        self.assertFalse(w._syncing_layer_rows)
        self.assertFalse(w.layer_list.signalsBlocked())
        w.layer_list.itemWidget(self.rows(w)[box]).findChildren(QPushButton)[0].click()
        self.assertFalse(box.isVisible())

    def test_theme_change_keeps_rows_and_updates_icons(self):
        w = self.editor('mixed', 60)
        box = self.box(w)
        row = self.rows(w)[box]
        widget = w.layer_list.itemWidget(row)
        original_theme = theme_manager().theme_id
        self.addCleanup(lambda: theme_manager().select(original_theme))
        def pixels():
            image = widget.findChildren(QPushButton)[0].icon().pixmap(16,16).toImage()
            return bytes(image.constBits())
        before = pixels()
        theme_manager().select('light' if original_theme == 'dark' else 'dark')
        self.settle()
        self.assertIs(w.layer_list.itemWidget(row),widget)
        self.assertNotEqual(before,pixels())


class LayerIdAllocationTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def test_missing_ids_keep_the_previous_lowest_available_id_rule(self):
        w = self.editor('mixed', 20)
        before = w._document_with_active_page()
        helpers = [QGraphicsRectItem(0, 0, 1, 1) for _ in range(6)]
        for index, item in enumerate(helpers):
            item.setZValue(10000 + index)
            w.scene.addItem(item)
        # Mistura atributo ausente, None, zero e identificadores esparsos.
        helpers[0].layer_id = None
        helpers[1].layer_id = 10000
        helpers[2].layer_id = 0
        items = w.scene.items()
        used = {item.layer_id for item in items if getattr(item, 'layer_id', None) is not None}
        expected = {}
        for item in items:
            identity = getattr(item, 'layer_id', None)
            if identity is None:
                identity = 0
                while identity in used:
                    identity += 1
                used.add(identity)
            expected[id(item)] = identity
        w.refresh_layer_list()
        self.assertEqual({id(item): item.layer_id for item in items}, expected)
        self.assertEqual(w._document_with_active_page(), before)

    def test_many_missing_ids_do_not_rescan_the_scene_per_item(self):
        w = self.editor('simple', 4)
        helpers = [QGraphicsRectItem(0, 0, 1, 1) for _ in range(100)]
        for item in helpers:
            w.scene.addItem(item)
        with patch.object(w.scene, 'items', wraps=w.scene.items) as reads:
            w.refresh_layer_list()
        self.assertLess(reads.call_count, 10)
        assigned = [item.layer_id for item in helpers]
        self.assertEqual(len(set(assigned)), len(helpers))

    def test_removed_ids_are_available_again_on_the_next_refresh(self):
        w = self.editor('simple', 4)
        first = QGraphicsRectItem(0, 0, 1, 1)
        w.scene.addItem(first)
        w.refresh_layer_list()
        identity = first.layer_id
        w.scene.removeItem(first)
        replacement = QGraphicsRectItem(0, 0, 1, 1)
        w.scene.addItem(replacement)
        w.refresh_layer_list()
        self.assertEqual(replacement.layer_id, identity)
        w.refresh_layer_list()
        self.assertEqual(replacement.layer_id, identity)


if __name__ == '__main__':
    unittest.main()
