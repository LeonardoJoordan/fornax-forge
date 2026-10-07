"""A camada do organograma separa os planos sem se tornar um objeto do modelo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QModelIndex, QItemSelectionModel
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from core.fornax_container import open_public_fornax, save_public_fornax
from core.model_document import persistent_model_document
from features.editor.editor_window import EditorWindow, _BOARD_LAYER_ROLE
from features.editor.canvas_items import DesignerBox, RectangleItem, ImageItem
from features.generator.organogram import OrganogramRenderer
from test_organogram import board_document


class OrganogramLayersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def document(self):
        document = board_document(1, 1)
        image = QImage(20, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor('#20a060'))
        path = self.root / 'image.png'
        self.assertTrue(image.save(str(path)))
        board = document['organogram']
        board['boxes'] = [{'x': 0, 'y': -150, 'w': 300, 'h': 100,
                           'html': 'Título', 'layer_id': 50, 'object_id': 'text:50'}]
        board['shapes'] = [{'x': 0, 'y': 0, 'width': 590, 'height': 826,
                            'shape_type': 'rectangle', 'fill_color': '#c03030',
                            'layer_id': 51, 'object_id': 'shape:51'}]
        board['images'] = [{'x': 800, 'y': 0, 'width': 200, 'height': 200,
                            'path': str(path), 'layer_id': 52, 'object_id': 'image:52'}]
        board['layer_order'] = ['shape:51', 'image:52', 'text:50']
        return document

    def editor(self, document=None):
        window = EditorWindow()
        window._load_document_into_scene(document if document is not None else self.document())
        window.switch_model_page('organogram')
        def cleanup():
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def marker(self, window):
        markers = [window.layer_list.item(i) for i in range(window.layer_list.count())
                   if window.layer_list.item(i).data(_BOARD_LAYER_ROLE)]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].data(Qt.ItemDataRole.AccessibleTextRole), 'Organograma')
        return markers[0]

    def layer(self, window, layer_id):
        for i in range(window.layer_list.count()):
            row = window.layer_list.item(i)
            if getattr(row.data(Qt.ItemDataRole.UserRole), 'layer_id', None) == layer_id:
                return row
        self.fail(f'Camada {layer_id} ausente')

    def move(self, window, entry, destination):
        source = window.layer_list.row(entry)
        self.assertTrue(window.layer_list.model().moveRows(
            QModelIndex(), source, 1, QModelIndex(), destination))

    def assert_planes(self, window):
        marker = window.layer_list.row(self.marker(window))
        for root in window._board_artwork_roots():
            row = self.layer(window, root.layer_id)
            self.assertEqual(root.board_behind, window.layer_list.row(row) > marker)
            self.assertEqual(root.zValue() < -20, root.board_behind)

    def assert_render_color(self, window, color, *, png=None):
        renderer = OrganogramRenderer(window._model_document, [{'Nome': 'Ana'}])
        if png is None:
            image = renderer.preview(max_side=800)
            scale = 800 / max(renderer.bounds.width(), renderer.bounds.height())
        else:
            renderer.export_png(png, dpi=150)
            image, scale = QImage(str(png)), 0.5
        x = round((100 - renderer.bounds.left()) * scale)
        y = round((600 - renderer.bounds.top()) * scale)
        self.assertEqual(image.pixelColor(x, y), QColor(color))

    def test_marker_is_board_only_and_selecting_it_cannot_delete_artwork(self):
        window = self.editor()
        self.assert_planes(window)
        self.assertEqual(window.layer_list.row(self.marker(window)), 3)
        self.assertIsInstance(self.layer(window, 50).data(Qt.ItemDataRole.UserRole), DesignerBox)
        self.layer(window, 50).setSelected(True)
        window.layer_list.setCurrentItem(self.marker(window), QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.assertFalse(window.scene.selectedItems())
        self.assertTrue(self.marker(window).isSelected())
        window.delete_selected_items()
        self.assertEqual(len(window._board_artwork_roots()), 3)
        with patch('features.editor.editor_window.dialog_get_text') as rename:
            window.rename_layer(self.marker(window))
            rename.assert_not_called()
        window.switch_model_page('front')
        self.assertFalse(any(window.layer_list.item(i).data(_BOARD_LAYER_ROLE)
                             for i in range(window.layer_list.count())))
        window.switch_model_page('organogram')
        self.assert_planes(window)

    def test_drag_shape_across_board_changes_editor_preview_export_and_survives_history(self):
        window = self.editor()
        self.assert_render_color(window, '#c03030')
        self.move(window, self.layer(window, 51), window.layer_list.count())
        self.assert_planes(window)
        self.assertTrue(self.layer(window, 51).data(Qt.ItemDataRole.UserRole).board_behind)
        self.assert_render_color(window, '#dcecf4')
        self.assert_render_color(window, '#dcecf4', png=self.root / 'behind.png')
        window.undo()
        self.assert_planes(window)
        self.assert_render_color(window, '#c03030')
        window.redo()
        self.assert_planes(window)
        self.assert_render_color(window, '#dcecf4')
        target = self.root / 'layers.fornax'
        save_public_fornax(persistent_model_document(window._model_document), target)
        opened = open_public_fornax(target).document()
        self.assertTrue(opened['organogram']['shapes'][0]['board_behind'])
        window._load_document_into_scene(opened)
        window.switch_model_page('organogram')
        self.assert_planes(window)
        self.assert_render_color(window, '#dcecf4')

    def test_drag_board_itself_changes_all_artwork_and_existing_position_control_stays_in_sync(self):
        window = self.editor()
        self.move(window, self.marker(window), 0)
        self.assert_planes(window)
        self.assertTrue(all(item.board_behind for item in window._board_artwork_roots()))
        self.move(window, self.marker(window), window.layer_list.count())
        self.assert_planes(window)
        self.assertTrue(all(not item.board_behind for item in window._board_artwork_roots()))
        image = self.layer(window, 52).data(Qt.ItemDataRole.UserRole)
        window.layer_list.setCurrentItem(self.layer(window, 52))
        window.change_board_artwork_position(True)
        self.assert_planes(window)
        self.assertTrue(image.board_behind)

    def test_masked_image_stays_with_shape_when_board_crosses_child_or_parent_moves(self):
        document = self.document()
        image = document['organogram']['images'][0]
        image.update(mask_shape_id='shape:51', mask_order=0, x=0, y=0)
        window = self.editor(document)
        shape = self.layer(window, 51).data(Qt.ItemDataRole.UserRole)
        child = self.layer(window, 52).data(Qt.ItemDataRole.UserRole)
        self.assertIsInstance(shape, RectangleItem)
        self.assertIsInstance(child, ImageItem)
        self.assertIs(child.parentItem(), shape)
        # Soltar a camada entre máscara e imagem não separa os dois elementos.
        self.move(window, self.marker(window), window.layer_list.row(self.layer(window, 52)))
        self.assert_planes(window)
        self.assertEqual(window.layer_list.row(self.layer(window, 52)),
                         window.layer_list.row(self.layer(window, 51)) + 1)
        self.move(window, self.layer(window, 51), window.layer_list.count())
        self.assert_planes(window)
        saved = persistent_model_document(window._model_document)['organogram']
        self.assertTrue(saved['shapes'][0]['board_behind'])
        self.assertTrue(saved['images'][0]['board_behind'])
        self.assertEqual(saved['images'][0]['mask_shape_id'], 'shape:51')

    def test_multiple_artwork_layers_can_cross_board_together(self):
        window = self.editor()
        window.layer_list.clearSelection()
        text, image = self.layer(window, 50), self.layer(window, 52)
        text.setSelected(True)
        image.setSelected(True)
        self.assertTrue(window.move_layer_group_from_badge(text, self.marker(window), after=True))
        self.assert_planes(window)
        self.assertTrue(self.layer(window, 50).data(Qt.ItemDataRole.UserRole).board_behind)
        self.assertTrue(self.layer(window, 52).data(Qt.ItemDataRole.UserRole).board_behind)
        self.assertFalse(self.layer(window, 51).data(Qt.ItemDataRole.UserRole).board_behind)

    def test_normal_page_layer_order_remains_independent_of_board(self):
        window = self.editor()
        window.switch_model_page('front')
        self.move(window, self.layer(window, 2), 0)
        first = window.layer_list.item(0).data(Qt.ItemDataRole.UserRole)
        self.assertEqual(first.layer_id, 2)
        self.assertGreater(first.zValue(), self.layer(window, 3).data(Qt.ItemDataRole.UserRole).zValue())
        state = window.get_current_scene_state()
        self.assertTrue(all('board_behind' not in entry for collection in ('boxes', 'images', 'shapes')
                            for entry in state.get(collection, [])))
        window.switch_model_page('organogram')
        self.assert_planes(window)


if __name__ == '__main__':
    unittest.main()
