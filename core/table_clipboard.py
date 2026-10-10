"""Intervalos de tabelas gráficas: contrato validado, sem objetos Qt."""
from copy import deepcopy
import csv
from html import escape
from io import StringIO
import json
from uuid import uuid4

from core.json_limits import validate_json_budget
from core.table_model import (new_table, validate_table, _selection, _edge_map,
                              _store_edges, edge_keys, effective_cell_style,
                              TableValidationError, MAX_TABLE_CELLS)

TABLE_RANGE_MIME = 'application/x-fornax-table-range+json'
MAX_CLIPBOARD_BYTES = 4 * 1024 * 1024


def copy_range(table, top, left, bottom, right):
    validate_table(table)
    cells = _selection(table, top, left, bottom, right)
    widths = table['column_widths'][left:right+1]
    heights = table['row_heights'][top:bottom+1]
    result = new_table(len(heights), len(widths), width=max(sum(widths),len(widths)*30),
                       height=max(sum(heights),len(heights)*30))
    result.update(column_widths=deepcopy(widths), row_heights=deepcopy(heights),
                  style=deepcopy(table['style']), border=deepcopy(table['border']))
    result['cells'] = []
    for cell in cells:
        entry = deepcopy(cell)
        entry.update(row=cell['row']-top, column=cell['column']-left)
        result['cells'].append(entry)
    result['edges'] = []
    for edge in table['edges']:
        r, c = edge['row'], edge['column']
        inside = (top <= r <= bottom+1 and left <= c <= right if edge['orientation']=='h'
                  else top <= r <= bottom and left <= c <= right+1)
        if inside:
            entry = deepcopy(edge)
            entry.update(row=r-top, column=c-left)
            result['edges'].append(entry)
    validate_table(result)
    return result


def encode_range(table):
    validate_table(table)
    payload = {'version': 1, 'table': table}
    validate_json_budget(payload)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) > MAX_CLIPBOARD_BYTES:
        raise TableValidationError('O intervalo excede o limite da área de transferência.')
    return encoded


def decode_range(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_CLIPBOARD_BYTES:
        raise TableValidationError('Área de transferência inválida ou excessiva.')
    try:
        payload = json.loads(raw.decode('utf-8'))
        validate_json_budget(payload)
        if (not isinstance(payload, dict) or set(payload) != {'version', 'table'}
                or type(payload['version']) is not int or payload['version'] != 1):
            raise ValueError('Versão de intervalo não reconhecida.')
        validate_table(payload['table'])
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        raise TableValidationError(str(error)) from error
    return deepcopy(payload['table'])


def paste_range(table, source, row, column, *, content_only=False):
    validate_table(table)
    validate_table(source)
    bottom, right = row+source['rows']-1, column+source['columns']-1
    selected = _selection(table, row, column, bottom, right)
    source_by_anchor = {(c['row']+row, c['column']+column): c for c in source['cells']}
    for cell in selected:
        if cell['row_span'] > 1 or cell['column_span'] > 1:
            counterpart = source_by_anchor.get((cell['row'], cell['column']))
            if (counterpart is None or (cell['row_span'], cell['column_span']) !=
                    (counterpart['row_span'], counterpart['column_span'])):
                raise TableValidationError('O intervalo intercepta uma mesclagem incompatível.')
    result = deepcopy(table)
    if content_only:
        # Planilhas externas trazem somente texto, nunca estilo/estrutura HTML.
        for cell in result['cells']:
            entry = source_by_anchor.get((cell['row'], cell['column']))
            if entry is not None:
                cell['html'] = entry['html']
    else:
        removed = {cell['id'] for cell in selected}
        result['cells'] = [cell for cell in result['cells'] if cell['id'] not in removed]
        for cell in source['cells']:
            entry = deepcopy(cell)
            entry.update(id='cell-'+uuid4().hex, row=cell['row']+row, column=cell['column']+column,
                         style=effective_cell_style(source, cell))
            result['cells'].append(entry)
        mapping, source_edges = _edge_map(result), _edge_map(source)
        for orientation, r, c in edge_keys(source['rows'], source['columns']):
            mapping[orientation, r+row, c+column] = {
                **source['border'], **source_edges.get((orientation, r, c), {})}
        _store_edges(result, mapping)
    # Mantém medidas das linhas/colunas do destino; não redimensiona vizinhos.
    validate_table(result)
    return result


def table_from_tsv(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_CLIPBOARD_BYTES:
        raise TableValidationError('Texto da área de transferência excessivo.')
    try:
        rows = []
        for values in csv.reader(StringIO(text, newline=''), delimiter='\t', strict=True):
            rows.append(values or [''])
            if len(rows) > 100 or len(values) > 100 or sum(len(r) for r in rows) > MAX_TABLE_CELLS:
                raise TableValidationError('O intervalo colado excede os limites da tabela.')
        if not rows:
            raise TableValidationError('A área de transferência está vazia.')
        columns = max(len(row) for row in rows)
        result = new_table(len(rows), columns, width=max(600, columns*30),
                           height=max(300, len(rows)*30))
        for cell in result['cells']:
            values = rows[cell['row']]
            value = values[cell['column']] if cell['column'] < len(values) else ''
            value = value.replace('\r\n', '\n').replace('\r', '\n')
            cell['html'] = '<p>'+escape(value).replace('\n', '<br>')+'</p>'
        validate_table(result)
        return result
    except csv.Error as error:
        raise TableValidationError('Texto tabular inválido: '+str(error)) from error
