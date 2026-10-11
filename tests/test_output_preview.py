"""A prévia de saída precisa mostrar a folha e suas marcas, mesmo com um cartão."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtTest import QTest
from unittest.mock import patch

from core.tiling import UNITS_PER_MM

import test_output_layout as fixtures


class OutputPreviewTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.OutputLayoutTest.setUpClass.__func__)
    setUp = fixtures.OutputLayoutTest.setUp
    config = fixtures.OutputLayoutTest.config
    dialog = fixtures.OutputLayoutTest.dialog

    def ready(self, panel):
        for _ in range(100):
            if panel.preview.image is not None and not panel._preview_timer.isActive():
                return
            QTest.qWait(10)
        self.fail('A prévia não ficou pronta')

    @staticmethod
    def mark_points(assembler):
        a = assembler
        gap = a.mark_gap + a.mark_len / 2
        points = []
        for col in range(a.cols + 1):
            points += [(a._grid_x(col), a.margin_top - gap),
                       (a._grid_x(col), a._grid_y(a.rows) + gap)]
        for row in range(a.rows + 1):
            points += [(a.margin_left - gap, a._grid_y(row)),
                       (a._grid_x(a.cols) + gap, a._grid_y(row))]
        return points

    def assert_dark_near(self, image, x, y, threshold=245):
        pixels = [image.pixelColor(px, py).lightness() for px in range(round(x) - 2, round(x) + 3)
                  for py in range(round(y) - 2, round(y) + 3)]
        self.assertLess(min(pixels), threshold, f'Marca ausente em ({x:.1f}, {y:.1f})')

    def test_map_contains_crop_marks_for_one_or_multiple_cards(self):
        for width, capacity in ((190, 1), (90, 4)):
            with self.subTest(cards=capacity):
                dialog = self.dialog(self.config(target_size_mm=[width, width * 1.4],
                    margin_enabled=True, margin_value=10, crop_marks=True, auto_orientation=False))
                dialog.show()
                panel = dialog.tiling_panel
                self.ready(panel)
                self.assertEqual(panel.assembler.capacity, capacity)
                preview = panel.preview
                image = preview.grab().toImage()
                for x, y in self.mark_points(panel.assembler):
                    point = preview.map_rect(QRectF(x, y, 0, 0)).topLeft()
                    self.assert_dark_near(image, point.x(), point.y(), threshold=128)
                dialog.reject()

    def test_invalid_item_size_never_displays_card_as_sheet(self):
        for mode in (0, 1):
            with self.subTest(view_mode=mode):
                dialog = self.dialog()
                dialog.show()
                panel = dialog.tiling_panel
                panel.view_mode.setCurrentIndex(mode)
                self.ready(panel)
                panel.target_width.setValue(600)
                self.assertFalse(panel.valid)
                self.assertIsNone(panel.preview.image)
                self.assertFalse(panel._preview_timer.isActive())
                self.assertIn('não cabe', panel.preview.message.lower())
                # Corrigir o campo deve recuperar a folha sem reabrir a janela.
                panel.restore_size.click()
                self.ready(panel)
                self.assertTrue(panel.valid)
                self.assertFalse(panel.preview.message)
                self.assertTrue(panel.preview.has_layout)
                dialog.reject()

    def test_selected_sheet_with_one_card_keeps_paper_margins_and_all_crop_marks(self):
        dialog = self.dialog(self.config(target_size_mm=[190, 266], margin_enabled=True,
                                        margin_value=10, crop_marks=True, auto_orientation=False))
        dialog.show()
        panel = dialog.tiling_panel
        panel.view_mode.setCurrentIndex(1)
        self.ready(panel)
        image = panel.preview.image.toImage()
        a = panel.assembler
        self.assertEqual(a.capacity, 1)
        self.assertAlmostEqual(image.width() / image.height(), 210 / 297, delta=.002)
        self.assertEqual(image.pixelColor(2, 2).name(), '#ffffff')
        scale = 900 / max(a.sheet_w, a.sheet_h)
        for x, y in self.mark_points(a):
            self.assert_dark_near(image, x * scale, y * scale)
        # A área externa ao cartão é a mesma da montagem final em 300 DPI.
        base = panel._base_image.toImage()
        full_sheet = a.render_sheet([base])
        final = full_sheet.scaled(image.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        for x, y in self.mark_points(a):
            self.assert_dark_near(final, x * scale, y * scale)
        dialog.reject()

    def test_marks_move_with_cards_while_paper_stays_fixed(self):
        dialog = self.dialog(self.config(target_size_mm=[90, 126], margin_enabled=True,
                                        margin_value=10, crop_marks=True, auto_orientation=False))
        dialog.show()
        panel = dialog.tiling_panel
        self.ready(panel)
        preview = panel.preview
        paper = preview.map_rect(preview.paper_rects()[0][0])
        QTest.mousePress(preview, Qt.MouseButton.LeftButton,
                         pos=preview.map_rect(preview.drawing_bounds()).center().toPoint())
        panel._move_drawing(3 * UNITS_PER_MM, 8 * UNITS_PER_MM)
        self.assertEqual(preview.map_rect(preview.paper_rects()[0][0]), paper)
        image = preview.grab().toImage()
        for x, y in self.mark_points(panel.assembler):
            point = preview.map_rect(QRectF(QPointF(x, y) + preview._translation,
                                          QPointF(x, y) + preview._translation)).topLeft()
            self.assert_dark_near(image, point.x(), point.y())
        QTest.mouseRelease(preview, Qt.MouseButton.LeftButton)
        self.assertTrue(panel.valid)
        dialog.reject()

    def test_invalid_configuration_cancels_pending_preview(self):
        dialog = self.dialog()
        panel = dialog.tiling_panel
        self.assertTrue(panel._preview_timer.isActive())
        with patch.object(panel.renderer, 'preview') as render:
            panel.target_width.setValue(600)
            QTest.qWait(120)
            render.assert_not_called()
        self.assertIsNone(panel.preview.image)
        self.assertIn('não cabe', panel.preview.message.lower())
        dialog.reject()


if __name__ == '__main__':
    unittest.main()
