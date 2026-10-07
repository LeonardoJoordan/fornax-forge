"""Compara o texto pintado no editor com a prévia e a saída de geração."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from core.text_layout import build_document, resolve_rich_text, text_geometry, variables_in_html
from core.starter_templates import model_from_starter, starter_catalog
from features.editor.canvas_items import DesignerBox
from features.generator.renderer import NativeRenderer


def editor_box(data):
    box = DesignerBox(x=data.get("x", 0), y=data.get("y", 0),
                      w=data.get("w", 300), h=data.get("h", 100))
    for name, value in data.items():
        if hasattr(box.state, name):
            setattr(box.state, name, value)
    box.state.rich_text_version = data.get("rich_text_version", 0)
    box.state.html_content = data["html"]
    box.apply_state()
    return box


def editor_text_image(data, width=600, height=400):
    box = editor_box(data)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.setDotsPerMeterX(3780)
    image.setDotsPerMeterY(3780)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = data["w"], data["h"]
        painter.translate(data["x"] + w / 2, data["y"] + h / 2)
        painter.rotate(data.get("rotation", 0))
        painter.translate(-w / 2, -h / 2 + box.text_item.y())
        option = QStyleOptionGraphicsItem()
        option.exposedRect = QRectF(0, -10000, w, 20000)
        # Pinta o item de texto real, sem as alças e molduras de edição.
        box.text_item.paint(painter, option)
    finally:
        painter.end()
    return image


class TextFidelityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def assert_fidelity(self, data):
        editor = editor_text_image(data)
        values = {name: "{" + name + "}" for name in variables_in_html(data["html"])}
        renderer = NativeRenderer({"canvas_size": {"w": 600, "h": 400}, "boxes": [data]})
        self.assertEqual(renderer.render_preview_image(values), editor)
        self.assertEqual(renderer.render_to_qimage(values, values), editor)
        self.assertTrue(any(editor.pixelColor(x, y) != Qt.GlobalColor.white
                            for y in range(400) for x in range(600)))

    def test_rich_paragraph_uses_current_line_height_and_indent_instead_of_stale_html(self):
        for align in ("left", "center", "justify"):
            for vertical in ("top", "center", "bottom"):
                with self.subTest(align=align, vertical=vertical):
                    self.assert_fidelity({
                        "html": '<p style="line-height:85%; text-indent:17px;">'
                                'Certificamos que <b>{nome}</b> concluiu o estágio com '
                                'aproveitamento e dedicação.</p><p>Parabéns!</p>',
                        "rich_text_version": 1, "font_family": "DejaVu Sans", "font_size": 18,
                        "line_height": .7, "indent_px": 5, "align": align, "vertical_align": vertical,
                        "x": 70, "y": 90, "w": 410, "h": 190,
                    })

    def test_legacy_heading_keeps_editor_font_and_paragraph_layout(self):
        self.assert_fidelity({
            "html": '<h1 style="color:red; font-size:48pt;">Certificado</h1><p>{nome}</p>',
            "font_family": "DejaVu Sans", "font_size": 20, "font_color": "#124678",
            "line_height": .8, "align": "center", "vertical_align": "center",
            "x": 70, "y": 90, "w": 410, "h": 190,
        })

    def test_mixed_rich_fonts_colors_and_rotation_match_editor(self):
        self.assert_fidelity({
            "html": '<p><span style="font-size:25pt;color:#145678;">Certificado</span>'
                    '<br/><span style="font-family:DejaVu Serif;font-size:14pt;">'
                    '<i>{nome}</i> — <u>Conclusão de estágio</u></span></p>',
            "rich_text_version": 1, "font_family": "DejaVu Sans", "font_size": 18,
            "line_height": .9, "align": "center", "vertical_align": "center", "rotation": 12,
            "x": 70, "y": 90, "w": 410, "h": 190,
        })

    def test_updated_bundled_models_have_same_text_layout_in_editor_and_renderer(self):
        for template in starter_catalog("model")[:2]:
            document, _provider = model_from_starter(template)
            for data in document["pages"][0]["boxes"]:
                with self.subTest(template=template.id, box=data.get("id")):
                    box = editor_box(data)
                    values = {name: "{" + name + "}" for name in variables_in_html(data["html"])}
                    content = resolve_rich_text(data, values) if data.get("rich_text_version") == 1 else data["html"]
                    doc = build_document(data, content)
                    self.assertAlmostEqual(box.text_item.y(), text_geometry(doc, data)[0], delta=.05)
                    self.assertAlmostEqual(box.text_item.document().size().height(), doc.size().height(), delta=.05)
                    block, editor_block = doc.begin(), box.text_item.document().begin()
                    while block.isValid():
                        self.assertTrue(editor_block.isValid())
                        self.assertAlmostEqual(block.blockFormat().lineHeight(), editor_block.blockFormat().lineHeight())
                        self.assertAlmostEqual(block.blockFormat().textIndent(), editor_block.blockFormat().textIndent())
                        block, editor_block = block.next(), editor_block.next()
                    self.assertFalse(editor_block.isValid())


if __name__ == "__main__":
    unittest.main()
