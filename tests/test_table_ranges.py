"""Contrato de intervalos: integridade, interoperabilidade e recusa atômica."""
from copy import deepcopy
import json
import unittest

from core.table_model import (new_table, merge_cells, format_cells, format_edges,
    set_cell_html, cell_at, set_track_sizes, validate_table, effective_cell_style,
    TableValidationError)
from core.table_clipboard import (copy_range, encode_range, decode_range,
    paste_range, table_from_tsv, MAX_CLIPBOARD_BYTES)


class TableRangeTest(unittest.TestCase):
    def test_mime_roundtrip_preserves_merges_style_edges_and_literal_fields(self):
        source = merge_cells(new_table(3,3),0,0,0,1)
        source = set_cell_html(source,0,0,'<p><b>{nome}</b> |{cargo}|</p>')
        source = format_cells(source,0,0,1,1,{'fill_color':'#123456','font_size':9.5})
        source = format_edges(source,0,0,1,1,{'color':'#abcdef','width':2},target='outer')
        before = deepcopy(source)
        copied = copy_range(source,0,0,1,1)
        self.assertEqual(decode_range(encode_range(copied)),copied)
        self.assertEqual(cell_at(copied,0,0)['column_span'],2)
        self.assertIn('{nome}',cell_at(copied,0,0)['html'])
        self.assertEqual(source,before)

    def test_internal_paste_new_cell_ids_keeps_destination_tracks_and_neighbors(self):
        source = merge_cells(new_table(2,2),0,0,0,1)
        source = format_cells(source,0,0,1,1,{'fill_color':'#aabbcc'})
        source = set_cell_html(source,0,0,'<p>Nome</p>')
        target = new_table(4,4,width=800,height=600)
        before = deepcopy(target)
        result = paste_range(target,source,1,1)
        self.assertEqual(result['object_id'],target['object_id'])
        self.assertEqual(result['column_widths'],target['column_widths'])
        self.assertEqual(result['row_heights'],target['row_heights'])
        self.assertEqual(cell_at(result,0,0),cell_at(target,0,0))
        self.assertEqual(cell_at(result,1,1)['column_span'],2)
        self.assertEqual(effective_cell_style(result,cell_at(result,1,1))['fill_color'],'#aabbcc')
        self.assertFalse({c['id'] for c in source['cells']} & {c['id'] for c in result['cells']})
        self.assertEqual(target,before)
        validate_table(result)

    def test_tsv_quotes_unicode_multiline_and_literal_html(self):
        source = table_from_tsv('José\t"linha 1\nlinha 2"\r\n"a\tb"\t<img src=""x"">\r\n')
        self.assertEqual((source['rows'],source['columns']),(2,2))
        self.assertIn('linha 1<br>linha 2',cell_at(source,0,1)['html'])
        self.assertIn('a\tb',cell_at(source,1,0)['html'])
        self.assertIn('&lt;img',cell_at(source,1,1)['html'])

    def test_external_content_only_keeps_ids_styles_and_edges(self):
        target = format_cells(new_table(3,3),0,0,2,2,{'fill_color':'#123456','font_size':11})
        target = format_edges(target,0,0,2,2,{'color':'#112233'})
        result = paste_range(target,table_from_tsv('1\t2\n3\t4'),0,0,content_only=True)
        for old,new in zip(target['cells'],result['cells']):
            self.assertEqual(old['id'],new['id']);self.assertEqual(old['style'],new['style'])
        self.assertEqual(result['edges'],target['edges'])
        self.assertIn('4',cell_at(result,1,1)['html'])

    def test_rejects_nonfitting_and_partial_or_incompatible_merges_without_mutation(self):
        target = merge_cells(new_table(3,3),0,0,0,1)
        before = deepcopy(target)
        for row,col,source in ((2,2,new_table(2,2)),(0,1,new_table(1,1)),(0,0,new_table(1,2))):
            with self.subTest(row=row,column=col),self.assertRaises(TableValidationError):
                paste_range(target,source,row,col)
            self.assertEqual(target,before)
        with self.assertRaises(TableValidationError):copy_range(target,0,1,1,1)

    def test_matching_merge_can_replace_without_shared_references(self):
        target = merge_cells(new_table(2,2),0,0,0,1)
        source = set_cell_html(deepcopy(target),0,0,'<p>Alterado</p>')
        result = paste_range(target,source,0,0)
        cell_at(result,0,0)['style']['fill_color'] = '#000000'
        self.assertNotIn('fill_color',cell_at(source,0,0)['style'])
        self.assertNotIn('Alterado',cell_at(target,0,0)['html'])

    def test_invalid_mime_version_keys_json_resources_and_budget(self):
        source = new_table(1,1)
        invalid = [b'bad',b'\xff',b'['*100,b'x'*(MAX_CLIPBOARD_BYTES+1),
                   json.dumps({'version':True,'table':source}).encode(),
                   json.dumps({'version':2,'table':source}).encode(),
                   json.dumps({'version':1,'table':source,'extra':0}).encode()]
        malicious = deepcopy(source);malicious['cells'][0]['html']='<img src="https://example.org/x.png">'
        invalid.append(json.dumps({'version':1,'table':malicious}).encode())
        for raw in invalid:
            with self.subTest(length=len(raw)),self.assertRaises(TableValidationError):decode_range(raw)

    def test_tsv_limits_and_ragged_rows(self):
        for text in ('','x'*(MAX_CLIPBOARD_BYTES+1),'\n'.join(['x']*101),
                     '\t'.join(['x']*101),'\n'.join(['\t'.join(['x']*40)]*30),'"unterminated'):
            with self.subTest(length=len(text)),self.assertRaises(TableValidationError):table_from_tsv(text)
        result = table_from_tsv('a\tb\nc')
        self.assertEqual(cell_at(result,1,1)['html'],'<p></p>')
        self.assertEqual(table_from_tsv('\n'.join(['x']*100))['rows'],100)

    def test_batch_track_resize_is_atomic_and_keeps_unselected_tracks(self):
        target = new_table(3,3);before = deepcopy(target)
        result = set_track_sizes(target,'column',[0,2],300)
        self.assertEqual(result['column_widths'],[300,200,300])
        self.assertEqual(target,before)
        for indexes,size in (([0,4],300),([0,1],.01),([],300),([False],300)):
            with self.assertRaises(TableValidationError):set_track_sizes(target,'column',indexes,size)
            self.assertEqual(target,before)

    def test_copy_narrow_valid_cells_uses_original_metrics(self):
        target = new_table(2,2)
        target = format_cells(target,0,0,1,1,{'padding':0})
        target = set_track_sizes(target,'column',[0,1],3)
        copied = copy_range(target,0,0,1,1)
        self.assertEqual(copied['column_widths'],[3,3]);validate_table(copied)

    def test_literal_resource_tokens_allowed_but_encoded_markup_css_rejected(self):
        target = new_table(1,1)
        literal = '<p>&lt;img src="x"&gt; url(x) @import</p>'
        self.assertEqual(set_cell_html(target,0,0,literal)['cells'][0]['html'],literal)
        for content in ('<img src="x">','<style>p {background:url(x)}</style>',
                        '<style>@import "x";</style>', '<p style="background:u&#114;l&#40;x)">X</p>',
                        '<p sr&#99;="x">X</p>',
                        '<p style="font-family:\'>\'; background:url(x)">X</p>'):
            with self.subTest(content=content),self.assertRaises(TableValidationError):
                set_cell_html(target,0,0,content)


if __name__ == '__main__':unittest.main()
