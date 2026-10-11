"""Saída automática: geometria, interação e uso do mesmo plano na produção."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QRectF, QPointF, QEvent
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from core.tiling import UNITS_PER_MM
from features.generator.output_layout import resolve_output_layout, effective_settings, output_bounds, from_legacy_preset
from features.generator.imposition import SheetAssembler
from features.generator.production_plan import build_imposition_plan
from features.generator.tiled_document import PageTilingRenderer
from features.generator.export_dialog import ConfigDialog
from features.generator.workers import PageRenderWorker, HybridAssemblerWorker, SecureGroupedPdfWorker
from features.generator.renderer import NativeRenderer
from pypdf import PdfReader
from test_organogram import card_document, board_document
import test_organogram_preview as preview_fixtures


class OutputLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))
        self.bounds = QRectF(0, 0, 100 * UNITS_PER_MM, 140 * UNITS_PER_MM)

    def config(self, **changes):
        result = dict(layout_mode='auto', enabled=True, paper_index=4, paper=[210, 297],
                      target_size_mm=[100, 140], auto_orientation=True, offset_mm=[0, 0],
                      margin_enabled=False, crop_marks=False, positioned=False)
        result.update(changes)
        return result

    def dialog(self, configuration=None, presets=None):
        dialog = ConfigDialog(None, 'Modelo', ['Nome'], tile_renderer=PageTilingRenderer(card_document()),
                              current_tiling=configuration or self.config(), current_imposition=presets)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.tiling_panel.stop_preview)
        return dialog

    def test_auto_uses_multiple_items_then_tiles_without_changing_scale(self):
        small = resolve_output_layout(self.config(), self.bounds)
        self.assertEqual(small.mode, 'imposition')
        self.assertEqual((small.assembler.cols, small.assembler.rows), (2, 2))
        self.assertEqual(small.assembler.target_w_mm, 100)
        large = resolve_output_layout(self.config(target_size_mm=[400, 560]), self.bounds)
        self.assertEqual(large.mode, 'tiles')
        self.assertEqual(large.plan.scale, 4)
        self.assertEqual(len(large.plan.tiles), 4)

    def test_exact_fit_does_not_create_extra_pages(self):
        settings = self.config(paper=[100, 140], auto_orientation=False)
        layout = resolve_output_layout(settings, self.bounds)
        self.assertEqual(layout.mode, 'imposition')
        self.assertEqual(layout.assembler.capacity, 1)
        settings['target_size_mm'] = [100.01, 140.014]
        self.assertEqual(resolve_output_layout(settings, self.bounds).mode, 'tiles')

    def test_orientation_maximizes_capacity_and_respects_manual_choice(self):
        bounds = QRectF(0, 0, 140 * UNITS_PER_MM, 90 * UNITS_PER_MM)
        settings = self.config(target_size_mm=[140, 90])
        auto = resolve_output_layout(settings, bounds).assembler
        self.assertEqual((auto.sheet_w_mm, auto.sheet_h_mm, auto.capacity), (297, 210, 4))
        fixed = resolve_output_layout(dict(settings, auto_orientation=False), bounds).assembler
        self.assertEqual((fixed.sheet_w_mm, fixed.sheet_h_mm, fixed.capacity), (210, 297, 3))

    def test_margin_and_crop_marks_are_explicit_in_both_modes(self):
        settings = self.config(crop_marks=True)
        original = deepcopy(settings)
        self.assertEqual(resolve_output_layout(settings, self.bounds).assembler.edge_reserve_mm, 0)
        self.assertEqual(settings, original)
        settings.update(margin_enabled=True, margin_value=10)
        layout = resolve_output_layout(settings, self.bounds)
        self.assertEqual(layout.assembler.edge_reserve_mm, 10)
        settings['target_size_mm'] = [400, 560]
        self.assertEqual(resolve_output_layout(settings, self.bounds).plan.margin_mm, 10)

    def test_organogram_remains_one_drawing_even_when_many_could_fit(self):
        layout = resolve_output_layout(self.config(target_size_mm=[20, 28]), self.bounds, repeat=False)
        self.assertEqual(layout.mode, 'tiles')
        self.assertIsNone(layout.assembler)
        self.assertEqual(len(layout.plan.tiles), 1)
        self.assertEqual(layout.plan.paper, (210, 297))

    def test_plan_preserves_position_in_preview_and_generation(self):
        settings = self.config(positioned=True, offset_mm=[7, 9], margin_enabled=True, margin_value=5,
                               target_size_mm=[90, 126], auto_orientation=False)
        layout = resolve_output_layout(settings, self.bounds)
        production = build_imposition_plan(list(range(5)), layout.imposition)
        self.assertEqual(production.capacity, layout.assembler.capacity)
        self.assertEqual(production.assembler.margin_left_mm, 12)
        self.assertEqual(production.assembler.margin_top_mm, 14)
        self.assertEqual(production.assembler.sheet_w_mm, 210)
        image = QImage(10, 14, QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        sheet = production.assembler.render_sheet([image])
        self.assertEqual(sheet.pixelColor(production.assembler._grid_x(0) + 2,
                                         production.assembler._grid_y(0) + 2), QColor('red'))
        self.assertEqual(sheet.pixelColor(0, 0), QColor('white'))
        self.assertAlmostEqual(sheet.dotsPerMeterX() * .0254, 300, places=1)

    def test_legacy_margin_capacity_and_centering_are_preserved_on_migration(self):
        for marks in (False, True):
            for bleed in (False, True):
                preset = dict(enabled=True, w=40, h=56, sheet_w=210, sheet_h=297, crop=marks, bleed=bleed)
                legacy = SheetAssembler(40, 56, crop_marks=marks, bleed_margin=bleed)
                converted = from_legacy_preset(preset, self.bounds)
                current = resolve_output_layout(converted, self.bounds).assembler
                for attribute in ('capacity', 'edge_reserve_mm', 'margin_left_mm', 'margin_top_mm'):
                    self.assertAlmostEqual(getattr(legacy, attribute), getattr(current, attribute))

    def test_effective_layout_rechecks_model_geometry_and_fixed_dpi(self):
        document = card_document()
        settings = self.config(dpi=150)
        result = effective_settings(document, settings)
        self.assertFalse(result['tiling'])
        self.assertEqual(result['dpi'], 300)
        self.assertEqual(settings['dpi'], 150)
        large = effective_settings(document, dict(settings, target_size_mm=[800, 1120]))
        self.assertTrue(large['tiling'])
        board = board_document()
        self.assertEqual(output_bounds(board), __import__('core.organogram', fromlist=['board_bounds']).board_bounds(board['organogram']))

    def test_dialog_enter_commits_fields_and_never_accepts(self):
        dialog = self.dialog(self.config(auto_orientation=False))
        dialog.show()
        self.app.processEvents()
        with patch.object(dialog, '_on_accept', side_effect=AssertionError('Enter fechou a configuração')):
            for field, value in ((dialog.tiling_panel.target_width, '120'),
                                 (dialog.tiling_panel.width, '215'), (dialog.tiling_panel.height, '300')):
                field.setFocus()
                field.selectAll()
                QTest.keyClicks(field, value)
                QTest.keyClick(field, Qt.Key.Key_Return)
                self.assertEqual(field.value(), float(value))
                self.assertTrue(dialog.isVisible())
                self.assertEqual(dialog.result(), 0)
            dialog.tabs.setCurrentIndex(1)
            dialog.txt_pattern.setFocus()
            QTest.keyClicks(dialog.txt_pattern, '{Nome}')
            QTest.keyClick(dialog.txt_pattern, Qt.Key.Key_Enter)
            self.assertTrue(dialog.isVisible())
        dialog.reject()

    def test_enter_on_ok_button_still_confirms(self):
        dialog = self.dialog()
        dialog.show()
        self.app.processEvents()
        button = dialog.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        button.setFocus()
        with patch('features.generator.export_dialog.dialog_get_text', return_value=('Folhas', True)):
            QTest.keyClick(button, Qt.Key.Key_Return)
        self.assertEqual(dialog.result(), 1)

    def test_dialog_changes_layout_only_when_the_user_selects_a_mode(self):
        dialog = self.dialog()
        panel = dialog.tiling_panel
        self.assertFalse(hasattr(panel, 'dpi'))
        self.assertEqual(panel.output_layout.mode, 'imposition')
        self.assertAlmostEqual(panel.offset_y.value(), panel.assembler.margin_top_mm, places=2)
        old_y = panel.offset_y.value()
        panel.offset_x.setValue(1)
        self.assertAlmostEqual(panel.assembler.margin_top_mm, old_y, places=2)
        panel._optimize()
        panel.target_width.setValue(600)
        self.assertFalse(panel.valid)
        self.assertIsNone(panel.output_layout)
        panel.tiles_button.click()
        self.assertEqual(panel.output_layout.mode, 'tiles')
        self.assertTrue(dialog.get_tiling_settings()['tiling'])
        panel.restore_size.click()
        self.assertEqual(panel.output_layout.mode, 'tiles')
        panel.items_button.click()
        panel.restore_size.click()
        self.assertEqual(panel.output_layout.mode, 'imposition')
        panel.tiling.setChecked(False)
        self.assertFalse(dialog.get_tiling_settings()['enabled'])
        self.assertFalse(dialog.get_imposition_settings()['enabled'])

    def test_drag_keeps_paper_stationary_until_release_then_recenters_drawing(self):
        dialog = self.dialog(self.config(target_size_mm=[400, 560]))
        dialog.show()
        panel = dialog.tiling_panel
        QTest.qWait(130)
        preview = panel.preview
        self.assertIsNotNone(preview.image)
        old_plan = panel.plan
        paper_rects = [preview.map_rect(r) for r, _ in preview.paper_rects()]
        point = preview.map_rect(preview.drawing_bounds()).center().toPoint()
        QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(preview, point + QPointF(20, 15).toPoint())
        self.assertIs(panel.plan, old_plan)
        self.assertEqual([preview.map_rect(r) for r, _ in preview.paper_rects()], paper_rects)
        self.assertGreater(preview._translation.x(), 0)
        QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point + QPointF(20, 15).toPoint())
        self.assertIsNot(panel.plan, old_plan)
        self.assertTrue(preview._translation.isNull())
        self.assertEqual(preview.scene_bounds().center(), preview.drawing_bounds().center())
        self.assertIsNone(preview._drag_position)
        dialog.reject()

    def test_dragging_imposition_defers_rebuild_and_loss_of_focus_finishes_drag(self):
        dialog = self.dialog()
        dialog.show()
        panel = dialog.tiling_panel
        QTest.qWait(130)
        preview = panel.preview
        assembler = panel.assembler
        point = preview.map_rect(preview.drawing_bounds()).center().toPoint()
        QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(preview, point + QPointF(4, 4).toPoint())
        self.assertIs(panel.assembler, assembler)
        self.app.sendEvent(preview, QEvent(QEvent.Type.FocusOut))
        self.assertIsNone(preview._drag_position)
        self.assertIsNot(panel.assembler, assembler)
        dialog.reject()

    def test_save_and_reopen_preserves_all_output_choices(self):
        settings = self.config(target_size_mm=[450, 630], margin_enabled=True, margin_value=7,
                               crop_marks=True, offset_mm=[3, 4], overlap_mm=2, positioned=True)
        dialog = self.dialog(settings)
        with patch('features.generator.export_dialog.dialog_get_text', return_value=('Cartaz', True)):
            dialog._on_accept()
        saved = dialog.get_tiling_settings()
        presets = dialog.get_imposition_settings()
        reopened = self.dialog(saved, presets)
        self.assertEqual(reopened.get_tiling_settings(), saved)
        self.assertEqual(reopened.tiling_panel.plan.tiles, dialog.tiling_panel.plan.tiles)
        self.assertIn('output_layout', presets['presets']['Cartaz'])

    def test_switching_main_presets_restores_unified_settings_and_native_size(self):
        window = preview_fixtures.OrganogramPreviewTest.workspace(self, document=card_document())
        self.enterContext(patch.object(window, '_start_sheet_preview_preload'))
        config = self.config(target_size_mm=[40, 56])
        window._update_template_json({'tiling_settings': config, 'imposition_settings': {
            'active_preset_name': 'Cartões', 'presets': {'Cartões': {'enabled': True, 'output_layout': config}}}})
        window._refresh_imposition_presets()
        self.assertEqual(window.cbo_presets_main.findData('__tiling__'), -1)
        self.assertTrue(window._resolve_imposition_settings()['enabled'])
        index = window.cbo_presets_main.findData(window.SYSTEM_IMPOSITION_PRESET)
        window._on_main_preset_changed(index)
        self.assertFalse(window._resolve_imposition_settings()['enabled'])
        index = window.cbo_presets_main.findData('Cartões')
        window._on_main_preset_changed(index)
        settings = window._resolve_imposition_settings()
        self.assertTrue(settings['enabled'])
        self.assertEqual(settings['target_w_mm'], 40)
        self.assertEqual(window._model_tiling_settings(window.cached_model_document)['layout_mode'], 'auto')

    def test_positioned_duplex_mirrors_margins_and_link_rectangles(self):
        image = QImage(10, 14, QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        for paper in ([210, 297], [297, 210]):
            layout = resolve_output_layout(self.config(paper=paper, auto_orientation=False,
                target_size_mm=[90, 126], positioned=True, offset_mm=[8, 12]), self.bounds)
            plan = build_imposition_plan([image], dict(layout.imposition, duplex=True))
            assembler = plan.assembler
            front_links, back_links = [], []
            original_margin = assembler.margin_left_mm, assembler.margin_top_mm
            for face, slots, links in ((False, plan.sheets[0].front, front_links),
                                       (True, plan.sheets[0].back, back_links)):
                card_links = [[dict(url='https://example.org', rect=QRectF(0, 0, 10, 14))] if item else []
                              for item in slots]
                assembler.render_sheet(list(slots), preserve_slots=True, back_face=face,
                    canvas_size=(10, 14), card_links=card_links, out_links=links)
            front, back = front_links[0]['rect'], back_links[0]['rect']
            if paper[0] < paper[1]:
                self.assertAlmostEqual(back.left(), assembler.sheet_w - front.right(), delta=1)
                self.assertAlmostEqual(back.top(), front.top(), delta=1)
            else:
                self.assertAlmostEqual(back.top(), assembler.sheet_h - front.bottom(), delta=1)
                self.assertAlmostEqual(back.left(), front.left(), delta=1)
            self.assertEqual((assembler.margin_left_mm, assembler.margin_top_mm), original_margin)

    def test_custom_position_and_orientation_reach_png_and_both_pdf_workers(self):
        bounds = QRectF(0, 0, 140, 90)
        layout = resolve_output_layout(self.config(target_size_mm=[14, 9], paper=[21, 29.7],
            auto_orientation=False, positioned=True, offset_mm=[1, 2]), bounds)
        settings = layout.imposition
        renderer = NativeRenderer({'canvas_size': {'w': 140, 'h': 90}, 'boxes': []})
        task = (0, 0, 1, {}, {}, 'card')
        def run(worker):
            errors = []
            worker.error_occurred.connect(errors.append)
            worker.run()
            self.assertEqual(errors, [])
        page_tasks = [{'page_num': 1, 'front': [task], 'back': None, 'output_base': 'folha'}]
        work, grouped, separate, secure = (self.root / name for name in ('work', 'grouped', 'separate', 'secure'))
        for directory in (work, grouped, separate, secure):
            directory.mkdir()
        png_worker = PageRenderWorker(page_tasks, [renderer], work, settings)
        run(png_worker)
        image = QImage(str(work / 'folha.png'))
        self.assertEqual((image.width(), image.height()), (round(21 * UNITS_PER_MM), round(29.7 * UNITS_PER_MM)))
        self.assertEqual(png_worker.assembler.margin_left_mm, 1)
        self.assertEqual(png_worker.assembler.margin_top_mm, 2)
        run(HybridAssemblerWorker(['folha.png'], work, grouped, True, settings, 14, 9))
        run(PageRenderWorker(page_tasks, [renderer], separate, settings, 'PDF'))
        run(SecureGroupedPdfWorker([task], [renderer], secure, settings, 14, 9))
        for directory in (grouped, separate, secure):
            page = PdfReader(next(directory.glob('*.pdf'))).pages[0]
            # QPdfWriter expressa o MediaBox em pontos inteiros; não em milímetros.
            self.assertAlmostEqual(float(page.mediabox.width), 21 * 72 / 25.4, delta=.6)
            self.assertAlmostEqual(float(page.mediabox.height), 29.7 * 72 / 25.4, delta=.6)

    def test_crop_marks_without_margin_keep_accept_enabled_and_preserve_choices(self):
        dialog = self.dialog()
        dialog.tiling_panel.crop_marks.setChecked(True)
        self.assertTrue(dialog.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        self.assertFalse(dialog.tiling_panel.margin_enabled.isChecked())
        dialog.tiling_panel.margin_enabled.setChecked(True)
        self.assertTrue(dialog.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled())

    def test_disabled_automatic_layout_uses_original_dimensions(self):
        dialog = self.dialog(self.config(enabled=False, target_size_mm=[600, 840]))
        self.assertFalse(dialog.get_imposition_settings()['enabled'])
        self.assertFalse(dialog.get_tiling_settings()['tiling'])
        self.assertEqual(dialog.tiling_panel.output_layout, None)

    def test_selected_sheet_preview_can_switch_between_both_layouts(self):
        dialog = self.dialog()
        dialog.show()
        panel = dialog.tiling_panel
        panel.view_mode.setCurrentIndex(1)
        QTest.qWait(130)
        self.assertFalse(panel.preview.image.isNull())
        self.assertTrue(panel.preview.sheet)
        self.assertEqual(panel.position.count(), 1)
        panel.target_width.setValue(400)
        self.assertFalse(panel.valid)
        panel.tiles_button.click()
        QTest.qWait(130)
        self.assertFalse(panel.preview.image.isNull())
        self.assertGreater(panel.position.count(), 1)
        panel.target_width.setValue(100)
        panel.items_button.click()
        panel.restore_size.click()
        panel.view_mode.setCurrentIndex(0)
        QTest.qWait(130)
        self.assertIs(panel.preview.image, panel._base_image)
        self.assertIsNotNone(panel.assembler)
        dialog.reject()

    def test_fornax_roundtrip_keeps_automatic_layout_and_presets(self):
        from core.fornax_container import save_public_fornax, open_public_fornax
        document = card_document()
        config = self.config(target_size_mm=[400, 560], positioned=True, offset_mm=[3, 4])
        document['tiling_settings'] = config
        document['imposition_settings'] = {'active_preset_name': 'Cartaz', 'presets': {
            'Cartaz': {'enabled': True, 'output_layout': deepcopy(config)}}}
        path = self.root / 'cartaz.fornax'
        save_public_fornax(document, path)
        reopened = open_public_fornax(path).document()
        self.assertEqual(reopened['tiling_settings'], config)
        self.assertEqual(reopened['imposition_settings'], document['imposition_settings'])
        self.assertTrue(effective_settings(reopened, reopened['tiling_settings'])['tiling'])
        from core.starter_templates import StarterTemplate, model_from_starter
        starter, _ = model_from_starter(StarterTemplate('teste', 'model', 'Teste', '', path))
        self.assertNotIn('imposition_settings', starter)
        self.assertNotIn('tiling_settings', starter)


if __name__ == '__main__':
    unittest.main()
