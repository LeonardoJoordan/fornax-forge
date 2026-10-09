"""Reconstruir cenas com máscaras não pode descartar seus textos e imagens."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import gc
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from core.fornax_container import open_public_fornax, save_public_fornax
from core.model_document import persistent_model_document
from features.editor.canvas_items import DesignerBox, ImageItem, RectangleItem
from features.editor.editor_window import EditorWindow
from test_organogram import board_document


class SceneLoadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def document(self, *, organogram=True):
        document = board_document(1, 1)
        image = QImage(20, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        path = self.root / 'photo.png'
        self.assertTrue(image.save(str(path)))
        page = document['organogram'] if organogram else document['pages'][0]
        page['boxes'] = [
            {'layer_id': i, 'object_id': f'text:{i}', 'x': 0, 'y': (i - 51) * 100,
             'w': 300, 'h': 80, 'id': f'Texto {i}', 'html': f'<p>Texto {i}</p>',
             'rich_text_version': 1} for i in (51, 52, 53, 54)
        ]
        page['shapes'] = [
            {'layer_id': 60, 'object_id': 'shape:60', 'x': 400, 'y': 0,
             'width': 300, 'height': 300, 'shape_type': 'rectangle',
             'custom_name': 'Máscara', 'outline_enabled': True}
        ]
        page['images'] = [
            {'layer_id': i, 'object_id': f'image:{i}', 'path': str(path),
             'mask_shape_id': 'shape:60', 'mask_order': i - 61,
             'x': 0, 'y': 0, 'width': 300, 'height': 300} for i in (61, 62)
        ]
        page['layer_order'] = ['shape:60', 'image:61', 'image:62'] + [
            f'text:{i}' for i in (51, 52, 53, 54)]
        if not organogram:
            del document['organogram']
            document['schema_version'] = 4
        return document

    def editor(self, document, *, organogram=True):
        window = EditorWindow()
        def cleanup():
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        window._load_document_into_scene(document)
        if organogram:
            window.switch_model_page('organogram')
        self.app.processEvents()
        return window

    def assert_artwork(self, window):
        # A proteção durante o carregamento não pode apenas adiar a perda dos itens.
        gc.collect()
        self.app.processEvents()
        texts = {item.layer_id: item for item in window.scene.items() if isinstance(item, DesignerBox)}
        self.assertEqual(set(texts), {51, 52, 53, 54})
        for identity, item in texts.items():
            self.assertEqual(item.text_item.toPlainText(), f'Texto {identity}')
        layers = {getattr(window.layer_list.item(i).data(Qt.ItemDataRole.UserRole), 'layer_id', None)
                  for i in range(window.layer_list.count())}
        self.assertTrue({51, 52, 53, 54, 60, 61, 62} <= layers)
        shape = next(item for item in window.scene.items()
                     if isinstance(item, RectangleItem) and item.layer_id == 60)
        self.assertEqual([item.layer_id for item in shape.masked_images()], [61, 62])
        for image in shape.masked_images():
            self.assertIsInstance(image, ImageItem)
            self.assertIs(image.parentItem(), shape)
        state = window.get_current_scene_state()
        self.assertEqual({item['layer_id'] for item in state['boxes']}, {51, 52, 53, 54})
        self.assertEqual({item['layer_id'] for item in state['images']}, {61, 62})
        return texts

    def test_loading_masked_organogram_keeps_every_text_and_image(self):
        window = self.editor(self.document())
        self.assert_artwork(window)

    def test_loading_masked_normal_page_keeps_every_text_and_image(self):
        window = self.editor(self.document(organogram=False), organogram=False)
        self.assert_artwork(window)

    def test_switch_history_save_and_reopen_do_not_drop_masked_board_artwork(self):
        window = self.editor(self.document())
        self.assert_artwork(window)
        window.switch_model_page('front')
        window.switch_model_page('organogram')
        texts = self.assert_artwork(window)
        texts[51].setPos(100, 100)
        window.save_snapshot()
        window.undo()
        self.assert_artwork(window)
        window.redo()
        self.assert_artwork(window)
        target = self.root / 'masked.fornax'
        save_public_fornax(persistent_model_document(window._document_with_active_page()), target)
        opened = open_public_fornax(target)
        saved = opened.document()
        self.assertEqual({entry['layer_id'] for entry in saved['organogram']['boxes']}, {51, 52, 53, 54})
        window.load_from_fornax(
            saved, path=target, mode=opened.descriptor.mode,
            model_id=opened.descriptor.model_id, asset_provider=opened.asset,
            session_manager=None,
        )
        window.switch_model_page('organogram')
        self.assert_artwork(window)


if __name__ == '__main__':
    unittest.main()
