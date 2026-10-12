"""Perfis, dimensões físicas e edição grande sem buffers gigantes implícitos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from pypdf import PdfReader

from core.performance import EXPORT_DPI, PIXEL_LIMITS, ExportPerformance, PROFILES, load_performance
from core.model_document import normalize_model_document, ModelValidationError
from features.generator.renderer import NativeRenderer, renderers_for_document
from features.generator.workers import DirectRenderWorker, SecureGroupedPdfWorker
from features.generator.imposition import SheetAssembler
from features.generator.manager import RenderManager, _bounded_worker_count
from features.workspace.settings_dialogs import PerformanceDialog
from features.generator.tiled_document import PageTilingRenderer, TiledDocumentWorker
from features.generator.organogram import OrganogramWorker
from features.preview.sheet_preview_worker import SheetPreviewWorker
from core.tiling import build_tile_plan


def page(mm=(120, 80)):
    return dict(name='Teste', target_w_mm=mm[0], target_h_mm=mm[1],
                canvas_size=dict(w=int(mm[0] * 300 / 25.4), h=int(mm[1] * 300 / 25.4)),
                boxes=[], images=[], shapes=[], signatures=[])


class PerformanceProfilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)

    def test_profiles_persist_custom_and_reject_corrupt_settings(self):
        self.assertEqual(load_performance(self.settings), PROFILES['large'])
        self.assertEqual(ExportPerformance(), PROFILES['large'])
        dialog = PerformanceDialog(self.settings)
        self.assertEqual(dialog.pixels.currentData(), 150)
        dialog.reject()
        self.assertFalse(self.settings.contains('performance/profile'))
        self.settings.setValue('performance/profile', 'invalid')
        self.assertEqual(load_performance(self.settings), PROFILES['large'])
        dialog = PerformanceDialog(self.settings)
        self.assertEqual(dialog.pixels.currentData(), 150)
        dialog.reject()
        self.settings.setValue('performance/profile', 'custom')
        self.settings.setValue('performance/megapixels', 150)
        self.settings.setValue('performance/dpi', 96)
        self.assertEqual(load_performance(self.settings), ExportPerformance(150))
        self.settings.setValue('performance/dpi', 'invalid')
        self.assertEqual(load_performance(self.settings), ExportPerformance(150))
        self.settings.setValue('performance/megapixels', 'invalid')
        self.assertEqual(load_performance(self.settings), PROFILES['large'])
        for mp, dpi in ((20, 300), (151, 300), (True, 300), (80, 72), (80, 96), (80, 150), (80, True)):
            with self.assertRaises(ValueError):
                ExportPerformance(mp, dpi)

    def test_dialog_cancel_does_not_change_settings_and_apply_persists(self):
        dialog = PerformanceDialog(self.settings, normalize_model_document(page((3000, 3000))))
        dialog.pixels.setCurrentIndex(dialog.pixels.findData(300))
        self.assertFalse(hasattr(dialog, 'dpi'))
        self.assertIn('1255', dialog.estimate.text())
        self.assertNotIn('Ladrilhos', dialog.estimate.text())
        self.assertFalse(hasattr(dialog, 'profile'))
        dialog.reject()
        self.assertEqual(load_performance(self.settings), PROFILES['large'])
        buttons = dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        self.assertEqual(load_performance(self.settings), ExportPerformance(300))
        reopened = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        self.assertEqual(load_performance(reopened), ExportPerformance(300))
        self.assertFalse(self.settings.contains('performance/dpi'))

    def test_three_metre_document_opens_under_conservative_profile_and_has_bounded_preview(self):
        document = normalize_model_document(page((3000, 3000)))
        renderer = renderers_for_document(document)[0]
        image = renderer.render_preview_image(max_side=1600)
        self.assertEqual((image.width(), image.height()), (1600, 1600))
        self.assertEqual(image.sizeInBytes(), 1600 * 1600 * 4)
        self.assertEqual(document['target_w_mm'], 3000)
        self.assertIsNone(renderer._static_base_cache)
        with self.assertRaises(ValueError):
            renderer.configure_export(PROFILES['balanced'], 3000, 3000)
        with self.assertRaises(ValueError):
            renderer.configure_export(ExportPerformance(150), 3000, 3000)
        with patch('features.generator.renderer.QImage', side_effect=AssertionError('Giant static base')), self.assertRaises(ValueError):
            renderer.pre_render_static_base()
        self.assertIsNone(renderer._static_base_cache)

    def test_limits_apply_before_allocating_and_do_not_resize_the_document(self):
        renderer = NativeRenderer(page((3000, 3000)))
        for policy in PROFILES.values():
            with patch('features.generator.renderer.QImage', side_effect=AssertionError('Allocated')), self.assertRaises(ValueError):
                renderer.configure_export(policy, 3000, 3000)
        self.assertEqual(renderer.tpl['target_w_mm'], 3000)
        with self.assertRaises(ValueError):
            ExportPerformance(150, 300).validate(33000, 1)
        with self.assertRaises(ModelValidationError):
            normalize_model_document(page((10001, 120)))
        self.assertEqual(normalize_model_document(page((10000, 10000)))['target_w_mm'], 10000)

    def test_profiles_preserve_same_pixels_and_physical_size_for_png_and_jpeg(self):
        original_size = NativeRenderer(page()).output_dimensions()
        for key, policy in PROFILES.items():
            renderer = NativeRenderer(page())
            renderer.configure_export(policy, 120, 80)
            for fmt in ('PNG', 'JPEG'):
                path = self.root / f'{key}.{fmt.lower()}'
                renderer.render_row({}, {}, path, export_format=fmt)
                image = QImage(str(path))
                self.assertEqual((image.width(), image.height()), original_size)
                self.assertAlmostEqual(image.width() * 1000 / image.dotsPerMeterX(), 120,
                                       delta=.3 if fmt == 'JPEG' else .04)
                self.assertAlmostEqual(image.height() * 1000 / image.dotsPerMeterY(), 80,
                                       delta=.3 if fmt == 'JPEG' else .04)

    def test_pdf_individual_and_grouped_preserve_exact_physical_page(self):
        for key, policy in PROFILES.items():
            directory = self.root / key
            directory.mkdir()
            renderer = NativeRenderer(page())
            renderer.configure_export(policy, 120, 80)
            task = (0, 0, 1, {}, {}, 'card')
            workers = [DirectRenderWorker([task], [renderer], directory, 'PDF', target_w_mm=120, target_h_mm=80),
                       SecureGroupedPdfWorker([task], [renderer], directory, {}, 120, 80)]
            for worker in workers:
                errors = []
                worker.error_occurred.connect(errors.append)
                worker.run()
                self.assertFalse(errors, errors)
            for path in directory.glob('*.pdf'):
                box = PdfReader(path).pages[0].mediabox
                self.assertAlmostEqual(float(box.width) * 25.4 / 72, 120, places=5)
                self.assertAlmostEqual(float(box.height) * 25.4 / 72, 80, places=5)

    def test_logical_links_do_not_change_with_output_profile(self):
        data = page()
        data['shapes'] = [dict(type='rect', object_id='s', x=100, y=120, width=200, height=100,
                               has_link=True, link_key='url', fill_color='#ffffff')]
        expected = None
        for policy in PROFILES.values():
            renderer = NativeRenderer(data)
            renderer.configure_export(policy, 120, 80)
            links = []
            renderer.render_to_qimage({'url': 'https://example.com'}, {}, links)
            self.assertEqual(len(links), 1)
            if expected is None:
                expected = links[0]['rect']
            for actual, old in zip(links[0]['rect'].getRect(), expected.getRect()):
                self.assertAlmostEqual(actual, old, places=8)

    def test_native_300_dpi_keeps_existing_pixels_and_static_cache_fidelity(self):
        data = page()
        data['boxes'] = [dict(x=30, y=40, w=800, h=200, html='<p>Exemplo <b>{nome}</b></p>',
                              font_family='Inter', font_size=18)]
        original = NativeRenderer(data).render_to_qimage({'nome': 'Ana'}, {'nome': 'Ana'})
        renderer = NativeRenderer(data)
        renderer.configure_export(ExportPerformance(40, 300), 120, 80)
        self.assertEqual(renderer.render_to_qimage({'nome': 'Ana'}, {'nome': 'Ana'}), original)
        renderer.pre_render_static_base()
        self.assertEqual(renderer.render_to_qimage({'nome': 'Ana'}, {'nome': 'Ana'}), original)

    def test_imposition_geometry_and_sheet_pixels_stay_fixed_in_all_profiles(self):
        for policy in PROFILES.values():
            assembler = SheetAssembler(40, 30, 120, 80, False, False, False, performance=policy)
            self.assertEqual(assembler.capacity, 6)
            card = QImage(round(40 * EXPORT_DPI / 25.4), round(30 * EXPORT_DPI / 25.4), QImage.Format.Format_RGB32)
            card.fill(0xff000000)
            image = assembler.render_sheet([card])
            self.assertEqual(image.width(), round(120 * EXPORT_DPI / 25.4))
            self.assertAlmostEqual(image.width() * 1000 / image.dotsPerMeterX(), 120, delta=.04)

    def test_sheet_preview_of_large_document_is_independent_of_export_limit(self):
        worker = SheetPreviewWorker(normalize_model_document(page((3000, 3000))),
                                    [({}, {})], dict(enabled=True, target_w_mm=3000, target_h_mm=3000,
                                    sheet_w_mm=3000, sheet_h_mm=3000, crop_marks=False,
                                    bleed_margin=False), self.root, 1, memory_only=True)
        received, errors = [], []
        worker.pageReady.connect(lambda _page, _face, image, _generation: received.append(image))
        worker.pageFailed.connect(lambda *args: errors.append(args))
        worker.run()
        self.assertFalse(errors, errors)
        self.assertEqual(len(received), 1)
        self.assertLessEqual(max(received[0].width(), received[0].height()), 1800)

    def test_large_document_tiles_do_not_render_a_full_document_bitmap(self):
        renderer = PageTilingRenderer(normalize_model_document(page((3000, 3000))))
        renderer.performance = ExportPerformance(40)
        plan = build_tile_plan(renderer.bounds, paper=(210, 297))
        with patch.object(renderer.card, 'render_to_qimage', side_effect=AssertionError('Full bitmap')):
            image = renderer.tile_image(plan, plan.tiles[0], scale=1)
        self.assertEqual(image.width(), round(210 * EXPORT_DPI / 25.4))
        self.assertEqual(image.height(), round(297 * EXPORT_DPI / 25.4))
        self.assertLess(image.sizeInBytes(), 36_000_000)

    def test_manager_propagates_profile_to_all_forks_and_sheet_assembler(self):
        for imposed in (False, True):
            settings = dict(enabled=imposed, target_w_mm=40, target_h_mm=30,
                            sheet_w_mm=120, sheet_h_mm=80, crop_marks=False, bleed_margin=False)
            renderer = NativeRenderer(page())
            manager = RenderManager([renderer], [{}], [{}], self.root, 'test',
                                    settings, target_w_mm=120, target_h_mm=80,
                                    performance=ExportPerformance(40))
            with patch('features.generator.workers.QThread.start'):
                manager._start()
            self.assertTrue(manager.workers)
            child = manager.workers[0].renderers[0]
            self.assertEqual(child.output_dimensions(),
                             ExportPerformance(40).dimensions(40, 30) if imposed else (1417, 944))
            if imposed:
                self.assertEqual(manager.workers[0].assembler.dpi, EXPORT_DPI)
            manager._is_running = False

    def test_memory_planning_uses_export_dimensions_instead_of_logical_canvas(self):
        renderer = NativeRenderer(page((1000, 1000)))
        policy = ExportPerformance(150)
        # Este caso mede o planejador; a memória do host é testada separadamente.
        with patch('core.performance.available_memory_bytes', return_value=None):
            renderer.configure_export(policy, 1000, 1000)
        self.assertEqual(_bounded_worker_count(20, [renderer], memory_budget=policy.memory_budget), 1)
        self.assertEqual(_bounded_worker_count(20, [renderer], jpeg=True, memory_budget=policy.memory_budget), 1)

    def test_available_memory_can_restrict_large_profile_without_changing_settings(self):
        policy = ExportPerformance(150)
        with patch('core.performance.available_memory_bytes', return_value=512 * 1024**2):
            with self.assertRaises(MemoryError):
                policy.validate(*policy.dimensions(1000, 1000))
        self.assertEqual(policy, ExportPerformance(150))

    def test_legacy_worker_and_sheet_settings_cannot_restore_lower_output_dpi(self):
        document = normalize_model_document(page())
        workers = [OrganogramWorker(document, [], [], self.root, 'PNG', dpi=96),
                   TiledDocumentWorker(document, [], [], self.root, 'PNG', options={}, dpi=150)]
        for worker in workers:
            self.assertEqual(worker.dpi, EXPORT_DPI)
        assembler = SheetAssembler.from_settings(dict(pixel_limit=40, export_dpi=96))
        self.assertEqual(assembler.dpi, EXPORT_DPI)

    def test_five_profiles_and_custom_limits_migrate_previous_preferences(self):
        self.assertEqual(PIXEL_LIMITS, (40, 80, 150, 300, 600))
        self.assertEqual(tuple(policy.megapixels for policy in PROFILES.values()), PIXEL_LIMITS)
        self.assertEqual(PROFILES['balanced'].megapixels, 40)
        self.settings.setValue('performance/profile', 'economy')
        self.assertEqual(load_performance(self.settings), PROFILES['balanced'])
        dialog = PerformanceDialog(self.settings)
        self.assertEqual(dialog.pixels.currentData(), 40)
        dialog.save()
        self.assertEqual(self.settings.value('performance/profile'), 'custom')
        self.assertEqual(load_performance(self.settings), PROFILES['balanced'])
        for key, policy in PROFILES.items():
            self.settings.setValue('performance/profile', key)
            self.assertEqual(load_performance(self.settings), policy)
        self.settings.setValue('performance/profile', 'custom')
        self.assertEqual(load_performance(self.settings), PROFILES['balanced'])
        self.settings.remove('performance/megapixels')
        self.assertEqual(load_performance(self.settings), PROFILES['large'])
        for old, new in ((12, 40), (20, 40), (36, 40), (72, 80), (150, 150), (600, 600)):
            self.settings.setValue('performance/megapixels', old)
            self.assertEqual(load_performance(self.settings), ExportPerformance(new))
            migrated = PerformanceDialog(self.settings)
            self.assertEqual(migrated.pixels.currentData(), new)
            migrated.reject()
        dialog = PerformanceDialog(self.settings)
        self.assertFalse(hasattr(dialog, 'profile'))
        self.assertEqual(dialog.pixels.count(), 5)
        self.assertEqual(dialog.pixels.currentData(), 600)
        for key, policy in PROFILES.items():
            dialog.pixels.setCurrentIndex(dialog.pixels.findData(policy.megapixels))
            self.assertEqual(dialog.pixels.currentData(), policy.megapixels)
        dialog.save()
        self.assertEqual(load_performance(self.settings), PROFILES['maximum'])

    def test_large_profiles_validate_without_allocating_giant_buffers(self):
        with patch('core.performance.available_memory_bytes', return_value=10_000_000_000):
            for mp, side in ((300, 17320), (600, 24494)):
                policy = ExportPerformance(mp)
                self.assertEqual(policy.validate(side, side), (side, side))
                self.assertGreaterEqual(policy.memory_budget, side * side * 8)
            renderer = NativeRenderer(page((2000, 2000)))
            with patch('features.generator.renderer.QImage', side_effect=AssertionError('Giant allocation')):
                renderer.configure_export(PROFILES['maximum'], 2000, 2000)
                self.assertEqual(renderer.output_dimensions(), (23622, 23622))
                self.assertEqual(renderer.fork().output_dimensions(), renderer.output_dimensions())
                self.assertEqual(_bounded_worker_count(20, [renderer],
                    memory_budget=PROFILES['maximum'].buffer_budget()), 1)

    def test_capacity_and_memory_errors_give_actionable_distinct_guidance(self):
        with patch('core.performance.available_memory_bytes', return_value=10_000_000_000):
            with self.assertRaisesRegex(ValueError, 'configurado para até 40 MP') as error:
                PROFILES['balanced'].validate(10000, 10000)
            self.assertIn('Configurações → Limite de exportação', str(error.exception))
            self.assertIn('memória disponível', str(error.exception))
            PROFILES['large'].validate(10000, 10000)
            with self.assertRaisesRegex(ValueError, 'limite técnico') as error:
                PROFILES['maximum'].validate(33000, 1)
            self.assertIn('não remove esse limite', str(error.exception))
        with patch('core.performance.available_memory_bytes', return_value=6_800_000_000):
            with self.assertRaisesRegex(MemoryError, 'memória suficiente') as error:
                PROFILES['maximum'].validate(24494, 24494)
            self.assertIn('não aumenta a memória livre', str(error.exception))
        with patch('core.performance.available_memory_bytes', return_value=7_000_000_000):
            PROFILES['maximum'].validate(24494, 24494)
        with self.assertRaisesRegex(MemoryError, 'Configurações → Limite de exportação'):
            _bounded_worker_count(1, [SimpleNamespace(output_dimensions=lambda: (10000, 10000))],
                                  memory_budget=100_000_000)

    def test_generation_error_is_visible_once_even_when_log_is_hidden(self):
        from features.workspace.main_window import MainWindow
        messages = []
        window = SimpleNamespace(_generation_failed=False,
                                 log_panel=SimpleNamespace(append=messages.append))
        with patch('features.workspace.main_window.QMessageBox.warning') as warning:
            MainWindow._on_generation_error(window, 'Capacidade insuficiente')
            MainWindow._on_generation_error(window, 'Erro repetido')
        warning.assert_called_once_with(window, 'Não foi possível gerar o material', 'Capacidade insuficiente')
        self.assertTrue(window._generation_failed)
        self.assertEqual(len(messages), 2)

    def test_over_limit_generation_emits_guidance_before_rendering_or_starting_workers(self):
        renderer = NativeRenderer(page((1000, 1000)))
        manager = RenderManager([renderer], [{}], [{}], self.root, 'test',
                                target_w_mm=1000, target_h_mm=1000,
                                performance=PROFILES['balanced'])
        errors, finished = [], []
        manager.error_occurred.connect(errors.append)
        manager.finished_process.connect(lambda: finished.append(True))
        with (patch('features.generator.renderer.QImage', side_effect=AssertionError('Allocated')),
              patch('features.generator.workers.QThread.start') as start):
            manager.start()
        self.assertEqual(len(errors), 1)
        self.assertIn('configurado para até 40 MP', errors[0])
        self.assertIn('Configurações → Limite de exportação', errors[0])
        self.assertEqual(finished, [True])
        start.assert_not_called()

    def test_compact_dialog_estimates_without_allocating_or_probing_memory(self):
        document = normalize_model_document(page((2000, 2000)))
        with (patch('core.performance.available_memory_bytes', side_effect=AssertionError('RAM probe')),
              patch('features.generator.renderer.QImage', side_effect=AssertionError('Allocated'))):
            dialog = PerformanceDialog(self.settings, document)
            self.addCleanup(dialog.reject)
            dialog.show()
            self.app.processEvents()
            self.assertIn('558.0 MP', dialog.estimate.text())
            estimate = dialog.estimate.text()
            for mp in PIXEL_LIMITS:
                dialog.pixels.setCurrentIndex(dialog.pixels.findData(mp))
                self.assertEqual(dialog.estimate.text(), estimate)
            self.assertGreaterEqual(dialog.estimate.height(),
                                    dialog.estimate.heightForWidth(dialog.estimate.width()))
            self.assertFalse(hasattr(dialog, 'recommendation'))
            empty = PerformanceDialog(self.settings)
            self.addCleanup(empty.reject)
            empty.show()
            self.app.processEvents()
            self.assertFalse(empty.estimate.isVisible())


if __name__ == '__main__':
    unittest.main()
