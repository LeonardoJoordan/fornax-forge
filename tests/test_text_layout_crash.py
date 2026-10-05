"""Protege a prévia quando o Qt não retorna o quadro raiz do texto."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.html_utils import TextOnlyDocument
from core.text_layout import build_document, resolve_rich_text
from features.generator.renderer import NativeRenderer


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


if __name__ == "__main__":
    unittest.main()
