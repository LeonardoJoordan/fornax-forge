"""Converte as especificações sintéticas da etapa 00 para o contrato v6."""
from core.model_document import persistent_model_document, add_blank_back_page, add_model_table
from core.table_model import new_table, validate_table
from table_fixtures import cases

UNITS_PER_MM = 300 / 25.4


def document_from_spec(fixture):
    document = persistent_model_document(dict(
        name='Tabela sintética: '+fixture['id'], canvas_size={'w':2480,'h':3508},
        target_w_mm=210,target_h_mm=297,boxes=[],images=[],shapes=[],signatures=[],placeholders=[]))
    if len(fixture['pages']) == 2:
        document = add_blank_back_page(document)
    for page in fixture['pages']:
        for spec in page['tables']:
            widths = [value*UNITS_PER_MM for value in spec['column_widths_mm']]
            heights = [value*UNITS_PER_MM for value in spec['row_heights_mm']]
            table = new_table(spec['rows'],spec['columns'],width=sum(widths),height=sum(heights),name=spec['key'])
            table.update(column_widths=widths,row_heights=heights,
                         x=spec['origin_mm'][0]*UNITS_PER_MM,y=spec['origin_mm'][1]*UNITS_PER_MM)
            table['style'].update(font_family=spec['default_font'],font_size=spec['default_font_size_pt'],
                                  padding=spec['padding_mm']*UNITS_PER_MM)
            table['border'].update(color=spec['outline']['color'],width=spec['outline']['width_mm']*UNITS_PER_MM)
            table['cells'] = [dict(id=entry['key'],row=entry['row'],column=entry['column'],
                                   row_span=entry['row_span'],column_span=entry['column_span'],html=entry['html'],
                                   style=dict(align=entry['align'],vertical_align=entry['vertical_align'],
                                              wrap=entry['wrap'],fill_color=entry['fill'])) for entry in spec['cells']]
            validate_table(table)
            document = add_model_table(document,table,page['page'])
    return document


def documents():
    return {fixture['id']:document_from_spec(fixture) for fixture in cases()}
