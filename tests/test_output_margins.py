"""Reservas cumulativas e guia de sangria: mesmos limites na prévia e saída."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest

from core.tiling import UNITS_PER_MM, reserved_margin_mm
from features.generator.tiled_document import tiling_options
from features.generator.production_plan import build_imposition_plan
import test_output_layout as fixtures
import test_output_preview as preview_fixtures


class OutputMarginsTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.OutputLayoutTest.setUpClass.__func__)
    setUp = fixtures.OutputLayoutTest.setUp
    config = fixtures.OutputLayoutTest.config
    dialog = fixtures.OutputLayoutTest.dialog
    ready = preview_fixtures.OutputPreviewTest.ready

    def test_reservations_are_additive_in_both_modes_and_generation(self):
        for mode in ('imposition', 'tiles'):
            for bleed, marks, total in ((False, False, 0), (True, False, 5),
                                         (False, True, 5), (True, True, 10)):
                with self.subTest(mode=mode, bleed=bleed, marks=marks):
                    dialog = self.dialog(self.config(mode=mode, margin_enabled=bleed, crop_marks=marks,
                        margin_value=3, auto_orientation=False, positioned=True, offset_mm=[0, 0]))
                    panel = dialog.tiling_panel
                    settings = dialog.get_tiling_settings()
                    self.assertEqual(settings['margin_value'], 5)
                    self.assertEqual(reserved_margin_mm(settings), total)
                    self.assertEqual(panel.preview.bleed_mm, 5 if bleed else 0)
                    if mode == 'tiles':
                        self.assertEqual(panel.plan.margin_mm, total)
                        self.assertEqual(tiling_options(settings)['margin_mm'], total)
                        self.assertEqual(panel.preview.paper_rects()[0][0].topLeft(),
                                         panel.plan.tiles[0].region.topLeft() -
                                         QPointF(total * UNITS_PER_MM, total * UNITS_PER_MM))
                    else:
                        self.assertEqual(panel.assembler.edge_reserve_mm, total)
                        self.assertEqual((panel.assembler.margin_left_mm, panel.assembler.margin_top_mm), (total, total))
                        production = build_imposition_plan([({}, {})], dialog.get_imposition_settings())
                        self.assertEqual(production.assembler.edge_reserve_mm, total)
                        self.assertEqual(production.capacity, panel.assembler.capacity)
                    dialog.reject()

    def test_bleed_is_a_30_percent_red_ring_only_in_preview(self):
        for mode in ('imposition', 'tiles'):
            for view in (0, 1):
                with self.subTest(mode=mode, view=view):
                    dialog = self.dialog(self.config(mode=mode, margin_enabled=True,
                        crop_marks=True, auto_orientation=False, positioned=True, offset_mm=[0, 0]))
                    dialog.show()
                    panel = dialog.tiling_panel
                    panel.view_mode.setCurrentIndex(view)
                    self.ready(panel)
                    preview = panel.preview
                    image = preview.grab().toImage()
                    if view:
                        outer = preview.image_rect()
                        point = lambda x, y: (round(outer.left() + x * outer.width() / 210),
                                              round(outer.top() + y * outer.height() / 297))
                        base = preview.image.toImage()
                        self.assertEqual(base.pixelColor(2, 2), QColor('white'))
                    else:
                        paper = preview.paper_rects()[0][0]
                        def point(x, y):
                            mapped = preview.map_rect(QRectF(paper.left() + x * UNITS_PER_MM,
                                                            paper.top() + y * UNITS_PER_MM, 0, 0)).topLeft()
                            return round(mapped.x()), round(mapped.y())
                    for x, y in ((2.5, 40), (207.5, 40), (40, 2.5), (40, 294.5)):
                        color = image.pixelColor(*point(x, y))
                        self.assertEqual(color.red(), 255)
                        self.assertAlmostEqual(color.green(), 179, delta=1)
                        self.assertAlmostEqual(color.blue(), 179, delta=1)
                    self.assertEqual(image.pixelColor(*point(7.5, 40)), QColor('white'))
                    # A geração recebe a margem física, jamais a guia vermelha.
                    if panel.assembler:
                        card = QImage(10, 14, QImage.Format.Format_ARGB32)
                        card.fill(Qt.GlobalColor.white)
                        output = panel.assembler.render_sheet([card])
                    else:
                        output = panel.renderer.tile_image(panel.plan, panel.plan.tiles[0], scale=1)
                    self.assertEqual(output.pixelColor(round(2.5 * UNITS_PER_MM), round(40 * UNITS_PER_MM)), QColor('white'))
                    dialog.reject()

    def test_toggling_bleed_does_not_add_controls_or_move_the_layout(self):
        for mode in ('imposition', 'tiles'):
            dialog = self.dialog(self.config(mode=mode))
            dialog.show()
            self.ready(dialog.tiling_panel)
            QTest.qWait(20)
            panel = dialog.tiling_panel
            watched = (panel.margin_enabled, panel.crop_marks, panel.paper, panel.target_width, panel.preview)
            geometry = [widget.geometry() for widget in watched]
            count = panel.paper_form.rowCount()
            for _ in range(4):
                panel.margin_enabled.click()
                QTest.qWait(20)
                self.assertTrue(panel.margin.isHidden())
                self.assertEqual(panel.paper_form.rowCount(), count)
                self.assertEqual([widget.geometry() for widget in watched], geometry)
                self.assertEqual(panel.margin_enabled.height(), 33)
                self.assertEqual(panel.crop_marks.height(), 33)
            dialog.reject()

    def test_tiles_drag_into_unused_paper_without_clipping_to_previous_card_extent(self):
        for size in ([100, 140], [360, 504]):
            for bleed, marks in ((False, False), (True, False), (False, True), (True, True)):
                with self.subTest(size=size, bleed=bleed, marks=marks):
                    dialog = self.dialog(self.config(mode='tiles', target_size_mm=size,
                        margin_enabled=bleed, crop_marks=marks, auto_orientation=False,
                        positioned=True, offset_mm=[0, 0]))
                    dialog.show()
                    panel = dialog.tiling_panel
                    self.ready(panel)
                    preview = panel.preview
                    old_plan = panel.plan
                    papers = [preview.map_rect(rect) for rect, _ in preview.paper_rects()]
                    # Points just beyond the original right/bottom edges, in blank
                    # usable paper. After a 10 mm drag, both belong to the card.
                    probes = [(size[0] + 5, size[1] - 15), (size[0] - 15, size[1] + 5)]
                    def color_at(image, x, y):
                        point = preview.map_rect(QRectF(x * UNITS_PER_MM, y * UNITS_PER_MM, 0, 0)).center()
                        return image.pixelColor(round(point.x()), round(point.y()))
                    before = preview.grab().toImage()
                    for x, y in probes:
                        self.assertEqual(color_at(before, x, y), QColor('white'))
                    point = preview.map_rect(preview.drawing_bounds()).center().toPoint()
                    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
                    # Use physical units to avoid rounding the requested displacement
                    # in a small multi-sheet thumbnail; the actual drag handler runs.
                    panel._move_drawing(10 * UNITS_PER_MM, 10 * UNITS_PER_MM)
                    self.assertIs(panel.plan, old_plan)
                    self.assertEqual([preview.map_rect(rect) for rect, _ in preview.paper_rects()], papers)
                    during = preview.grab().toImage()
                    for x, y in probes:
                        self.assertEqual(color_at(during, x, y), QColor('#dcecf4'))
                    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
                    self.assertIsNot(panel.plan, old_plan)
                    self.assertEqual(len(panel.plan.tiles), len(old_plan.tiles))
                    # After release the map recenters, but the same card pixels remain.
                    after = preview.grab().toImage()
                    for x, y in probes:
                        self.assertEqual(color_at(after, x - 10, y - 10), QColor('#dcecf4'))
                    dialog.reject()

    def test_tiles_drag_still_clips_content_out_of_reserved_paper_edges(self):
        dialog = self.dialog(self.config(mode='tiles', margin_enabled=True, crop_marks=True,
            auto_orientation=False, positioned=True, offset_mm=[0, 0]))
        dialog.show()
        panel = dialog.tiling_panel
        self.ready(panel)
        preview = panel.preview
        paper = preview.paper_rects()[0][0]
        point = preview.map_rect(preview.drawing_bounds()).center().toPoint()
        QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
        panel._move_drawing(130 * UNITS_PER_MM, 170 * UNITS_PER_MM)
        image = preview.grab().toImage()
        for x, y, expected in ((202.5, 220, '#ffffff'), (207.5, 220, '#ffb3b3'),
                                (170, 289.5, '#ffffff'), (170, 294.5, '#ffb3b3')):
            mapped = preview.map_rect(QRectF(paper.left() + x * UNITS_PER_MM,
                                            paper.top() + y * UNITS_PER_MM, 0, 0)).center()
            actual = image.pixelColor(round(mapped.x()), round(mapped.y()))
            for channel in ('red', 'green', 'blue'):
                self.assertAlmostEqual(getattr(actual, channel)(), getattr(QColor(expected), channel)(), delta=1)
        QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
        dialog.reject()

    def test_crop_reserve_reduces_capacity_without_resizing_cards(self):
        dialog = self.dialog(self.config(mode='imposition', paper=[210, 297],
                                        target_size_mm=[100, 140], auto_orientation=False))
        panel = dialog.tiling_panel
        self.assertEqual(panel.assembler.capacity, 4)
        panel.margin_enabled.click()
        self.assertEqual(panel.assembler.capacity, 4)
        panel.crop_marks.click()
        self.assertEqual(panel.assembler.capacity, 1)
        self.assertEqual((panel.assembler.target_w_mm, panel.assembler.target_h_mm), (100, 140))
        self.assertEqual(panel.assembler.mark_len_mm, 3)
        self.assertEqual(panel.assembler.mark_gap_mm, 2)

    def test_tiles_use_both_sheet_margins_without_an_extra_content_overlap(self):
        dialog = self.dialog(self.config(mode='tiles', target_size_mm=[380, 532],
            margin_enabled=True, crop_marks=False, overlap_mm=17,
            auto_orientation=False, positioned=True, offset_mm=[0, 0]))
        panel = dialog.tiling_panel
        self.assertFalse(hasattr(panel, 'overlap'))
        settings = dialog.get_tiling_settings()
        self.assertEqual(settings['overlap_mm'], 0)
        self.assertEqual(panel.plan.overlap_mm, 0)
        self.assertEqual(tiling_options(settings)['overlap_mm'], 0)
        first, right, below = panel.plan.tiles[:3]
        papers = [panel.preview.sheet_rect(tile) for tile in (first, right, below)]
        # A4: 5 mm on each edge leaves 200 x 287 mm of useful paper.
        self.assertAlmostEqual(first.region.width() / UNITS_PER_MM, 200)
        self.assertAlmostEqual(first.region.height() / UNITS_PER_MM, 287)
        self.assertAlmostEqual((papers[0].right() - papers[1].left()) / UNITS_PER_MM, 10)
        self.assertAlmostEqual((papers[0].bottom() - papers[2].top()) / UNITS_PER_MM, 10)
        self.assertAlmostEqual(first.region.right(), right.region.left())
        self.assertAlmostEqual(first.region.bottom(), below.region.top())
        # With no margin there is no overlap at all, including after restoring
        # an older preset that still contains the removed numeric option.
        panel.margin_enabled.click()
        self.assertEqual(panel.plan.margin_mm, 0)
        self.assertEqual(panel.plan.overlap_mm, 0)
        panel.apply_configuration(dict(settings, overlap_mm=30))
        self.assertEqual(panel.configuration()['overlap_mm'], 0)
        self.assertEqual(panel.plan.overlap_mm, 0)

    def test_tiles_crop_marks_stay_close_to_artwork_after_positioning_and_dragging(self):
        for size in ([100, 140], [360, 504]):
            for bleed in (False, True):
                with self.subTest(size=size, bleed=bleed):
                    dialog = self.dialog(self.config(mode='tiles', target_size_mm=size,
                        margin_enabled=bleed, crop_marks=True, auto_orientation=False,
                        positioned=True, offset_mm=[40, 60]))
                    dialog.show()
                    panel = dialog.tiling_panel
                    self.ready(panel)
                    preview = panel.preview
                    def probes(rect):
                        gap_midpoint = 3.5 * UNITS_PER_MM  # 2 mm gap + half of the 3 mm line.
                        return [(rect.left(), rect.top() - gap_midpoint),
                                (rect.left() - gap_midpoint, rect.top()),
                                (rect.right(), rect.bottom() + gap_midpoint),
                                (rect.right() + gap_midpoint, rect.bottom())]
                    def assert_mark(image, x, y):
                        darkest = min(image.pixelColor(px, py).lightness()
                                      for px in range(round(x) - 1, round(x) + 2)
                                      for py in range(round(y) - 1, round(y) + 2))
                        self.assertLess(darkest, 128, f'Marca afastada da arte em ({x}, {y})')
                    for tile in (panel.plan.tiles[0], panel.plan.tiles[-1]):
                        visible = tile.region.intersected(panel.plan.drawing_bounds)
                        output = panel.renderer.tile_image(panel.plan, tile, scale=1)
                        margin = panel.plan.margin_mm * UNITS_PER_MM
                        for x, y in probes(visible):
                            assert_mark(output, x - tile.region.left() + margin,
                                        y - tile.region.top() + margin)
                    point = preview.map_rect(preview.drawing_bounds()).center().toPoint()
                    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
                    panel._move_drawing(20 * UNITS_PER_MM, 20 * UNITS_PER_MM)
                    image = preview.grab().toImage()
                    margin = panel.plan.margin_mm * UNITS_PER_MM
                    for tile in (panel.plan.tiles[0], panel.plan.tiles[-1]):
                        usable = preview.sheet_rect(tile).adjusted(margin, margin, -margin, -margin)
                        visible = usable.intersected(panel.plan.drawing_bounds.translated(preview._translation))
                        for x, y in probes(visible):
                            mapped = preview.map_rect(QRectF(x, y, 0, 0)).center()
                            assert_mark(image, mapped.x(), mapped.y())
                    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point)
                    self.ready(panel)
                    panel.view_mode.setCurrentIndex(1)
                    self.ready(panel)
                    tile = panel.plan.tiles[preview.selected]
                    scale = 900 / (max(panel.plan.paper) * UNITS_PER_MM)
                    expected = panel.renderer.tile_image(panel.plan, tile, scale=scale)
                    self.assertEqual(preview.image.toImage(), expected.convertToFormat(preview.image.toImage().format()))
                    dialog.reject()

    def test_existing_modes_adopt_fixed_reservations_and_legacy_totals_are_not_doubled(self):
        settings = self.config(mode='imposition', crop_marks=True, margin_enabled=False)
        self.assertEqual(reserved_margin_mm(settings), 5)
        settings.update(margin_enabled=True, margin_value=3)
        self.assertEqual(reserved_margin_mm(settings), 10)
        settings.pop('mode')
        # O formato anterior, sem modos separados, guardava a margem total.
        self.assertEqual(reserved_margin_mm(settings), 3)
        dialog = self.dialog(settings)
        self.assertEqual(dialog.get_tiling_settings()['margin_value'], 5)
        self.assertEqual(dialog.tiling_panel.assembler.edge_reserve_mm, 10)


if __name__ == '__main__':
    unittest.main()
