"""Sombras de objetos: desenho comum, transparência, histórico e persistência."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtTest import QTest

from core.fornax_container import save_public_fornax, open_public_fornax
from core.model_document import normalize_model_document, adapt_model_page, validate_model_document, add_model_table
from core.table_model import new_table, validate_table
from core.text_effects import normalize_shadow, MAX_MASK_PIXELS, paint_object_shadow, new_shadow_cache
from features.editor.canvas_items import RectangleItem, ImageItem
from features.editor.table_item import TableItem
from features.generator.renderer import NativeRenderer
from features.generator.manager import _bounded_worker_count
import test_object_floating as objects


class ObjectShadowTest(unittest.TestCase):
    setUpClass = classmethod(objects.ObjectFloatingTest.setUpClass.__func__)
    tearDownClass = classmethod(objects.ObjectFloatingTest.tearDownClass.__func__)
    setUp = objects.ObjectFloatingTest.setUp
    tearDown = objects.ObjectFloatingTest.tearDown
    editor = objects.ObjectFloatingTest.editor
    drain = objects.ObjectFloatingTest.drain
    select = objects.ObjectFloatingTest.select

    def shadow(self, **changes):
        return normalize_shadow(dict(enabled=True, distance=30., blur=6., spread=6.25, color='#b02050', **changes))

    def document(self, kind, **changes):
        source = dict(canvas_size=dict(w=900, h=650))
        if kind == 'table':
            item = new_table(3, 3, width=330, height=240)
            item.update(x=200, y=180, layer_id=1, opacity=.65)
            item['cells'][0]['html'] = '<p>Texto</p>'
            source['tables'] = [item]
        elif kind == 'image':
            path = self.root/'alpha.png'
            image = QImage(80, 60, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setPen(QPen(QColor('#224488'), 10))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(5, 5, 70, 50)
            painter.end(); image.save(str(path))
            item = dict(path=str(path), x=200, y=180, width=80, height=60, layer_id=1, opacity=.65)
            source['images'] = [item]
        else:
            item = dict(x=200, y=180, width=180, height=120, layer_id=1,
                        shape_type=kind, fill_color='#556688', fill_opacity=.5, opacity=.65,
                        outline_enabled=True, outline_color='#112244', outline_opacity=.7,
                        outline_width=8, outline_position='outside', outline_join='round', corner_radius=15)
            source['shapes'] = [item]
        item.update(shadow=self.shadow(), **changes)
        if kind == 'table':
            source.pop('tables')
            return add_model_table(normalize_model_document(source), item)
        return normalize_model_document(source)

    def scene_image(self, window, *, clear_selection=True):
        if clear_selection:
            window.scene.clearSelection()
        self.drain()
        for item in window.scene.items():
            if isinstance(item, TableItem):
                item.overlays_enabled = False
        image = QImage(900, 650, QImage.Format.Format_ARGB32)
        image.setDotsPerMeterX(3780); image.setDotsPerMeterY(3780)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            window.scene.render(painter, QRectF(0, 0, 900, 650), QRectF(0, 0, 900, 650))
        finally:
            painter.end()
        return image

    def test_editor_preview_and_final_match_for_shapes_images_and_whole_tables(self):
        for kind, rotation in (('rectangle', 0), ('ellipse', 17), ('line', 9), ('image', 13), ('table', 8)):
            with self.subTest(kind=kind):
                window = self.editor(self.document(kind, rotation=rotation))
                editor = self.scene_image(window)
                template = adapt_model_page(window._document_with_active_page())
                renderer = NativeRenderer(template)
                for output in (renderer.render_preview_image(), renderer.render_to_qimage({}, {})):
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(bytes(editor.constBits()), bytes(output.constBits()))), 1)
                plain = deepcopy(template)
                for collection in ('images', 'shapes', 'tables'):
                    for item in plain.get(collection, []):
                        item.pop('shadow', None)
                self.assertNotEqual(editor, NativeRenderer(plain).render_preview_image())

    def test_image_shadow_follows_alpha_instead_of_the_rectangular_container(self):
        template = adapt_model_page(self.document('image'))
        template['images'][0]['shadow'].update(distance=100, blur=0, spread=3, angle=0)
        image = NativeRenderer(template).render_preview_image()
        self.assertEqual(image.pixelColor(340, 210), QColor('white'))
        self.assertNotEqual(image.pixelColor(340, 185), QColor('white'))

    def test_masked_transparent_shape_and_clipped_image_keep_editor_export_fidelity(self):
        source = self.document('image')
        page = source['pages'][0]
        page['shapes'] = [dict(object_id='shape:2', layer_id=2, x=180, y=170, width=130, height=100,
                              shape_type='ellipse', fill_opacity=0., shadow=self.shadow())]
        page['images'][0].update(mask_shape_id='shape:2', x=15, y=10, rotation=12)
        page['layer_order'] = ['shape:2', page['images'][0]['object_id']]
        source = normalize_model_document(source)
        window = self.editor(source)
        image = self.scene_image(window)
        template = adapt_model_page(window._document_with_active_page())
        output = NativeRenderer(template).render_preview_image()
        self.assertLessEqual(max(abs(a-b) for a,b in zip(bytes(image.constBits()), bytes(output.constBits()))), 1)

    def test_controls_live_preview_undo_duplicate_and_file_reopen_for_each_kind(self):
        for kind, collection, cls in (('image', 'images', ImageItem), ('rectangle', 'shapes', RectangleItem),
                                      ('table', 'tables', TableItem)):
            with self.subTest(kind=kind):
                window = self.editor(self.document(kind))
                item = next(i for i in window.scene.items() if isinstance(i, cls)
                            and not getattr(i, 'is_document_background', False))
                self.select(window, item); window.save_snapshot()
                controls = window.table_panel.shadow_controls if cls is TableItem else window.object_shadow_controls
                self.assertTrue(controls.isVisible())
                index = window.history._current_index
                controls.spread.setFocus()
                from features.editor.canvas_items import mm_to_px
                for value in (.25, .30, .35):
                    controls.spread.setValue(value)
                    self.assertAlmostEqual(item.shadow['spread'], mm_to_px(value))
                    self.assertEqual(window.history._current_index, index)
                QTest.keyClick(controls.spread, Qt.Key.Key_Return); self.drain()
                self.assertEqual(window.history._current_index, index+1)
                window.undo(); self.drain()
                self.assertEqual(window.get_current_scene_state()[collection][0]['shadow']['spread'], 6.25)
                window.redo(); self.drain()
                self.assertAlmostEqual(window.get_current_scene_state()[collection][0]['shadow']['spread'], mm_to_px(.35))
                expected = deepcopy(window.get_current_scene_state()[collection][0]['shadow'])
                window.duplicate_selected(); self.drain()
                copies = [i for i in window.scene.items() if type(i) is cls and not getattr(i, 'is_document_background', False)]
                self.assertEqual(len(copies), 2)
                self.assertIsNot(copies[0].shadow, copies[1].shadow)
                document = window._document_with_active_page()
                path = self.root/f'{kind}-shadow.fornax'
                save_public_fornax(document, path)
                reopened = open_public_fornax(path).document()
                entries = [i for i in reopened['pages'][0][collection] if not i.get('is_document_background')]
                self.assertTrue(all(entry['shadow'] == expected for entry in entries))
                window._load_document_into_scene(reopened)
                self.assertTrue(all(i.shadow == expected for i in window.scene.items()
                                    if type(i) is cls and not getattr(i, 'is_document_background', False)))

    def test_disabled_shadow_preserves_pixels_for_every_object_kind(self):
        for kind in ('image', 'rectangle', 'ellipse', 'table'):
            template = adapt_model_page(self.document(kind))
            plain = deepcopy(template)
            for collection in ('images', 'shapes', 'tables'):
                for item in plain.get(collection, []):
                    item.pop('shadow', None)
            expected = NativeRenderer(plain).render_preview_image()
            for value in ({'enabled': False}, {'opacity': 0}):
                changed = deepcopy(template)
                for collection in ('images', 'shapes', 'tables'):
                    for item in changed.get(collection, []):
                        if 'shadow' in item:
                            item['shadow'].update(value)
                self.assertEqual(NativeRenderer(changed).render_preview_image(), expected)

    def test_table_text_shadow_updates_during_editing_without_publishing_each_key(self):
        from core.table_paint import paint_table_shadow
        source = self.document('table')
        source['pages'][0]['tables'][0]['style']['fill_opacity'] = 0
        source['pages'][0]['tables'][0]['border']['opacity'] = 0
        source['pages'][0]['tables'][0]['cells'][0]['html'] = '<p>I</p>'
        window = self.editor(source)
        item = next(i for i in window.scene.items() if isinstance(i, TableItem))

        def shadow_image(layout):
            image = QImage(900, 650, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            try:
                paint_table_shadow(painter, layout)
            finally:
                painter.end()
            return image

        old_shadow = shadow_image(item.layout)
        revision = item.presentation_revision
        window.table_edit.begin(item, (0, 0))
        cursor = window.table_edit.text.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText('WW')
        window.table_edit.text.setTextCursor(cursor)
        with patch('features.editor.table_item.paint_table_shadow', wraps=paint_table_shadow) as paint:
            self.scene_image(window, clear_selection=False)
            live_shadow = shadow_image(paint.call_args.args[1])
        self.assertEqual(item.presentation_revision, revision)
        self.assertNotEqual(live_shadow, old_shadow)
        window.table_edit.finish()
        self.assertEqual(shadow_image(item.layout), live_shadow)

    def test_mask_shadow_refreshes_after_child_motion_resize_and_opacity(self):
        source = self.document('image')
        page = source['pages'][0]
        page['shapes'] = [dict(object_id='shape:2', layer_id=2, x=180, y=170, width=180, height=150,
                              shape_type='rectangle', fill_opacity=0., shadow=self.shadow())]
        page['images'][0].update(mask_shape_id='shape:2', x=15, y=10)
        page['layer_order'] = ['shape:2', page['images'][0]['object_id']]
        window = self.editor(normalize_model_document(source))
        child = next(i for i in window.scene.items() if type(i) is ImageItem)
        before = self.scene_image(window)
        child.setPos(55, 35); child.resize_custom(100, 80); child.setOpacity(.4)
        changed = self.scene_image(window)
        template = adapt_model_page(window._document_with_active_page())
        output = NativeRenderer(template).render_preview_image()
        self.assertNotEqual(before, changed)
        self.assertLessEqual(max(abs(a-b) for a,b in zip(bytes(changed.constBits()), bytes(output.constBits()))), 1)

    def test_object_shadows_obey_bounded_masks_and_reuse_offset_cache(self):
        from core import text_effects
        cache = new_shadow_cache(); output = QImage(200, 200, QImage.Format.Format_ARGB32)
        output.fill(Qt.GlobalColor.white); painter = QPainter(output)
        try:
            with patch.object(text_effects, '_blur', wraps=text_effects._blur) as blur:
                for angle in (0, 90, 180):
                    data = dict(shadow=self.shadow(angle=angle))
                    paint_object_shadow(painter, QRectF(0, 0, 1_000_000, 1_000_000), data,
                        lambda target: target.fillRect(QRectF(0, 0, 1_000_000, 1_000_000), Qt.GlobalColor.black),
                        ('fixed-source',), cache)
                self.assertEqual(blur.call_count, 1)
                mask = blur.call_args.args[0]
                self.assertLessEqual(mask.width()*mask.height(), MAX_MASK_PIXELS)
        finally:
            painter.end()

    def test_validation_and_worker_budget_cover_images_shapes_and_tables(self):
        for kind, collection in (('image', 'images'), ('rectangle', 'shapes'), ('table', 'tables')):
            document = self.document(kind)
            document['pages'][0][collection][0]['shadow']['blur'] = float('inf')
            with self.assertRaises(ValueError):
                validate_model_document(document)
            if kind == 'table':
                with self.assertRaises(ValueError):
                    validate_table(document['pages'][0]['tables'][0])
            renderer = SimpleNamespace(tpl=dict(canvas_size=dict(w=1000, h=1000), **{collection:[dict(shadow=self.shadow())]}))
            self.assertLess(_bounded_worker_count(6, [renderer], memory_budget=64*1024**2, jpeg=True), 6)


if __name__ == '__main__':
    unittest.main()
