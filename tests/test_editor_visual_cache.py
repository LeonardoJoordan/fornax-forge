"""Reutilização visual mantém pixels, renova assets e limita memória da sessão."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QPushButton

from core.model_document import adapt_model_page
from features.editor import canvas_items
from features.editor.editor_window import EditorWindow
from features.editor.visual_cache import EditorVisualCache
from features.generator.renderer import NativeRenderer
from test_organogram import board_document


def image_bytes(color):
    image = QImage(20, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    output = QByteArray()
    buffer = QBuffer(output)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'BMP')
    return bytes(output)


class EditorVisualCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))
        self.cache = EditorVisualCache()

    def test_asset_proxy_is_decoded_once_and_detached_from_callers(self):
        payload = image_bytes('red')
        with patch.object(canvas_items, '_load_proxy_pixmap_bytes',
                          wraps=canvas_items._load_proxy_pixmap_bytes) as decode:
            first = self.cache.proxy(data=payload)
            first[0].fill(QColor('blue'))
            second = self.cache.proxy(data=payload)
            self.assertEqual(decode.call_count, 1)
        self.assertEqual(second[0].toImage().pixelColor(0, 0), QColor('red'))
        self.assertEqual(first[1:], second[1:])

    def test_file_proxy_detects_replacement_even_with_same_size_and_timestamp(self):
        path = self.root / 'photo.bmp'
        red, blue = image_bytes('red'), image_bytes('blue')
        self.assertEqual(len(red), len(blue))
        path.write_bytes(red)
        stamp = path.stat()
        with patch.object(canvas_items, '_load_proxy_pixmap',
                          wraps=canvas_items._load_proxy_pixmap) as decode:
            self.cache.proxy(path)
            self.cache.proxy(path)
            self.assertEqual(decode.call_count, 1)
            path.write_bytes(blue)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            replaced = self.cache.proxy(path)
            self.assertEqual(decode.call_count, 2)
        self.assertEqual(replaced[0].toImage().pixelColor(0, 0), QColor('blue'))

    def test_proxy_preserves_original_scaling_and_pixels(self):
        path = self.root / 'large.png'
        image = QImage(4096, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor('green'))
        self.assertTrue(image.save(str(path)))
        expected = canvas_items._load_proxy_pixmap(str(path))
        actual = self.cache.proxy(path)
        self.assertEqual(actual[0].toImage(), expected[0].toImage())
        self.assertEqual(actual[1:], expected[1:])

    def test_proxy_memory_is_bounded_and_least_recently_used_image_is_evicted(self):
        cache = EditorVisualCache(proxy_bytes=2 * 20 * 20 * 4)
        with patch.object(canvas_items, '_load_proxy_pixmap_bytes',
                          wraps=canvas_items._load_proxy_pixmap_bytes) as decode:
            for color in ('red', 'blue', 'red', 'green', 'red'):
                cache.proxy(data=image_bytes(color))
            self.assertEqual(decode.call_count, 3)
            cache.proxy(data=image_bytes('blue'))
            self.assertEqual(decode.call_count, 4)
        self.assertLessEqual(cache.proxies.retained_bytes, cache.proxies.limit)
        self.assertEqual(len(cache.proxies.entries), 2)

    def test_preview_uses_content_and_template_and_detaches_cached_pixels(self):
        template = {'images': [{'path': 'asset:photo'}], 'boxes': [{'html': '{Nome}'}]}
        assets = {'asset:photo': image_bytes('red')}
        calls = []
        def render(provider):
            calls.append(1)
            return QImage.fromData(provider('asset:photo'))
        first = self.cache.card_preview(template, assets.__getitem__, render)
        first.fill(QColor('black'))
        second = self.cache.card_preview(deepcopy(template), assets.__getitem__, render)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.pixelColor(0, 0), QColor('red'))
        assets['asset:photo'] = image_bytes('blue')
        changed = self.cache.card_preview(template, assets.__getitem__, render)
        self.assertEqual(changed.pixelColor(0, 0), QColor('blue'))
        template['boxes'][0]['html'] = '<b>{Nome}</b>'
        self.cache.card_preview(template, assets.__getitem__, render)
        self.assertEqual(len(calls), 3)

    def test_unavailable_asset_does_not_reuse_its_authorized_preview(self):
        template = {'images': [{'path': 'asset:photo'}]}
        def render(provider):
            try:
                return QImage.fromData(provider('asset:photo'))
            except FileNotFoundError:
                image = QImage(20, 20, QImage.Format.Format_ARGB32)
                image.fill(QColor('white'))
                return image
        self.cache.card_preview(template, lambda ref: image_bytes('red'), render)
        def unavailable(ref):
            raise PermissionError('Sessão encerrada')
        result = self.cache.card_preview(template, unavailable, render)
        self.assertEqual(result.pixelColor(0, 0), QColor('white'))

    def test_preview_larger_than_memory_limit_is_not_retained(self):
        cache = EditorVisualCache(preview_bytes=1)
        cache.card_preview({}, None, lambda provider: QImage.fromData(image_bytes('red')))
        self.assertEqual(cache.previews.retained_bytes, 0)
        self.assertFalse(cache.previews.entries)

    def editor(self):
        path = self.root / 'photo.bmp'
        path.write_bytes(image_bytes('red'))
        document = board_document(1, 1)
        front = document['pages'][0]
        front['images'] = [{'path': str(path), 'x': 0, 'y': 0, 'width': 100, 'height': 100,
                            'layer_id': 4, 'object_id': 'image:4'}]
        front['layer_order'].append('image:4')
        document['organogram']['images'] = deepcopy(front['images'])
        document['organogram']['layer_order'] = ['image:4']
        window = EditorWindow()
        def cleanup():
            window._finish_page_interaction()
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        window._load_document_into_scene(document)
        window.switch_model_page('organogram')
        return window, path

    def test_history_reuses_images_and_preview_and_notifies_complete_selection_once(self):
        window, _ = self.editor()
        group = window._board_items()[0]
        group.setSelected(True)
        window.change_board_border(cards=True, width_mm=1.2)
        final_selection = []
        def record_selection():
            final_selection.append(
                [item.data['id'] for item in window.scene.selectedItems()
                 if hasattr(item, 'data') and isinstance(item.data, dict)])
        window.scene.selectionChanged.connect(record_selection)
        self.addCleanup(lambda: window.scene.selectionChanged.disconnect(record_selection))
        buttons = window.findChildren(QPushButton, 'pageMain')
        expected_pixels = QImage(window._board_card_preview)
        with patch.object(canvas_items, '_load_proxy_pixmap',
                          wraps=canvas_items._load_proxy_pixmap) as decode, \
             patch.object(NativeRenderer, 'render_preview_image', autospec=True,
                          side_effect=NativeRenderer.render_preview_image) as render:
            window.undo()
            window.redo()
            # O fundo vazio transparente continua sendo criado a cada cena.
            self.assertFalse([call for call in decode.call_args_list if call.args[0]])
            self.assertEqual(render.call_count, 0)
        self.assertEqual(final_selection, [[group.data['id']], [group.data['id']]])
        self.assertEqual(window.findChildren(QPushButton, 'pageMain'), buttons)
        self.assertEqual(window._board_card_preview, expected_pixels)
        template = adapt_model_page(window._model_document, 'front')
        fresh = NativeRenderer(template, asset_provider=window._editor_asset_provider).render_preview_image(max_side=640)
        self.assertEqual(window._board_card_preview, fresh)

    def test_history_refreshes_changed_image_and_matches_uncached_rendering(self):
        window, path = self.editor()
        old = QImage(window._board_card_preview)
        window._board_items()[0].setSelected(True)
        window.change_board_border(cards=True)
        path.write_bytes(image_bytes('blue'))
        window.undo()
        self.assertNotEqual(window._board_card_preview, old)
        template = adapt_model_page(window._model_document, 'front')
        fresh = NativeRenderer(template, asset_provider=window._editor_asset_provider).render_preview_image(max_side=640)
        self.assertEqual(window._board_card_preview, fresh)

    def test_card_edit_renews_board_preview(self):
        window, _ = self.editor()
        old = QImage(window._board_card_preview)
        window.switch_model_page('front')
        box = next(item for item in window.scene.items() if isinstance(item, canvas_items.DesignerBox))
        box.state.html_content = '<p>Conteúdo novo</p>'
        box.apply_state()
        window.save_snapshot()
        window.switch_model_page('organogram')
        self.assertNotEqual(window._board_card_preview, old)
        template = adapt_model_page(window._model_document, 'front')
        fresh = NativeRenderer(template, asset_provider=window._editor_asset_provider).render_preview_image(max_side=640)
        self.assertEqual(window._board_card_preview, fresh)

    def test_explicit_invalidation_and_document_change_and_close_release_visual_cache(self):
        window, _ = self.editor()
        self.assertTrue(window._visual_cache.proxies.entries)
        self.assertTrue(window._visual_cache.previews.entries)
        window._clear_visual_cache()
        self.assertFalse(window._visual_cache.proxies.entries)
        self.assertFalse(window._visual_cache.previews.entries)
        window._visual_cache.proxy(data=image_bytes('red'))
        window._load_document_into_scene(board_document(1, 1))
        self.assertFalse(window._visual_cache.proxies.entries)
        window.switch_model_page('organogram')
        self.assertTrue(window._visual_cache.previews.entries)
        window._last_saved_state = window.get_current_scene_state()
        window._last_saved_document_state = window._capture_document_history_state()
        window.close()
        self.assertFalse(window._visual_cache.previews.entries)

    def test_page_buttons_follow_page_addition_and_history(self):
        window, _ = self.editor()
        from test_organogram import card_document
        window._load_document_into_scene(card_document())
        self.assertEqual(len(window.findChildren(QPushButton, 'pageMain')), 1)
        window.add_model_page()
        self.assertEqual(window._active_page_id, 'back')
        self.assertEqual(len(window.findChildren(QPushButton, 'pageMain')), 2)
        window.undo()
        self.assertEqual(window._active_page_id, 'front')
        self.assertEqual(len(window.findChildren(QPushButton, 'pageMain')), 1)
        window.redo()
        self.assertEqual(window._active_page_id, 'back')
        self.assertEqual(len(window.findChildren(QPushButton, 'pageMain')), 2)

    def test_failed_restoration_reenables_view_and_scene_notifications(self):
        window, _ = self.editor()
        state = window._capture_document_history_state()
        with patch.object(window, 'apply_scene_state', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                window._restore_history_state(state)
        self.assertTrue(window.view.updatesEnabled())
        self.assertFalse(window.scene.signalsBlocked())
        self.assertFalse(window._restoring_history)


if __name__ == '__main__':
    unittest.main()
