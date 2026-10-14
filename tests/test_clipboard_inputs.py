"""Entradas sintéticas de interoperabilidade; não certificam aplicativos externos."""
import csv
from io import StringIO
import unittest
from unittest.mock import patch

from features.spreadsheet import clipboard as cb


def plain(grid):
    return [[cell.plain for cell in row] for row in grid]


class ClipboardInputsTest(unittest.TestCase):
    def test_content_comments_and_unrelated_metadata_do_not_identify_origin(self):
        cases = [
            ('', 'Ana data-sheets-'),
            ('', 'google-sheets-html-origin LibreOffice Microsoft Excel excel.sheet class=xl'),
            ('<!-- <meta name="generator" content="LibreOffice"> data-sheets-value -->', 'Ana'),
            ('<meta name="description" content="LibreOffice data-sheets-value">', 'Ana'),
            ('<script>const source = "data-sheets-value LibreOffice";</script>', 'Ana'),
        ]
        for prefix, value in cases:
            with self.subTest(prefix=prefix, value=value):
                html = prefix + '<style>.destacado {font-weight:bold}</style>' + (
                    f'<table><tr><td class="destacado">{value}</td></tr></table>')
                with patch.object(cb.GoogleSheets, 'processar', wraps=cb.GoogleSheets.processar) as sheets, patch.object(
                    cb.LibreOffice, 'processar', wraps=cb.LibreOffice.processar
                ) as calc:
                    result = cb.router(html, value)
                self.assertEqual(sheets.call_count, 0)
                self.assertEqual(calc.call_count, 0)
                self.assertEqual(result[0][0].rich_html, f'<b>{value}</b>')

    def test_generator_has_priority_over_compatibility_attributes(self):
        for generator, processor in (('LibreOffice 24.2', cb.LibreOffice), ('OpenOffice.org', cb.LibreOffice),
                                     ('Microsoft Excel 16', cb.Excel), ('WPS Office', cb.Excel)):
            with self.subTest(generator=generator):
                html = (f'<META CONTENT="{generator}" NAME=Generator>'
                        '<style>.cell {font-weight:bold}</style>'
                        '<table><tr><td class="cell" data-sheets-value="{}">Ana</td></tr></table>')
                with patch.object(processor, 'processar', wraps=processor.processar) as selected:
                    result = cb.router(html, 'Ana')
                    self.assertEqual(selected.call_count, 1)
                self.assertEqual(result[0][0].rich_html, '<b>Ana</b>')

    def test_actual_sheets_attributes_and_origin_tag_are_recognized(self):
        for html in ('<table><tr><td data-sheets-value="{}"><b>Ana</b></td></tr></table>',
                     '<google-sheets-html-origin><table><tr><td><b>Ana</b></td></tr></table></google-sheets-html-origin>'):
            with self.subTest(html=html), patch.object(cb.GoogleSheets, 'processar', wraps=cb.GoogleSheets.processar) as sheets:
                self.assertEqual(cb.router(html, 'Ana')[0][0].rich_html, '<b>Ana</b>')
                self.assertEqual(sheets.call_count, 1)

    def test_unknown_generators_use_standard_html_styles(self):
        for generator in ('WPS Office', 'ONLYOFFICE', 'Numbers', 'Zoho Sheet', 'Outro editor'):
            with self.subTest(generator=generator):
                html = (f'<meta name="generator" content="{generator}">'
                        '<style>.bold {font-weight:700}</style><table><tr><td>'
                        '<span class="bold">João</span> <i>da</i> <u>Silva</u></td></tr></table>')
                self.assertEqual(cb.router(html, '')[0][0].rich_html, '<b>João</b> <i>da</i> <u>Silva</u>')

    def test_tsv_preserves_blank_rows_and_trailing_columns(self):
        self.assertEqual(plain(cb.router('', '\t\r\nAna\tDireção\r\n\t\r\nBruno\t\r\n\t\r\n')),
                         [['', ''], ['Ana', 'Direção'], ['', ''], ['Bruno', ''], ['', '']])
        self.assertEqual(plain(cb.router('', 'Ana\tDireção\n\nBruno\tSecretaria\n')),
                         [['Ana', 'Direção'], ['', ''], ['Bruno', 'Secretaria']])

    def test_tsv_quoted_multiline_tabs_quotes_and_unicode_round_trip(self):
        expected = [['00123', 'João\nMaria', 'Texto\tcom "aspas"'],
                    ['03/04/2026', '1.234,56', '  ação 🏫  '], ['', '', ''],
                    ['=1+1', 'A\u2028B', '<b>texto literal</b> &amp;']]
        stream = StringIO(newline='')
        csv.writer(stream, delimiter='\t', lineterminator='\r\n').writerows(expected)
        result = cb.router('', stream.getvalue())
        self.assertEqual(plain(result), expected)
        self.assertEqual(result[0][1].rich_html, 'João<br>Maria')
        self.assertEqual(result[3][2].rich_html, '&lt;b&gt;texto literal&lt;/b&gt; &amp;amp;')

    def test_malformed_quoted_text_does_not_swallow_following_records(self):
        self.assertEqual(plain(cb.router('', '"Nome sem fechar\tDireção\nBruno\tSecretaria')),
                         [['"Nome sem fechar', 'Direção'], ['Bruno', 'Secretaria']])

    def test_empty_clipboard_and_record_terminators(self):
        self.assertEqual(cb.router('', ''), [])
        self.assertEqual(plain(cb.router('', 'Ana\n')), [['Ana']])
        self.assertEqual(plain(cb.router('', 'Ana\n\n')), [['Ana'], ['']])
        self.assertEqual(plain(cb.router('', '\t')), [['', '']])

    def test_html_entities_are_decoded_once_for_display_only(self):
        for prefix in ('', '<meta name="generator" content="LibreOffice">', '<google-sheets-html-origin>'):
            with self.subTest(prefix=prefix):
                result = cb.router(prefix + '<table><tr><td><b>São José &amp; &lt;grupo&gt;</b>'
                                   ' &amp;lt;b&amp;gt;</td></tr></table>', '')[0][0]
                self.assertEqual(result.plain, 'São José & <grupo> &lt;b&gt;')
                self.assertEqual(result.rich_html, '<b>São José &amp; &lt;grupo&gt;</b> &amp;lt;b&amp;gt;')

    def test_html_fragment_retains_styles_without_table(self):
        result = cb.router('<p><b>João</b> <i>Silva</i></p>', 'João Silva')
        self.assertEqual(result[0][0].rich_html, '<b>João</b> <i>Silva</i>')

    def test_empty_or_truncated_html_can_use_available_text(self):
        for html in ('<table></table>', '<table><tr><td>', '<meta name="generator" content="Microsoft Excel">'):
            with self.subTest(html=html):
                self.assertEqual(plain(cb.router(html, '00123\tAna\n00024\tBruno')),
                                 [['00123', 'Ana'], ['00024', 'Bruno']])

    def test_html_merges_reserve_grid_positions(self):
        for prefix in ('', '<meta name="generator" content="LibreOffice">', '<google-sheets-html-origin>'):
            with self.subTest(prefix=prefix):
                html = prefix + ('<table><tr><td rowspan="2" colspan="2"><b>Grupo</b></td><td>A</td></tr>'
                                 '<tr><td>B</td></tr><tr><td>C</td><td>D</td><td>E</td></tr></table>')
                result = cb.router(html, '')
                self.assertEqual(plain(result), [['Grupo', '', 'A'], ['', '', 'B'], ['C', 'D', 'E']])
                self.assertEqual(result[0][0].rich_html, '<b>Grupo</b>')

    def test_extreme_html_spans_use_text_without_allocating_a_giant_grid(self):
        result = cb.router('<table><tr><td colspan="999999999999999999999">Ana</td></tr></table>', 'Ana')
        self.assertEqual(plain(result), [['Ana']])

    def test_fully_covered_rows_and_empty_html_rows_keep_their_position(self):
        html = ('<table><tr><td rowspan="2" colspan="2">Grupo</td></tr><tr></tr>'
                '<tr><td>A</td><td>B</td></tr></table>')
        self.assertEqual(plain(cb.router(html, '')), [['Grupo', ''], ['', ''], ['A', 'B']])
        self.assertEqual(plain(cb.router('<table><tr><td>A</td><td>B</td></tr><tr></tr></table>', '')),
                         [['A', 'B'], ['', '']])

    def test_invalid_html_never_loses_the_available_plain_records(self):
        for html in ('<table><tr><td>A</td></tr><tr><td>B', '<![malformed]>',
                     '<table><tr><td>A<table><tr><td>B</td></tr></table></td></tr></table>'):
            with self.subTest(html=html):
                self.assertEqual(plain(cb.router(html, 'A\nB')), [['A'], ['B']])

    def test_sparse_input_does_not_multiply_into_an_unbounded_rectangle(self):
        result = cb.router('', '\t' * 1000 + '\n' * 200)
        self.assertEqual(len(result), 200)
        self.assertEqual(len(result[0]), 1001)
        self.assertLess(sum(map(len, result)), 2000)


# Exercise the actual Ctrl+V and Qt rich-text boundary as well as the parsers.
import test_calc_clipboard as calc_tests


class ClipboardPasteTest(unittest.TestCase):
    setUpClass = classmethod(calc_tests.CalcClipboardTest.setUpClass.__func__)
    table = calc_tests.CalcClipboardTest.table

    def test_ctrl_v_blank_rows_clear_previous_cells_and_preserve_leading_zeros(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QTableWidgetItem
        table = self.table()
        table.setRowCount(3)
        for r in range(3):
            for c in (1, 2):
                table.setItem(r, c, QTableWidgetItem('Anterior'))
        self.app.clipboard().setText('00123\tDireção\n\n00024\t')
        # Force the sparse representation; the widget fills only destination columns.
        with patch.object(cb._TableHTMLParser, 'MAX_EXPANDED_CELLS', 4):
            QTest.keyClick(table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual([[table.item(r, c).text() for c in (1, 2)] for r in range(3)],
                         [['00123', 'Direção'], ['', ''], ['00024', '']])

    def test_ctrl_v_literals_multiline_and_styles_reach_model_and_renderer(self):
        from html import escape
        from types import SimpleNamespace
        from PySide6.QtCore import QMimeData, Qt
        from PySide6.QtGui import QTextDocument
        from PySide6.QtTest import QTest
        from core.text_layout import resolve_rich_text
        from features.generator.renderer import NativeRenderer
        from features.workspace.main_window import MainWindow
        table = self.table()
        workspace = SimpleNamespace(table_panel=SimpleNamespace(table=table))
        box = {'x': 10, 'y': 10, 'w': 480, 'h': 160, 'font_size': 20,
               'html': '<p>{nome}</p>', 'rich_text_version': 1}
        renderer = NativeRenderer({'canvas_size': {'w': 500, 'h': 180}, 'boxes': [box]})
        for value in ('São José & <grupo>', '00123', 'Linha 1\nLinha 2', 'Ana data-sheets-'):
            for rich_source in (False, True):
                with self.subTest(value=value, html=rich_source):
                    md = QMimeData()
                    stream = StringIO(newline='')
                    csv.writer(stream, delimiter='\t').writerow([value])
                    md.setText(stream.getvalue())
                    escaped = escape(value, quote=False).replace('\n', '<br>')
                    reference = '<span>' + escaped + '</span>'
                    if rich_source:
                        md.setHtml('<style>.emphasis{font-weight:bold}</style>'
                                   f'<table><tr><td class="emphasis">{escaped}</td></tr></table>')
                        reference = '<b>' + escaped + '</b>'
                    table.clearSelection(); table.setCurrentCell(0, 1)
                    self.app.clipboard().setMimeData(md)
                    QTest.keyClick(table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
                    values = MainWindow._get_row_data_rich(workspace, 0)
                    doc = QTextDocument(); doc.setHtml(resolve_rich_text(box, values))
                    self.assertEqual(table.item(0, 1).text(), value)
                    self.assertEqual(doc.toPlainText(), value)
                    expected = {'nome': reference}
                    self.assertEqual(renderer.render_preview_image(values), renderer.render_preview_image(expected))
                    self.assertEqual(renderer.render_to_qimage({'nome': value}, values),
                                     renderer.render_to_qimage({'nome': value}, expected))


if __name__ == '__main__':
    unittest.main()
