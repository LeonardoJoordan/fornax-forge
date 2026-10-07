"""Protege o texto quando o Qt não retorna um quadro raiz utilizável."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from core.html_utils import TextOnlyDocument
from core.text_layout import build_document, resolve_rich_text
from features.generator.renderer import NativeRenderer
from features.editor.canvas_items import DesignerBox


class TextLayoutCrashTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_root_frame_preserves_text_and_placeholder_resolution(self):
        box = {"html": "<b>{Nome}</b>", "rich_text_version": 1, "w": 200, "h": 60}
        with patch.object(TextOnlyDocument, "rootFrame", return_value=None):
            doc = build_document(box, box["html"])
            self.assertEqual(doc.toPlainText(), "{Nome}")
            html = resolve_rich_text(box, {"Nome": "Ana"})
            resolved = TextOnlyDocument()
            resolved.setHtml(html)
            self.assertEqual(resolved.toPlainText(), "Ana")

    def test_missing_root_frame_does_not_abort_preview_or_export(self):
        box = {
            "html": "<b>{Nome}</b>", "rich_text_version": 1,
            "x": 10, "y": 10, "w": 180, "h": 60,
        }
        renderer = NativeRenderer({"canvas_size": {"w": 200, "h": 100}, "boxes": [box]})
        with patch.object(TextOnlyDocument, "rootFrame", return_value=None):
            preview = renderer.render_preview_image({"Nome": "Ana"})
            export = renderer.render_to_qimage({"Nome": "Ana"}, {"Nome": "Ana"})
        self.assertFalse(preview.isNull())
        self.assertEqual(preview, export)
        self.assertTrue(any(
            preview.pixelColor(x, y).name() != "#ffffff"
            for x in range(10, 190) for y in range(10, 70)
        ))

    def test_table_item_returned_as_root_frame_preserves_formatted_placeholder(self):
        box = {"html": "<b>{Nome}</b>", "rich_text_version": 1, "w": 200, "h": 60}
        expected = resolve_rich_text(box, {"Nome": "Ana"})
        with patch.object(TextOnlyDocument, "rootFrame", return_value=QTableWidgetItem("Ana")):
            actual = resolve_rich_text(box, {"Nome": "Ana"})
        self.assertEqual(actual, expected)

    def test_table_item_returned_as_root_frame_preserves_preview_and_export(self):
        box = {
            "html": "<b>{Nome}</b>", "rich_text_version": 1,
            "x": 10, "y": 10, "w": 180, "h": 60,
        }
        renderer = NativeRenderer({"canvas_size": {"w": 200, "h": 100}, "boxes": [box]})
        expected = renderer.render_preview_image({"Nome": "Ana"})
        with patch.object(TextOnlyDocument, "rootFrame", return_value=QTableWidgetItem("Ana")):
            preview = renderer.render_preview_image({"Nome": "Ana"})
            export = renderer.render_to_qimage({"Nome": "Ana"}, {"Nome": "Ana"})
        self.assertEqual(preview, expected)
        self.assertEqual(export, expected)

    def test_editor_does_not_depend_on_root_frame_wrapper(self):
        with patch.object(QTextDocument, "rootFrame", return_value=QTableWidgetItem("Ana")):
            box = DesignerBox(text="Ana")
            box.state.html_content = "<b>Bruno</b>"
            box.apply_state()
        self.assertEqual(box.text_item.toPlainText(), "Bruno")
        self.assertEqual(box.text_item.document().documentMargin(), 0)
        self.assertFalse(box.text_item.signalsBlocked())

    def test_html_frame_margins_are_reset_without_changing_paragraph_margins(self):
        source = TextOnlyDocument()
        source.setHtml('<p style="margin-top:11px; margin-bottom:13px;">Ana</p>')
        source.setDocumentMargin(29)
        box = {"rich_text_version": 1, "w": 200, "h": 60}
        doc = build_document(box, source.toHtml())
        frame_format = doc.rootFrame().frameFormat()
        self.assertEqual(doc.documentMargin(), 0)
        self.assertEqual((frame_format.topMargin(), frame_format.rightMargin(),
                          frame_format.bottomMargin(), frame_format.leftMargin()), (0, 0, 0, 0))
        self.assertEqual(doc.begin().blockFormat().topMargin(), 11)
        self.assertEqual(doc.begin().blockFormat().bottomMargin(), 13)


if __name__ == "__main__":
    unittest.main()
