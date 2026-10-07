"""Montagem física, nomes, arquivos e escolhas explícitas do ladrilhamento."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import unittest
from unittest.mock import patch, Mock

from PySide6.QtCore import QRectF, QPointF, QEvent, Qt
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton, QProgressBar
from PySide6.QtTest import QTest
from pypdf import PdfReader

from core.tiling import build_tile_plan, spreadsheet_position, UNITS_PER_MM
from features.generator.organogram import OrganogramRenderer, OrganogramWorker
from features.generator.tiling_panel import TilingPanel
from features.generator.export_dialog import ConfigDialog
from features.generator.tiled_document import PageTilingRenderer, TiledDocumentWorker, tiling_options
from test_organogram import board_document, card_document
import test_organogram_preview as preview_fixtures
from core.fornax_container import FornaxError, open_public_fornax, save_public_fornax


class TiledExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def renderer(self):
        document = board_document(2, 2)
        board = document['organogram']
        board['margin_mm'] = 0
        board['groups'][0].update(x=-37, y=-29, card_w=120, card_h=168, gap_x=0, gap_y=0)
        rows = [{'Nome': name} for name in ('Ana', 'Bruno', 'Carla', 'Diana')]
        return OrganogramRenderer(document, rows)

    def options(self, **kwargs):
        return dict(paper=(100 / UNITS_PER_MM, 150 / UNITS_PER_MM), margin_mm=0,
                    overlap_mm=0, crop_marks=False, **kwargs)

    def worker(self, renderer, directory, *, mode='pdf', separate=False, options=None, **kwargs):
        directory.mkdir(exist_ok=True)
        rows = [slot[3] for slot in renderer.slots]
        worker = OrganogramWorker(renderer.document, rows, rows, directory, mode,
                                 tiling_options=options or self.options(), separate_files=separate, **kwargs)
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        return errors

    def dialog(self, **kwargs):
        dialog = TilingPanel(self.renderer(), **kwargs)
        def cleanup():
            dialog.stop_preview()
            dialog.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.addCleanup(cleanup)
        return dialog

    def wait_preview(self, dialog):
        for _ in range(200):
            if not dialog._preview_timer.isActive() and dialog.preview.image is not None:
                return
            QTest.qWait(10)
        self.fail('A prévia não terminou')

    def test_positions_follow_spreadsheet_columns_and_rows(self):
        self.assertEqual([spreadsheet_position(column, 0) for column in (0, 1, 25, 26, 27, 51, 52)],
                         ['A1', 'B1', 'Z1', 'AA1', 'AB1', 'AZ1', 'BA1'])
        self.assertEqual(spreadsheet_position(26, 99), 'AA100')

    def test_automatic_orientation_minimizes_sheet_count_and_manual_choice_remains_available(self):
        bounds = QRectF(0, 0, 235 * UNITS_PER_MM, 465 * UNITS_PER_MM)
        portrait = build_tile_plan(bounds, (210, 297))
        landscape = build_tile_plan(bounds, (297, 210))
        automatic = build_tile_plan(bounds, auto_orientation=True)
        self.assertEqual(len(portrait.tiles), 4)
        self.assertEqual(len(landscape.tiles), 3)
        self.assertEqual(automatic.paper, (297, 210))
        self.assertEqual(len(automatic.tiles), 3)
        enlarged = build_tile_plan(bounds, target_size_mm=(470, 930), auto_orientation=True)
        candidates = [build_tile_plan(bounds, paper, target_size_mm=(470, 930))
                      for paper in ((210, 297), (297, 210))]
        self.assertEqual(len(enlarged.tiles), min(len(plan.tiles) for plan in candidates))

    def test_scaled_and_repositioned_tiles_reassemble_the_native_design_without_distortion(self):
        renderer = self.renderer()
        plan = build_tile_plan(renderer.bounds, (200 / UNITS_PER_MM, 300 / UNITS_PER_MM),
            target_size_mm=(480 / UNITS_PER_MM, 672 / UNITS_PER_MM),
            offset_mm=(20 / UNITS_PER_MM, 30 / UNITS_PER_MM))
        expected = QImage(500, 702, QImage.Format.Format_ARGB32)
        expected.setDotsPerMeterX(3780)
        expected.setDotsPerMeterY(3780)
        expected.fill(QColor('white'))
        painter = QPainter(expected)
        try:
            painter.translate(20, 30)
            painter.scale(2, 2)
            painter.translate(-renderer.bounds.left(), -renderer.bounds.top())
            renderer.paint(painter)
        finally:
            painter.end()
        actual = QImage(expected.size(), expected.format())
        actual.fill(QColor('white'))
        painter = QPainter(actual)
        try:
            origin = plan.tiles[0].trim.topLeft()
            for tile in plan.tiles:
                image = renderer.tile_image(plan, tile, scale=1)
                painter.drawImage(tile.trim.topLeft() - origin,
                                  image.copy(0, 0, round(tile.trim.width()), round(tile.trim.height())))
        finally:
            painter.end()
        self.assertEqual(actual, expected)

    def test_configuration_contains_mutually_exclusive_print_modes_and_keeps_presets(self):
        current = {'active_preset_name': 'Turma', 'presets': {
            'Turma': {'enabled': True, 'sheet_w': 210, 'sheet_h': 297, 'w': 20, 'h': 28}}}
        original = deepcopy(current)
        dialog = ConfigDialog(None, 'teste', [], current_imposition=current,
                              tile_renderer=self.renderer(), current_tiling={'tiling': True})
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.chk_imposition.isChecked())
        self.assertTrue(dialog.tiling_panel.tiling.isChecked())
        dialog.chk_imposition.setChecked(True)
        self.assertFalse(dialog.tiling_panel.tiling.isChecked())
        dialog.tiling_panel.tiling.setChecked(True)
        self.assertFalse(dialog.chk_imposition.isChecked())
        dialog._on_accept()
        self.assertTrue(dialog.get_imposition_settings()['presets']['Turma']['enabled'])
        self.assertEqual(current, original)

    def test_dragging_preview_repositions_design_and_releases_the_mouse_state(self):
        panel = self.dialog(initial={'tiling': True})
        panel.resize(820, 650)
        panel.show()
        self.wait_preview(panel)
        preview = panel.preview
        point = preview.map_rect(panel.plan.drawing_bounds).center().toPoint()
        QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(preview, point + QPointF(18, 12).toPoint())
        QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point + QPointF(18, 12).toPoint())
        self.assertGreater(panel.offset_x.value(), 0)
        self.assertGreater(panel.offset_y.value(), 0)
        self.assertIsNone(preview._drag_position)
        self.assertIsNone(preview._drag_scene)
        panel._optimize()
        self.assertEqual(panel.plan.offset_mm, (0, 0))
        self.assertTrue(panel.configuration()['auto_orientation'])

    def test_restore_original_size_keeps_print_choices_and_exact_scale(self):
        panel = self.dialog(initial={'tiling': True, 'offset_mm': [3, 7],
                                     'margin_enabled': True, 'margin_value': 5,
                                     'crop_marks': True, 'overlap_mm': 2})
        original = (panel.renderer.bounds.width() / UNITS_PER_MM,
                    panel.renderer.bounds.height() / UNITS_PER_MM)
        panel.target_width.setValue(original[0] * 2)
        before = panel.configuration()
        self.assertGreater(panel.plan.scale, 1.9)
        panel.restore_size.click()
        self.assertEqual(panel.configuration()['target_size_mm'], list(original))
        self.assertEqual(panel.plan.scale, 1)
        self.assertEqual(panel.plan.drawing_bounds.size(), panel.renderer.bounds.size())
        for key in ('offset_mm', 'paper', 'margin_enabled', 'margin_value',
                    'crop_marks', 'overlap_mm', 'dpi', 'auto_orientation'):
            self.assertEqual(panel.configuration()[key], before[key], key)
        # Uma dimensão não exata em centésimos também deve continuar em 100% ao reabrir.
        renderer = self.renderer()
        renderer.bounds.setWidth(renderer.bounds.width() + 0.123)
        other = TilingPanel(renderer, initial={'tiling': True})
        self.addCleanup(other.stop_preview)
        self.addCleanup(other.deleteLater)
        other.target_width.setValue(50)
        other.restore_size.click()
        restored = TilingPanel(renderer, initial=other.configuration())
        self.addCleanup(restored.stop_preview)
        self.addCleanup(restored.deleteLater)
        self.assertEqual(restored.plan.scale, 1)

    def test_regular_pages_keep_names_data_and_both_pdf_output_modes(self):
        document = card_document()
        document['tiling_settings'] = {'tiling': True, 'paper': [30, 45], 'auto_orientation': True,
            'target_size_mm': [100, 140], 'offset_mm': [2, 3], 'margin_enabled': False}
        path = self.root / 'configured.fornax'
        save_public_fornax(document, path)
        opened = open_public_fornax(path)
        self.assertEqual(opened.document()['tiling_settings'], document['tiling_settings'])
        options = tiling_options(document['tiling_settings'])
        rows = [{'Nome': 'Ana'}, {'Nome': 'Bruno'}]
        all_files = {}
        for mode in ('pdf_item', 'pdf_grouped', 'png'):
            directory = self.root / mode
            directory.mkdir()
            worker = TiledDocumentWorker(document, rows, rows, directory, mode,
                                         options=options, pattern='{Nome}')
            errors = []
            worker.error_occurred.connect(errors.append)
            worker.run()
            self.assertEqual(errors, [])
            all_files[mode] = list(directory.iterdir())
        grouped = PdfReader(all_files['pdf_grouped'][0])
        self.assertEqual(len(grouped.pages), len(all_files['pdf_item']))
        self.assertEqual(len(all_files['png']), len(grouped.pages))
        self.assertTrue((self.root / 'pdf_item' / 'Ana_A1.pdf').exists())
        self.assertTrue((self.root / 'pdf_item' / 'Bruno_A1.pdf').exists())
        self.assertTrue(any('Ana' in page.extract_text() for page in grouped.pages))
        self.assertTrue(any('Bruno' in page.extract_text() for page in grouped.pages))
        self.assertTrue(any('Bruno' in label for label in grouped.page_labels))

    def test_chart_layout_size_stays_stable_when_last_positions_are_empty(self):
        document = board_document(4, 6)
        full = OrganogramRenderer(document, [], layout_preview=True, fixed_layout=True)
        partial = OrganogramRenderer(document, [{'Nome': 'Ana'}], fixed_layout=True)
        self.assertEqual(full.bounds, partial.bounds)
        configuration = {'tiling': True, 'paper': [210, 297], 'auto_orientation': True,
                         'target_size_mm': [500, 989.36], 'offset_mm': [5, 7]}
        first = build_tile_plan(full.bounds, **tiling_options(configuration, full.bounds))
        other = build_tile_plan(partial.bounds, **tiling_options(configuration, partial.bounds))
        self.assertEqual(first.tiles, other.tiles)
        self.assertEqual(first.scale, other.scale)

    def test_tiled_mode_and_multiple_items_can_be_switched_from_main_presets(self):
        window = preview_fixtures.OrganogramPreviewTest.workspace(self)
        window._update_template_json({'tiling_settings': {'tiling': True, 'paper': [210, 297]},
            'imposition_settings': {'active_preset_name': 'Equipe', 'presets': {
                'Equipe': {'enabled': True, 'sheet_w': 210, 'sheet_h': 297, 'w': 40, 'h': 56}}}})
        window._refresh_imposition_presets()
        self.assertEqual(window.cbo_presets_main.currentData(), '__tiling__')
        self.assertFalse(window._resolve_imposition_settings()['enabled'])
        index = window.cbo_presets_main.findData('Equipe')
        window.cbo_presets_main.setCurrentIndex(index)
        window._on_main_preset_changed(index)
        self.assertFalse(window.cached_model_document['tiling_settings']['tiling'])
        self.assertTrue(window._resolve_imposition_settings()['enabled'])
        index = window.cbo_presets_main.findData('__tiling__')
        window.cbo_presets_main.setCurrentIndex(index)
        window._on_main_preset_changed(index)
        self.assertTrue(window.cached_model_document['tiling_settings']['tiling'])
        self.assertTrue(window.cached_model_document['imposition_settings']['presets']['Equipe']['enabled'])

    def test_protected_regular_model_exports_asynchronous_tiles_from_saved_settings(self):
        document = card_document()
        document['tiling_settings'] = {'tiling': True, 'paper': [60, 80], 'auto_orientation': False,
            'target_size_mm': [100, 140], 'offset_mm': [3, 7], 'margin_enabled': False}
        window = preview_fixtures.OrganogramPreviewTest.workspace(self, protected=True, document=document)
        window.current_filename_suffix = '{Nome}'
        window.btn_generate_cards = QPushButton(window)
        window.progress_bar = QProgressBar(window)
        window.cbo_export_format.addItem('PDF único', 'pdf_grouped')
        window.cbo_export_format.setCurrentIndex(window.cbo_export_format.findData('pdf_grouped'))
        snapshot = window._fornax_sessions.borrow_job(window._current_library_entry().path)
        with patch.object(ConfigDialog, 'exec', side_effect=AssertionError('A configuração já foi salva')):
            window._generate_tiled_pages(snapshot.document(), [{'Nome': 'Ana'}], [{'Nome': 'Ana'}],
                                         self.root, snapshot.asset, snapshot)
        for _ in range(300):
            if not window.manager.isRunning():
                break
            QTest.qWait(10)
        self.app.processEvents()
        self.assertFalse(window.manager.isRunning())
        self.assertFalse(window._generation_failed)
        reader = PdfReader(window._last_forge_output_dir / 'ladrilhos.pdf')
        self.assertEqual(len(reader.pages), 4)
        self.assertEqual(reader.page_labels, [f'Ana — {label}' for label in ('A1', 'B1', 'A2', 'B2')])
        self.assertTrue(window.btn_generate_cards.isEnabled())
        with self.assertRaises(FornaxError):
            snapshot.document()

    def test_two_page_models_name_the_source_page_as_well_as_tile_position(self):
        from core.model_document import add_blank_back_page
        document = add_blank_back_page(card_document())
        document['pages'][1] = {**deepcopy(document['pages'][0]), 'page_id': 'back'}
        rows = [{'Nome': 'Ana'}]
        worker = TiledDocumentWorker(document, rows, rows, self.root, 'pdf_item',
            options={'paper': (30, 45), 'auto_orientation': True}, pattern='{Nome}')
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])
        self.assertTrue((self.root / 'Ana_pag1_A1.pdf').exists())
        self.assertTrue((self.root / 'Ana_pag2_A1.pdf').exists())

    def test_trim_areas_cover_design_once_and_overlap_is_only_repeated_content(self):
        bounds = QRectF(-37, -29, 300 * UNITS_PER_MM, 420 * UNITS_PER_MM)
        plan = build_tile_plan(bounds, (150, 210), margin_mm=5, overlap_mm=10, crop_marks=True)
        self.assertEqual((plan.columns, plan.rows), (3, 3))
        self.assertEqual([tile.name for tile in plan.tiles], ['A1', 'B1', 'C1', 'A2', 'B2', 'C2', 'A3', 'B3', 'C3'])
        self.assertAlmostEqual(sum(tile.trim.width() * tile.trim.height() for tile in plan.tiles),
                               bounds.width() * bounds.height())
        for tile in plan.tiles:
            self.assertTrue(tile.region.contains(tile.trim))
            self.assertTrue(bounds.contains(tile.region))
        self.assertAlmostEqual(plan.tiles[0].trim.right(), plan.tiles[1].trim.left())
        self.assertAlmostEqual(plan.tiles[0].region.right() - plan.tiles[1].region.left(), 10 * UNITS_PER_MM)
        self.assertAlmostEqual(plan.tiles[0].trim.bottom(), plan.tiles[3].trim.top())

    def test_exact_fit_does_not_add_a_blank_sheet_and_large_grid_is_rejected(self):
        plan = build_tile_plan(QRectF(0, 0, 420 * UNITS_PER_MM, 594 * UNITS_PER_MM))
        self.assertEqual((plan.columns, plan.rows), (2, 2))
        with self.assertRaisesRegex(ValueError, '1.000'):
            build_tile_plan(QRectF(0, 0, 100000 * UNITS_PER_MM, 100000 * UNITS_PER_MM))

    def test_invalid_dimensions_do_not_change_user_margin_to_make_marks_fit(self):
        bounds = self.renderer().bounds
        for options in ({'margin_mm': 0, 'crop_marks': True}, {'margin_mm': 150},
                        {'overlap_mm': 210}, {'margin_mm': -1}, {'paper': (float('nan'), 210)}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_tile_plan(bounds, **options)

    def test_reassembling_tiles_matches_full_native_drawing_with_and_without_overlap(self):
        renderer = self.renderer()
        original = renderer.preview(max_side=336)
        for overlap in (0, 20 / UNITS_PER_MM):
            with self.subTest(overlap=overlap):
                options = self.options()
                options['overlap_mm'] = overlap
                plan = build_tile_plan(renderer.bounds, **options)
                assembled = QImage(original.size(), QImage.Format.Format_ARGB32)
                assembled.fill(QColor('white'))
                painter = QPainter(assembled)
                try:
                    for tile in plan.tiles:
                        image = renderer.tile_image(plan, tile, scale=1)
                        piece = image.copy(0, 0, round(tile.trim.width()), round(tile.trim.height()))
                        painter.drawImage(QPointF(tile.trim.left() - renderer.bounds.left(),
                                                 tile.trim.top() - renderer.bounds.top()), piece)
                finally:
                    painter.end()
                self.assertEqual(assembled, original)

    def test_pdf_grouped_and_separate_preserve_page_size_positions_and_vector_text(self):
        renderer = self.renderer()
        single, separate = self.root / 'single', self.root / 'separate'
        self.assertEqual(self.worker(renderer, single), [])
        self.assertEqual(self.worker(renderer, separate, separate=True), [])
        plan = build_tile_plan(renderer.bounds, **self.options())
        combined = PdfReader(single / 'organograma.pdf')
        self.assertEqual(combined.page_labels, [tile.name for tile in plan.tiles])
        self.assertEqual(len(combined.pages), len(plan.tiles))
        self.assertEqual(set(path.name for path in separate.iterdir()),
                         {f'organograma_{tile.name}.pdf' for tile in plan.tiles})
        for index, tile in enumerate(plan.tiles):
            page = PdfReader(separate / f'organograma_{tile.name}.pdf')
            self.assertEqual(page.page_labels, [tile.name])
            self.assertEqual(len(page.pages), 1)
            self.assertEqual(page.pages[0].mediabox, combined.pages[index].mediabox)
            self.assertEqual(page.pages[0].extract_text(), combined.pages[index].extract_text())
            self.assertAlmostEqual(float(page.pages[0].mediabox.width) * 25.4 / 72,
                                   plan.paper[0], delta=1e-6)
            self.assertAlmostEqual(float(page.pages[0].mediabox.height) * 25.4 / 72,
                                   plan.paper[1], delta=1e-6)
        self.assertTrue(any('Ana' in page.extract_text() for page in combined.pages))

    def test_png_tiles_have_position_suffix_and_physical_resolution(self):
        renderer = self.renderer()
        directory = self.root / 'png'
        self.assertEqual(self.worker(renderer, directory, mode='png', dpi=300), [])
        image = QImage(str(directory / 'organograma_A1.png'))
        self.assertAlmostEqual(image.dotsPerMeterX() * 25.4 / 1000, 300, delta=0.1)
        self.assertEqual(image.width(), 100)
        self.assertEqual(len(list(directory.glob('*.png'))), 9)

    def test_partial_failure_and_cancellation_leave_no_published_tiles_and_close_snapshot(self):
        renderer = self.renderer()
        snapshot = Mock()
        real_export = OrganogramRenderer.export_pdf
        count = 0
        def failing_export(instance, path, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('Falha de disco simulada')
            return real_export(instance, path, **kwargs)
        directory = self.root / 'failure'
        with patch.object(OrganogramRenderer, 'export_pdf', failing_export):
            errors = self.worker(renderer, directory, separate=True, authorized_snapshot=snapshot)
        self.assertIn('Falha de disco', errors[0])
        self.assertFalse(list(directory.iterdir()))
        snapshot.close.assert_called_once()
        directory = self.root / 'cancel'
        with patch.object(OrganogramWorker, 'isInterruptionRequested', return_value=True):
            errors = self.worker(renderer, directory, separate=True)
        self.assertIn('cancelada', errors[0])
        self.assertFalse(list(directory.iterdir()))

    def test_dialog_explicit_choices_default_to_no_margin_marks_or_overlap(self):
        dialog = self.dialog()
        self.assertIsNone(dialog.tiling_options())
        dialog.tiling.setChecked(True)
        self.assertEqual(dialog.tiling_options()['margin_mm'], 0)
        self.assertEqual(dialog.tiling_options()['overlap_mm'], 0)
        self.assertFalse(dialog.tiling_options()['crop_marks'])
        self.assertTrue(dialog.tiling_options()['auto_orientation'])
        dialog.crop_marks.setChecked(True)
        self.assertEqual(dialog.margin.value(), 5)
        self.assertFalse(dialog.margin_enabled.isChecked())
        self.assertFalse(dialog.valid)
        self.assertIn('5 mm', dialog.error.text())
        dialog.margin_enabled.setChecked(True)
        self.assertIsNotNone(dialog.plan)
        self.assertTrue(dialog.valid)
        dialog.orientation.setCurrentIndex(1)
        self.assertEqual(dialog.plan.paper, (297, 210))

    def test_selected_sheet_preview_uses_same_plan_and_repeated_changes_keep_last_selection(self):
        dialog = self.dialog(initial={'tiling': True, 'paper_index': 4,
                                      'paper': [10, 15], 'margin_enabled': False})
        self.wait_preview(dialog)
        dialog.view_mode.setCurrentIndex(1)
        for index in range(len(dialog.plan.tiles)):
            dialog.position.setCurrentIndex(index)
        self.wait_preview(dialog)
        tile = dialog.plan.tiles[dialog.position.currentIndex()]
        scale = 900 / (max(dialog.plan.paper) * UNITS_PER_MM)
        expected = dialog.renderer.tile_image(dialog.plan, tile, scale=scale)
        self.assertEqual(dialog.preview.image.toImage(), expected.convertToFormat(dialog.preview.image.toImage().format()))
        dialog.view_mode.setCurrentIndex(0)
        self.wait_preview(dialog)
        self.assertEqual(dialog.preview.image, dialog._base_image)
        self.assertFalse(dialog.preview.sheet)

    def test_dialog_configuration_round_trip_preserves_user_choices(self):
        dialog = self.dialog(initial={'tiling': True, 'paper_index': 4, 'paper': [100, 150],
                                      'margin_enabled': True, 'margin_value': 7, 'crop_marks': True,
                                      'overlap_mm': 3, 'dpi': 300})
        restored = self.dialog(initial=dialog.configuration())
        self.assertEqual(restored.tiling_options(), dialog.tiling_options())
        self.assertEqual(restored.plan.tiles, dialog.plan.tiles)

    def test_dialog_reuses_existing_paper_margin_and_marks_without_altering_model(self):
        dialog = self.dialog(initial={'auto_orientation': False}, imposition_settings={'sheet_w_mm': 420, 'sheet_h_mm': 297,
                                                 'crop_marks': True, 'bleed_margin': False})
        original = deepcopy(dialog.renderer.document)
        dialog.tiling.setChecked(True)
        self.assertEqual(dialog.paper.currentText(), 'A3')
        self.assertEqual(dialog.width.value(), 420)
        self.assertFalse(dialog.margin_enabled.isChecked())
        self.assertTrue(dialog.crop_marks.isChecked())
        self.assertIsNone(dialog.plan)
        dialog.crop_marks.setChecked(False)
        self.assertEqual(dialog.plan.paper, (420, 297))
        self.assertEqual(dialog.renderer.document, original)

    def test_workspace_passes_selected_output_and_tiling_to_authorized_background_job(self):
        window = preview_fixtures.OrganogramPreviewTest.workspace(self, protected=True)
        preview_fixtures.OrganogramPreviewTest.paste(self, window)
        window.btn_generate_cards = QPushButton(window)
        window.progress_bar = QProgressBar(window)
        window.cbo_export_format.addItem('PDF por item', 'pdf_item')
        window.cbo_export_format.setCurrentIndex(window.cbo_export_format.findData('pdf_item'))
        window._update_template_json({'tiling_settings': {
            'tiling': True, 'paper': [60, 80], 'auto_orientation': False,
            'margin_enabled': False, 'crop_marks': False, 'overlap_mm': 0}})
        snapshot = window._fornax_sessions.borrow_job(window._current_library_entry().path)
        plain, rich = window._scrape_table_data()
        with patch.object(ConfigDialog, 'exec', side_effect=AssertionError('A geração não deve abrir configuração')):
            window._generate_organogram(snapshot.document(), plain, rich, self.root,
                                       snapshot.asset, snapshot)
        for _ in range(300):
            if not window.manager.isRunning():
                break
            QTest.qWait(10)
        self.assertFalse(window.manager.isRunning())
        self.app.processEvents()
        self.assertFalse(window._generation_failed)
        self.assertTrue(window.btn_generate_cards.isEnabled())
        self.assertTrue(window.manager.separate_files)
        self.assertEqual(window.manager.tiling_options['paper'], (60, 80))
        files = list(window._last_forge_output_dir.glob('*.pdf'))
        self.assertGreater(len(files), 1)
        self.assertTrue((window._last_forge_output_dir / 'organograma_A1.pdf').exists())
        self.assertTrue(all(len(PdfReader(path).pages) == 1 for path in files))
        self.assertTrue(window.cached_model_document['tiling_settings']['tiling'])
        with self.assertRaises(FornaxError):
            snapshot.document()

    def test_cancelling_configuration_does_not_change_the_model_or_start_generation(self):
        window = preview_fixtures.OrganogramPreviewTest.workspace(self, protected=True)
        window.current_filename_suffix = ''
        original = deepcopy(window.cached_model_document)
        def reject(dialog):
            dialog.tiling_panel.tiling.setChecked(True)
            dialog.tiling_panel.target_width.setValue(1000)
            dialog.reject()
            return dialog.result()
        with patch.object(ConfigDialog, 'exec', reject), patch.object(window, '_update_template_json') as save:
            window._open_config_dialog()
        save.assert_not_called()
        self.assertEqual(window.cached_model_document, original)

    def test_marks_stay_outside_content_and_can_be_disabled(self):
        renderer = self.renderer()
        plan = build_tile_plan(renderer.bounds, (100, 150), margin_mm=5, crop_marks=True)
        clean_plan = build_tile_plan(renderer.bounds, (100, 150), margin_mm=5, crop_marks=False)
        marked = renderer.tile_image(plan, plan.tiles[0], scale=1)
        clean = renderer.tile_image(clean_plan, clean_plan.tiles[0], scale=1)
        self.assertNotEqual(marked, clean)
        margin = round(5 * UNITS_PER_MM)
        rect = plan.tiles[0].region
        self.assertEqual(marked.copy(margin, margin, round(rect.width()), round(rect.height())),
                         clean.copy(margin, margin, round(rect.width()), round(rect.height())))

    @unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler não disponível para conferir os pixels do PDF')
    def test_a4_without_margin_preserves_exact_physical_size_and_content_at_sheet_edges(self):
        document = board_document(1, 1)
        document['organogram']['margin_mm'] = 0
        document['organogram']['groups'][0].update(
            x=0, y=0, card_w=420 * UNITS_PER_MM, card_h=594 * UNITS_PER_MM)
        renderer = OrganogramRenderer(document, [{'Nome': 'Teste'}])
        plan = build_tile_plan(renderer.bounds)
        path = self.root / 'a4.pdf'
        renderer.export_pdf(path, plan=plan, tiles=(plan.tiles[0],))
        page = PdfReader(path).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width) * 25.4 / 72, 210, delta=1e-6)
        self.assertAlmostEqual(float(page.mediabox.height) * 25.4 / 72, 297, delta=1e-6)
        subprocess.run(['pdftoppm', '-f', '1', '-l', '1', '-r', '300', '-singlefile', '-png',
                        str(path), str(self.root / 'a4')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        image = QImage(str(self.root / 'a4.png'))
        expected = QColor('#dcecf4')
        self.assertEqual(image.pixelColor(image.width() - 2, image.height() // 2), expected)
        self.assertEqual(image.pixelColor(image.width() // 2, image.height() - 2), expected)

    @unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler não disponível para conferir os pixels do PDF')
    def test_combined_and_separate_pdf_pages_render_identically_with_marks_overlap_and_links(self):
        renderer = self.renderer()
        document = renderer.document
        document['pages'][0]['boxes'][0].update(has_link=True, link_key='URL')
        rows = [{'Nome': name, 'URL': 'https://example.org/'} for name in ('Ana', 'Bruno', 'Carla', 'Diana')]
        renderer = OrganogramRenderer(document, rows)
        options = {'paper': (25, 30), 'margin_mm': 5, 'crop_marks': True, 'overlap_mm': 2,
                   'offset_mm': (1, 2), 'target_size_mm':
                   (renderer.bounds.width() * 1.5 / UNITS_PER_MM, renderer.bounds.height() * 1.5 / UNITS_PER_MM)}
        combined_dir, separate_dir = self.root / 'combined', self.root / 'parts'
        self.assertEqual(self.worker(renderer, combined_dir, options=options), [])
        self.assertEqual(self.worker(renderer, separate_dir, options=options, separate=True), [])
        combined = combined_dir / 'organograma.pdf'
        reader = PdfReader(combined)
        has_link = False
        for index, label in enumerate(reader.page_labels):
            part = separate_dir / f'organograma_{label}.pdf'
            for source, prefix, first_page in ((combined, self.root / 'whole', index + 1),
                                               (part, self.root / 'part', 1)):
                subprocess.run(['pdftoppm', '-f', str(first_page), '-l', str(first_page), '-r', '96',
                                '-png', '-singlefile', str(source), str(prefix)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.assertEqual(QImage(str(self.root / 'whole.png')), QImage(str(self.root / 'part.png')))
            for annotation in reader.pages[index].get('/Annots', []):
                has_link = True
                x0, y0, x1, y1 = map(float, annotation.get_object()['/Rect'])
                self.assertGreaterEqual(min(x0, y0), 0)
                self.assertLessEqual(x1, float(reader.pages[index].mediabox.width))
                self.assertLessEqual(y1, float(reader.pages[index].mediabox.height))
        self.assertTrue(has_link)


if __name__ == '__main__':
    unittest.main()
