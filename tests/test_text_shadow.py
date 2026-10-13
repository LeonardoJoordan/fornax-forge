"""Fidelidade, escala, limites e invalidação da sombra externa."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from core.text_effects import normalize_shadow, paint_text_shadow, new_shadow_cache, MAX_MASK_PIXELS
from core.text_layout import build_document, text_geometry
from core.ui_font import install_ui_font
from features.generator.renderer import NativeRenderer
from test_text_fidelity import editor_text_image, editor_box


def data(**kwargs):
    return dict(html='<p>Ação <b>Texto</b><br/><i>Çgj</i></p>', rich_text_version=1,
                font_family='Inter 18pt', font_size=24, font_color='#2255aa',
                x=90, y=80, w=300, h=180,
                shadow=normalize_shadow(dict(enabled=True, color='#af0022', blur=6., distance=18.)),
                **kwargs)


def render(box, width=600, height=400):
    return NativeRenderer(dict(canvas_size=dict(w=width, h=height), boxes=[box])).render_to_qimage({}, {})


class TextShadowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_ui_font(cls.app)

    def test_editor_preview_output_match_without_moving_text(self):
        for angle, blur, rotation in ((45, 0, 0), (225, 6, 13), (90, 30, 0)):
            with self.subTest(angle=angle, blur=blur):
                box = data(rotation=rotation, align='center', vertical_align='bottom')
                box['shadow'].update(angle=angle, blur=blur)
                plain = {**box, 'shadow': {}}
                self.assertEqual(text_geometry(build_document(box, box['html']), box),
                                 text_geometry(build_document(plain, plain['html']), plain))
                editor = editor_text_image(box)
                renderer = NativeRenderer(dict(canvas_size=dict(w=600, h=400), boxes=[box]))
                self.assertEqual(editor, renderer.render_preview_image({}))
                self.assertEqual(editor, renderer.render_to_qimage({}, {}))
                self.assertNotEqual(editor, editor_text_image(plain))

    def test_disabled_and_transparent_shadow_preserve_pixels(self):
        box = data()
        plain = render({**box, 'shadow': {}})
        for change in ({'enabled': False}, {'opacity': 0}):
            altered = deepcopy(box)
            altered['shadow'].update(change)
            self.assertEqual(plain, render(altered))

    def test_shadow_extends_outside_box_and_scene_bounds_cover_it(self):
        box = data(align='right')
        box['shadow'].update(distance=80, angle=0)
        item = editor_box(box)
        self.assertGreater(item.text_item.boundingRect().right(), box['w']+70)
        original = render({**box, 'shadow': {}})
        image = render(box)
        self.assertNotEqual(original.copy(390, 70, 100, 200), image.copy(390, 70, 100, 200))

    def test_clipped_tiles_have_no_shadow_seams(self):
        box = data(rotation=9)
        renderer = NativeRenderer(dict(canvas_size=dict(w=600, h=400), boxes=[box]))
        full = renderer.render_to_qimage({}, {})
        for left in (0, 200, 400):
            tile = QImage(200, 400, QImage.Format.Format_ARGB32)
            tile.setDotsPerMeterX(3780); tile.setDotsPerMeterY(3780)
            tile.fill(Qt.GlobalColor.white)
            painter = QPainter(tile)
            try:
                painter.translate(-left, 0)
                painter.setClipRect(QRectF(left, 0, 200, 400))
                renderer._paint_card(painter, {}, row_plain={})
            finally:
                painter.end()
            crop = full.copy(left, 0, 200, 400)
            # O rasterizador Qt pode arredondar um canal em 1/255 ao recortar
            # uma imagem girada. Não pode perder conteúdo nem criar faixa.
            self.assertLessEqual(max(abs(a-b) for a, b in
                zip(bytes(crop.constBits()), bytes(tile.constBits()))), 1)

    def test_cache_reuses_mask_but_content_color_and_blur_invalidate_it(self):
        from core import text_effects
        cache = new_shadow_cache()
        box = data()
        target = QImage(600, 400, QImage.Format.Format_ARGB32)
        target.fill(Qt.GlobalColor.white)
        painter = QPainter(target)
        try:
            with patch.object(text_effects, '_blur', wraps=text_effects._blur) as blur:
                for i in range(3):
                    doc = build_document(box, box['html'])
                    paint_text_shadow(painter, doc, box, cache)
                self.assertEqual(blur.call_count, 1)
                for change in ('color', 'blur', 'html'):
                    if change == 'html':
                        box['html'] = '<p>Outro texto</p>'
                    else:
                        box['shadow'][change] = '#00ff00' if change == 'color' else 20
                    paint_text_shadow(painter, build_document(box, box['html']), box, cache)
                self.assertEqual(blur.call_count, 4)
        finally:
            painter.end()

    def test_huge_text_cannot_allocate_a_full_canvas_mask(self):
        from core import text_effects
        box = data()
        box['w'] = 100000
        box['shadow']['blur'] = 120
        target = QImage(20, 20, QImage.Format.Format_ARGB32)
        target.fill(Qt.GlobalColor.white)
        painter = QPainter(target)
        try:
            with patch.object(text_effects, '_image', wraps=text_effects._image) as allocation:
                paint_text_shadow(painter, build_document(box, box['html']), box)
                self.assertTrue(allocation.called)
                self.assertTrue(all(w*h <= MAX_MASK_PIXELS for w, h in
                                    (call.args for call in allocation.call_args_list)))
        finally:
            painter.end()

    def test_invalid_persisted_effect_is_rejected(self):
        from core.model_document import normalize_model_document, ModelValidationError
        for invalid in (None, [], {'enabled': 1}, {'color': 'red'}, {'blur': float('nan')},
                        {'distance': 10**9}, {'opacity': -1}):
            with self.subTest(invalid=invalid), self.assertRaises(ModelValidationError):
                box = data()
                box['shadow'] = invalid
                normalize_model_document(dict(canvas_size=dict(w=600, h=400), boxes=[box]))

    def test_allocation_failure_cannot_silently_export_missing_text(self):
        with patch('features.generator.renderer.paint_text_shadow', side_effect=MemoryError('sombra')):
            with self.assertRaises(MemoryError):
                render(data())

    def test_worker_budget_includes_shadow_buffers(self):
        from features.generator.manager import _bounded_worker_count
        from types import SimpleNamespace
        without = SimpleNamespace(tpl={'canvas_size': {'w': 1000, 'h': 1000}})
        with_shadow = SimpleNamespace(tpl={**without.tpl, 'boxes': [data()]})
        budget = 64 * 1024**2
        self.assertEqual(_bounded_worker_count(6, [without], memory_budget=budget, jpeg=True), 6)
        self.assertLess(_bounded_worker_count(6, [with_shadow], memory_budget=budget, jpeg=True), 6)


if __name__ == '__main__':
    unittest.main()
