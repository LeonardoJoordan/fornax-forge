"""Leitura limitada do ODS que o Calc oferece na cópia de células.

O HTML/RTF do Calc pode omitir ênfases parciais. Lemos apenas texto, estilos
e posição da seleção do pacote nativo, em memória, sem executar conteúdo.
"""
from html import escape
from io import BytesIO
import re
import zlib
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from .clipboard import CellValue, _merge_style_states, _style_state_from_style

MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 1024
MAX_CELLS = 100_000
MAX_TEXT_CHARS = 4 * 1024 * 1024
MAX_CELL_CHARS = 64 * 1024
NS = {name: f'urn:oasis:names:tc:opendocument:xmlns:{name}:1.0'
      for name in ('office', 'style', 'text', 'table', 'config')}
NS['fo'] = 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0'


def q(name):
    prefix, local = name.split(':')
    return '{' + NS[prefix] + '}' + local


def is_calc_format(mime):
    # Qt exposes native Windows clipboard formats through this wrapper.
    base = mime.partition(';')[0].strip().lower()
    return (base == 'application/x-openoffice-embed-source-xml' or
            (base == 'application/x-qt-windows-mime' and re.search(
                r';\s*value\s*=\s*"Star Embed Source \(XML\)"(?:\s*;|\s*$)', mime, re.I) is not None))


def _number(value, maximum, minimum=0):
    if not re.fullmatch(r'[0-9]{1,10}', value or ''):
        raise ValueError('Número inválido no clipboard Calc')
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError('Limite de células do clipboard Calc')
    return result


def _repeat(element, axis):
    return _number(element.get(q('table:number-' + axis + '-repeated'), '1'),
                   1_048_576 if axis == 'rows' else 16_384, 1)


def _xml(archive, name, optional=False):
    try:
        info = archive.getinfo(name)
    except KeyError:
        if optional:
            return None
        raise ValueError('Pacote Calc incompleto') from None
    if (info.file_size > MAX_XML_BYTES or info.flag_bits & 1 or
            info.compress_type not in (ZIP_STORED, ZIP_DEFLATED)):
        raise ValueError('XML do clipboard Calc excede os limites')
    with archive.open(info) as stream:
        data = stream.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError('XML excessivo')
    root = ET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    pending = [(root, 0)]
    count = 0
    while pending:
        element, depth = pending.pop()
        count += 1
        if count > 200_000 or depth > 64:
            raise ValueError('XML excessivamente complexo')
        pending.extend((child, depth + 1) for child in element)
    return root


class _Styles:
    def __init__(self, *documents):
        self.named, self.defaults, self.cache = {}, {}, {}
        for document in documents:
            if document is None:
                continue
            for container in document:
                if container.tag not in (q('office:styles'), q('office:automatic-styles')):
                    continue
                for element in container:
                    family = element.get(q('style:family'))
                    if family not in ('table-cell', 'paragraph', 'text'):
                        continue
                    props = element.find('style:text-properties', NS)
                    css = '' if props is None else ';'.join(
                        css_name + ':' + props.get(q(attr), '') for attr, css_name in (
                            ('fo:font-weight', 'font-weight'), ('fo:font-style', 'font-style'),
                            ('style:text-underline-style', 'text-underline-style')) if props.get(q(attr)) is not None)
                    state = _style_state_from_style(css)
                    if element.tag == q('style:default-style'):
                        self.defaults[family] = state
                    elif element.tag == q('style:style'):
                        self.named[family, element.get(q('style:name'))] = (
                            element.get(q('style:parent-style-name')), state)

    def get(self, family, name, chain=()):
        key = (family, name)
        if key in self.cache:
            return self.cache[key]
        if key in chain or len(chain) >= 64:
            raise ValueError('Herança circular de estilos Calc')
        parent, own = self.named.get(key, (None, {}))
        state = _merge_style_states(self.get(family, parent, chain + (key,)) if parent else {}, own)
        self.cache[key] = state
        return state


def _elements(parent, target, wrappers):
    for child in parent:
        if child.tag == q(target):
            yield child
        elif child.tag in {q(tag) for tag in wrappers}:
            yield from _elements(child, target, wrappers)


def _origin(settings):
    if settings is None:
        return 0, 0, None
    for views in settings.iter(q('config:config-item-map-indexed')):
        if views.get(q('config:name')) != 'Views':
            continue
        entry = views.find('config:config-item-map-entry', NS)
        if entry is not None:
            values = {e.get(q('config:name')): e.text for e in entry if e.tag == q('config:config-item')}
            return (_number(values.get('PositionLeft', '0'), 16_383),
                    _number(values.get('PositionTop', '0'), 1_048_575), values.get('ActiveTable'))
    return 0, 0, None


def _cell(element, base, styles):
    if element.tag == q('table:covered-table-cell'):
        return CellValue('', '')
    runs = []
    count = 0

    def append(text, state):
        nonlocal count
        if not text:
            return
        count += len(text)
        if count > MAX_CELL_CHARS:
            raise ValueError('Texto da célula excede o limite')
        tags = tuple(tag for tag in ('b', 'i', 'u') if state.get(tag))
        runs.append((text, tags))

    def walk(node, state):
        family = 'paragraph' if node.tag in (q('text:p'), q('text:h')) else 'text'
        state = _merge_style_states(state, styles.get(family, node.get(q('text:style-name'))))
        append(node.text, state)
        for child in node:
            if child.tag == q('text:s'):
                append(' ' * _number(child.get(q('text:c'), '1'), MAX_CELL_CHARS, 1), state)
            elif child.tag == q('text:tab'):
                append('\t', state)
            elif child.tag == q('text:line-break'):
                append('\n', state)
            elif child.tag in (q('text:span'), q('text:a')):
                walk(child, state)
            # Images, annotations, scripts and linked resources are not text runs.
            append(child.tail, state)

    paragraphs = [p for p in element if p.tag in (q('text:p'), q('text:h'))]
    for index, paragraph in enumerate(paragraphs):
        if index:
            append('\n', base)
        walk(paragraph, base)
    if not paragraphs:
        # Display cached values only. No formula is evaluated.
        value = next((element.get(q('office:' + key)) for key in
                      ('string-value', 'value', 'date-value', 'time-value', 'boolean-value')
                      if element.get(q('office:' + key)) is not None), '')
        append(value, base)
    plain, rich, active = [], [], ()
    for text, tags in runs:
        if tags != active:
            rich.extend('</' + tag + '>' for tag in reversed(active))
            rich.extend('<' + tag + '>' for tag in tags)
            active = tags
        plain.append(text)
        rich.append(escape(text, quote=False).replace('\n', '<br>'))
    rich.extend('</' + tag + '>' for tag in reversed(active))
    return CellValue(''.join(plain), ''.join(rich))


def _grid(content, styles, settings):
    left, top, active = _origin(settings)
    tables = content.findall('office:body/office:spreadsheet/table:table', NS)
    table = next((t for t in tables if t.get(q('table:name')) == active), None)
    if table is None:
        if len(tables) != 1:
            raise ValueError('Seleção Calc ambígua')
        table = tables[0]
    columns = list(_elements(table, 'table:table-column', ('table:table-column-group', 'table:table-columns', 'table:table-header-columns')))
    rows = list(_elements(table, 'table:table-row', ('table:table-row-group', 'table:table-rows', 'table:table-header-rows')))
    width = sum(_repeat(c, 'columns') for c in columns)
    height = sum(_repeat(r, 'rows') for r in rows)
    cell_tags = {q('table:table-cell'), q('table:covered-table-cell')}
    width = max([width] + [sum(_repeat(c, 'columns') for c in row if c.tag in cell_tags) for row in rows])
    if not (0 < width - left <= MAX_COLUMNS and 0 < height - top <= MAX_ROWS
            and (width - left) * (height - top) <= MAX_CELLS
            and width <= 16_384 and height <= 1_048_576):
        raise ValueError('Intervalo Calc excede os limites')
    defaults = [''] * (width - left)
    position = 0
    for column in columns:
        end = position + _repeat(column, 'columns')
        for col in range(max(left, position), min(end, width)):
            defaults[col - left] = column.get(q('table:default-cell-style-name'), '')
        position = end
    result, row_position, text_size = [], 0, 0
    for row in rows:
        end = row_position + _repeat(row, 'rows')
        repeat = end - max(top, row_position)
        row_position = end
        if repeat <= 0:
            continue
        values = [CellValue('', '') for _ in defaults]
        col = 0
        for cell in row:
            if cell.tag not in cell_tags:
                continue
            end_col = col + _repeat(cell, 'columns')
            cached = {}
            for index in range(max(left, col), min(end_col, width)):
                name = (cell.get(q('table:style-name')) or row.get(q('table:default-cell-style-name'))
                        or defaults[index - left])
                if name not in cached:
                    base = _merge_style_states(styles.defaults.get('table-cell', {}), styles.get('table-cell', name))
                    cached[name] = _cell(cell, base, styles)
                values[index - left] = cached[name]
                text_size += repeat * (len(cached[name].plain) + len(cached[name].rich_html))
                if text_size > MAX_TEXT_CHARS:
                    raise ValueError('Conteúdo Calc excede o limite')
            col = end_col
        result.extend([values.copy() for _ in range(repeat)])
    return result


def parse_calc_package(data):
    """Retorna None para dados indisponíveis/inválidos; o chamador usa HTML/TSV."""
    if not data or len(data) > MAX_PACKAGE_BYTES:
        return None
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > 512 or len(names) != len(set(names)):
                return None
            info = archive.getinfo('mimetype')
            if info.file_size > 128 or archive.read(info) != b'application/vnd.oasis.opendocument.spreadsheet':
                return None
            selected = {'content.xml', 'styles.xml', 'settings.xml'}
            if sum(e.file_size for e in entries if e.filename in selected) > 2 * MAX_XML_BYTES:
                return None
            content = _xml(archive, 'content.xml')
            styles = _Styles(_xml(archive, 'styles.xml', optional=True), content)
            return _grid(content, styles, _xml(archive, 'settings.xml', optional=True))
    except (BadZipFile, KeyError, ValueError, RuntimeError, OSError, EOFError,
            ET.ParseError, DefusedXmlException, NotImplementedError, zlib.error):
        return None
