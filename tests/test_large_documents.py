"""A1/A2 preservam resolução, com buffers e dimensões limitados."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from core.model_document import validate_raster_dimensions, ModelValidationError
from features.editor.canvas_items import mm_to_px
from features.generator.renderer import NativeRenderer
from features.generator.manager import _bounded_worker_count, RenderManager
from features.generator.workers import SecureGroupedPdfWorker


class LargeDocumentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def renderer(self, mm=(594, 841)):
        return NativeRenderer({'canvas_size': dict(zip(('w', 'h'), map(lambda x: int(mm_to_px(x)), mm))),
                               'boxes': [], 'shapes': []})

    def test_a1_and_a2_keep_native_300_dpi_dimensions(self):
        for mm in ((594, 841), (420, 594)):
            r = self.renderer(mm)
            self.assertEqual(validate_raster_dimensions(*r.tpl['canvas_size'].values()),
                             tuple(int(mm_to_px(x)) for x in mm))

    def test_abusive_dimensions_still_rejected(self):
        for size in ((9000, 9000), (17000, 1), (0, 1), (float('inf'), 1), (3.5, 1)):
            with self.subTest(size=size), self.assertRaises(ModelValidationError):
                validate_raster_dimensions(*size)

    def test_large_static_base_is_skipped_without_allocation(self):
        r = self.renderer()
        with patch('features.generator.renderer.QImage', side_effect=AssertionError('Full cache allocated')):
            r.pre_render_static_base()
        self.assertIsNone(r._static_base_cache)
        self.assertIsNone(r.fork()._static_base_cache)

    def test_preview_is_bounded_even_for_a1(self):
        r = self.renderer()
        preview = r.render_preview_image(max_side=1600)
        self.assertEqual(max(preview.width(), preview.height()), 1600)
        self.assertLess(preview.sizeInBytes(), 11_000_000)

    def test_large_generation_limits_parallel_buffers(self):
        self.assertEqual(_bounded_worker_count(24, [self.renderer()]), 1)
        self.assertEqual(_bounded_worker_count(24, [self.renderer()], jpeg=True), 1)
        self.assertEqual(_bounded_worker_count(24, [self.renderer((420, 594))]), 2)
        # Frente e verso são pintados sequencialmente; nenhuma base A1 fica retida.
        self.assertEqual(_bounded_worker_count(24, [self.renderer(), self.renderer()]), 1)

    def test_large_card_batches_rejected_before_allocating_unbounded_buffers(self):
        sheet = SimpleNamespace(sheet_w=9933, sheet_h=7015)
        with self.assertRaises(MemoryError):
            _bounded_worker_count(24, [self.renderer()], sheet=sheet, capacity=3)

    def test_large_public_grouped_pdf_uses_sequential_raster_without_png_cache(self):
        with TemporaryDirectory() as root:
            for imposed in (False, True):
                renderer = self.renderer((20, 30)) if imposed else self.renderer()
                settings = {'enabled': imposed, 'sheet_w_mm': 594, 'sheet_h_mm': 841,
                            'target_w_mm': 100, 'target_h_mm': 150}
                manager = RenderManager([renderer], [{}], [{}], Path(root), 'teste', settings,
                                        'PDF', True, target_w_mm=594, target_h_mm=841)
                with patch('features.generator.manager.SecureGroupedPdfWorker.start'):
                    manager._start()
                self.assertFalse(manager.is_hybrid)
                self.assertIsNone(manager._hybrid_temporary)
                self.assertEqual(len(manager.workers), 1)
                self.assertIsInstance(manager.workers[0], SecureGroupedPdfWorker)
                manager._is_running = False

    def test_null_raster_allocation_raises_instead_of_exporting_blank_image(self):
        class NullImage(QImage):
            def __init__(self, *args):
                super().__init__()
        r = self.renderer((20, 30))
        with patch('features.generator.renderer.QImage', NullImage):
            for action in (r.pre_render_static_base, r.render_preview_image,
                           lambda: r.render_to_qimage({}, {})):
                with self.assertRaises(MemoryError):
                    action()
                r._static_base_cache = None

    def test_skipping_static_cache_does_not_change_pixels(self):
        data = {'canvas_size': {'w': 500, 'h': 400}, 'shapes': [],
                'boxes': [{'x': 20, 'y': 30, 'w': 450, 'h': 130,
                           'html': '<p>Instituição <b>{nome}</b></p>', 'font_family': 'Inter', 'font_size': 18}],
                'placeholders': ['nome']}
        r = NativeRenderer(data)
        r.pre_render_static_base()
        expected = r.render_to_qimage({'nome': 'Ana'}, {'nome': 'Ana'})
        with patch('features.generator.renderer.MAX_STATIC_BASE_PIXELS', 1):
            r.pre_render_static_base()
        self.assertEqual(r.render_to_qimage({'nome': 'Ana'}, {'nome': 'Ana'}), expected)
