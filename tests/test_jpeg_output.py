"""JPEG a 95%: qualidade, medidas, nomes e publicação segura em todos os fluxos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.fornax_container import PUBLIC_MODE, open_public_fornax
from core.model_document import add_blank_back_page
from core.tiling import build_tile_plan
from features.generator.image_output import JPEG_QUALITY, export_choices, save_image
from features.generator.renderer import NativeRenderer
from features.generator.manager import RenderManager, _bounded_worker_count
from features.generator.workers import DirectRenderWorker, PageRenderWorker
from features.generator.organogram import OrganogramRenderer, OrganogramWorker
from features.generator.tiled_document import PageTilingRenderer, TiledDocumentWorker
from test_organogram import card_document, board_document
import test_signature_preview as workspace_fixtures


class JpegOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))
        self.renderer = NativeRenderer({'canvas_size': {'w': 120, 'h': 160}})
        self.task = (0, 0, 1, {}, {}, 'Ana')

    def directory(self, name):
        path = self.root / name
        path.mkdir()
        return path

    def run_worker(self, worker):
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])

    def assert_jpeg(self, path, width, height, dpi=300):
        self.assertEqual(path.suffix, '.jpg')
        self.assertEqual(path.read_bytes()[:2], b'\xff\xd8')
        image = QImage(str(path))
        self.assertFalse(image.isNull())
        self.assertEqual((image.width(), image.height()), (width, height))
        self.assertFalse(image.hasAlphaChannel())
        self.assertAlmostEqual(image.dotsPerMeterX() * .0254, dpi, delta=.6)
        self.assertAlmostEqual(image.dotsPerMeterY() * .0254, dpi, delta=.6)
        return image

    def test_quality_matches_explicit_95_encoding(self):
        image = QImage(160, 120, QImage.Format.Format_RGB32)
        for x in range(image.width()):
            for y in range(image.height()):
                image.setPixelColor(x, y, QColor((x * 13 + y * 7) % 256, (x * 3) % 256, (y * 9) % 256))
        for fmt in JPEG_QUALITY:
            with self.subTest(fmt=fmt):
                path, expected = self.root / f'{fmt}.jpg', self.root / f'{fmt}-reference.jpg'
                self.assertTrue(save_image(image, path, fmt))
                self.assertTrue(image.save(str(expected), 'JPEG', 95))
                self.assertEqual(path.read_bytes(), expected.read_bytes())

    def test_jpeg_composes_alpha_over_white_and_png_preserves_alpha(self):
        image = QImage(120, 160, QImage.Format.Format_ARGB32)
        image.fill(QColor(255, 0, 0, 128))
        image.setDotsPerMeterX(round(300 / .0254))
        image.setDotsPerMeterY(round(300 / .0254))
        for fmt in JPEG_QUALITY:
            path = self.root / f'{fmt}.jpg'
            self.assertTrue(save_image(image, path, fmt))
            result = self.assert_jpeg(path, 120, 160)
            color = result.pixelColor(60, 80)
            self.assertAlmostEqual(color.red(), 255, delta=3)
            self.assertAlmostEqual(color.green(), 127, delta=3)
            self.assertAlmostEqual(color.blue(), 127, delta=3)
        path = self.root / 'alpha.png'
        self.assertTrue(save_image(image, path, 'PNG'))
        self.assertEqual(QImage(str(path)), image)

    def test_cards_preserve_pixels_dimensions_and_physical_density(self):
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            self.run_worker(DirectRenderWorker([self.task], [self.renderer], directory, fmt,
                target_w_mm=120 * 25.4 / 300, target_h_mm=160 * 25.4 / 300))
            self.assertEqual([p.name for p in directory.iterdir()], ['Ana.jpg'])
            self.assert_jpeg(directory / 'Ana.jpg', 120, 160)

    def test_duplex_cards_keep_individual_face_names_in_protected_output(self):
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            self.run_worker(DirectRenderWorker([self.task], [self.renderer, self.renderer], directory, fmt,
                secure_output=True, target_w_mm=120 * 25.4 / 300, target_h_mm=160 * 25.4 / 300))
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ['Ana_pag1.jpg', 'Ana_pag2.jpg'])
            for path in directory.iterdir():
                self.assert_jpeg(path, 120, 160)

    def test_imposition_duplex_keeps_physical_sheet_dimensions_and_faces(self):
        settings = dict(target_w_mm=10, target_h_mm=14, sheet_w_mm=20, sheet_h_mm=28,
                        auto_rotate=False, duplex=True, crop_marks=False, bleed_margin=False)
        task = dict(page_num=1, output_base='Folha_01', front=[self.task] * 4, back=[self.task] * 4)
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            worker = PageRenderWorker([task], [self.renderer, self.renderer], directory, settings, fmt)
            self.run_worker(worker)
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ['Folha_01_frente.jpg', 'Folha_01_verso.jpg'])
            for path in directory.iterdir():
                self.assert_jpeg(path, worker.assembler.sheet_w, worker.assembler.sheet_h)

    def test_manager_keeps_copies_and_generates_jpeg_without_pdf_intermediates(self):
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            # The workspace expands copies before handing records to the manager.
            rows = [{'nome': 'Ana'}, {'nome': 'Ana'}, {'nome': 'Bruno'}]
            manager = RenderManager(self.renderer, rows, rows, directory, '{nome}', export_format=fmt, source_rows=[0, 0, 1],
                target_w_mm=120 * 25.4 / 300, target_h_mm=160 * 25.4 / 300)
            errors, finished = [], []
            manager.error_occurred.connect(errors.append)
            manager.finished_process.connect(lambda: finished.append(True))
            manager.start()
            for _ in range(500):
                if finished:
                    break
                QTest.qWait(10)
            for worker in manager.workers:
                worker.wait()
            self.assertTrue(finished)
            self.assertEqual(errors, [])
            self.assertFalse(manager.is_hybrid)
            self.assertIsNone(manager._hybrid_temporary)
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ['Ana.jpg', 'Ana_01.jpg', 'Bruno.jpg'])

    def test_whole_organogram_exports_jpeg(self):
        document, rows = board_document(1, 1), [{'Nome': 'Ana'}]
        renderer = OrganogramRenderer(document, rows)
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            worker = OrganogramWorker(document, rows, rows, directory, fmt.lower(), dpi=300)
            self.run_worker(worker)
            self.assertEqual([p.name for p in directory.iterdir()], ['organograma.jpg'])
            self.assert_jpeg(directory / 'organograma.jpg', math.ceil(renderer.bounds.width()), math.ceil(renderer.bounds.height()))

    def test_tiled_organogram_exports_separate_labeled_jpegs_and_crop_marks(self):
        document, rows = board_document(1, 1), [{'Nome': 'Ana'}]
        renderer = OrganogramRenderer(document, rows)
        options = dict(paper=(40, 50), margin_mm=5, crop_marks=True, overlap_mm=0)
        plan = build_tile_plan(renderer.bounds, **options)
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            self.run_worker(OrganogramWorker(document, rows, rows, directory, fmt.lower(), dpi=300, tiling_options=options))
            self.assertEqual(sorted(p.name for p in directory.iterdir()), sorted(f'organograma_{tile.name}.jpg' for tile in plan.tiles))
            for path in directory.iterdir():
                self.assert_jpeg(path, math.ceil(40 * 300 / 25.4), math.ceil(50 * 300 / 25.4))
            expected = self.root / f'{fmt}-expected.jpg'
            renderer.export_tile_image(expected, plan, plan.tiles[0], dpi=300, export_format=fmt)
            self.assertEqual((directory / f'organograma_{plan.tiles[0].name}.jpg').read_bytes(), expected.read_bytes())

    def test_tiled_front_and_back_cards_preserve_record_face_and_tile_names(self):
        document = add_blank_back_page(card_document())
        rows = [{'Nome': 'Ana'}, {'Nome': 'Ana'}]
        options = dict(paper=(100, 100), margin_mm=5, crop_marks=True, overlap_mm=0)
        for fmt in JPEG_QUALITY:
            directory = self.directory(fmt)
            self.run_worker(TiledDocumentWorker(document, rows, rows, directory, fmt.lower(),
                dpi=300, options=options, pattern='{Nome}'))
            self.assertEqual(sorted(p.name for p in directory.iterdir()),
                ['Ana_01_pag1_A1.jpg', 'Ana_01_pag2_A1.jpg', 'Ana_pag1_A1.jpg', 'Ana_pag2_A1.jpg'])
            for path in directory.iterdir():
                self.assert_jpeg(path, math.ceil(100 * 300 / 25.4), math.ceil(100 * 300 / 25.4))

    def test_failed_second_face_leaves_no_partial_or_published_card(self):
        original = save_image
        for secure in (False, True):
            directory = self.directory(str(secure))
            worker = DirectRenderWorker([self.task], [self.renderer, self.renderer], directory,
                                        'JPEG', secure_output=secure)
            errors, calls = [], []
            worker.error_occurred.connect(errors.append)
            def failing(image, path, fmt):
                calls.append(path)
                if len(calls) == 2:
                    Path(path).write_bytes(b'incomplete')
                    return False
                return original(image, path, fmt)
            with patch('features.generator.renderer.save_image', side_effect=failing):
                worker.run()
            self.assertEqual(len(errors), 1)
            self.assertEqual(list(directory.iterdir()), [])

    def test_failed_sheet_write_removes_partial_jpeg(self):
        directory = self.directory('failed-sheet')
        settings = dict(target_w_mm=10, target_h_mm=14, sheet_w_mm=20, sheet_h_mm=28,
                        auto_rotate=False, crop_marks=False, bleed_margin=False)
        task = dict(page_num=1, output_base='Folha_01', front=[self.task] * 4)
        worker = PageRenderWorker([task], [self.renderer], directory, settings, 'JPEG')
        errors = []
        worker.error_occurred.connect(errors.append)
        def failed_save(image, path, fmt):
            Path(path).write_bytes(b'incomplete')
            return False
        with patch('features.generator.workers.save_image', side_effect=failed_save):
            worker.run()
        self.assertEqual(len(errors), 1)
        self.assertEqual(list(directory.iterdir()), [])

    def test_worker_memory_budget_includes_white_composition_buffer(self):
        from types import SimpleNamespace
        renderer = SimpleNamespace(tpl={'canvas_size': {'w': 1000, 'h': 1000}})
        with patch('features.generator.manager.RENDER_MEMORY_BUDGET', 20_000_000):
            self.assertEqual(_bounded_worker_count(20, [renderer]), 4)
            self.assertEqual(_bounded_worker_count(20, [renderer], jpeg=True), 2)
            sheet = SimpleNamespace(sheet_w=1000, sheet_h=1000)
            self.assertEqual(_bounded_worker_count(20, [renderer], sheet=sheet), 2)
            self.assertEqual(_bounded_worker_count(20, [renderer], sheet=sheet, jpeg=True), 1)

    def test_cancelled_cards_and_tiles_do_not_publish_files(self):
        rows, document = [{'Nome': 'Ana'}], board_document(1, 1)
        directory = self.directory('cancelled')
        direct = DirectRenderWorker([self.task], [self.renderer], directory, 'JPEG')
        direct.stop()
        direct.run()
        self.assertEqual(list(directory.iterdir()), [])
        workers = [
            OrganogramWorker(document, rows, rows, directory, 'jpeg', tiling_options=dict(paper=(40, 50))),
            TiledDocumentWorker(card_document(), rows, rows, directory, 'jpeg', options=dict(paper=(40, 50))),
        ]
        for worker in workers:
            # QThread ignores requestInterruption before it starts; simulate the
            # cancellation flag that is available during its actual execution.
            with patch.object(worker, 'isInterruptionRequested', return_value=True):
                worker.run()
            self.assertEqual(list(directory.iterdir()), [])

    def test_failed_tile_write_cleans_staging_and_preserves_existing_files(self):
        rows = [{'Nome': 'Ana'}]
        for board in (False, True):
            directory = self.directory(str(board))
            sentinel = directory / 'existing.jpg'
            sentinel.write_bytes(b'keep')
            worker = (OrganogramWorker(board_document(1, 1), rows, rows, directory, 'jpeg',
                tiling_options=dict(paper=(40, 50))) if board else
                TiledDocumentWorker(card_document(), rows, rows, directory, 'jpeg', options=dict(paper=(40, 50))))
            errors = []
            worker.error_occurred.connect(errors.append)
            def failed_save(image, path, fmt):
                Path(path).write_bytes(b'incomplete')
                return False
            with patch('features.generator.organogram.save_image', side_effect=failed_save):
                worker.run()
            self.assertEqual(len(errors), 1)
            self.assertEqual([p.name for p in directory.iterdir()], ['existing.jpg'])
            self.assertEqual(sentinel.read_bytes(), b'keep')


class JpegWorkspaceTest(unittest.TestCase):
    setUpClass = classmethod(workspace_fixtures.SignaturePreviewTest.setUpClass.__func__)
    setUp = workspace_fixtures.SignaturePreviewTest.setUp
    make_workspace = workspace_fixtures.SignaturePreviewTest.make_workspace
    dispose_workspace = workspace_fixtures.SignaturePreviewTest.dispose_workspace

    def test_jpeg_choices_are_remembered_after_document_reload(self):
        window = self.make_workspace(PUBLIC_MODE)
        window.cbo_export_format.clear()
        for label, mode, tooltip in export_choices():
            window.cbo_export_format.addItem(label, mode)
            window._export_mode_tooltips[mode] = tooltip
        for fmt in JPEG_QUALITY:
            mode = fmt.lower()
            window.cbo_export_format.setCurrentIndex(window.cbo_export_format.findData(mode))
            self.assertEqual(window._current_export_mode(), (mode, fmt, False))
            window._on_export_mode_changed(0)
            document = open_public_fornax(window._active_library_model.path).document()
            self.assertEqual(document['last_export_mode'], mode)
            window.cbo_export_format.setCurrentIndex(0)
            window._load_fornax_document(document, window._fornax_asset_provider, window._active_fornax_status)
            self.assertEqual(window.cbo_export_format.currentData(), mode)
            self.assertEqual(window.cbo_export_format.currentText(), 'JPEG')

    def test_format_list_has_only_four_options_in_requested_order(self):
        choices = export_choices()
        self.assertEqual([choice[0] for choice in choices], ['PNG', 'JPEG', 'PDF', 'PDF Agrupado'])
        self.assertEqual([choice[1] for choice in choices], ['png', 'jpeg', 'pdf_item', 'pdf_grouped'])
        self.assertEqual(choices[1][2], '')

    def test_old_jpeg_preferences_reload_as_single_jpeg(self):
        window = self.make_workspace(PUBLIC_MODE)
        window.cbo_export_format.clear()
        for label, mode, tooltip in export_choices():
            window.cbo_export_format.addItem(label, mode)
        for old_mode in ('jpeg_fine', 'jpeg_fast'):
            document = deepcopy(window.cached_model_document)
            document['last_export_mode'] = old_mode
            document['last_export_format'] = old_mode.upper()
            window._load_fornax_document(document, window._fornax_asset_provider, window._active_fornax_status)
            self.assertEqual(window._current_export_mode(), ('jpeg', 'JPEG', False))

    def test_workspace_routes_organograms_to_jpeg_instead_of_pdf(self):
        window = self.make_workspace(PUBLIC_MODE)
        document, rows = board_document(1, 1), [{'Nome': 'Ana'}]
        window.cbo_export_format.clear()
        for label, mode, tooltip in export_choices():
            window.cbo_export_format.addItem(label, mode)
        for fmt in JPEG_QUALITY:
            window.cbo_export_format.setCurrentIndex(window.cbo_export_format.findData(fmt.lower()))
            output = self.root / fmt
            output.mkdir()
            with patch('features.workspace.main_window.create_forge_output_dir', return_value=(output, 1)), patch.object(
                window, '_start_tiled_generation') as start:
                window._generate_organogram(document, rows, rows, self.root, None, None)
            start.assert_called_once()
            worker = start.call_args.args[0]
            self.assertEqual(worker.mode, fmt.lower())
            errors = []
            worker.error_occurred.connect(errors.append)
            worker.run()
            self.assertEqual(errors, [])
            self.assertEqual([path.name for path in output.iterdir()], ['organograma.jpg'])


if __name__ == '__main__':
    unittest.main()
