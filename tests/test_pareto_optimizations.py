"""Economias locais conservam geometria, isolamento de pixels e pacotes protegidos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


class ParetoOptimizationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_shapes_share_pixels_but_keep_independent_geometry_and_content(self):
        from features.editor.canvas_items import RectangleItem, ImageItem
        items = [RectangleItem(100 + i, 50 + i) for i in range(40)]
        self.assertEqual(len({i.pixmap().cacheKey() for i in items}), 1)
        before = items[1].pixmap().toImage()
        changed = items[0].pixmap()
        changed.fill(QColor('red'))
        items[0].setPixmap(changed)
        self.assertEqual(items[1].pixmap().toImage(), before)
        self.assertEqual(items[1].pixmap().toImage().pixelColor(0, 0).alpha(), 0)
        items[0].resize_custom(800, 400)
        self.assertEqual(items[1].rect().width(), 101)
        self.assertEqual(ImageItem()._logical_w, 1000)
        self.assertEqual(RectangleItem(50, 60).pixmap().toImage(), before)

    def test_obstacle_memo_preserves_hits_exclusions_and_reversed_segments(self):
        from core.board_routing import _Rectangles
        rects = {'a': (0., 0., 10., 10.), 'b': (15., -5., 25., 15.)}
        obstacles = _Rectangles(rects)
        rng = random.Random(2048)
        with patch.object(obstacles, '_count_hits', wraps=obstacles._count_hits) as count:
            for _ in range(300):
                a = (float(rng.randrange(-10, 30)), float(rng.randrange(-10, 30)))
                b = (a[0], a[1] + 20) if rng.randrange(2) else (a[0] + 20, a[1])
                excluded = ('a',) if rng.randrange(2) else ()
                expected = obstacles._count_hits(a, b, excluded)
                self.assertEqual(obstacles.hits(a, b, excluded), expected)
                calls = count.call_count
                self.assertEqual(obstacles.hits(b, a, excluded), expected)
                self.assertEqual(count.call_count, calls)
        self.assertNotEqual(obstacles.hits((-1, 5), (12, 5)),
                            obstacles.hits((-1, 5), (12, 5), ('a',)))

    def test_obstacle_memo_is_bounded_and_does_not_survive_geometry_changes(self):
        from core.board_routing import _Rectangles
        with patch.object(_Rectangles, 'CACHE_LIMIT', 8):
            obstacles = _Rectangles({'a': (0, 0, 10, 10)})
            for x in range(30): obstacles.hits((x, -1), (x, 11))
            self.assertLessEqual(len(obstacles._hit_cache), 8)
            self.assertEqual(obstacles.hits((5, -1), (5, 11)), 1)
        moved = _Rectangles({'a': (100, 100, 110, 110)})
        self.assertEqual(moved.hits((5, -1), (5, 11)), 0)

    def test_blocked_segments_do_not_evaluate_crossing_penalty(self):
        from core.board_routing import _Rectangles, _Channels, _search
        obstacles = _Rectangles({'wall': (-100, -100, 100, 100)})
        channels = _Channels(1)
        with patch.object(channels, 'crossings', side_effect=AssertionError('Trecho bloqueado')):
            self.assertIsNone(_search((0, 0), (10, 10), obstacles, channels, 'parent', 1, []))

    def test_fast_zip_preserves_image_bytes_and_compresses_metadata(self):
        from core.fornax_container import _inner_zip
        entries = {'assets/photo.png': b'x' * 300_000,
                   'assets/small.png': b'x' * 50,
                   'assets/vector.svg': b'<svg/>' * 50_000,
                   'document.json': b'{}'}
        for fast in (False, True):
            with zipfile.ZipFile(BytesIO(_inner_zip(entries, store_images=fast))) as archive:
                self.assertEqual({name: archive.read(name) for name in entries}, entries)
                self.assertEqual(archive.getinfo('assets/photo.png').compress_type,
                                 zipfile.ZIP_STORED if fast else zipfile.ZIP_DEFLATED)
                for name in ('assets/small.png', 'assets/vector.svg', 'document.json'):
                    self.assertEqual(archive.getinfo(name).compress_type, zipfile.ZIP_DEFLATED)

    def test_fast_inner_zip_retries_compression_at_existing_size_limit(self):
        import core.fornax_container as container
        entries = {'document.json': b'{}', 'assets/photo.png': b'x' * 300_000}
        with patch.object(container, 'MAX_INNER_BYTES', 10_000):
            payload = container._inner_zip(entries, store_images=True)
            self.assertLessEqual(len(payload), 10_000)
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                self.assertEqual(archive.read('assets/photo.png'), entries['assets/photo.png'])
        with patch.object(container, 'MAX_INNER_BYTES', 1):
            with self.assertRaises(container.FornaxLimitError):
                container._inner_zip(entries, store_images=True)

    def test_fast_outer_zip_retries_without_relaxing_package_limit(self):
        import core.fornax_container as container
        entries = {'public/document.json': b'{}', 'public/assets/photo.png': b'x' * 300_000}
        with TemporaryDirectory() as root, patch.object(container, 'MAX_PACKAGE_BYTES', 10_000):
            destination = Path(root) / 'recovery.fornax'
            def verify(path):
                self.assertLessEqual(path.stat().st_size, 10_000)
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual({name: archive.read(name) for name in entries}, entries)
            container._publish_package(destination, entries, verify, expected_stamp=None, store_images=True)
            verify(destination)

    def test_recovery_roundtrips_all_modes_with_original_assets_and_unchanged_source(self):
        from editor_scenarios import Scenario, make_document
        from core.fornax_session import FornaxSessionManager
        import core.fornax_container as container
        from core.model_document import iter_page_asset_paths
        document, provider = make_document(Scenario('recovery', 'autosave', 'mixed', 20, large=True))
        with TemporaryDirectory() as root:
            for mode in ('public', 'signatures', 'full'):
                with self.subTest(mode=mode):
                    path = Path(root) / (mode + '.fornax')
                    if mode == 'public':
                        container.save_public_fornax(document, path, asset_provider=provider)
                    else:
                        container.save_protected_fornax(document, path, 'teste-pareto', mode=mode, asset_provider=provider)
                    original = path.read_bytes()
                    manager = FornaxSessionManager()
                    try:
                        manager.select(path)
                        if mode != 'public': manager.unlock(path, 'teste-pareto')
                        source = manager.document()
                        expected = sorted(manager.asset(ref) for ref in
                                          {ref for _, _, ref in iter_page_asset_paths(source)})
                        source['name'] = 'Edição recuperada'
                        authorization = manager.prepare_recovery(path)
                        authorization.check_source()
                        destination = path.with_name('recovery-' + path.name)
                        def commit(action):
                            authorization.check_source()
                            with authorization.publication(): action(authorization.check_publication)
                        try:
                            authorization.write(source, destination, manager.asset, commit)
                        finally:
                            authorization.cancel()
                        opened = manager.read_recovery(destination, path=path)
                        self.assertEqual(opened.document()['name'], 'Edição recuperada')
                        self.assertEqual(sorted(opened.asset(ref) for ref in opened.asset_references), expected)
                        self.assertEqual(opened.descriptor.mode, container.PUBLIC_MODE if mode == 'public' else mode)
                        self.assertEqual(path.read_bytes(), original)
                        if mode == 'full':
                            with zipfile.ZipFile(destination) as archive:
                                self.assertEqual(set(archive.namelist()), {'manifest.json', 'protected.bin'})
                    finally:
                        manager.close()

    def test_signature_recovery_keeps_combined_public_and_protected_budget(self):
        import core.fornax_container as container
        from core.fornax_session import FornaxSessionManager
        from editor_scenarios import Scenario, make_document
        document, provider = make_document(Scenario('limit', 'autosave', 'mixed', 20))
        # PNG válido com bytes finais compressíveis; simula a diferença entre
        # o tamanho original dos assets e o ZIP sem reservar centenas de MiB.
        payload = provider('asset:photo.png') + b'\x00' * 300_000
        with TemporaryDirectory() as root:
            source = Path(root) / 'source.fornax'
            destination = Path(root) / 'recovery.fornax'
            container.save_protected_fornax(document, source, 'teste-pareto',
                                           mode=container.SIGNATURES_MODE, asset_provider=lambda _: payload)
            manager = FornaxSessionManager()
            try:
                manager.unlock(source, 'teste-pareto')
                authorization = manager.prepare_recovery(source)
                authorization.check_source()
                try:
                    with patch.object(container, 'MAX_PACKAGE_BYTES', 500_000):
                        authorization.write(manager.document(), destination, manager.asset,
                                            lambda action: action())
                        opened = manager.read_recovery(destination, path=source)
                        self.assertTrue(opened.asset_references)
                        self.assertTrue(all(opened.asset(ref) == payload for ref in opened.asset_references))
                        self.assertLessEqual(destination.stat().st_size, 500_000)
                finally:
                    authorization.cancel()
            finally:
                manager.close()


if __name__ == '__main__':
    unittest.main()
