"""Expansão circular: cobertura alpha, retrocompatibilidade e orçamento."""
from copy import deepcopy
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from core.text_effects import (_spread_mask, normalize_shadow, paint_object_shadow,
                               new_shadow_cache, MAX_MASK_PIXELS, MAX_MASK_SIDE)
from core.text_safety import validate_text_shadow
from features.generator.manager import _bounded_worker_count


class ShadowSpreadTest(unittest.TestCase):
    def source(self):
        image = QImage(31, 29, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        for x, y, alpha in ((15, 14, 100), (8, 10, 200), (10, 21, 45)):
            image.setPixelColor(x, y, QColor(220, 50, 100, alpha))
        return image

    def test_circular_expansion_matches_maximum_alpha_without_darkening_or_square_corners(self):
        source = self.source()
        before = bytes(source.constBits())
        for radius in (1, 3, 8):
            with self.subTest(radius=radius):
                grown = _spread_mask(source, radius)
                for y in range(source.height()):
                    for x in range(source.width()):
                        expected = max(source.pixelColor(xx, yy).alpha()
                                       for yy in range(max(0, y-radius), min(source.height(), y+radius+1))
                                       for xx in range(max(0, x-radius), min(source.width(), x+radius+1))
                                       if (xx-x)**2 + (yy-y)**2 <= radius**2)
                        self.assertEqual(grown.pixelColor(x, y).alpha(), expected)
        self.assertEqual(bytes(source.constBits()), before)

    def test_fractional_spread_changes_smoothly_and_zero_preserves_original_image(self):
        source = self.source()
        self.assertIs(_spread_mask(source, 0), source)
        lower, middle, upper = (_spread_mask(source, radius) for radius in (1, 1.5, 2))
        for y in range(source.height()):
            for x in range(source.width()):
                a, b = lower.pixelColor(x, y).alpha(), upper.pixelColor(x, y).alpha()
                self.assertAlmostEqual(middle.pixelColor(x, y).alpha(), (a+b)/2, delta=1)

    def test_missing_spread_is_zero_and_does_not_change_old_shadow_pixels(self):
        data = dict(shadow=dict(enabled=True, distance=5, blur=3))
        self.assertEqual(normalize_shadow(data['shadow'])['spread'], 0)
        validate_text_shadow(data['shadow'])
        source = self.source()
        def render(value):
            image = QImage(70, 70, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            try:
                paint_object_shadow(painter, QRectF(20, 20, 31, 29), value,
                    lambda target: target.drawImage(20, 20, source), ('source',))
            finally:
                painter.end()
            return image
        explicit = deepcopy(data); explicit['shadow']['spread'] = 0
        self.assertEqual(render(data), render(explicit))
        explicit['shadow']['spread'] = 3
        self.assertNotEqual(render(data), render(explicit))

    def test_large_sources_keep_all_buffers_bounded_and_expansion_radius_limited(self):
        from core import text_effects
        image = QImage(30, 30, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            with patch.object(text_effects, '_image', wraps=text_effects._image) as allocate, \
                    patch.object(text_effects, '_spread_mask', wraps=text_effects._spread_mask) as spread:
                paint_object_shadow(painter, QRectF(0, 0, 100_000, 20_000),
                    dict(shadow=dict(enabled=True, spread=120, blur=120)),
                    lambda target: target.fillRect(QRectF(0, 0, 100_000, 20_000), Qt.GlobalColor.black),
                    ('large',), new_shadow_cache())
            for call in allocate.call_args_list:
                w, h = call.args[:2]
                self.assertLessEqual(w*h, MAX_MASK_PIXELS)
                self.assertLessEqual(max(w, h), MAX_MASK_SIDE)
            self.assertLessEqual(spread.call_args.args[1], 8)
        finally:
            painter.end()

    def test_invalid_spread_is_rejected_and_worker_budget_covers_expansion_buffers(self):
        for invalid in (-1, 121, True, '1', math.inf, math.nan):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_text_shadow(dict(enabled=True, spread=invalid))
        def workers(spread):
            renderer = SimpleNamespace(tpl=dict(canvas_size=dict(w=1000, h=1000),
                                       boxes=[dict(shadow=dict(enabled=True, spread=spread))]))
            return _bounded_worker_count(6, [renderer], memory_budget=128*1024**2, jpeg=True)
        self.assertLess(workers(3), workers(0))


if __name__ == '__main__':
    unittest.main()
