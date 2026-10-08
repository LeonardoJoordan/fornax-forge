"""Catálogo local de pontos de partida; cada escolha cria uma cópia editável."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from html import escape
from pathlib import Path

from core.resources import PROJECT_ROOT
from core.model_document import normalize_model_document, ModelValidationError, iter_page_asset_paths
from core.organogram import add_organogram, new_group, group_rect, UNITS_PER_MM
from core.board_borders import bordered_group_bounds

TEMPLATES_DIR = PROJECT_ROOT / "assets" / "templates"


@dataclass(frozen=True)
class StarterTemplate:
    id: str
    kind: str
    title: str
    description: str
    path: Path
    configurable_grid: bool = False


def starter_catalog(kind, *, directory=None):
    directory = Path(directory or TEMPLATES_DIR).resolve()
    source = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    result, ids = [], set()
    for entry in source["templates"]:
        if entry["kind"] != kind:
            continue
        path = (directory / entry["file"]).resolve()
        if not path.is_relative_to(directory) or entry["id"] in ids:
            raise ModelValidationError("Entrada inválida no catálogo de exemplos.")
        ids.add(entry["id"])
        result.append(StarterTemplate(entry["id"], kind, entry["title"], entry["description"], path,
                                      entry.get("configurable_grid", False)))
    return tuple(result)


def _read_document(path):
    if path.suffix.lower() == ".fornax":
        from core.fornax_container import inspect_fornax, open_public_fornax, PUBLIC_MODE
        descriptor = inspect_fornax(path)
        if descriptor.mode != PUBLIC_MODE:
            raise ModelValidationError("Use um exemplo .fornax salvo sem proteção.")
        opened = open_public_fornax(descriptor)
        return opened.document(), opened.asset
    source = json.loads(path.read_text(encoding="utf-8"))
    document = normalize_model_document(source)
    document["__model_dir"] = str(path.parent)
    assets = {reference: (path.parent / reference).read_bytes()
              for _page, _kind, reference in iter_page_asset_paths(document)}
    return document, assets.__getitem__ if assets else None


def model_from_starter(template):
    document, provider = _read_document(template.path)
    document["name"] = ""
    # Preferências, origem e credenciais pertencem ao modelo que será criado.
    for key in ("origin_info", "protection_preferences", "imposition_settings",
                "last_export_mode", "last_export_format", "last_single_pdf"):
        document.pop(key, None)
    return document, provider


def organogram_from_starter(document, template, *, columns=None, rows=None):
    """Usa apenas a estrutura escolhida e mantém a Página 1 do documento atual."""
    result = add_organogram(document)
    if template is None:
        return result
    if template.path.suffix.lower() == ".fornax":
        source, _provider = _read_document(template.path)
    else:
        source = json.loads(template.path.read_text(encoding="utf-8"))
    if "organogram" in source:
        # Um organograma desenhado no editor pode virar um exemplo. A estrutura
        # reaproveita os grupos/conexões, sem importar o cartão ou seus assets.
        source = normalize_model_document(source)
        board = result["organogram"]
        original = source["organogram"]
        source_canvas, canvas = source["canvas_size"], result["canvas_size"]
        ratio = (canvas["h"] / canvas["w"]) / (source_canvas["h"] / source_canvas["w"])
        board["groups"] = deepcopy(original["groups"])
        board["connections"] = deepcopy(original["connections"])
        board["connector_style"] = deepcopy(original["connector_style"])
        for group in board["groups"]:
            group["y"] *= ratio
            group["gap_y"] *= ratio
            group["card_h"] = group["card_w"] * canvas["h"] / canvas["w"]
        for key in ("grid_mm", "margin_mm"):
            board[key] = original[key]
        return normalize_model_document(result)
    if source.get("preset_version") not in (1, 2):
        raise ModelValidationError("Versão de estrutura de exemplo não reconhecida.")
    board = result["organogram"]
    decorated = source["preset_version"] == 2
    if decorated:
        board["connector_style"] = deepcopy(source["connector_style"])
        board["margin_mm"] = source.get("margin_mm", 10)
    levels, positions, by_name = {}, {}, {}
    for settings in source["groups"]:
        group = new_group(result, columns=columns if template.configurable_grid and columns is not None else settings["columns"],
                          rows=rows if template.configurable_grid and rows is not None else settings["rows"],
                          card_width_mm=source.get("card_width_mm", 50), gap_mm=source.get("gap_mm", 5))
        group["name"] = settings["name"]
        group["order"] = len(board["groups"])
        if decorated:
            group["border"] = deepcopy(settings.get("border", source["border"]))
            for key in ("entry_sides", "exit_sides"):
                if key in settings:
                    group[key] = deepcopy(settings[key])
        level, column = settings["level"], settings["column"]
        if type(level) is not int or not 0 <= level <= 10 or not isinstance(column, (int, float)) or not math.isfinite(column) or abs(column) > 100:
            raise ModelValidationError("Posição de grupo inválida no exemplo.")
        bounds = bordered_group_bounds(group) if decorated else group_rect(group)
        levels[level] = max(levels.get(level, 0), bounds.height())
        positions[group["id"]] = (level, column)
        board["groups"].append(group)
        by_name[group["name"]] = group["id"]
    horizontal_gap = source.get("column_gap_mm", 20) if decorated else 20
    vertical_gap = source.get("level_gap_mm", 20) if decorated else 20
    stride = max(((bordered_group_bounds(group) if decorated else group_rect(group)).width()
                  for group in board["groups"]), default=0) + horizontal_gap * UNITS_PER_MM
    for group in board["groups"]:
        level, column = positions[group["id"]]
        group["x"] = column * stride - group_rect(group).width() / 2
        group["y"] = sum(levels.get(index, 0) + vertical_gap * UNITS_PER_MM for index in range(level))
    board["connections"] = [{"source": by_name[edge["source"]], "target": by_name[edge["target"]]}
                            for edge in source.get("connections", [])]
    if decorated:
        # Usa a mesma ordem de pintura e salvamento dos conectores no editor.
        board["connections"].sort(key=lambda edge: (edge["source"], edge["target"]))
        _add_preset_title(board, source["title"])
    return normalize_model_document(result)


def _add_preset_title(board, title):
    """Título livre acompanha a largura composta, inclusive na grade ajustável."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication
    from core.ui_font import DOCUMENT_FONT_FAMILY

    bounds = QRectF()
    for group in board["groups"]:
        bounds = bounds.united(bordered_group_bounds(group))
    padding = title.get("padding_mm", 0) * UNITS_PER_MM
    bounds = bounds.adjusted(-padding, 0, padding, 0)
    text = title["text"]
    size = title.get("font_size", 90)
    # A escolha de uma grade estreita não pode deixar um título cortado.
    font = QFont(DOCUMENT_FONT_FAMILY, size, QFont.Weight.Bold)
    width = (QFontMetricsF(font).horizontalAdvance(text) if QGuiApplication.instance()
             else len(text) * size * 1.4)
    size = max(1, min(size, int(size * bounds.width() * 0.95 / max(1, width))))
    height = title.get("height_mm", 20) * UNITS_PER_MM
    gap = title.get("gap_mm", 12) * UNITS_PER_MM
    board["boxes"].append({
        "object_id": "text:1", "layer_id": 1,
        "custom_name": "Título do quadro", "id": text,
        "html": f'<p align="center"><b>{escape(text)}</b></p>',
        "font_family": DOCUMENT_FONT_FAMILY, "font_size": size,
        "font_color": "#333333", "align": "center", "vertical_align": "center",
        "line_height": 1.15, "indent_px": 0.0, "rich_text_version": 1,
        "x": round(bounds.left(), 2), "y": round(bounds.top() - gap - height, 2),
        "w": round(bounds.width(), 2), "h": round(height, 2), "rotation": 0.0,
        "visible": True, "locked": False, "opacity": 1.0,
        "keep_proportion": False, "has_link": False, "link_key": "Link - Título do quadro",
        "board_behind": False, "z_value": 0.0,
    })
    board["layer_order"].append("text:1")
