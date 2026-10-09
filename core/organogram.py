"""Composição de quadros com uma única referência ao cartão da página 1.

As coordenadas usam as unidades de cena existentes (300 unidades/polegada).
Nenhuma dimensão de quadro implica alocar um bitmap do mesmo tamanho.
"""
from copy import deepcopy
import math
import re
from uuid import uuid4

from PySide6.QtCore import QRectF, QPointF
from PySide6.QtGui import QTransform

from core.model_document import ModelValidationError, MAX_OBJECT_COORDINATE
from core.board_connectors import connector_style, validate_connector_style, connector_paths
from core.board_borders import border_style, validate_border_style, bordered_group_bounds, bordered_card_bounds
from core.i18n import tr

UNITS_PER_MM = 300 / 25.4
MAX_SLOTS = 2500
BLOCK_DESTINATION_KEY = "__board_block__"
DISABLED_ROW_KEY = "__board_disabled__"


def block_name_key(name):
    """A identidade legível ignora espaços externos e caixa, mas mantém acentos."""
    return str(name or "").strip().casefold()


def validate_block_name(name, groups, *, exclude_id=None):
    if not isinstance(name, str) or not name.strip():
        raise ModelValidationError(tr("Informe um nome para o bloco."))
    if any(group["id"] != exclude_id and block_name_key(group.get("name")) == block_name_key(name)
           for group in groups):
        raise ModelValidationError(tr("O nome ‘{nome}’ já está em uso. Escolha outro nome.").format(nome=name.strip()))


def upgrade_legacy_block_names(board):
    """Migra somente quadros anteriores à regra de nomes únicos.

    O chamador trabalha em uma cópia. UUIDs, geometria, filtros e conexões não
    mudam; nomes já únicos ficam reservados antes de renomear as repetições.
    O marcador persistido mantém a validação estrita nas próximas edições.
    """
    if not isinstance(board, dict) or "block_names_version" in board:
        return
    groups = board.get("groups")
    if not isinstance(groups, list) or not all(isinstance(group, dict) for group in groups):
        return
    reserved = {block_name_key(group.get("name")) for group in groups
                if isinstance(group.get("name", ""), str) and group.get("name", "").strip()}
    seen = set()
    numbered = re.escape(tr("Bloco {numero}")).replace(re.escape("{numero}"), r"\d+")
    for group in groups:
        original = group.get("name", "")
        if not isinstance(original, str):
            continue  # A validação normal ainda rejeita tipos inválidos.
        name = original.strip()
        if not name or block_name_key(name) in seen:
            number = 1
            if not name or block_name_key(name) == block_name_key(tr("Bloco")) or re.fullmatch(numbered, name, re.IGNORECASE):
                candidate = tr("Bloco {numero}").format(numero=number)
                while block_name_key(candidate) in reserved:
                    number += 1
                    candidate = tr("Bloco {numero}").format(numero=number)
            else:
                base = name + tr(" — cópia")
                candidate = base
                while block_name_key(candidate) in reserved:
                    number += 1
                    candidate = f"{base} {number}"
            name = candidate
            reserved.add(block_name_key(name))
        group["name"] = name
        seen.add(block_name_key(name))
    board["block_names_version"] = 1


def blank_organogram():
    return {
        "page_id": "organogram", "field_ids": [], "boxes": [], "images": [],
        "shapes": [], "signatures": [], "layer_order": [], "guidelines": [],
        "background_path": None, "editable_background_initialized": True,
        "groups": [], "connections": [], "grid_mm": 5.0, "margin_mm": 10.0,
        "connector_style": connector_style(),
        "block_names_version": 1,
    }


def add_organogram(document):
    from core.model_document import normalize_model_document, persistent_model_document
    result = persistent_model_document(document)
    if len(result["pages"]) != 1 or result.get("organogram") is not None:
        raise ModelValidationError("Escolha uma segunda página ou um organograma.")
    result["schema_version"] = 5
    result["organogram"] = blank_organogram()
    return normalize_model_document(result)


def new_group(document, *, columns=4, rows=10, card_width_mm=50, gap_mm=5,
              start_row=0, x=0, y=0, filter_field="", filter_value=""):
    canvas = document["canvas_size"]
    names = {block_name_key(group.get("name")) for group in (document.get("organogram") or {}).get("groups", [])}
    number = 1
    while block_name_key(tr("Bloco {numero}").format(numero=number)) in names:
        number += 1
    return {
        "id": f"block-{uuid4().hex}", "name": tr("Bloco {numero}").format(numero=number), "columns": columns,
        "rows": rows, "card_w": card_width_mm * UNITS_PER_MM,
        "card_h": card_width_mm * UNITS_PER_MM * canvas["h"] / canvas["w"],
        "gap_x": gap_mm * UNITS_PER_MM, "gap_y": gap_mm * UNITS_PER_MM,
        "start_row": start_row, "x": x, "y": y,
        "filter_field": filter_field, "filter_value": filter_value,
        "entry_sides": ["bottom"], "exit_sides": ["top"],
    }


def group_rect(group):
    cols, rows = group["columns"], group["rows"]
    return QRectF(group["x"], group["y"],
                  cols * group["card_w"] + (cols - 1) * group["gap_x"],
                  rows * group["card_h"] + (rows - 1) * group["gap_y"])


def slot_rect(group, index):
    return QRectF(group["x"] + index % group["columns"] * (group["card_w"] + group["gap_x"]),
                  group["y"] + index // group["columns"] * (group["card_h"] + group["gap_y"]),
                  group["card_w"], group["card_h"])


def validate_organogram(board):
    validate_connector_style(board.get("connector_style", {}))
    for collection in ("boxes", "images", "shapes"):
        for entry in board.get(collection, []):
            if type(entry.get("board_behind", False)) is not bool:
                raise ModelValidationError("Posição do elemento no organograma inválida.")
    if board.get("signatures") or board.get("background_path"):
        raise ModelValidationError("O organograma não possui assinatura ou fundo de documento.")
    for key, minimum in (("grid_mm", 0.1), ("margin_mm", 0)):
        value = board.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not minimum <= value <= 1000):
            raise ModelValidationError(f"Valor inválido de {key} no organograma.")
    groups, connections = board.get("groups"), board.get("connections")
    if not isinstance(groups, list) or not isinstance(connections, list):
        raise ModelValidationError("Blocos e conexões devem ser listas.")
    ids = set()
    names = set()
    count = 0
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("id"), str) or not group["id"]:
            raise ModelValidationError("Bloco sem identidade.")
        if group["id"] in ids:
            raise ModelValidationError("Identidade de bloco repetida.")
        ids.add(group["id"])
        validate_border_style(group.get("border", {}))
        for key, default in (("entry_sides", ["bottom"]), ("exit_sides", ["top"])):
            sides = group.get(key, default)
            if (not isinstance(sides, list) or not sides or not all(isinstance(side, str) for side in sides)
                    or len(set(sides)) != len(sides) or not set(sides) <= {"top", "right", "bottom", "left"}):
                raise ModelValidationError("Escolha pelo menos um lado válido para entrada e saída dos conectores.")
        for key in ("columns", "rows"):
            if type(group.get(key)) is not int or not 1 <= group[key] <= 100:
                raise ModelValidationError("Linhas e colunas devem estar entre 1 e 100.")
        count += group["columns"] * group["rows"]
        if type(group.get("start_row")) is not int or not 0 <= group["start_row"] <= 1_000_000:
            raise ModelValidationError("Linha inicial inválida.")
        for key in ("name", "filter_field", "filter_value"):
            if not isinstance(group.get(key, ""), str):
                raise ModelValidationError("Nome ou filtro de bloco inválido.")
        name = group.get("name", "")
        if not name.strip():
            raise ModelValidationError(tr("Informe um nome para o bloco."))
        if block_name_key(name) in names:
            raise ModelValidationError(tr("O nome ‘{nome}’ já está em uso. Escolha outro nome.").format(nome=name.strip()))
        names.add(block_name_key(name))
        for key in ("x", "y", "card_w", "card_h", "gap_x", "gap_y"):
            value = group.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or abs(value) > MAX_OBJECT_COORDINATE):
                raise ModelValidationError("Geometria de bloco inválida.")
        if min(group["card_w"], group["card_h"]) <= 0 or min(group["gap_x"], group["gap_y"]) < 0:
            raise ModelValidationError("Tamanho ou espaçamento de cartão inválido.")
        bounds = bordered_group_bounds(group)
        if max(abs(bounds.left()), abs(bounds.right()), abs(bounds.top()), abs(bounds.bottom())) > MAX_OBJECT_COORDINATE:
            raise ModelValidationError("O bloco excede a área segura de edição.")
    if count > MAX_SLOTS:
        raise ModelValidationError(f"O protótipo aceita até {MAX_SLOTS} posições por quadro.")
    parents = {}
    for edge in connections:
        if (not isinstance(edge, dict) or not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str)
                or edge["source"] not in ids or edge["target"] not in ids):
            raise ModelValidationError("Conexão aponta para um bloco inexistente.")
        source, target = edge["source"], edge["target"]
        validate_connector_style(edge.get("style", {}))
        if source == target or target in parents:
            raise ModelValidationError("Cada bloco pode possuir apenas um superior.")
        parents[target] = source
    for node in parents:
        visited = set()
        while node in parents:
            if node in visited:
                raise ModelValidationError("A hierarquia não pode conter ciclos.")
            visited.add(node)
            node = parents[node]


def card_fields(document):
    from core.text_layout import variables_in_html
    page = document["pages"][0]
    fields = set()
    images = set()
    for box in page.get("boxes", []):
        if box.get("visible", True):
            fields.update(variables_in_html(box.get("html", "")))
    for shape in page.get("shapes", []):
        if shape.get("visible", True) and shape.get("dynamic_image_field"):
            images.add(shape["dynamic_image_field"])
    fields.discard("modelo")  # Valor automático do workspace não ocupa uma posição.
    fields.difference_update((BLOCK_DESTINATION_KEY, DISABLED_ROW_KEY))
    images.difference_update((BLOCK_DESTINATION_KEY, DISABLED_ROW_KEY))
    return fields, images


def row_is_valid(document, row, dynamic_directory=None, *, fields=None):
    from core.dynamic_images import resolve_dynamic_image
    from PySide6.QtGui import QImageReader
    if row.get(DISABLED_ROW_KEY):
        return False
    text_fields, image_fields = fields if fields is not None else card_fields(document)
    for field in text_fields:
        value = row.get(field, "")
        if value is not None and str(value).strip():
            return True
    for field in image_fields:
        result = resolve_dynamic_image(dynamic_directory, row.get(field, ""))
        if result.path is not None and QImageReader(str(result.path)).canRead():
            return True
    return False


def assigned_slots(document, rows_plain, rows_rich=None, dynamic_directory=None):
    """Usa o mesmo plano de distribuição na prévia e na exportação."""
    slots, _issues = assignment_plan(document, rows_plain, rows_rich, dynamic_directory)
    yield from slots


def assignment_plan(document, rows_plain, rows_rich=None, dynamic_directory=None):
    """Distribui por nome; chamadas antigas sem metadados conservam intervalos/filtros.

    Uma linha destinada ao bloco reserva sua posição mesmo se estiver vazia ou
    desativada. Pendências só são relatadas para linhas com conteúdo variável válido.
    """
    fields = card_fields(document)
    rich = rows_rich if rows_rich is not None else rows_plain
    slots, issues = [], []
    valid = [row_is_valid(document, row, dynamic_directory, fields=fields) for row in rows_plain]
    groups = document["organogram"]["groups"]
    if any(BLOCK_DESTINATION_KEY in row for row in rows_plain):
        destinations = {block_name_key(group["name"]): group for group in groups}
        positions = {group["id"]: 0 for group in groups}
        for row_index, plain in enumerate(rows_plain):
            name = str(plain.get(BLOCK_DESTINATION_KEY) or "").strip()
            group = destinations.get(block_name_key(name))
            reason = "missing" if not name else "unknown" if group is None else None
            if group is not None:
                index = positions[group["id"]]
                positions[group["id"]] += 1
                if index >= group["rows"] * group["columns"]:
                    reason = "overflow"
                elif valid[row_index]:
                    slots.append((group["id"], index, slot_rect(group, index), plain, rich[row_index]))
            if reason and valid[row_index]:
                issues.append({"row": row_index, "reason": reason, "name": name})
        return slots, issues
    represented = set()
    for group in document["organogram"]["groups"]:
        candidates = list(range(len(rows_plain)))
        if group.get("filter_field"):
            candidates = [index for index in candidates
                          if str(rows_plain[index].get(group["filter_field"], "")).strip() == group.get("filter_value", "").strip()]
        candidates = candidates[group["start_row"]:group["start_row"] + group["rows"] * group["columns"]]
        for index, row_index in enumerate(candidates):
            plain = rows_plain[row_index]
            if valid[row_index]:
                slots.append((group["id"], index, slot_rect(group, index), plain, rich[row_index]))
                represented.add(row_index)
    issues = [{"row": index, "reason": "unassigned", "name": ""}
              for index, is_valid in enumerate(valid) if is_valid and index not in represented]
    return slots, issues


def assignment_issue_text(issues):
    descriptions = {
        "missing": tr("preencha a coluna Bloco"),
        "unknown": tr("bloco ‘{nome}’ não encontrado"),
        "overflow": tr("o bloco ‘{nome}’ não tem mais posições disponíveis"),
        "unassigned": tr("registro fora dos intervalos ou filtros dos blocos"),
    }
    lines = [tr("Linha {linha}: {motivo}.").format(
        linha=issue["row"] + 1, motivo=descriptions[issue["reason"]].format(nome=issue["name"]))
        for issue in issues[:20]]
    if len(issues) > 20:
        lines.append(tr("Mais {quantidade} pendência(s).").format(quantidade=len(issues) - 20))
    return "\n".join(lines)


def artwork_bounds(board):
    bounds = QRectF()
    for collection in ("boxes", "images", "shapes"):
        for item in board.get(collection, []):
            if not item.get("visible", True):
                continue
            w, h = item.get("w", item.get("width", 1)), item.get("h", item.get("height", 1))
            transform = QTransform()
            transform.translate(item.get("x", 0) + w / 2, item.get("y", 0) + h / 2)
            transform.rotate(item.get("rotation", 0))
            rect = transform.mapRect(QRectF(-w / 2, -h / 2, w, h))
            # Inclui folga de borda das formas na sugestão de impressão.
            padding = float(item.get("outline_width", 0))
            bounds = bounds.united(rect.adjusted(-padding, -padding, padding, padding))
    return bounds


def board_bounds(board, *, visible_slots=None, paths=None):
    bounds = artwork_bounds(board)
    if visible_slots is None:
        for group in board["groups"]:
            bounds = bounds.united(bordered_group_bounds(group))
    else:
        groups_by_id = {group["id"]: group for group in board["groups"]}
        for slot in visible_slots:
            bounds = bounds.united(bordered_card_bounds(groups_by_id[slot[0]], slot[2]))
        # Conexões seguem os limites dos conjuntos, mesmo parcialmente ocupados.
        visible = {slot[0] for slot in visible_slots}
        linked = {edge[key] for edge in board["connections"]
                  if edge["source"] in visible and edge["target"] in visible
                  for key in ("source", "target")}
        for group in board["groups"]:
            if group["id"] in linked or (group["id"] in visible and border_style(group)["group"]
                                           and border_style(group)["opacity"] > 0):
                bounds = bounds.united(bordered_group_bounds(group))
    groups = {group["id"]: group for group in board["groups"]}
    visible = set(groups) if visible_slots is None else {slot[0] for slot in visible_slots}
    if paths is None:
        paths = connector_paths(board)
    for edge in board["connections"]:
        if edge["source"] in visible and edge["target"] in visible:
            style = connector_style(edge, board)
            padding = style["width_mm"] * UNITS_PER_MM / 2
            rect = paths[(edge["source"], edge["target"])].boundingRect()
            bounds = bounds.united(rect.adjusted(-padding, -padding, padding, padding))
    if bounds.isEmpty():
        bounds = QRectF(0, 0, UNITS_PER_MM, UNITS_PER_MM)
    margin = board["margin_mm"] * UNITS_PER_MM
    return bounds.adjusted(-margin, -margin, margin, margin)


def connection_points(source, target):
    from core.board_routing import board_routes
    board = {"groups": [source, target], "connections": [{"source": source["id"], "target": target["id"]}]}
    return board_routes(board)[(source["id"], target["id"])][0]


def scene_page(document):
    board = document["organogram"]
    bounds = board_bounds(board)
    return {
        **{key: deepcopy(value) for key, value in document.items()
           if key not in ("pages", "organogram", "schema_version")},
        **deepcopy(board), "canvas_size": {"w": max(1, math.ceil(bounds.width())), "h": max(1, math.ceil(bounds.height()))},
        "target_w_mm": bounds.width() / UNITS_PER_MM, "target_h_mm": bounds.height() / UNITS_PER_MM,
        "__page_id": "organogram", "__page_field_ids": board["field_ids"],
        "__board_groups": deepcopy(board["groups"]), "__board_connections": deepcopy(board["connections"]),
        "__board_grid_mm": board["grid_mm"], "__board_margin_mm": board["margin_mm"],
        "__board_connector_style": connector_style(board=board),
    }
