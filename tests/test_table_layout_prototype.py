"""Contratos da prova técnica; não testa uma tabela integrada ao produto."""
from copy import deepcopy
import math
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent / 'performance'))

from PySide6.QtCore import Qt, QPointF, QRectF, QCoreApplication, QEvent
from PySide6.QtGui import QColor, QImage, QPainter, QTextCursor, QTransform
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from core.ui_font import install_ui_font
from table_layout_prototype import (
    FixedTableLayout, PrototypeTableItem, native_qtexttable, render_image, specimen,
)
from table_fixtures import cases, validate_fixture


class TablePrototypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_ui_font(cls.app)
        cls.callback_errors = []
        cls.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: cls.callback_errors.append(str(value))

    @classmethod
    def tearDownClass(cls):
        sys.excepthook = cls.previous_hook

    def setUp(self):
        self.data = specimen()
        self.layout = FixedTableLayout(self.data)

    def tearDown(self):
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(self.callback_errors, [])

    def test_fixed_dimensions_independent_of_text_and_device(self):
        self.assertAlmostEqual(self.layout.width, 160 * 300 / 25.4)
        self.assertAlmostEqual(self.layout.height, 80 * 300 / 25.4)
        longer = deepcopy(self.data)
        longer['cells'][1]['html'] = '<p>' + '<br>'.join(['Texto longo'] * 100) + '</p>'
        other = FixedTableLayout(longer)
        self.assertEqual((self.layout.width, self.layout.height), (other.width, other.height))
        self.assertEqual([e.rect for e in self.layout.cells], [e.rect for e in other.cells])
        self.assertTrue(other.cells[1].overflow_y)
        self.assertEqual(other.device.logicalDpiX(), 300)

    def test_merge_has_one_anchor_and_canonical_edges(self):
        self.assertEqual(len(self.layout.cells), 10)
        self.assertEqual(len(self.layout.edges), 40)
        self.assertEqual(len(self.layout.visible_edges), 33)
        for col in range(4):
            self.assertEqual(self.layout.anchors[0, col], (0, 0))
        for row in (2, 3):
            for col in (2, 3):
                self.assertEqual(self.layout.anchors[row, col], (2, 2))
        self.assertNotIn(('h', 3, 2), self.layout.visible_edges)
        self.assertIn(('h', 3, 2), self.layout.edges)
        # Ordem de pintura não muda com ordem de armazenamento das células.
        reordered = deepcopy(self.data)
        reordered['cells'].reverse()
        self.assertEqual(render_image(self.layout, .5), render_image(FixedTableLayout(reordered), .5))

    def test_vertical_horizontal_alignment_and_manual_automatic_wrap(self):
        top, center, bottom = self.layout.cells[1], self.layout.cells[3], self.layout.cells[4]
        self.assertEqual(top.offset_y, 0)
        self.assertAlmostEqual(center.offset_y, (center.inner.height()-center.text_height)/2)
        self.assertAlmostEqual(bottom.offset_y, bottom.inner.height()-bottom.text_height)
        self.assertGreater(center.lines[0][2], 0)
        self.assertGreater(bottom.lines[0][2], center.lines[0][2])
        self.assertEqual(len(self.layout.cells[2].lines), 2)  # <br> manual.
        self.assertGreater(len(self.layout.cells[5].lines), 1)  # automática.
        nowrap = self.layout.cells[6]
        self.assertEqual(len(nowrap.lines), 1)
        self.assertTrue(nowrap.overflow_x)
        self.assertTrue(self.layout.cells[8].overflow_y)

    def test_clipping_never_paints_into_neighbour_or_outside_table(self):
        empty = deepcopy(self.data)
        empty['cells'][1]['html'] = '<p></p>'
        empty['cells'][1]['wrap'] = False
        baseline = render_image(FixedTableLayout(empty), .5)
        empty['cells'][1]['html'] = '<p>' + '<br>'.join(['M' * 150] * 30) + '</p>'
        layout = FixedTableLayout(empty)
        image = render_image(layout, .5)
        self.assertTrue(layout.cells[1].overflow_x and layout.cells[1].overflow_y)
        allowed = layout.cells[1].inner.translated(24, 24)
        allowed = QRectF(allowed.x()*.5, allowed.y()*.5, allowed.width()*.5, allowed.height()*.5)
        # Cada pixel fora da região de texto permanece rigorosamente igual.
        a, b = bytes(baseline.constBits()), bytes(image.constBits())
        differences = 0
        for y in range(image.height()):
            for x in range(image.width()):
                start = y * image.bytesPerLine() + x * 4
                if a[start:start+4] != b[start:start+4]:
                    differences += 1
                    self.assertTrue(allowed.adjusted(-1, -1, 1, 1).contains(QPointF(x+.5, y+.5)), (x, y))
        self.assertGreater(differences, 100)

    def test_rich_text_literal_placeholder_and_html_roundtrip(self):
        title_cursor = QTextCursor(self.layout.cells[0].document)
        title_cursor.setPosition(1)
        self.assertEqual(title_cursor.charFormat().foreground().color().name(), '#ffffff')
        entry = self.layout.cells[1]
        self.assertEqual(entry.document.toPlainText(), '{nome}\nParticipante')
        cursor = QTextCursor(entry.document)
        cursor.setPosition(1)
        self.assertGreater(cursor.charFormat().fontWeight(), 400)
        copy = deepcopy(self.data)
        copy['cells'][1]['html'] = entry.document.toHtml()
        roundtrip = FixedTableLayout(copy).cells[1]
        self.assertEqual(roundtrip.document.toPlainText(), entry.document.toPlainText())
        self.assertEqual(roundtrip.lines, entry.lines)
        self.assertEqual(roundtrip.text_height, entry.text_height)

    def test_untrusted_html_does_not_load_resources(self):
        self.data['cells'][1]['html'] = '<p>Seguro<img src="file:///etc/passwd"></p>'
        layout = FixedTableLayout(self.data)
        self.assertEqual(layout.cells[1].document.toPlainText(), 'Seguro')
        self.assertNotIn('<img', layout.cells[1].document.toHtml())
        self.assertIsNone(layout.cells[1].document.loadResource(2, 'file:///etc/passwd'))

    def test_no_wrap_keeps_manual_newlines_and_individual_rich_colors(self):
        self.data['cells'][1].update(wrap=False, html='<p><span style="color:#c02040"><b>Ω𝄞</b></span><br>Manual</p>')
        entry = FixedTableLayout(self.data).cells[1]
        self.assertEqual(len(entry.lines), 2)
        self.assertEqual(entry.document.toPlainText(), 'Ω𝄞\nManual')
        cursor = QTextCursor(entry.document)
        cursor.setPosition(1)
        self.assertEqual(cursor.charFormat().foreground().color().name(), '#c02040')
        self.assertGreater(cursor.charFormat().fontWeight(), 400)

    def test_partial_selection_expands_merges_and_half_open_hit(self):
        area = self.layout.selection((1, 1), (2, 2))
        self.assertEqual(area, QRectF(self.layout.x[1], self.layout.y[1],
                                    self.layout.width-self.layout.x[1], self.layout.height-self.layout.y[1]))
        self.assertIsNone(self.layout.hit(QPointF(self.layout.width, 20)))
        self.assertIsNone(self.layout.hit(QPointF(-.1, 20)))
        self.assertEqual(self.layout.hit(QPointF(self.layout.x[3]+5, self.layout.y[3]+5)), (2, 2))

    def test_zoom_rotation_hit_testing_and_real_canvas_selection(self):
        scene = QGraphicsScene()
        item = PrototypeTableItem(self.layout)
        scene.addItem(item)
        self.assertEqual(len(scene.items()), 1)
        self.assertEqual(item.childItems(), [])
        item.setPos(140, 90)
        item.setTransformOriginPoint(self.layout.width/2, self.layout.height/2)
        for scale in (.25, .5, 1, 2):
            for angle in (0, 30, 90, -45):
                item.setRotation(angle)
                viewport = QTransform.fromScale(scale, scale)
                device = item.deviceTransform(viewport)
                inverse, valid = device.inverted()
                self.assertTrue(valid)
                for entry in self.layout.cells:
                    point = entry.rect.center()
                    origin = item.transformOriginPoint()
                    dx, dy = point.x()-origin.x(), point.y()-origin.y()
                    radians = math.radians(angle)
                    scene_point = QPointF(item.x()+origin.x()+dx*math.cos(radians)-dy*math.sin(radians),
                                          item.y()+origin.y()+dx*math.sin(radians)+dy*math.cos(radians))
                    expected_device = viewport.map(scene_point)
                    actual_device = device.map(point)
                    self.assertAlmostEqual(actual_device.x(), expected_device.x())
                    self.assertAlmostEqual(actual_device.y(), expected_device.y())
                    recovered = inverse.map(expected_device)
                    self.assertEqual(self.layout.hit(recovered), (entry.spec['row'], entry.spec['column']))
        item.setRotation(30)
        view = QGraphicsView(scene)
        view.resize(900, 650)
        view.show()
        view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.app.processEvents()
        start = view.mapFromScene(item.mapToScene(self.layout.cells[2].rect.center()))
        end = view.mapFromScene(item.mapToScene(self.layout.cells[7].rect.center()))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(item.active, self.layout.selection((1, 1), (2, 2)))
        self.assertIsNone(item.drag_anchor)
        self.assertIsNone(scene.mouseGrabberItem())
        view.close()

    def test_scene_and_export_paint_match_without_selection_overlay(self):
        scene = QGraphicsScene()
        scene.addItem(PrototypeTableItem(self.layout))
        expected = render_image(self.layout, .5)
        image = QImage(expected.size(), expected.format())
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            source = QRectF(-24, -24, self.layout.width+48, self.layout.height+48)
            target = QRectF(0, 0, source.width()*.5, source.height()*.5)
            scene.render(painter, target, source, Qt.AspectRatioMode.IgnoreAspectRatio)
        finally:
            painter.end()
        self.assertEqual(image, expected)

    def test_painting_moving_scaling_do_not_rebuild_text_or_mutate_data(self):
        before = self.layout.measurements()
        input_before = deepcopy(self.data)
        scene = QGraphicsScene()
        item = PrototypeTableItem(self.layout)
        scene.addItem(item)
        for index in range(5):
            item.setPos(index * 20, index * 10)
            render_image(self.layout, .25 + index*.25)
        self.assertEqual(before, self.layout.measurements())
        self.assertEqual(self.data, input_before)
        self.assertEqual(self.layout.build_count, 10)

    def test_all_acceptance_fixtures_have_fixed_geometry_and_safe_layout(self):
        for fixture in cases():
            validate_fixture(fixture)
            for page in fixture['pages']:
                for spec in page['tables']:
                    with self.subTest(fixture=fixture['id'], page=page['page']):
                        layout = FixedTableLayout(spec)
                        self.assertEqual(layout.build_count, len(spec['cells']))
                        self.assertEqual(len(layout.anchors), spec['rows'] * spec['columns'])
                        self.assertFalse(render_image(layout, .25).isNull())

    def test_native_table_auto_grows_and_fixed_total_height_does_not_clip_each_cell(self):
        short = deepcopy(self.data)
        short['cells'][1]['html'] = '<p>Curto</p>'
        long = deepcopy(short)
        long['cells'][1]['html'] = '<p>' + '<br>'.join(['Texto longo']*40) + '</p>'
        short_doc, short_table, short_device = native_qtexttable(short, fixed_height=False)
        long_doc, long_table, long_device = native_qtexttable(long, fixed_height=False)
        self.assertGreater(long_doc.size().height(), short_doc.size().height()+1000)
        fixed_doc, fixed_table, fixed_device = native_qtexttable(long)
        fixed_doc.size()
        text_rect = fixed_doc.documentLayout().blockBoundingRect(fixed_table.cellAt(1, 0).firstCursorPosition().block())
        self.assertGreater(text_rect.bottom(), self.layout.y[2])
        self.assertGreater(text_rect.bottom(), fixed_doc.documentLayout().frameBoundingRect(fixed_table).bottom())


if __name__ == '__main__':
    unittest.main()
