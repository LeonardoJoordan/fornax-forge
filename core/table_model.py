"""Tabelas gráficas: dados JSON, validação e operações sem Qt.

Operações são transações por cópia: entrada validada, alteração numa cópia,
resultado validado. Dimensões nas unidades de documento (300/polegada).
"""
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
import math
import re
from uuid import uuid4

from core.table_html import cell_html_has_unsupported_resources

MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 100
MAX_TABLE_CELLS = 1000  # Posições lógicas, mesmo quando mescladas.
MAX_DOCUMENT_TABLE_CELLS = 2000
MAX_DOCUMENT_TABLES = 20
MAX_CELL_HTML_BYTES = 32 * 1024
MAX_TABLE_HTML_BYTES = 512 * 1024
MAX_DOCUMENT_TABLE_HTML_BYTES = 1024 * 1024
MAX_TABLE_DIMENSION = 16_384 * 16  # Mesmo teto geométrico do editor.
MIN_TRACK_SIZE = 1.0

TABLE_KEYS = {'object_id', 'custom_name', 'x', 'y', 'rotation', 'z_value', 'opacity',
              'visible', 'locked', 'group_id', 'layer_id', 'board_behind', 'keep_proportion',
              'rows', 'columns', 'column_widths', 'row_heights', 'style', 'border', 'cells', 'edges'}
CELL_KEYS = {'id', 'row', 'column', 'row_span', 'column_span', 'html', 'style'}
STYLE_DEFAULTS = dict(font_family='Inter 18pt', font_size=10.0, font_color='#17242d',
                      fill_color='#ffffff', fill_opacity=1.0, align='left',
                      vertical_align='top', wrap=True, padding=6.0, line_height=1.15)
BORDER_DEFAULTS = dict(color='#203746', width=2.0, opacity=1.0, visible=True)
# Transparência é um campo próprio; evita ambiguidade ARGB do Qt vs RGBA CSS.
COLOR = re.compile(r'#[0-9a-fA-F]{6}\Z')


class TableValidationError(ValueError):
    """Tabela ou operação inválida; nenhuma alteração foi aplicada à origem."""


def _fail(message):
    raise TableValidationError(message)


def _number(value, lower, upper):
    try:
        return (type(value) in (int, float) and math.isfinite(float(value))
                and lower <= value <= upper)
    except (OverflowError, ValueError):
        return False


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _identity(value):
    return _text_value(value, 128) and value == value.strip()


def _text_value(value, limit):
    if (not isinstance(value, str) or not 0 < len(value) <= limit
            or not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def validate_style(style, *, border=False, complete=False):
    defaults = BORDER_DEFAULTS if border else STYLE_DEFAULTS
    if (not isinstance(style, dict) or set(style)-defaults.keys()
            or (complete and set(style) != defaults.keys())):
        _fail('Estilo de tabela inválido ou com campos desconhecidos.')
    for key, value in style.items():
        if key in ('color', 'font_color', 'fill_color'):
            valid = isinstance(value, str) and bool(COLOR.fullmatch(value))
        elif key in ('opacity', 'fill_opacity'):
            valid = _number(value, 0, 1)
        elif key in ('visible', 'wrap'):
            valid = type(value) is bool
        elif key == 'font_family':
            valid = _text_value(value, 256)
        elif key == 'font_size':
            valid = _number(value, 1, 200)
        elif key == 'padding':
            valid = _number(value, 0, 500)
        elif key == 'line_height':
            valid = _number(value, .5, 5)
        elif key == 'width':
            valid = _number(value, 0, 100)
        elif key == 'align':
            valid = value in ('left', 'center', 'right')
        elif key == 'vertical_align':
            valid = value in ('top', 'center', 'bottom')
        else:
            valid = False
        if not valid:
            _fail(f'Valor inválido para {key}.')


def edge_keys(rows, columns):
    for row in range(rows+1):
        for column in range(columns):
            yield 'h', row, column
    for row in range(rows):
        for column in range(columns+1):
            yield 'v', row, column


def table_size(table):
    return sum(table['column_widths']), sum(table['row_heights'])


def effective_cell_style(table, cell):
    return {**table['style'], **cell.get('style', {})}


def _edge_map(table):
    return {(entry['orientation'], entry['row'], entry['column']): entry['style']
            for entry in table['edges']}


def validate_table(table):
    if not isinstance(table, dict) or set(table)-TABLE_KEYS:
        _fail('Tabela inválida ou com campos desconhecidos.')
    required = {'object_id', 'custom_name', 'rows', 'columns', 'column_widths',
                'row_heights', 'style', 'border', 'cells', 'edges'}
    if not required <= table.keys() or not _identity(table['object_id']):
        _fail('Tabela sem identidade ou dados obrigatórios.')
    if not _identity(table['custom_name']):
        _fail('Nome de tabela inválido.')
    rows, columns = table['rows'], table['columns']
    if not _integer(rows, 1, MAX_TABLE_ROWS) or not _integer(columns, 1, MAX_TABLE_COLUMNS):
        _fail('Linhas e colunas devem estar entre 1 e 100.')
    if rows * columns > MAX_TABLE_CELLS:
        _fail(f'A tabela admite até {MAX_TABLE_CELLS} posições.')
    for key, count in (('column_widths', columns), ('row_heights', rows)):
        values = table[key]
        if (not isinstance(values, list) or len(values) != count
                or not all(_number(v, MIN_TRACK_SIZE, MAX_TABLE_DIMENSION) for v in values)
                or sum(values) > MAX_TABLE_DIMENSION):
            _fail('Medidas de linhas/colunas inválidas.')
    for key in ('x', 'y', 'rotation', 'z_value'):
        if not _number(table.get(key, 0), -MAX_TABLE_DIMENSION, MAX_TABLE_DIMENSION):
            _fail('Geometria de tabela inválida.')
    if not _number(table.get('opacity', 1), 0, 1):
        _fail('Opacidade de tabela inválida.')
    for key in ('visible', 'locked', 'board_behind', 'keep_proportion'):
        if key in table and type(table[key]) is not bool:
            _fail('Estado de tabela inválido.')
    if 'layer_id' in table and not _integer(table['layer_id'], 0, 1_000_000):
        _fail('Identidade de camada inválida.')
    if (table.get('group_id') is not None and not _identity(table['group_id'])
            and not _integer(table['group_id'], 0, 1_000_000)):
        _fail('Identidade de grupo inválida.')
    validate_style(table['style'], complete=True)
    validate_style(table['border'], border=True, complete=True)
    edges = table['edges']
    if not isinstance(edges, list) or len(edges) > 2*rows*columns+rows+columns:
        _fail('Fronteiras inválidas.')
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {'orientation', 'row', 'column', 'style'}:
            _fail('Fronteira com campos inválidos.')
        orientation = edge['orientation']
        if orientation not in ('h', 'v'):
            _fail('Orientação de fronteira inválida.')
        max_row, max_col = (rows, columns-1) if orientation == 'h' else (rows-1, columns)
        if not _integer(edge['row'], 0, max_row) or not _integer(edge['column'], 0, max_col):
            _fail('Fronteira fora da grade.')
        key = orientation, edge['row'], edge['column']
        if key in seen:
            _fail('Fronteira repetida.')
        seen.add(key)
        validate_style(edge['style'], border=True)
    cells = table['cells']
    if not isinstance(cells, list) or not 1 <= len(cells) <= rows*columns:
        _fail('Células inválidas.')
    occupied, ids, text_bytes = set(), set(), 0
    borders = _edge_map(table)
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != CELL_KEYS or not _identity(cell['id']):
            _fail('Célula inválida ou sem identidade.')
        if cell['id'] in ids:
            _fail('Identidade de célula repetida.')
        ids.add(cell['id'])
        r, c, rs, cs = cell['row'], cell['column'], cell['row_span'], cell['column_span']
        if (not _integer(r, 0, rows-1) or not _integer(c, 0, columns-1)
                or not _integer(rs, 1, rows-r) or not _integer(cs, 1, columns-c)):
            _fail('Índice ou alcance de mesclagem inválido.')
        area = {(y, x) for y in range(r, r+rs) for x in range(c, c+cs)}
        if occupied.intersection(area):
            _fail('Mesclagens sobrepostas.')
        occupied.update(area)
        content = cell['html']
        if not isinstance(content, str) or len(content) > MAX_CELL_HTML_BYTES:
            _fail('Conteúdo da célula excede o limite.')
        try:
            size = len(content.encode('utf-8'))
        except UnicodeError as error:
            raise TableValidationError('Texto Unicode inválido.') from error
        if size > MAX_CELL_HTML_BYTES:
            _fail('Conteúdo da célula excede o limite.')
        text_bytes += size
        if text_bytes > MAX_TABLE_HTML_BYTES:
            _fail('Texto da tabela excede o limite.')
        if cell_html_has_unsupported_resources(content) or re.search(r'(?is)<\s*(?:table|script)\b', content):
            _fail('A célula não admite recursos externos, gráficos ou tabelas aninhadas.')
        validate_style(cell['style'])
        style = effective_cell_style(table, cell)
        # Contorno e padding não podem produzir um retângulo de texto negativo.
        boundary = [*[("h", y, x) for y in (r, r+rs) for x in range(c,c+cs)],
                    *[("v", y, x) for y in range(r,r+rs) for x in (c,c+cs)]]
        width = max(({**table['border'], **borders.get(key, {})}['width'] for key in boundary), default=0)
        inset = 2*style['padding'] + width
        if min(sum(table['column_widths'][c:c+cs]), sum(table['row_heights'][r:r+rs])) <= inset:
            _fail('Espaçamento/contorno não cabe na célula.')

    if len(occupied) != rows*columns:
        _fail('A grade possui posições sem célula.')


def validate_document_tables(tables):
    if len(tables) > MAX_DOCUMENT_TABLES:
        _fail('O documento admite até 20 tabelas.')
    slots, text, ids = 0, 0, set()
    for table in tables:
        validate_table(table)
        slots += table['rows']*table['columns']
        text += sum(len(cell['html'].encode('utf-8')) for cell in table['cells'])
        for cell in table['cells']:
            if cell['id'] in ids:
                _fail('Identidade de célula repetida entre tabelas.')
            ids.add(cell['id'])
    if slots > MAX_DOCUMENT_TABLE_CELLS or text > MAX_DOCUMENT_TABLE_HTML_BYTES:
        _fail('O documento excede o limite de posições/texto das tabelas.')


def _cell(row, column):
    return dict(id='cell-'+uuid4().hex, row=row, column=column, row_span=1,
                column_span=1, html='<p></p>', style={})


def new_table(rows=3, columns=3, *, width=600, height=300, name='Tabela 1'):
    if (not _integer(rows,1,MAX_TABLE_ROWS) or not _integer(columns,1,MAX_TABLE_COLUMNS)
            or rows*columns > MAX_TABLE_CELLS or not _number(width,1,MAX_TABLE_DIMENSION)
            or not _number(height,1,MAX_TABLE_DIMENSION)):
        _fail('Dimensões inválidas para criar uma tabela.')
    result = dict(object_id='table-'+uuid4().hex, custom_name=name, x=0.0, y=0.0,
                  rotation=0.0, z_value=0.0, opacity=1.0, visible=True, locked=False,
                  rows=rows, columns=columns, column_widths=[width/columns]*columns,
                  row_heights=[height/rows]*rows, style=deepcopy(STYLE_DEFAULTS),
                  border=deepcopy(BORDER_DEFAULTS), edges=[],
                  cells=[_cell(r,c) for r in range(rows) for c in range(columns)])
    validate_table(result)
    return result


def _copy(table):
    validate_table(table)
    return deepcopy(table)


def _done(table):
    table['cells'].sort(key=lambda cell: (cell['row'],cell['column']))
    validate_table(table)
    return table


def cell_at(table, row, column):
    if not _integer(row,0,table['rows']-1) or not _integer(column,0,table['columns']-1):
        _fail('Célula fora da grade.')
    return next(cell for cell in table['cells'] if cell['row'] <= row < cell['row']+cell['row_span']
                and cell['column'] <= column < cell['column']+cell['column_span'])


def _selection(table, top, left, bottom, right):
    if (not _integer(top,0,table['rows']-1) or not _integer(bottom,top,table['rows']-1)
            or not _integer(left,0,table['columns']-1) or not _integer(right,left,table['columns']-1)):
        _fail('Intervalo de células inválido.')
    selected = []
    for cell in table['cells']:
        r,c,rs,cs = (cell[k] for k in ('row','column','row_span','column_span'))
        if r <= bottom and r+rs-1 >= top and c <= right and c+cs-1 >= left:
            if not (top <= r and r+rs-1 <= bottom and left <= c and c+cs-1 <= right):
                _fail('O intervalo corta uma mesclagem existente.')
            selected.append(cell)
    return sorted(selected,key=lambda cell: (cell['row'],cell['column']))


def set_cell_html(table, row, column, content):
    result = _copy(table)
    cell_at(result,row,column)['html'] = content
    return _done(result)


def format_cells(table, top, left, bottom, right, style):
    validate_style(style)
    result = _copy(table)
    for cell in _selection(result,top,left,bottom,right):
        cell['style'].update(deepcopy(style))
    return _done(result)


def _cells_by_ids(table, cell_ids):
    if not isinstance(cell_ids, (list, tuple, set, frozenset)) or not cell_ids:
        _fail('Seleção de células inválida.')
    if not all(isinstance(identity, str) for identity in cell_ids):
        _fail('Seleção de células inválida.')
    cell_ids = set(cell_ids)
    selected = [cell for cell in table['cells'] if cell['id'] in cell_ids]
    if {cell['id'] for cell in selected} != cell_ids:
        _fail('Seleção de células inválida.')
    return selected


def format_cell_ids(table, cell_ids, style):
    """Formata células avulsas numa única transação validada."""
    validate_style(style)
    result = _copy(table)
    for cell in _cells_by_ids(result, cell_ids):
        cell['style'].update(deepcopy(style))
    return _done(result)


def cell_edge_keys(cells):
    """Fronteiras das posições escolhidas, incluindo divisas de mesclagens."""
    keys = set()
    for cell in cells:
        r, c, rs, cs = (cell[k] for k in ('row', 'column', 'row_span', 'column_span'))
        keys.update(('h', y, x) for y in range(r, r+rs+1) for x in range(c, c+cs))
        keys.update(('v', y, x) for y in range(r, r+rs) for x in range(c, c+cs+1))
    return keys


def format_cell_edge_ids(table, cell_ids, style):
    """Altera apenas as fronteiras das células escolhidas, sem preencher lacunas."""
    validate_style(style, border=True)
    result = _copy(table)
    keys = cell_edge_keys(_cells_by_ids(result, cell_ids))
    mapping = deepcopy(_edge_map(result))
    for key in keys:
        mapping.setdefault(key, {}).update(deepcopy(style))
    _store_edges(result, mapping)
    return _done(result)


class _PlainText(HTMLParser):
    BLOCK_TAGS = {'p', 'div', 'br', 'li', 'hr', 'pre', 'blockquote', 'h1', 'h2', 'h3',
                  'h4', 'h5', 'h6', 'ul', 'ol', 'dl', 'dt', 'dd'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('head','script','style'):
            self.ignored += 1
        if not self.ignored and tag in self.BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('head','script','style'):
            self.ignored = max(0,self.ignored-1)
        if not self.ignored and tag in self.BLOCK_TAGS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def plain_cell_text(content):
    parser = _PlainText()
    parser.feed(content)
    parser.close()
    return ''.join(parser.parts)


def table_fields(table):
    return list(dict.fromkeys(field for cell in table['cells']
                             for field in re.findall(r'\{([\w]+)\}',plain_cell_text(cell['html']))))


def _merge_fragment(table, cell):
    style = effective_cell_style(table,cell)
    family = style['font_family'].replace('\\','\\\\').replace('"','\\"')
    css = f'font-family:"{family}";font-size:{style["font_size"]}pt;color:{style["font_color"]};'
    content = cell['html']
    body = re.search(r'(?is)<body\b([^>]*)>(.*?)</body\s*>',content)
    if body:
        content = '<div'+body[1]+'>'+body[2]+'</div>'
    return '<div style="'+escape(css,quote=True)+'">'+content+'</div>'


def merge_cells(table, top, left, bottom, right):
    result = _copy(table)
    selected = _selection(result,top,left,bottom,right)
    if len(selected) == 1:
        return result
    anchor = cell_at(result,top,left)
    fragments = [_merge_fragment(result,cell) for cell in selected if plain_cell_text(cell['html']).strip()]
    anchor['html'] = ''.join(fragments) if fragments else '<p></p>'
    anchor.update(row_span=bottom-top+1,column_span=right-left+1)
    ids = {cell['id'] for cell in selected if cell is not anchor}
    result['cells'] = [cell for cell in result['cells'] if cell['id'] not in ids]
    return _done(result)


def split_cell(table, row, column):
    result = _copy(table)
    anchor = cell_at(result,row,column)
    r,c,rs,cs = (anchor[k] for k in ('row','column','row_span','column_span'))
    for y in range(r,r+rs):
        for x in range(c,c+cs):
            if (y,x) != (r,c):
                new = _cell(y,x)
                new['style'] = deepcopy(anchor['style'])
                result['cells'].append(new)
    anchor.update(row_span=1,column_span=1)
    return _done(result)


def visible_edge_keys(table):
    owners = {(r,c): cell['id'] for cell in table['cells']
              for r in range(cell['row'],cell['row']+cell['row_span'])
              for c in range(cell['column'],cell['column']+cell['column_span'])}
    for orientation,r,c in edge_keys(table['rows'],table['columns']):
        if orientation == 'h':
            visible = r in (0,table['rows']) or owners[r-1,c] != owners[r,c]
        else:
            visible = c in (0,table['columns']) or owners[r,c-1] != owners[r,c]
        if visible:
            yield orientation,r,c


def _store_edges(table, mapping):
    table['edges'] = []
    for (orientation,r,c), override in sorted(mapping.items()):
        style = {key:value for key,value in override.items() if value != table['border'][key]}
        if style:
            table['edges'].append(dict(orientation=orientation,row=r,column=c,style=deepcopy(style)))


def format_edges(table, top, left, bottom, right, style, *, target='all'):
    validate_style(style,border=True)
    if target not in ('all','outer','inner','none'):
        _fail('Alvo de contorno inválido.')
    result = _copy(table)
    _selection(result,top,left,bottom,right)
    mapping = deepcopy(_edge_map(result))
    for orientation,r,c in edge_keys(result['rows'],result['columns']):
        if orientation == 'h':
            inside = top <= r <= bottom+1 and left <= c <= right
            outer = r in (top,bottom+1)
        else:
            inside = top <= r <= bottom and left <= c <= right+1
            outer = c in (left,right+1)
        if inside and (target in ('all','none') or (target=='outer')==outer):
            mapping.setdefault((orientation,r,c),{}).update(deepcopy(style) if target!='none' else {'visible':False})
    _store_edges(result,mapping)
    return _done(result)


def _fill_grid(table):
    occupied = {(r,c) for cell in table['cells'] for r in range(cell['row'],cell['row']+cell['row_span'])
                for c in range(cell['column'],cell['column']+cell['column_span'])}
    table['cells'].extend(_cell(r,c) for r in range(table['rows']) for c in range(table['columns'])
                          if (r,c) not in occupied)


def _change_axis(table, axis, index, count, *, insert, size=None):
    result = _copy(table)
    row_axis = axis == 'row'
    coordinate, span, quantity, tracks = ('row','row_span','rows','row_heights') if row_axis else ('column','column_span','columns','column_widths')
    old_size = result[quantity]
    if not _integer(index,0,old_size if insert else old_size-1) or not _integer(count,1,100):
        _fail('Posição/quantidade inválida para alterar a tabela.')
    if not insert and (index+count > old_size or count == old_size):
        _fail('A tabela precisa conservar ao menos uma linha e uma coluna.')
    new_size = old_size+count if insert else old_size-count
    max_size = MAX_TABLE_ROWS if row_axis else MAX_TABLE_COLUMNS
    other = result['columns' if row_axis else 'rows']
    if new_size > max_size or new_size*other > MAX_TABLE_CELLS:
        _fail('Inserção excede os limites da tabela.')
    if insert:
        size = result[tracks][min(index,old_size-1)] if size is None else size
        if not _number(size,MIN_TRACK_SIZE,MAX_TABLE_DIMENSION):
            _fail('Medida de linha/coluna inválida.')
        result[tracks][index:index] = [size]*count
    else:
        del result[tracks][index:index+count]
    result[quantity] = new_size
    retained = []
    for cell in result['cells']:
        start, stop = cell[coordinate],cell[coordinate]+cell[span]
        if insert:
            if index <= start:
                cell[coordinate] += count
            elif index < stop:
                cell[span] += count
        else:
            surviving = max(0,min(stop,index)-start)+max(0,stop-max(start,index+count))
            if not surviving:
                continue
            cell[coordinate] = start if start < index else (start-count if start >= index+count else index)
            cell[span] = surviving
        retained.append(cell)
    result['cells'] = retained
    old_mapping = _edge_map(table)
    new_mapping, priorities = {}, {}
    cross = 'h' if row_axis else 'v'
    for key in edge_keys(table['rows'],table['columns']):
        orientation,r,c = key
        position = r if row_axis else c
        boundary = orientation == cross
        if insert:
            shift = position >= index and not (boundary and index==position==0)
            new_position = position+count if shift else position
        elif boundary:
            if index < position < index+count:
                continue
            new_position = position-count if position >= index+count else position
        else:
            if index <= position < index+count:
                continue
            new_position = position-count if position >= index+count else position
        new_key = (orientation,new_position,c) if row_axis else (orientation,r,new_position)
        # Divisas que colapsam: contorno externo tem prioridade; depois a
        # fronteira anterior ao intervalo removido. Não depende da lista JSON.
        priority = (boundary and position in (0,old_size), -position)
        if new_key not in priorities or priority > priorities[new_key]:
            new_mapping[new_key] = deepcopy(old_mapping.get(key,{}))
            priorities[new_key] = priority
    if insert:
        if 0 < index < old_size:
            # A divisa existente delimita ambos os lados do intervalo novo.
            # Assim remover esse intervalo também conserva seu contorno.
            for key in edge_keys(table['rows'],table['columns']):
                orientation,r,c = key
                if orientation == cross and (r if row_axis else c) == index:
                    new_mapping[key] = deepcopy(old_mapping.get(key,{}))
        reference = min(index,old_size-1)
        for key in edge_keys(table['rows'],table['columns']):
            orientation,r,c = key
            if orientation != cross and (r if row_axis else c)==reference:
                for position in range(index,index+count):
                    new_key = (orientation,position,c) if row_axis else (orientation,r,position)
                    new_mapping[new_key] = deepcopy(old_mapping.get(key,{}))
    _store_edges(result,new_mapping)
    _fill_grid(result)
    return _done(result)


def insert_rows(table, index, count=1, *, height=None):
    return _change_axis(table,'row',index,count,insert=True,size=height)


def insert_columns(table, index, count=1, *, width=None):
    return _change_axis(table,'column',index,count,insert=True,size=width)


def remove_rows(table, index, count=1):
    return _change_axis(table,'row',index,count,insert=False)


def remove_columns(table, index, count=1):
    return _change_axis(table,'column',index,count,insert=False)


def resize_table(table, width, height):
    result = _copy(table)
    if not _number(width,1,MAX_TABLE_DIMENSION) or not _number(height,1,MAX_TABLE_DIMENSION):
        _fail('Dimensões inválidas para redimensionar.')
    old_w,old_h = table_size(result)
    result['column_widths'] = [value*width/old_w for value in result['column_widths']]
    result['row_heights'] = [value*height/old_h for value in result['row_heights']]
    return _done(result)


def set_track_size(table, axis, index, size):
    return set_track_sizes(table, axis, [index], size)


def set_track_sizes(table, axis, indexes, size):
    """Altera medidas em lote, validando a tabela uma vez antes/depois."""
    result = _copy(table)
    if axis not in ('row','column'):
        _fail('Eixo inválido.')
    key = 'row_heights' if axis=='row' else 'column_widths'
    if (not isinstance(indexes, list) or not indexes or len(indexes) > len(result[key])
            or not all(_integer(index,0,len(result[key])-1) for index in indexes)
            or not _number(size,MIN_TRACK_SIZE,MAX_TABLE_DIMENSION)):
        _fail('Medida de linha/coluna inválida.')
    for index in indexes:
        result[key][index] = size
    return _done(result)


def duplicate_table(table, *, name=None):
    result = _copy(table)
    result['object_id'] = 'table-'+uuid4().hex
    result.pop('layer_id',None)
    if name is not None:
        result['custom_name'] = name
    for cell in result['cells']:
        cell['id'] = 'cell-'+uuid4().hex
    return _done(result)
