"""Entradas determinísticas e públicas para medir o editor sem dados pessoais."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import random

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QColor

from core.model_document import normalize_model_document, add_blank_back_page
from core.organogram import add_organogram, new_group, UNITS_PER_MM
from core.starter_templates import starter_catalog, model_from_starter


@dataclass(frozen=True)
class Scenario:
    id: str
    operation: str
    fixture: str
    size: int = 20
    cold: bool = False
    mode: str = 'public'
    large: bool = False


def scenarios():
    result = []
    for size in (20, 60, 200):
        fixture = 'simple' if size == 20 else 'mixed'
        for operation in ('select_all', 'layers', 'snapshot_unchanged'):
            result.append(Scenario(f'{operation}-{size}', operation, fixture, size))
    for size in (20, 60):
        result.append(Scenario(f'paste-{size}', 'paste', 'simple' if size == 20 else 'mixed', size))
    for size in (40, 100):
        for operation in ('drag_one', 'drag_four'):
            result.append(Scenario(f'{operation}-{size}', operation, 'connected', size))
    for operation in ('connector_opacity', 'block_outline', 'paint_small', 'switch_board'):
        result.append(Scenario(operation, operation, 'institutional'))
    for size in (40, 400, 2500):
        for operation in ('paint_near', 'paint_far'):
            result.append(Scenario(f'{operation}-{size}', operation, 'grid', size))
    for size in (60, 1200):
        result.append(Scenario(f'text_insert-{size}', 'text_insert', 'text', size))
    result.append(Scenario('text_resize-1200', 'text_resize', 'text', 1200))
    result.append(Scenario('switch_back', 'switch_back', 'duplex', 60))
    result.append(Scenario('page_cycles', 'page_cycles', 'duplex', 60))
    for kind in ('model', 'organogram'):
        result.append(Scenario(f'gallery-{kind}-cold', 'gallery', kind, cold=True))
        result.append(Scenario(f'gallery-{kind}-warm', 'gallery', kind))
    for identity in ('personnel', 'internship-certificate', 'identification-prism', 'formal-invitation'):
        result.append(Scenario(f'load-{identity}', 'load', identity, cold=True))
    for mode, large in (('public', False), ('signatures', False), ('full', False), ('full', True)):
        result.append(Scenario(f'autosave-{mode}-'+('large' if large else 'small'),
                               'autosave', 'mixed', 20, cold=True, mode=mode, large=large))
    result.append(Scenario('autosave-repeated', 'autosave_repeat', 'mixed', 20))
    for operation, fixture, size in (
        ('select_group', 'mixed', 60), ('select_layers', 'mixed', 60),
        ('select_area', 'mixed', 60), ('select_tree', 'connected', 40),
        ('select_area', 'connected', 40),
    ):
        result.append(Scenario(f'{operation}-{fixture}-{size}', operation, fixture, size))
    for operation in ('layer_rename', 'layer_text', 'layer_hide', 'layer_lock',
                      'layer_add', 'layer_delete', 'layer_group', 'layer_ungroup',
                      'layer_reorder', 'layer_cycles'):
        result.append(Scenario(operation, operation, 'mixed', 60))
    for size in (20, 40):
        for count in (1, 4, 10):
            result.append(Scenario(f'board_drag_{count}-{size}', f'board_drag_{count}', 'connected', size))
    for operation in ('board_color', 'board_opacity', 'board_width', 'board_radius',
                      'board_ports', 'board_border_color', 'board_border_opacity',
                      'board_border_width', 'board_border_radius',
                      'board_text_move', 'board_text_edit', 'board_cutouts'):
        result.append(Scenario(operation, operation, 'connected', 40))
    for size in (60, 1200):
        for op in ('type', 'paste'):
            result.append(Scenario(f'typography_{op}-{size}', f'typography_{op}', 'text_work', size))
    for op in ('resize', 'resize_four', 'format', 'reapply'):
        result.append(Scenario(f'typography_{op}', f'typography_{op}', 'text_work', 1200))
    for size in (60, 200):
        result.append(Scenario(f'load_text-{size}', 'load_text', 'text_many', size, cold=True))
    for size in (20, 60, 200):
        for count in (1, 10, 50):
            result.append(Scenario(f'copy_paste-{count}-{size}', f'copy_paste_{count}', 'simple' if size==20 else 'mixed', size))
    result.append(Scenario('copy_cross', 'copy_cross', 'duplex', 60))
    for kind in ('plain', 'mask', 'group'):
        result.append(Scenario(f'copy_duplicate_{kind}', f'copy_duplicate_{kind}', 'mixed', 60))
    result.append(Scenario('copy_duplicate_board', 'copy_duplicate_board', 'connected', 40))
    return tuple(result)


def synthetic_assets(large=False):
    side = 1024 if large else 32
    if large:
        data = bytearray(random.Random(4108).randbytes(side * side * 4))
        data[3::4] = b'\xff' * (side * side)
        image = QImage(data, side, side, side * 4, QImage.Format.Format_RGBA8888).copy()
    else:
        image = QImage(side, side, QImage.Format.Format_ARGB32)
        image.fill(QColor('#547893'))
    encoded = QByteArray()
    output = QBuffer(encoded)
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(output, 'PNG'):
        raise RuntimeError('Não foi possível preparar a imagem sintética.')
    return {'asset:photo.png': bytes(encoded), 'asset:signature.png': bytes(encoded)}


def page_document(count=20, *, mixed=False):
    data = {'name': '', 'canvas_size': {'w': 1200, 'h': 2400},
            'target_w_mm': 101.6, 'target_h_mm': 203.2,
            'boxes': [], 'images': [], 'signatures': [], 'shapes': [],
            'layer_order': [], 'editable_background_initialized': True}
    kinds = ('text', 'shape', 'image', 'signature', 'text')
    collections = {'text': 'boxes', 'shape': 'shapes', 'image': 'images', 'signature': 'signatures'}
    for index in range(count):
        identity = index + 1
        kind = kinds[index % 5] if mixed else 'text'
        entry = {'layer_id': identity, 'object_id': f'{kind}:{identity}',
                 'x': 20 + index % 5 * 225, 'y': 20 + index // 5 * 52,
                 'custom_name': f'Objeto {identity}', 'z_value': identity}
        if kind == 'text':
            entry.update(w=200, h=42, font_size=12, rich_text_version=1,
                         html='<p>Exemplo <b>{Nome}</b></p>')
        else:
            entry.update(width=180, height=40)
            if kind == 'shape':
                entry.update(shape_type='rectangle', fill_color='#dcecf4',
                             outline_enabled=True, outline_width=2)
            else:
                entry['path'] = 'asset:signature.png' if kind == 'signature' else 'asset:photo.png'
                if kind == 'signature':
                    entry['signature_id'] = f'signature-{identity}'
                elif mixed and index % 10 == 2:
                    entry.update(mask_shape_id=f'shape:{identity-1}', mask_order=0, x=0, y=0)
        if mixed and 10 <= index < 20:
            entry['group_id'] = 1
        if index == 0:
            entry['locked'] = True
        if index == 4:
            entry['visible'] = False
        data[collections[kind]].append(entry)
        data['layer_order'].append(entry['object_id'])
    if mixed:
        data['guidelines'] = [{'pos': 400, 'vertical': True}, {'pos': 900, 'vertical': False}]
    data['protection_preferences'] = {'public_signatures_acknowledged': True}
    return normalize_model_document(data)


def make_document(scenario):
    assets = synthetic_assets(scenario.large)
    if scenario.fixture == 'institutional' or scenario.operation == 'load':
        identity = 'corporate-organogram' if scenario.fixture == 'institutional' else scenario.fixture
        template = next(entry for entry in starter_catalog('model') if entry.id == identity)
        return model_from_starter(template)
    if scenario.fixture in ('text_work', 'text_many'):
        from text_cases import text_document
        return text_document(scenario.size if scenario.fixture == 'text_many' else
                             (4 if scenario.operation == 'typography_resize_four' else 1),
                             long=scenario.size == 1200), assets.__getitem__
    if scenario.fixture == 'text':
        doc = page_document(1)
        box = doc['pages'][0]['boxes'][0]
        box['locked'] = False
        words = 'Texto ágil com ênfase, função e acentuação. '
        content = (words * math.ceil(scenario.size / len(words)))[:scenario.size]
        box.update(w=1000, h=2000, html=f'<p>{content}</p>', font_size=16)
        return doc, assets.__getitem__
    mixed = scenario.fixture in ('mixed', 'duplex')
    doc = page_document(scenario.size if mixed or scenario.fixture == 'simple' else 5, mixed=mixed)
    if scenario.fixture == 'duplex':
        doc = add_blank_back_page(doc)
        back = deepcopy(doc['pages'][0])
        back['page_id'] = 'back'
        for box in back['boxes']:
            box['html'] = '<p>Verso <b>{Nome}</b></p>'
        for signature in back['signatures']:
            signature['signature_id'] += '-back'
        doc['pages'][1] = back
        return normalize_model_document(doc), assets.__getitem__
    if scenario.fixture in ('connected', 'grid'):
        doc = add_organogram(doc)
        board = doc['organogram']
        total = scenario.size if scenario.fixture == 'connected' else 1
        for index in range(total):
            if scenario.fixture == 'grid':
                columns = max(n for n in range(1, min(50, math.isqrt(scenario.size)) + 1)
                              if scenario.size % n == 0)
                rows = scenario.size // columns
            else:
                columns = rows = 1
            # A grade usa divisores exatos para respeitar a quantidade solicitada.
            group = new_group(doc, columns=columns, rows=rows, card_width_mm=20,
                              x=(index % 10)*400, y=(index // 10)*650)
            group.update(id=f'block-{index:03}', name=f'Bloco {index+1}', order=index)
            board['groups'].append(group)
            if index:
                board['connections'].append({'source': f'block-{(index-1)//3:03}',
                                             'target': group['id']})
        if scenario.operation.startswith('board_text') or scenario.operation == 'board_cutouts':
            board['boxes'] = [{'layer_id': 501, 'object_id': 'text:501', 'x': 250, 'y': 400, 'w': 800, 'h': 90,
                              'html': '<p>Responsáveis pela unidade</p>', 'rotation': 12,
                              'font_size': 16, 'rich_text_version': 1}]
            board['layer_order'] = ['text:501']
        return normalize_model_document(doc), assets.__getitem__
    return doc, assets.__getitem__


def fingerprint(document, provider):
    from core.model_document import iter_page_asset_paths
    assets = {ref: sha256(provider(ref)).hexdigest()
              for _, _, ref in iter_page_asset_paths(document)}
    payload = {'document': document, 'assets': assets}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).hexdigest()
