"""Dados da tabela herdam a ênfase e a tipografia do placeholder."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit
from core.text_layout import build_document, resolve_rich_text
from features.generator.renderer import NativeRenderer


class PlaceholderFormattingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def box(self, content):
        return {'html': content, 'rich_text_version': 1, 'font_family': 'DejaVu Serif',
                'font_size': 24, 'x': 10, 'y': 10, 'w': 480, 'h': 180}

    def formats(self, document):
        cursor = QTextCursor(document)
        result = []
        for offset, character in enumerate(document.toPlainText()):
            if character in '\n\u2029':
                continue
            cursor.setPosition(offset)
            cursor.setPosition(offset + 1, QTextCursor.MoveMode.KeepAnchor)
            result.append(cursor.charFormat())
        return result

    def test_real_table_html_keeps_placeholder_bold_italic_and_underline_for_entire_value(self):
        cell = QTextEdit()
        cell.setFont(QFont('DejaVu Sans', 11))
        cell.setPlainText('Maria da Silva\nDiretora')
        html = cell.toHtml()
        cell.deleteLater()
        box = self.box('<b><i><u>{Nome}</u></i></b>')
        resolved = resolve_rich_text(box, {'Nome': html})
        doc = build_document(box, resolved)
        self.assertEqual(doc.toPlainText(), 'Maria da Silva\nDiretora')
        for fmt in self.formats(doc):
            self.assertGreaterEqual(fmt.fontWeight(), QFont.Weight.Bold)
            self.assertTrue(fmt.fontItalic())
            self.assertTrue(fmt.fontUnderline())
            self.assertEqual(fmt.fontFamilies(), ['DejaVu Serif'])
            self.assertEqual(fmt.fontPointSize(), 24)

    def test_cell_emphasis_adds_to_model_without_making_unformatted_fragments_bold(self):
        box = self.box('<i>{Nome}</i>')
        doc = build_document(box, resolve_rich_text(box, {'Nome': '<p>Ana <b>Silva</b></p>'}))
        formats = self.formats(doc)
        self.assertTrue(all(fmt.fontItalic() for fmt in formats))
        self.assertTrue(all(fmt.fontWeight() == QFont.Weight.Normal for fmt in formats[:4]))
        self.assertTrue(all(fmt.fontWeight() >= QFont.Weight.Bold for fmt in formats[4:]))

    def test_bold_placeholder_with_unformatted_html_matches_plain_data_in_preview_and_export(self):
        box = self.box('<p>Convidado: <b>{Nome}</b></p>')
        cell = QTextEdit()
        cell.setPlainText('Maria da Silva')
        html = cell.toHtml()
        cell.deleteLater()
        plain = {'Nome': 'Maria da Silva'}
        rich = {'Nome': html}
        for version in (0, 1):
            with self.subTest(version=version):
                box['rich_text_version'] = version
                renderer = NativeRenderer({'canvas_size': {'w': 500, 'h': 200}, 'boxes': [box]})
                self.assertEqual(renderer.render_preview_image(rich), renderer.render_preview_image(plain))
                self.assertEqual(renderer.render_to_qimage(plain, rich), renderer.render_to_qimage(plain, plain))


if __name__ == '__main__':
    unittest.main()
