"""Entradas/ações fixas de colagem e duplicação, compartilhadas pelas medições."""
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

from PySide6.QtCore import QSignalBlocker
from features.editor.canvas_items import DesignerBox, RectangleItem


def canonical_copy_document(document, *, history=False):
    """Guias não têm ordem de pintura; restore já normaliza z pela layer_order."""
    result = deepcopy(document)
    for page in [*result.get('pages', []), result.get('organogram') or {}]:
        if 'guidelines' in page:
            page['guidelines'].sort(key=lambda g: (g['vertical'], g['pos']))
        if history:
            order = {key: n for n, key in enumerate(page.get('layer_order', []))}
            for collection in ('boxes','images','signatures','shapes'):
                for entry in page.get(collection, []):
                    if not entry.get('mask_shape_id') and entry.get('object_id') in order:
                        entry['z_value'] = order[entry['object_id']]
    return result


def prepare_copy(w, operation):
    with QSignalBlocker(w.scene):
        w.scene.clearSelection()
    if operation.startswith('copy_paste_'):
        count = int(operation.rsplit('_', 1)[1])
        # Origem independente permite colar 50 itens num destino com apenas 20.
        # Dados completos do clipboard real, com posições e IDs reprodutíveis.
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox)
                   and i.isVisible() and i.layer_id != 1)
        box.setSelected(True)
        w.copy_selected_items()
        source = w._object_clipboard[0][1]
        w._object_clipboard = []
        for index in range(count):
            entry = deepcopy(source)
            entry.update(layer_id=1000+index, object_id=f'text:seed-{index}',
                         custom_name=f'Copiado {index+1}', x=20+index%5*225, y=20+index//5*52)
            w._object_clipboard.append(('text', entry))
        return count
    if operation == 'copy_duplicate_board':
        with w._selection_batch():
            for group in w._board_items()[:4]:
                group.setSelected(True)
        w.copy_board_selection()
        w._board_clipboard['groups'].sort(key=lambda g:g['order'])
        return len(w._board_clipboard['groups'])
    if operation == 'copy_duplicate_mask':
        mask = next(i for i in w.scene.items() if isinstance(i, RectangleItem) and i.masked_images()
                    and getattr(i, 'group_id', None) is None)
        mask.setSelected(True)
    elif operation == 'copy_duplicate_group':
        w.select_group(1)
    else:
        box = next(i for i in w.scene.items() if isinstance(i, DesignerBox) and i.isVisible()
                   and i.layer_id != 1 and getattr(i, 'group_id', None) is None)
        box.setSelected(True)
    w.copy_selected_items()
    count = len(w._object_clipboard)
    if operation == 'copy_cross':
        w.switch_model_page('back')
    return count


def perform_copy(w, operation):
    # Identidades novas continuam distintas; apenas a fonte de aleatoriedade do
    # instrumento é fixa para comparar o documento completo antes/depois.
    sequence = iter(range(10000, 11000))
    original_copy = w.copy_board_selection
    def stable_board_copy():
        result = original_copy()
        if result:
            w._board_clipboard['groups'].sort(key=lambda g:g['order'])
        return result
    with patch('features.editor.editor_window.new_signature_id', side_effect=lambda: f'copy-signature-{next(sequence)}'), \
         patch('features.editor.canvas_items.uuid4', side_effect=lambda: UUID(int=next(sequence))), \
         patch('features.editor.organogram_editor.uuid4', side_effect=lambda: UUID(int=next(sequence))), \
         patch.object(w,'copy_board_selection',side_effect=stable_board_copy):
        if operation.startswith('copy_duplicate_'):
            w.duplicate_selected()
        else:
            w.paste_copied_items()


def verify_copy(w, operation, before, after, count, history):
    def total(page):
        return sum(len(page.get(key, [])) for key in ('boxes','images','shapes','signatures'))
    if operation == 'copy_duplicate_board':
        if len(after['organogram']['groups']) != len(before['organogram']['groups'])+count:
            raise AssertionError('Quantidade incorreta de conjuntos duplicados.')
        if len(after['organogram']['connections']) != len(before['organogram']['connections'])+len(w._board_clipboard['connections']):
            raise AssertionError('Conexões internas não foram duplicadas.')
    else:
        index = 1 if operation == 'copy_cross' else 0
        if total(after['pages'][index]) != total(before['pages'][index])+count:
            raise AssertionError('Colagem/duplicação não acrescentou exatamente os itens previstos.')
    if w.history._current_index != history+1:
        raise AssertionError('A operação coletiva não produziu exatamente uma ação de histórico.')
