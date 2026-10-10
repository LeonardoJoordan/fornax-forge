"""Operações e limites das tabelas em dados puros, sem QApplication."""
from copy import deepcopy
import random
import subprocess
import sys
import unittest

from core.table_model import (
    TableValidationError, new_table, validate_table, validate_document_tables,
    table_size, cell_at, set_cell_html, format_cells, format_edges, merge_cells,
    split_cell, insert_rows, insert_columns, remove_rows, remove_columns,
    resize_table, set_track_size, duplicate_table, visible_edge_keys,
    plain_cell_text, table_fields, MAX_CELL_HTML_BYTES, MAX_TABLE_HTML_BYTES,
    MAX_TABLE_CELLS,
)
from core.json_limits import validate_json_budget, MAX_JSON_BYTES, MAX_JSON_OBJECTS, MAX_JSON_DEPTH


class TableModelTest(unittest.TestCase):
    def setUp(self):
        self.table = new_table(4,4,width=800,height=400)

    def test_data_module_does_not_import_qt(self):
        result = subprocess.run([sys.executable,'-c',
            'import sys; import core.table_model; assert not any(k.startswith("PySide6") for k in sys.modules)'],
            capture_output=True,text=True,check=True)
        self.assertEqual(result.stderr,'')

    def test_create_copy_independence_and_derived_size(self):
        copy = duplicate_table(self.table,name='Tabela 2')
        self.assertNotEqual(copy['object_id'],self.table['object_id'])
        self.assertTrue({c['id'] for c in copy['cells']}.isdisjoint(c['id'] for c in self.table['cells']))
        copy['column_widths'][0] = 210
        copy['cells'][0]['style']['font_color'] = '#ff0000'
        self.assertEqual(self.table['column_widths'][0],200)
        self.assertEqual(self.table['cells'][0]['style'],{})
        self.assertEqual(table_size(copy),(810,400))
        self.assertNotIn('width',copy)

    def test_all_failed_operations_preserve_original(self):
        before = deepcopy(self.table)
        failures = [lambda:insert_rows(self.table,True),lambda:insert_columns(self.table,1,101),
                    lambda:remove_rows(self.table,0,4),lambda:remove_columns(self.table,-1),
                    lambda:format_cells(self.table,0,0,1,1,{'font_size':False}),
                    lambda:format_edges(self.table,0,0,1,1,{'width':float('nan')}),
                    lambda:resize_table(self.table,.1,.1),
                    lambda:set_cell_html(self.table,0,0,'<img src="file:///etc/passwd">')]
        for operation in failures:
            with self.assertRaises(TableValidationError):
                operation()
            self.assertEqual(self.table,before)

    def test_invalid_structure_types_overlap_holes_and_unknown_fields(self):
        edits = [lambda t:t.update(rows=True),lambda t:t.update(columns=101),
                 lambda t:t.update(width=900),lambda t:t.update(column_widths=[float('inf')]*4),
                 lambda t:t.update(cells=t['cells'][:-1]),
                 lambda t:t['cells'][1].update(row=0,column=0),
                 lambda t:t['cells'][0].update(row_span=True),
                 lambda t:t['cells'][1].update(id=t['cells'][0]['id']),
                 lambda t:t['cells'][0].update(html=123),
                 lambda t:t['cells'][0].update(style={'align':['center']}),
                 lambda t:t.update(visible=1),lambda t:t.update(x=10**400),
                 lambda t:t.update(custom_name='\ud800'),lambda t:t.update(object_id='\ud800'),
                 lambda t:t['style'].update(font_family='\ud800'),
                 lambda t:t['style'].update(fill_color='#aa112233'),
                 lambda t:t.update(edges=[{'orientation':'h','row':True,'column':0,'style':{}}]),
                 lambda t:t.update(edges=[{'orientation':'v','row':0,'column':5,'style':{}}])]
        for edit in edits:
            table=deepcopy(self.table);edit(table)
            with self.subTest(table=edit),self.assertRaises(TableValidationError):
                validate_table(table)

    def test_external_resources_nested_tables_and_surrogate_rejected(self):
        for content in ('<table><tr><td>X</td></tr></table>','<script>alert(1)</script>',
                        '<p style="background:url(http://example.com/x)">X</p>',
                        '<svg></svg>','<object></object>', '\ud800'):
            with self.subTest(content=repr(content)),self.assertRaises(TableValidationError):
                set_cell_html(self.table,0,0,content)

    def test_merge_preserves_anchor_text_reading_order_styles_and_empty_cells(self):
        table=set_cell_html(self.table,0,0,'<p><b>Primeiro</b></p>')
        table=set_cell_html(table,0,1,'<p><i>Segundo</i></p>')
        table=set_cell_html(table,1,0,'<p><u>Terceiro</u></p>')
        table=format_cells(table,0,1,0,1,{'font_color':'#aa0000','font_size':14})
        before=deepcopy(table);anchor=cell_at(table,0,0)['id']
        merged=merge_cells(table,0,0,1,1)
        cell=cell_at(merged,1,1)
        self.assertEqual(cell['id'],anchor)
        self.assertEqual((cell['row_span'],cell['column_span']),(2,2))
        plain=plain_cell_text(cell['html'])
        self.assertLess(plain.index('Primeiro'),plain.index('Segundo'))
        self.assertLess(plain.index('Segundo'),plain.index('Terceiro'))
        self.assertIn('<b>Primeiro</b>',cell['html'])
        self.assertIn('<i>Segundo</i>',cell['html'])
        self.assertIn('<u>Terceiro</u>',cell['html'])
        self.assertIn('#aa0000',cell['html'])
        self.assertIn('14pt',cell['html'])
        self.assertEqual(table,before)

    def test_merge_selection_cut_is_rejected_and_full_merge_is_idempotent(self):
        merged=merge_cells(self.table,0,0,1,1)
        before=deepcopy(merged)
        with self.assertRaises(TableValidationError):
            merge_cells(merged,1,1,2,2)
        with self.assertRaises(TableValidationError):
            format_cells(merged,1,1,2,2,{'fill_color':'#001122'})
        self.assertEqual(merged,before)
        self.assertEqual(merge_cells(merged,0,0,1,1),merged)

    def test_split_keeps_joined_text_in_anchor_and_restores_hidden_borders(self):
        table=format_edges(self.table,0,0,1,1,{'color':'#aa1100'},target='inner')
        table=set_cell_html(table,0,0,'<p>A</p>');table=set_cell_html(table,1,1,'<p>B</p>')
        merged=merge_cells(table,0,0,1,1)
        self.assertEqual(merged['edges'],table['edges'])
        self.assertEqual(len(list(visible_edge_keys(merged))),36)
        divided=split_cell(merged,1,1)
        self.assertEqual(len(list(visible_edge_keys(divided))),40)
        self.assertEqual(divided['edges'],table['edges'])
        self.assertIn('B',cell_at(divided,0,0)['html'])
        self.assertEqual(cell_at(divided,1,1)['html'],'<p></p>')
        self.assertEqual(cell_at(divided,0,0)['id'],cell_at(table,0,0)['id'])
        self.assertNotEqual(divided,table)  # Dividir não é Undo.

    def test_insert_inside_expands_merge_outside_shifts_without_copying_text(self):
        table=set_cell_html(self.table,1,1,'<p><b>Conteúdo</b></p>')
        table=merge_cells(table,1,1,2,2);original=cell_at(table,1,1)
        for operation,axis,span in ((insert_rows,'row','row_span'),(insert_columns,'column','column_span')):
            expanded=operation(table,2,2)
            anchor=next(c for c in expanded['cells'] if c['id']==original['id'])
            self.assertEqual(anchor[span],4)
            self.assertEqual(anchor['html'],original['html'])
            shifted=operation(table,1)
            anchor=next(c for c in shifted['cells'] if c['id']==original['id'])
            self.assertEqual(anchor[axis],2)
            self.assertEqual(anchor[span],2)
            after=operation(table,3)
            self.assertEqual(next(c for c in after['cells'] if c['id']==original['id'])[span],2)

    def test_remove_anchor_preserves_content_identity_in_surviving_merge(self):
        table=set_cell_html(self.table,1,1,'<p>Preservar</p>')
        table=merge_cells(table,1,1,2,2);original=cell_at(table,1,1)
        for operation,span in ((remove_rows,'row_span'),(remove_columns,'column_span')):
            reduced=operation(table,1)
            survivor=next(c for c in reduced['cells'] if c['id']==original['id'])
            self.assertEqual(survivor[span],1)
            self.assertEqual(survivor['html'],original['html'])
            removed=operation(table,1,2)
            self.assertNotIn(original['id'],[c['id'] for c in removed['cells']])

    def test_axis_operations_every_legal_index_and_merge_shape(self):
        # Cobertura independente após cada transformação; não deduzida da tela.
        for top,left,bottom,right in ((0,0,3,3),(1,1,2,2),(0,1,3,1),(1,0,1,3)):
            merged=merge_cells(self.table,top,left,bottom,right)
            for operation in (insert_rows,insert_columns):
                for index in range(5):
                    validate_table(operation(merged,index))
            for operation in (remove_rows,remove_columns):
                for index in range(4):
                    validate_table(operation(merged,index))

    def test_edge_uniqueness_reindexing_and_external_style_priority(self):
        table=format_edges(self.table,0,0,3,3,{'color':'#eebb00'},target='outer')
        table=format_edges(table,0,0,3,3,{'color':'#1144cc'},target='inner')
        for insert,remove in ((insert_rows,remove_rows),(insert_columns,remove_columns)):
            for index in range(5):
                changed=insert(table,index)
                restored=remove(changed,index)
                self.assertEqual(restored['edges'],table['edges'])
        removed=remove_rows(table,3)
        edges={(e['orientation'],e['row'],e['column']):e['style'] for e in removed['edges']}
        self.assertEqual(edges['h',3,1]['color'],'#eebb00')
        self.assertEqual(len(edges),len(removed['edges']))

    def test_formatting_default_and_internal_external_none_targets(self):
        table=format_edges(self.table,1,1,2,2,{'color':'#123456'},target='outer')
        self.assertEqual(len(table['edges']),8)
        table=format_edges(table,1,1,2,2,{'opacity':.25},target='inner')
        self.assertEqual(len(table['edges']),12)
        table=format_edges(table,1,1,2,2,{},target='none')
        self.assertTrue(all(edge['style']['visible'] is False for edge in table['edges']))
        with self.assertRaises(TableValidationError):
            format_edges(self.table,0,0,1,1,{'width':100})

    def test_resize_tracks_preserves_font_padding_and_border(self):
        result=resize_table(self.table,1200,600)
        self.assertEqual(table_size(result),(1200,600))
        self.assertEqual(result['style'],self.table['style'])
        self.assertEqual(result['border'],self.table['border'])
        self.assertEqual(set_track_size(result,'row',0,160)['row_heights'],[160,150,150,150])

    def test_placeholders_across_spans_unicode_entities_and_paragraphs(self):
        table=set_cell_html(self.table,0,0,'<p><b>{no</b><i>me}</i> {ação} &#123;ano&#125;</p>')
        table=set_cell_html(table,1,0,'<p>{no</p><p>me}</p>')
        table=set_cell_html(table,2,0,'<h1>{apeli</h1><h2>do}</h2>')
        self.assertEqual(table_fields(table),['nome','ação','ano'])

    def test_logical_slots_and_axis_limits_at_boundary_and_above(self):
        largest=new_table(100,10,width=2000,height=10000)
        self.assertEqual(largest['rows']*largest['columns'],MAX_TABLE_CELLS)
        with self.assertRaises(TableValidationError):new_table(77,13,width=2600,height=7700)
        with self.assertRaises(TableValidationError):insert_rows(largest,0)
        with self.assertRaises(TableValidationError):insert_columns(largest,0)
        merged=merge_cells(largest,0,0,99,9)
        self.assertEqual(len(merged['cells']),1)
        with self.assertRaises(TableValidationError):insert_columns(merged,0)
        with self.assertRaises(TableValidationError):new_table(101,1,height=11000)
        with self.assertRaises(TableValidationError):new_table(1,101,width=11000)

    def test_document_slot_table_and_identity_limits(self):
        first=new_table(100,10,width=2000,height=10000)
        second=duplicate_table(first)
        validate_document_tables([first,second])
        with self.assertRaises(TableValidationError):validate_document_tables([first,second,new_table(1,1)])
        validate_document_tables([new_table(1,1) for _ in range(20)])
        with self.assertRaises(TableValidationError):validate_document_tables([new_table(1,1) for _ in range(21)])
        with self.assertRaises(TableValidationError):validate_document_tables([first,deepcopy(first)])

    def test_utf8_cell_text_limit_exact_and_above(self):
        exact='á'*(MAX_CELL_HTML_BYTES//2)
        table=set_cell_html(self.table,0,0,exact)
        self.assertEqual(len(cell_at(table,0,0)['html'].encode()),MAX_CELL_HTML_BYTES)
        with self.assertRaises(TableValidationError):set_cell_html(table,0,0,exact+'á')

    def test_table_and_document_text_limit_exact_and_above(self):
        table=deepcopy(self.table)
        for cell in table['cells']:cell['html']='x'*MAX_CELL_HTML_BYTES
        validate_table(table)
        self.assertEqual(sum(len(c['html']) for c in table['cells']),MAX_TABLE_HTML_BYTES)
        validate_document_tables([table,duplicate_table(table)])
        extra=insert_rows(self.table,4)
        for cell in extra['cells'][:16]:cell['html']='x'*MAX_CELL_HTML_BYTES
        extra['cells'][16]['html']='x'
        with self.assertRaises(TableValidationError):validate_table(extra)
        with self.assertRaises(TableValidationError):validate_document_tables([table,duplicate_table(table),new_table(1,1)])

    def test_merge_overflow_is_atomic(self):
        table=new_table(1,2)
        table=set_cell_html(table,0,0,'x'*(MAX_CELL_HTML_BYTES//2))
        table=set_cell_html(table,0,1,'y'*(MAX_CELL_HTML_BYTES//2))
        before=deepcopy(table)
        with self.assertRaises(TableValidationError):merge_cells(table,0,0,0,1)
        self.assertEqual(table,before)

    def test_existing_json_limits_exact_and_above(self):
        validate_json_budget([None]*(MAX_JSON_OBJECTS-1))
        with self.assertRaises(ValueError):validate_json_budget([None]*MAX_JSON_OBJECTS)
        value=None
        for _ in range(MAX_JSON_DEPTH-1):value=[value]
        validate_json_budget(value)
        with self.assertRaises(ValueError):validate_json_budget([value])
        validate_json_budget('x'*(MAX_JSON_BYTES-3))
        with self.assertRaises(ValueError):validate_json_budget('x'*(MAX_JSON_BYTES-2))

    def test_long_deterministic_sequence_has_no_holes_overlap_or_shared_state(self):
        randomizer=random.Random(20261009)
        table=self.table
        for _ in range(70):
            original=deepcopy(table)
            action=randomizer.choice(('insert_rows','insert_columns','remove_rows','remove_columns','merge','split'))
            try:
                if action.startswith('insert'):
                    limit=table['rows' if action.endswith('rows') else 'columns']
                    operation=insert_rows if action.endswith('rows') else insert_columns
                    result=operation(table,randomizer.randrange(limit+1))
                elif action.startswith('remove'):
                    limit=table['rows' if action.endswith('rows') else 'columns']
                    operation=remove_rows if action.endswith('rows') else remove_columns
                    result=operation(table,randomizer.randrange(limit))
                elif action=='merge':
                    result=merge_cells(table,0,0,min(1,table['rows']-1),min(1,table['columns']-1))
                else:
                    result=split_cell(table,0,0)
            except TableValidationError:
                result=table
            self.assertEqual(table,original)
            validate_table(result)
            table=result


if __name__=='__main__':
    unittest.main()
