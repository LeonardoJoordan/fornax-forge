"""Ordenação global opcional, compatível com coleções v3 existentes."""
from copy import deepcopy
from uuid import uuid4

GROUPS = {"image": "images", "text": "boxes", "signature": "signatures", "shape": "shapes"}


def layer_entries(data):
    entries = [(item.get("object_id", f"{kind}:{index}"), kind, item)
               for kind, group in GROUPS.items()
               for index, item in enumerate(data.get(group, []))]
    if "layer_order" not in data:
        return entries
    by_id = {key: (key, kind, item) for key, kind, item in entries}
    result, used = [], set()
    for key in data.get("layer_order", []):
        if key in by_id and key not in used:
            result.append(by_id[key])
            used.add(key)
    result.extend(entry for entry in entries if entry[0] not in used)
    return result


def upgrade_layers(source):
    """Retorna cópia; nunca escreve no arquivo de origem.

    Sem layer_order, a ordem inicial é exatamente a pintura histórica, não os
    z_values do antigo editor, que nem sempre coincidiam com a exportação.
    """
    data = deepcopy(source)
    background = None
    if data.get("background_path"):
        props = deepcopy(data.get("bg_props") or {})
        background = {**props, "path": data["background_path"],
                      "width": props.get("w", data["canvas_size"]["w"]),
                      "height": props.get("h", data["canvas_size"]["h"]),
                      "rotation": 0, "locked": props.get("locked", True),
                      "custom_name": props.get("custom_name") or "Fundo",
                      "object_id": uuid4().hex}
        data.setdefault("images", []).insert(0, background)
        # Preserve original metadata, but remove its rendering role.
        data["background_path"] = None
    used = set()
    for group in GROUPS.values():
        for item in data.setdefault(group, []):
            key = item.get("object_id")
            if not isinstance(key, str) or not key or key in used:
                item["object_id"] = uuid4().hex
            used.add(item["object_id"])
    ordered = layer_entries(data)
    if background:
        ordered = [entry for entry in ordered if entry[0] != background["object_id"]]
        ordered.insert(0, (background["object_id"], "image", background))
    data["layer_order"] = [key for key, _, _ in ordered]
    for index, (_, _, item) in enumerate(ordered):
        item["z_value"] = index
    return data
