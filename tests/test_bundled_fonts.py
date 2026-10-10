"""Confere a fonte efetiva e os arquivos usados, além do nome solicitado ao Qt."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QRawFont, QTextCursor
from PySide6.QtWidgets import QApplication

from core.font_utils import is_font_available, missing_template_fonts, system_font_families
from core.resources import PROJECT_ROOT
from core.text_layout import build_document
from core.ui_font import DOCUMENT_FONT_FAMILY, UI_FONT_FAMILY, UI_FONT_SIZE, install_ui_font
from features.editor.canvas_items import DesignerBox


class BundledFontsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_ui_font(cls.app)

    def assert_bundled_file(self, font, style='Regular'):
        actual = QRawFont.fromFont(font)
        bundled = QRawFont(str(PROJECT_ROOT / 'assets/fonts/ui' / f'Inter_18pt-{style}.ttf'), 16)
        self.assertTrue(actual.isValid())
        self.assertTrue(bundled.isValid())
        self.assertEqual(actual.familyName(), UI_FONT_FAMILY)
        # As tabelas de contornos e métricas identificam o arquivo físico,
        # independentemente da suavização utilizada pelo sistema operacional.
        for table in ('glyf', 'hmtx'):
            self.assertTrue(bundled.fontTable(table))
            self.assertTrue(bytes(actual.fontTable(table)) == bytes(bundled.fontTable(table)),
                            f'{actual.familyName()} {actual.styleName()} não corresponde a {style}: {table}')

    def test_all_weights_and_italics_use_the_shipped_files_and_are_packaged(self):
        from scripts.release_tools import selected_files
        shipped = set(selected_files())
        for style in ('Thin', 'ExtraLight', 'Light', 'Regular', 'Medium',
                      'SemiBold', 'Bold', 'ExtraBold', 'Black'):
            for italic in (False, True):
                variant = ('Italic' if style == 'Regular' else style+'Italic') if italic else style
                with self.subTest(variant=variant):
                    self.assertIn(PROJECT_ROOT / 'assets/fonts/ui' / f'Inter_18pt-{variant}.ttf', shipped)
                    qt_style = ('Italic' if style == 'Regular' else style+' Italic') if italic else style
                    font = QFontDatabase.font(UI_FONT_FAMILY, qt_style, 16)
                    self.assert_bundled_file(font, variant)

    def test_interface_weights_and_emphasis_resolve_to_real_font_variants(self):
        for variant, weight, italic in (('Regular', 400, False), ('Medium', 500, False),
                                        ('SemiBold', 600, False), ('Bold', 700, False),
                                        ('ExtraBold', 800, False), ('Italic', 400, True),
                                        ('BoldItalic', 700, True)):
            with self.subTest(variant=variant):
                self.assert_bundled_file(QFont(UI_FONT_FAMILY, 16, weight, italic), variant)

    def test_application_defaults_do_not_inherit_system_size_weight_or_style(self):
        original = self.app.font()
        self.addCleanup(self.app.setFont, original)
        system = QFont('Monospace', 23, QFont.Weight.Bold, True)
        system.setStyleName('Bold Italic')
        self.app.setFont(system)
        self.assertEqual(install_ui_font(self.app), UI_FONT_FAMILY)
        font = self.app.font()
        self.assertEqual(font.pointSize(), UI_FONT_SIZE)
        self.assertEqual(font.weight(), QFont.Weight.Normal)
        self.assertFalse(font.italic())
        self.assertEqual(font.styleName(), '')
        self.assert_bundled_file(font)

    def test_new_text_box_uses_bundled_font_even_with_another_application_font(self):
        original = self.app.font()
        self.addCleanup(self.app.setFont, original)
        self.app.setFont(QFont('Monospace', 20))
        box = DesignerBox(text='{campo}')
        self.assertEqual(box.state.font_family, DOCUMENT_FONT_FAMILY)
        self.assert_bundled_file(box.text_item.document().defaultFont())

    def test_aliases_in_rich_text_keep_bold_italic_and_other_font_choices(self):
        html = ('<p style="font-family:Inter"><b>Negrito</b> '
                '<i>Itálico</i> <span style="font-family:serif">Outra</span></p>')
        doc = build_document({'font_family': 'Inter', 'rich_text_version': 1, 'w': 500}, html)
        self.assert_bundled_file(doc.defaultFont())
        for word, variant in (('Negrito', 'Bold'), ('Itálico', 'Italic')):
            cursor = doc.find(word)
            fmt = cursor.charFormat()
            self.assertEqual(fmt.fontFamilies(), [DOCUMENT_FONT_FAMILY])
            self.assert_bundled_file(fmt.font().resolve(doc.defaultFont()), variant)
        self.assertEqual(doc.find('Outra').charFormat().fontFamilies(), ['serif'])
        self.assertEqual(doc.toPlainText(), 'Negrito Itálico Outra')

    def test_alias_in_empty_paragraph_applies_to_newly_typed_text(self):
        doc = build_document({'rich_text_version': 1}, '<p style="font-family:Inter"></p>')
        cursor = QTextCursor(doc)
        cursor.insertText('Novo texto')
        self.assertEqual(cursor.charFormat().fontFamilies(), [DOCUMENT_FONT_FAMILY])
        self.assert_bundled_file(cursor.charFormat().font().resolve(doc.defaultFont()))

    def test_availability_reports_fonts_actually_registered_in_qt(self):
        with patch('core.font_utils.QFontDatabase.families', return_value=['Noto Sans']):
            self.assertEqual(system_font_families(), {'noto sans'})
            self.assertFalse(is_font_available('Inter'))
            self.assertFalse(is_font_available(DOCUMENT_FONT_FAMILY))
            self.assertEqual(missing_template_fonts({'boxes': [{'font_family': 'Inter'}]}), ['Inter'])
        self.assertTrue(is_font_available('Inter'))
        self.assertEqual(QFontInfo(QFont('Inter')).family(), DOCUMENT_FONT_FAMILY)

    def test_missing_font_package_is_reported_instead_of_silently_claiming_success(self):
        with TemporaryDirectory() as directory, patch('core.ui_font.PROJECT_ROOT', Path(directory)):
            with self.assertLogs('core.ui_font', level='ERROR'):
                self.assertEqual(install_ui_font(self.app), '')


if __name__ == '__main__':
    unittest.main()
