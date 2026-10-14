"""Ctrl+V do Calc: dados reais fictícios, estilos parciais e fallback seguro."""
from io import BytesIO
from pathlib import Path
import os
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QMimeData, Qt, QEvent
from PySide6.QtGui import QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from features.spreadsheet import clipboard
from features.spreadsheet import calc_clipboard as calc
from features.spreadsheet.table_panel import RichTableWidget
from features.workspace.main_window import MainWindow
from core.text_layout import resolve_rich_text

FIXTURES = Path(__file__).parent / 'fixtures/calc_clipboard'
NATIVE_MIME = 'application/x-openoffice-embed-source-xml;windows_formatname="Star Embed Source (XML)"'


def package(label='partial', replacements=None):
    replacements = replacements or {}
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.writestr('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')
        for name in ('content.xml', 'styles.xml', 'settings.xml'):
            data = replacements.get(name, (FIXTURES / label / name).read_bytes())
            z.writestr(name, data)
    return out.getvalue()


def mime(label='partial', data=None, native_type=NATIVE_MIME):
    md = QMimeData()
    md.setHtml((FIXTURES / label / 'clipboard.html').read_text())
    md.setText('Ana Maria Silva\nBruno Costa\nCarla Souza\nDaniel Lima')
    md.setData(native_type, package(label) if data is None else data)
    return md


def synthetic(rows, *, columns='', styles='', left=0, top=0):
    """Small ODS clipboard with explicit selection coordinates; no document I/O."""
    namespaces = ' '.join(f'xmlns:{key}="{value}"' for key, value in calc.NS.items())
    content = (f'<office:document-content {namespaces}><office:automatic-styles>{styles}'
               '</office:automatic-styles><office:body><office:spreadsheet>'
               f'<table:table table:name="Sheet1">{columns}{rows}</table:table>'
               '</office:spreadsheet></office:body></office:document-content>')
    settings = (f'<office:document-settings {namespaces}><office:settings>'
                '<config:config-item-map-indexed config:name="Views"><config:config-item-map-entry>'
                f'<config:config-item config:name="PositionLeft">{left}</config:config-item>'
                f'<config:config-item config:name="PositionTop">{top}</config:config-item>'
                '<config:config-item config:name="ActiveTable">Sheet1</config:config-item>'
                '</config:config-item-map-entry></config:config-item-map-indexed>'
                '</office:settings></office:document-settings>')
    return package(replacements={'content.xml': content, 'settings.xml': settings,
                                'styles.xml': f'<office:document-styles {namespaces}/>'})


class CalcClipboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def table(self):
        table = RichTableWidget(1, 3)
        table.setHorizontalHeaderLabels(['Cópias', 'nome', 'cargo'])
        table.setCurrentCell(0, 1)
        table.show()
        self.app.processEvents()
        def cleanup():
            self.app.clipboard().clear()
            table._row_height_timer.stop()
            table.close(); table.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.addCleanup(cleanup)
        return table

    def test_ctrl_v_preserves_partial_styles_through_placeholder(self):
        table = self.table()
        self.app.clipboard().setMimeData(mime())
        QTest.keyClick(table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        expected = ['<b>Ana</b> Maria Silva', '<b>Bruno Costa</b>', '<i>Carla</i> Souza', '<u>Daniel</u> Lima']
        self.assertEqual([table.item(r, 1).data(table.RICH_ROLE) for r in range(4)], expected)
        # Use the production workspace data reader, then the production placeholder resolver.
        from types import SimpleNamespace
        workspace = SimpleNamespace(table_panel=SimpleNamespace(table=table))
        for row, emphasis in ((0, 'bold'), (2, 'italic'), (3, 'underline')):
            values = MainWindow._get_row_data_rich(workspace, row)
            html = resolve_rich_text(dict(html='<p>{nome}</p>', w=600, h=100, font_size=20), values)
            doc = QTextDocument(); doc.setHtml(html)
            it = doc.begin().begin(); first = it.fragment(); it += 1; last = it.fragment()
            if emphasis == 'bold':
                self.assertGreater(first.charFormat().fontWeight(), 400)
                self.assertEqual(last.charFormat().fontWeight(), 400)
            elif emphasis == 'italic':
                self.assertTrue(first.charFormat().fontItalic()); self.assertFalse(last.charFormat().fontItalic())
            else:
                self.assertTrue(first.charFormat().fontUnderline()); self.assertFalse(last.charFormat().fontUnderline())

    def test_calc_generator_takes_priority_over_sheets_attributes(self):
        html = (FIXTURES / 'partial/clipboard.html').read_text()
        with patch.object(clipboard.LibreOffice, 'processar', wraps=clipboard.LibreOffice.processar) as calc:
            clipboard.router(html, '')
            self.assertEqual(calc.call_count, 1)

    def test_partial_styles_reach_preview_and_generated_image(self):
        from features.generator.renderer import NativeRenderer
        renderer = NativeRenderer({'canvas_size': {'w': 500, 'h': 200}, 'boxes': [{
            'x': 20, 'y': 20, 'w': 460, 'h': 150, 'font_size': 22,
            'html': '<p>{nome}</p>', 'rich_text_version': 1,
        }]})
        rows = clipboard.parse_clipboard_mime_data(mime())
        for index, expected in ((0, '<b>Ana</b> Maria Silva'), (2, '<i>Carla</i> Souza'),
                                (3, '<u>Daniel</u> Lima')):
            with self.subTest(row=index):
                cell = rows[index][0]
                rich, plain = {'nome': cell.rich_html}, {'nome': cell.plain}
                reference = {'nome': expected}
                self.assertEqual(renderer.render_preview_image(rich), renderer.render_preview_image(reference))
                output = renderer.render_to_qimage(row_plain=plain, row_rich=rich)
                self.assertEqual(output, renderer.render_to_qimage(row_plain=plain, row_rich=reference))
                self.assertNotEqual(output, renderer.render_to_qimage(row_plain=plain, row_rich=plain))

    def test_real_offset_selection_keeps_blanks_without_original_sheet_offset(self):
        table = self.table()
        self.app.clipboard().setMimeData(mime('offset'))
        changes = []
        table.dataBatchChanged.connect(changes.append)
        QTest.keyClick(table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(table.rowCount(), 3)
        self.assertEqual([[table.item(r, c).text() for c in (1, 2)] for r in range(3)],
                         [['', ''], ['', 'Dentro da seleção'], ['Última linha', '']])
        self.assertEqual(table.item(1, 2).data(table.RICH_ROLE), '<b>Dentro</b> da seleção')
        self.assertEqual(len(changes), 1)

    def test_native_only_and_windows_qt_mime(self):
        for native_type in (NATIVE_MIME, 'application/x-openoffice-embed-source-xml',
                            'application/x-qt-windows-mime;value="Star Embed Source (XML)"'):
            with self.subTest(mime=native_type):
                md = QMimeData()
                md.setData(native_type, package())
                values = clipboard.parse_clipboard_mime_data(md)
                self.assertEqual(values[0][0].rich_html, '<b>Ana</b> Maria Silva')
                self.assertEqual(values[3][0].rich_html, '<u>Daniel</u> Lima')

    def test_invalid_native_falls_back_to_html_or_plain_text(self):
        md = mime(data=b'broken archive')
        expected = clipboard.router(md.html(), md.text())
        self.assertEqual(clipboard.parse_clipboard_mime_data(md), expected)
        self.assertEqual(expected[1][0].rich_html, '<b>Bruno Costa</b>')
        md = QMimeData()
        md.setData(NATIVE_MIME, b'broken archive')
        md.setText('João\tDiretor\nMaria\tDocente')
        self.assertEqual([[v.plain for v in row] for row in clipboard.parse_clipboard_mime_data(md)],
                         [['João', 'Diretor'], ['Maria', 'Docente']])

    def test_google_excel_and_generic_html_keep_partial_styles(self):
        sources = (
            ('<google-sheets-html-origin><table><tr><td data-sheets-value="{}">'
             '<span style="font-weight:700">Ana</span> <span style="font-style:italic">Maria</span>'
             ' <span style="text-decoration:underline">Silva</span></td></tr></table>'
             '</google-sheets-html-origin>'),
            ('<html xmlns:x="urn:schemas-microsoft-com:office:excel"><style>'
             '.xl65 {font-weight:700}.xl66 {font-style:italic}.xl67 {text-decoration:underline}'
             '</style><table><tr><td><span class="xl65">Ana</span> <span class="xl66">Maria</span>'
             ' <span class="xl67">Silva</span></td></tr></table></html>'),
            '<table><tr><td><b>Ana</b> <i>Maria</i> <u>Silva</u></td></tr></table>',
        )
        for html in sources:
            with self.subTest(html=html[:60]):
                md = QMimeData(); md.setHtml(html); md.setText('Ana Maria Silva')
                value = clipboard.parse_clipboard_mime_data(md)[0][0]
                self.assertEqual(value.plain, 'Ana Maria Silva')
                self.assertEqual(value.rich_html, '<b>Ana</b> <i>Maria</i> <u>Silva</u>')

    def test_styles_inherit_and_explicit_normal_overrides_only_its_run(self):
        styles = '''
          <style:style style:name="Base" style:family="table-cell">
            <style:text-properties fo:font-weight="bold"/>
          </style:style>
          <style:style style:name="Cell" style:family="table-cell" style:parent-style-name="Base">
            <style:text-properties fo:font-style="italic"/>
          </style:style>
          <style:style style:name="Normal" style:family="text">
            <style:text-properties fo:font-weight="normal" fo:font-style="normal"/>
          </style:style>
          <style:style style:name="Underline" style:family="text" style:parent-style-name="Normal">
            <style:text-properties style:text-underline-style="solid"/>
          </style:style>'''
        data = synthetic('''<table:table-row><table:table-cell table:style-name="Cell"><text:p>
            A<text:span text:style-name="Normal">B<text:span text:style-name="Underline">C</text:span>D</text:span>E
            </text:p></table:table-cell></table:table-row>'''.replace('\n', '').replace('            ', ''), styles=styles)
        value = calc.parse_calc_package(data)[0][0]
        self.assertEqual(value.plain, 'ABCDE')
        self.assertEqual(value.rich_html, '<b><i>A</i></b>B<u>C</u>D<b><i>E</i></b>')

    def test_column_and_row_defaults_repeated_cells_and_merged_blanks(self):
        styles = ('<style:style style:name="B" style:family="table-cell">'
                  '<style:text-properties fo:font-weight="bold"/></style:style>'
                  '<style:style style:name="I" style:family="table-cell">'
                  '<style:text-properties fo:font-style="italic"/></style:style>')
        data = synthetic(
            '<table:table-row table:number-rows-repeated="2">'
            '<table:table-cell table:number-columns-repeated="2"><text:p>Nome</text:p></table:table-cell>'
            '</table:table-row><table:table-row table:default-cell-style-name="I">'
            '<table:table-cell table:number-columns-spanned="2"><text:p>Mesclada</text:p></table:table-cell>'
            '<table:covered-table-cell/></table:table-row>',
            columns='<table:table-column table:default-cell-style-name="B"/><table:table-column/>', styles=styles)
        self.assertEqual([[v.rich_html for v in row] for row in calc.parse_calc_package(data)],
                         [['<b>Nome</b>', 'Nome'], ['<b>Nome</b>', 'Nome'], ['<i>Mesclada</i>', '']])

    def test_far_selection_skips_original_empty_rows_and_columns(self):
        data = synthetic('<table:table-row table:number-rows-repeated="1000000"/>'
                         '<table:table-row><table:table-cell table:number-columns-repeated="15000"/>'
                         '<table:table-cell><text:p>Última</text:p></table:table-cell></table:table-row>',
                         left=15000, top=1000000)
        self.assertEqual(calc.parse_calc_package(data), [[clipboard.CellValue('Última', 'Última')]])

    def test_multiline_spaces_unicode_links_and_cached_formula_only(self):
        data = synthetic('<table:table-row><table:table-cell><text:p>João &amp; &lt;b&gt;'
                         '<text:s text:c="2"/><text:a>ação 🏫</text:a><text:tab/>A<text:line-break/>B</text:p>'
                         '<text:p>C</text:p></table:table-cell>'
                         '<table:table-cell office:value="42" table:formula="of:=6*7"/></table:table-row>')
        values = calc.parse_calc_package(data)[0]
        self.assertEqual(values[0].plain, 'João & <b>  ação 🏫\tA\nB\nC')
        self.assertEqual(values[0].rich_html, 'João &amp; &lt;b&gt;  ação 🏫\tA<br>B<br>C')
        self.assertEqual(values[1], clipboard.CellValue('42', '42'))

    def test_invalid_xml_entities_and_oversized_selection_are_rejected(self):
        bad_contents = ['<broken>',
                        '<!DOCTYPE x [<!ENTITY example "expanded">]><x>&example;</x>']
        for content in bad_contents:
            with self.subTest(content=content):
                self.assertIsNone(calc.parse_calc_package(package(replacements={'content.xml': content})))
        for repeat in ('0', '-1', '1048577', '9999999999999999999999'):
            with self.subTest(repeat=repeat):
                self.assertIsNone(calc.parse_calc_package(synthetic(
                    f'<table:table-row table:number-rows-repeated="{repeat}"><table:table-cell/></table:table-row>')))
        self.assertIsNone(calc.parse_calc_package(synthetic(
            '<table:table-row table:number-rows-repeated="10000">'
            '<table:table-cell table:number-columns-repeated="1000"/></table:table-row>')))

    def test_xml_package_and_text_budgets_fall_back_safely(self):
        data = package()
        for name in ('MAX_XML_BYTES', 'MAX_PACKAGE_BYTES', 'MAX_TEXT_CHARS', 'MAX_CELL_CHARS'):
            with self.subTest(limit=name), patch.object(calc, name, 4):
                self.assertIsNone(calc.parse_calc_package(data))
        # A small compressed package must not expand into an enormous rich-text grid.
        data = synthetic('<table:table-row table:number-rows-repeated="1000">'
                         '<table:table-cell><text:p><text:s text:c="65536"/></text:p></table:table-cell>'
                         '</table:table-row>')
        self.assertIsNone(calc.parse_calc_package(data))

    def test_cyclic_style_inheritance_is_rejected(self):
        data = synthetic('<table:table-row><table:table-cell table:style-name="A">'
                         '<text:p>Texto</text:p></table:table-cell></table:table-row>',
                         styles='<style:style style:name="A" style:family="table-cell" style:parent-style-name="B"/>'
                         '<style:style style:name="B" style:family="table-cell" style:parent-style-name="A"/>')
        self.assertIsNone(calc.parse_calc_package(data))

    def test_thousand_rows_preserve_partial_formatting(self):
        data = synthetic('<table:table-row table:number-rows-repeated="1000">'
                         '<table:table-cell><text:p><text:span text:style-name="B">Ana</text:span> Silva</text:p>'
                         '</table:table-cell></table:table-row>',
                         styles='<style:style style:name="B" style:family="text">'
                         '<style:text-properties fo:font-weight="bold"/></style:style>')
        values = calc.parse_calc_package(data)
        self.assertEqual(len(values), 1000)
        self.assertTrue(all(row[0].rich_html == '<b>Ana</b> Silva' for row in values))


if __name__ == '__main__':
    unittest.main()
