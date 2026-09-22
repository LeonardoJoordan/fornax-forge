"""Fronteira entre documentos persistidos e o estado plano da cena do editor."""

from __future__ import annotations

from copy import deepcopy


def prepare_scene_page(page_data: dict) -> dict:
    """Retorna uma cópia com os poucos padrões exigidos pela cena atual.

    A normalização estrutural v3/v4 pertence a ``core.model_document``. Esta
    função concentra somente tolerâncias do editor para campos que versões
    antigas não gravavam e que o carregador da cena ainda acessa diretamente.
    """
    data = deepcopy(page_data)
    entries = [item for collection in ('shapes', 'images', 'signatures', 'boxes')
               for item in data.get(collection, [])]
    background = data.get('bg_props')
    background_id = background.get('layer_id') if isinstance(background, dict) else None
    used = {background_id} if type(background_id) is int else set()
    next_id = max([0, *used, *(item['layer_id'] for item in entries
                             if type(item.get('layer_id')) is int)]) + 1
    for item in entries:
        layer_id = item.get('layer_id')
        if type(layer_id) is not int or layer_id in used:
            item['layer_id'] = next_id
            next_id += 1
        used.add(item['layer_id'])
    # O arquivo aceita IDs estáveis arbitrários; a cena usa shape:<layer_id>.
    shape_ids = {item.get('object_id'): f"shape:{item['layer_id']}"
                 for item in data.get('shapes', []) if item.get('object_id')}
    for item in data.get('images', []):
        reference = item.get('mask_shape_id')
        if reference in shape_ids:
            item['mask_shape_id'] = shape_ids[reference]

    background = data.get("bg_props")
    if isinstance(background, dict):
        background.setdefault("layer_id", None)
        background.setdefault("custom_name", "")

    for box in data.get("boxes", []):
        box.setdefault("layer_id", None)
        if "html" not in box:
            box["html"] = f"<p>{box.get('id', 'Placeholder')}</p>"

    for collection in ("signatures", "images"):
        for item in data.get(collection, []):
            item.setdefault("layer_id", None)

    return data
