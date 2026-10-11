"""Modos explícitos de saída, configurações independentes e corte sem margem."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import unittest

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QPushButton, QCheckBox

from core.tiling import UNITS_PER_MM, build_tile_plan
from features.generator.output_layout import resolve_output_layout
from features.generator.imposition import SheetAssembler
from features.generator.tiled_document import PageTilingRenderer
from core.fornax_container import save_public_fornax, open_public_fornax
from test_organogram import card_document
import test_output_layout as fixtures
import test_output_preview as preview_fixtures


class OutputModesTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.OutputLayoutTest.setUpClass.__func__)
    setUp = fixtures.OutputLayoutTest.setUp
    config = fixtures.OutputLayoutTest.config
    dialog = fixtures.OutputLayoutTest.dialog
    ready = preview_fixtures.OutputPreviewTest.ready

    def test_mode_selection_is_exclusive_and_does_not_depend_on_item_size(self):
        dialog = self.dialog(self.config(mode='imposition'))
        panel = dialog.tiling_panel
        self.assertTrue(panel.items_button.isChecked())
        self.assertFalse(panel.tiles_button.isChecked())
        self.assertTrue(panel.tiling.isHidden())
        panel.target_width.setValue(400)
        self.assertFalse(panel.valid)
        self.assertTrue(panel.items_button.isChecked())
        panel.tiles_button.click()
        self.assertTrue(panel.tiles_button.isChecked())
        self.assertFalse(panel.items_button.isChecked())
        self.assertTrue(dialog.get_tiling_settings()['tiling'])
        panel.target_width.setValue(20)
        self.assertEqual(panel.output_layout.mode, 'tiles')
        self.assertEqual(len(panel.plan.tiles), 1)
        panel.items_button.click()
        self.assertEqual(panel.target_width.value(), 400)
        self.assertFalse(panel.valid)
        panel.restore_size.click()
        self.assertTrue(panel.valid)
        self.assertFalse(dialog.get_tiling_settings()['tiling'])
        self.assertTrue(dialog.get_imposition_settings()['enabled'])

    def test_switching_modes_and_reopening_preserve_each_configuration(self):
        dialog = self.dialog(self.config(mode='imposition'))
        panel = dialog.tiling_panel
        panel.target_width.setValue(90)
        panel.crop_marks.click()
        items = panel.configuration(include_modes=False)
        panel.tiles_button.click()
        panel.target_width.setValue(400)
        panel.margin_enabled.click()
        panel.margin.setValue(7)
        panel.offset_x.setValue(3)
        tiles = panel.configuration(include_modes=False)
        panel.items_button.click()
        self.assertEqual(panel.configuration(include_modes=False), items)
        panel.tiles_button.click()
        self.assertEqual(panel.configuration(include_modes=False), tiles)
        settings = dialog.get_tiling_settings()
        document = card_document()
        document['tiling_settings'] = deepcopy(settings)
        path = self.root / 'modos.fornax'
        save_public_fornax(document, path)
        loaded = open_public_fornax(path).document()['tiling_settings']
        reopened = self.dialog(loaded).tiling_panel
        self.assertTrue(reopened.tiles_button.isChecked())
        reopened.items_button.click()
        self.assertEqual(reopened.configuration(include_modes=False), items)
        reopened.tiles_button.click()
        self.assertEqual(reopened.configuration(include_modes=False), tiles)

    def test_items_panel_shows_only_relevant_controls_and_slim_toggle_buttons(self):
        dialog = self.dialog(self.config(mode='imposition'))
        panel = dialog.tiling_panel
        for button in (panel.margin_enabled, panel.crop_marks):
            self.assertIsInstance(button, QPushButton)
            self.assertTrue(button.isCheckable())
            self.assertEqual(button.height(), 33)
        self.assertFalse([w for w in panel.findChildren(QCheckBox) if not w.isHidden()])
        for widget in (panel.offset_x, panel.offset_y, panel.optimize,
                       panel.position, panel.view_mode, panel.margin):
            self.assertTrue(widget.isHidden())
        panel.margin_enabled.click()
        self.assertTrue(panel.margin.isHidden())
        panel.tiles_button.click()
        for widget in (panel.optimize,
                       panel.position, panel.view_mode):
            self.assertFalse(widget.isHidden())
        for widget in (panel.offset_x, panel.offset_y):
            self.assertTrue(widget.isHidden())
            self.assertEqual(panel.paper_form.indexOf(widget), -1)

    def test_crop_marks_without_bleed_reserve_their_own_area(self):
        dialog = self.dialog(self.config(mode='imposition', target_size_mm=[100, 140],
            paper=[210, 290], crop_marks=True, auto_orientation=False))
        dialog.show()
        panel = dialog.tiling_panel
        self.ready(panel)
        self.assertTrue(panel.valid)
        self.assertFalse(panel.margin_enabled.isChecked())
        assembler = panel.assembler
        self.assertEqual(assembler.capacity, 4)
        self.assertEqual(assembler.edge_reserve_mm, 5)
        self.assertEqual((assembler.target_w_mm, assembler.target_h_mm), (100, 140))
        image = panel.preview.grab().toImage()
        # Marcas externas à malha: 3 mm de traço, separados por 2 mm.
        for x, y in preview_fixtures.OutputPreviewTest.mark_points(assembler):
            point = panel.preview.map_rect(QRectF(x, y, 0, 0)).topLeft()
            pixels = [image.pixelColor(px, py).lightness()
                      for px in range(round(point.x()) - 2, round(point.x()) + 3)
                      for py in range(round(point.y()) - 2, round(point.y()) + 3)]
            self.assertLess(min(pixels), 128)
        card = QImage(10, 14, QImage.Format.Format_ARGB32)
        card.fill(Qt.GlobalColor.white)
        sheet = assembler.render_sheet([card] * 4)
        clean = SheetAssembler(100, 140, 210, 290, crop_marks=False,
                               auto_rotate=False, margin_mm=5).render_sheet([card] * 4)
        self.assertEqual(sheet.size(), clean.size())
        self.assertNotEqual(sheet, clean)
        midpoint = assembler.margin_top - assembler.mark_gap - assembler.mark_len // 2
        self.assertLess(sheet.pixelColor(assembler._grid_x(1), midpoint).lightness(), 30)
        self.assertEqual(sheet.pixelColor(sheet.width() // 4, sheet.height() // 4), QColor('white'))
        dialog.reject()

    def test_tiled_marks_without_margin_are_visible_in_generated_page(self):
        document = card_document()
        document['boxes'] = []
        renderer = PageTilingRenderer(document)
        options = dict(paper=(50, 70), margin_mm=0, target_size_mm=(100, 140))
        marked = build_tile_plan(renderer.bounds, crop_marks=True, **options)
        clean = build_tile_plan(renderer.bounds, crop_marks=False, **options)
        self.assertEqual((marked.columns, marked.rows), (2, 2))
        self.assertEqual(marked.margin_mm, 0)
        image = renderer.tile_image(marked, marked.tiles[0], scale=1)
        plain = renderer.tile_image(clean, clean.tiles[0], scale=1)
        self.assertEqual(image.size(), plain.size())
        self.assertNotEqual(image, plain)
        self.assertLess(image.pixelColor(0, 10).lightness(), 128)
        self.assertEqual(image.pixelColor(image.width() // 2, image.height() // 2),
                         plain.pixelColor(plain.width() // 2, plain.height() // 2))

    def test_explicit_modes_resolve_consistently_for_preview_and_generation(self):
        settings = self.config(mode='imposition', crop_marks=True)
        self.assertEqual(resolve_output_layout(settings, self.bounds).mode, 'imposition')
        settings['target_size_mm'] = [400, 560]
        with self.assertRaisesRegex(ValueError, 'não cabe'):
            resolve_output_layout(settings, self.bounds)
        settings.update(mode='tiles', target_size_mm=[20, 28])
        layout = resolve_output_layout(settings, self.bounds)
        self.assertEqual(layout.mode, 'tiles')
        self.assertIsNone(layout.assembler)
        self.assertEqual(len(layout.plan.tiles), 1)


if __name__ == '__main__':
    unittest.main()
