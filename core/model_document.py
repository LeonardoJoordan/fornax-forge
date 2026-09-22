"""Contrato e persistência de modelos de uma ou duas páginas."""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from core.html_utils import text_html_has_unsupported_resources


SCHEMA_VERSION = 4
LEGACY_SCHEMA_VERSION = 3
V4_FILENAME = "template_v4.json"
V4_BACKUP_FILENAME = "template_v4.json.bak"
V3_FILENAME = "template_v3.json"
PAGE_IDS = ("front", "back")

# O Qt armazena imagens ARGB em aproximadamente quatro bytes por pixel. O
# canvas usa um teto menor que assets isolados porque geração paralela mantém
# bases e imagens de saída simultaneamente.
MAX_CANVAS_DIMENSION = 16_384
MAX_CANVAS_PIXELS = 32_000_000
MAX_PHYSICAL_DIMENSION_MM = 5_000.0
MAX_OBJECT_COORDINATE = MAX_CANVAS_DIMENSION * 16

PAGE_COLLECTIONS = ("boxes", "images", "signatures", "shapes")
PAGE_KEYS = {
    *PAGE_COLLECTIONS,
    "background_path",
    "bg_props",
    "layer_order",
    "guidelines",
    "editable_background_initialized",
}
DOCUMENT_ONLY_KEYS = {"schema_version", "__source_schema_version", "pages"}


def new_signature_id() -> str:
    """Cria a identidade persistente de uma assinatura nova."""
    return f"sig-{uuid4().hex}"


def _ensure_signature_ids(document: dict) -> None:
    """Adapta modelos anteriores sem vincular a identidade ao nome da camada."""
    reserved = {
        signature_id
        for page in document.get("pages", [])
        for signature in page.get("signatures", [])
        if isinstance((signature_id := signature.get("signature_id")), str)
        and signature_id.strip()
    }
    generated = set()
    for page in document.get("pages", []):
        page_id = page.get("page_id", "page")
        for index, signature in enumerate(page.get("signatures", [])):
            current = signature.get("signature_id")
            if isinstance(current, str) and current.strip():
                continue
            object_id = signature.get("object_id") or f"signature-{index}"
            seed = f"fornax-forge:{page_id}:{object_id}"
            candidate = f"sig-{uuid5(NAMESPACE_URL, seed).hex}"
            suffix = 2
            while candidate in reserved or candidate in generated:
                candidate = f"sig-{uuid5(NAMESPACE_URL, f'{seed}:{suffix}').hex}"
                suffix += 1
            signature["signature_id"] = candidate
            generated.add(candidate)


class ModelDocumentError(ValueError):
    """Base para erros que impedem a abertura segura de um modelo."""


class UnsupportedSchemaError(ModelDocumentError):
    """A versão do modelo não é reconhecida por esta versão do programa."""


class ModelValidationError(ModelDocumentError):
    """O arquivo possui versão conhecida, mas estrutura inválida."""


def _positive_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def validate_raster_dimensions(width: Any, height: Any, *, label: str = "imagem") -> tuple[int, int]:
    """Valida dimensões antes de entregá-las a um buffer raster do Qt."""
    if not _positive_number(width) or not _positive_number(height):
        raise ModelValidationError(f"As dimensões de {label} devem ser positivas.")
    numeric_width = float(width)
    numeric_height = float(height)
    if not numeric_width.is_integer() or not numeric_height.is_integer():
        raise ModelValidationError(f"As dimensões de {label} devem ser números inteiros de pixels.")
    pixel_width, pixel_height = int(numeric_width), int(numeric_height)
    if (
        pixel_width > MAX_CANVAS_DIMENSION
        or pixel_height > MAX_CANVAS_DIMENSION
        or pixel_width * pixel_height > MAX_CANVAS_PIXELS
    ):
        raise ModelValidationError(f"As dimensões de {label} excedem o limite seguro do programa.")
    return pixel_width, pixel_height


def _validate_dimensions(document: dict) -> None:
    canvas = document.get("canvas_size")
    if not isinstance(canvas, dict) or not _positive_number(canvas.get("w")) or not _positive_number(canvas.get("h")):
        raise ModelValidationError("canvas_size deve conter largura e altura positivas.")

    validate_raster_dimensions(canvas["w"], canvas["h"], label="canvas")

    width = document.get("target_w_mm")
    height = document.get("target_h_mm")
    if (width is None) != (height is None):
        raise ModelValidationError("As dimensões físicas devem possuir largura e altura juntas.")
    if width is not None and (not _positive_number(width) or not _positive_number(height)):
        raise ModelValidationError("As dimensões físicas devem ser positivas.")
    if width is not None and (
        float(width) > MAX_PHYSICAL_DIMENSION_MM
        or float(height) > MAX_PHYSICAL_DIMENSION_MM
    ):
        raise ModelValidationError("As dimensões físicas excedem o limite seguro do programa.")


def _validate_object_geometry(item: dict, *, page_id: str) -> None:
    for key in ("x", "y", "z_value", "rotation"):
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ModelValidationError(f"Geometria inválida em objeto da página {page_id}.")
        if abs(float(value)) > MAX_OBJECT_COORDINATE:
            raise ModelValidationError(f"Geometria de objeto excede o limite na página {page_id}.")
    for key in ("w", "h", "width", "height"):
        if key not in item:
            continue
        value = item[key]
        if not _positive_number(value) or float(value) > MAX_OBJECT_COORDINATE:
            raise ModelValidationError(f"Dimensão de objeto inválida na página {page_id}.")


def _ensure_legacy_object_ids(page: dict) -> None:
    """Cria identidade determinística sem alterar geometria ou ordem de pintura."""
    used = set()
    for kind, collection in (("text", "boxes"), ("image", "images"),
                             ("signature", "signatures"), ("shape", "shapes")):
        for index, item in enumerate(page.get(collection, [])):
            candidate = item.get("object_id")
            if not isinstance(candidate, str) or not candidate.strip() or candidate in used:
                layer_id = item.get("layer_id")
                base = f"{kind}:{layer_id}" if layer_id is not None else f"legacy-{kind}-{index}"
                candidate = base
                suffix = 2
                while candidate in used:
                    candidate = f"{base}-{suffix}"
                    suffix += 1
                item["object_id"] = candidate
            used.add(candidate)


def _ordered_unique(values):
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def _required_page_fields(page: dict) -> list[str]:
    """Campos funcionais também pertencem à tabela, inclusive no verso."""
    return _ordered_unique(
        [
            *(
                item.get("link_key")
                for collection in ("boxes", "images", "shapes")
                for item in page.get(collection, [])
                if (
                    item.get("has_link")
                    and item.get("link_key")
                    and not (collection == "images" and item.get("mask_shape_id"))
                )
            ),
            *(
                shape.get("dynamic_image_field")
                for shape in page.get("shapes", [])
                if shape.get("dynamic_image_field")
            ),
        ]
    )


def _reconcile_document_fields(document: dict, preferred_order=()) -> None:
    """Reconstrói a união global sem perder a ordem escolhida pelo usuário."""
    required = _ordered_unique(
        field_id
        for page in document.get("pages", [])
        for field_id in [*page.get("field_ids", []), *_required_page_fields(page)]
    )
    required_set = set(required)
    document["placeholders"] = _ordered_unique([
        *(value for value in preferred_order if value in required_set),
        *(value for value in document.get("placeholders", []) if value in required_set),
        *required,
    ])


def document_signatures(document: dict):
    """Retorna cópias das assinaturas de todas as páginas, em ordem de página."""
    normalized = normalize_model_document(document)
    return [
        deepcopy(signature)
        for page in normalized["pages"]
        for signature in page.get("signatures", [])
    ]


def _legacy_page(source: dict) -> dict:
    page = {"page_id": "front", "field_ids": deepcopy(source.get("placeholders", []))}
    for key in PAGE_KEYS:
        if key in source:
            page[key] = deepcopy(source[key])
    for collection in PAGE_COLLECTIONS:
        page.setdefault(collection, [])
    page.setdefault("background_path", None)
    page.setdefault("guidelines", [])
    _ensure_legacy_object_ids(page)
    return page


def _normalize_legacy(source: dict) -> dict:
    document = {
        key: deepcopy(value)
        for key, value in source.items()
        if key not in PAGE_KEYS and key not in DOCUMENT_ONLY_KEYS
    }
    document["schema_version"] = SCHEMA_VERSION
    document["__source_schema_version"] = LEGACY_SCHEMA_VERSION
    document.setdefault("placeholders", deepcopy(source.get("placeholders", [])))
    document.setdefault("guidelines_visible", source.get("guidelines_visible", True))
    document.setdefault("guidelines_locked", source.get("guidelines_locked", False))
    document["pages"] = [_legacy_page(source)]
    return document


def _validate_page(page: Any, expected_id: str, *, legacy_source: bool) -> None:
    if not isinstance(page, dict):
        raise ModelValidationError("Cada página deve ser um objeto.")
    if page.get("page_id") != expected_id:
        raise ModelValidationError(f"A página {expected_id} está ausente ou fora de ordem.")
    shared_keys = {"canvas_size", "target_w_mm", "target_h_mm", "guidelines_visible", "guidelines_locked"}
    if shared_keys.intersection(page):
        raise ModelValidationError("Dimensões e estado global das guias pertencem ao documento, não às páginas.")
    if not isinstance(page.get("field_ids", []), list) or not all(isinstance(value, str) for value in page.get("field_ids", [])):
        raise ModelValidationError(f"field_ids inválido na página {expected_id}.")
    if len(page.get("field_ids", [])) != len(set(page.get("field_ids", []))):
        raise ModelValidationError(f"field_ids contém identificadores repetidos na página {expected_id}.")
    if not isinstance(page.get("guidelines", []), list) or not all(isinstance(value, dict) for value in page.get("guidelines", [])):
        raise ModelValidationError(f"guidelines inválido na página {expected_id}.")
    background_path = page.get("background_path")
    if background_path is not None and not isinstance(background_path, str):
        raise ModelValidationError(f"background_path inválido na página {expected_id}.")

    object_ids = []
    for collection in PAGE_COLLECTIONS:
        items = page.get(collection)
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ModelValidationError(f"{collection} deve ser uma lista na página {expected_id}.")
        for item in items:
            object_id = item.get("object_id")
            if not isinstance(object_id, str) or not object_id.strip():
                raise ModelValidationError(f"Objeto sem identidade na página {expected_id}.")
            object_ids.append(object_id)
            _validate_object_geometry(item, page_id=expected_id)
    if len(object_ids) != len(set(object_ids)):
        raise ModelValidationError(f"Há object_id repetido na página {expected_id}.")

    shapes = {item['object_id']: item for item in page.get('shapes', [])}
    for box in page.get("boxes", []):
        html = box.get("html", "")
        if not isinstance(html, str):
            raise ModelValidationError(f"HTML de texto inválido na página {expected_id}.")
        if text_html_has_unsupported_resources(html):
            raise ModelValidationError(
                f"Caixa de texto contém recurso externo ou gráfico não permitido na página {expected_id}."
            )
    for shape in shapes.values():
        field = shape.get("dynamic_image_field")
        if field is not None and not isinstance(field, str):
            raise ModelValidationError(
                f"Campo de imagem dinâmica inválido na página {expected_id}."
            )
        if isinstance(field, str) and field and not field.strip():
            raise ModelValidationError(
                f"Campo de imagem dinâmica inválido na página {expected_id}."
            )
        if field:
            if shape.get("shape_type") not in ("rectangle", "ellipse", "circle"):
                raise ModelValidationError(
                    f"Imagem dinâmica exige uma forma fechada na página {expected_id}."
                )
            if shape.get("is_document_background"):
                raise ModelValidationError(
                    f"O plano de fundo não pode ser uma imagem dinâmica na página {expected_id}."
                )
            if shape.get("dynamic_image_fit", "cover") not in ("cover", "contain"):
                raise ModelValidationError(
                    f"Enquadramento de imagem dinâmica inválido na página {expected_id}."
                )
    mask_orders = {}
    for image in page.get('images', []):
        mask_id = image.get('mask_shape_id')
        if mask_id is None:
            continue
        shape = shapes.get(mask_id)
        if shape is None or shape.get('shape_type') not in ('rectangle', 'ellipse', 'circle'):
            raise ModelValidationError(
                f"Imagem vinculada a uma máscara inexistente ou incompatível na página {expected_id}."
            )
        if shape.get("dynamic_image_field"):
            raise ModelValidationError(
                f"Uma forma dinâmica não pode conter imagens fixas na página {expected_id}."
            )
        order = image.get('mask_order', 0)
        if not isinstance(order, int) or order < 0:
            raise ModelValidationError(f"Ordem interna de máscara inválida na página {expected_id}.")
        if order in mask_orders.setdefault(mask_id, set()):
            raise ModelValidationError(f"Ordem interna de máscara repetida na página {expected_id}.")
        mask_orders[mask_id].add(order)

    layer_order = page.get("layer_order")
    if layer_order is None and legacy_source:
        return
    if not isinstance(layer_order, list) or not all(isinstance(value, str) for value in layer_order):
        raise ModelValidationError(f"layer_order inválido na página {expected_id}.")
    if len(layer_order) != len(set(layer_order)):
        raise ModelValidationError(f"layer_order contém identidades repetidas na página {expected_id}.")
    if legacy_source:
        # O renderer legado ignora referências antigas e acrescenta objetos
        # ausentes. Manter essa tolerância evita recusar modelos já válidos.
        return
    if set(layer_order) != set(object_ids):
        raise ModelValidationError(f"layer_order não corresponde aos objetos da página {expected_id}.")


def validate_model_document(document: dict) -> None:
    if not isinstance(document, dict):
        raise ModelValidationError("O modelo deve ser um objeto JSON.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise UnsupportedSchemaError(f"Versão de modelo não suportada: {document.get('schema_version')!r}.")
    if "protection_preferences" in document:
        preferences = document["protection_preferences"]
        if not isinstance(preferences, dict):
            raise ModelValidationError("protection_preferences deve ser um objeto.")
        if set(preferences) != {"public_signatures_acknowledged"}:
            raise ModelValidationError("protection_preferences possui campos inválidos.")
        if not isinstance(preferences["public_signatures_acknowledged"], bool):
            raise ModelValidationError(
                "public_signatures_acknowledged deve ser um valor booleano."
            )
    _validate_dimensions(document)
    placeholders = document.get("placeholders", [])
    if not isinstance(placeholders, list) or not all(isinstance(value, str) for value in placeholders):
        raise ModelValidationError("placeholders deve ser uma lista de identificadores.")
    if len(placeholders) != len(set(placeholders)):
        raise ModelValidationError("placeholders contém identificadores repetidos.")

    pages = document.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 2:
        raise ModelValidationError("O modelo deve possuir uma ou duas páginas.")
    legacy_source = document.get("__source_schema_version") == LEGACY_SCHEMA_VERSION
    signature_ids = []
    for index, page in enumerate(pages):
        _validate_page(page, PAGE_IDS[index], legacy_source=legacy_source)
        for signature in page.get("signatures", []):
            signature_id = signature.get("signature_id")
            if not isinstance(signature_id, str) or not signature_id.strip():
                raise ModelValidationError(
                    f"Assinatura sem identidade persistente na página {PAGE_IDS[index]}."
                )
            signature_ids.append(signature_id)
    if len(signature_ids) != len(set(signature_ids)):
        raise ModelValidationError("Há signature_id repetido no documento.")


def normalize_model_document(source: dict) -> dict:
    """Retorna uma cópia v4 validada, sem modificar ou gravar a origem."""
    if not isinstance(source, dict):
        raise ModelValidationError("O modelo deve ser um objeto JSON.")
    version = source.get("schema_version", LEGACY_SCHEMA_VERSION)
    if version == LEGACY_SCHEMA_VERSION:
        document = _normalize_legacy(source)
    elif version == SCHEMA_VERSION:
        document = deepcopy(source)
    else:
        raise UnsupportedSchemaError(f"Versão de modelo não suportada: {version!r}.")
    _ensure_signature_ids(document)
    validate_model_document(document)
    _reconcile_document_fields(document, document.get("placeholders", []))
    validate_model_document(document)
    return document


def page_ids(document: dict) -> tuple[str, ...]:
    normalized = normalize_model_document(document)
    return tuple(page["page_id"] for page in normalized["pages"])


def adapt_model_page(document: dict, page_id: str = "front") -> dict:
    """Cria uma visão plana da página para cena e renderer, sem compartilhar mutações."""
    normalized = normalize_model_document(document)
    page = next((value for value in normalized["pages"] if value["page_id"] == page_id), None)
    if page is None:
        raise ModelValidationError(f"Página inexistente: {page_id!r}.")

    adapted = {
        key: deepcopy(value)
        for key, value in normalized.items()
        if key not in DOCUMENT_ONLY_KEYS
    }
    for key, value in page.items():
        if key not in {"page_id", "field_ids"}:
            adapted[key] = deepcopy(value)
    adapted["__page_id"] = page_id
    adapted["__page_field_ids"] = deepcopy(page.get("field_ids", []))
    adapted["__document_schema_version"] = SCHEMA_VERSION
    return adapted


def replace_model_page(document: dict, page_data: dict, page_id: str = "front") -> dict:
    """Retorna documento novo com uma página substituída e metadados comuns atualizados."""
    normalized = normalize_model_document(document)
    page_index = next((index for index, value in enumerate(normalized["pages"])
                       if value["page_id"] == page_id), None)
    if page_index is None:
        raise ModelValidationError(f"Página inexistente: {page_id!r}.")

    page_fields = (
        page_data.get("__page_field_ids", [])
        if page_data.get("__page_fields_authoritative")
        else page_data.get("placeholders", [])
    )
    replacement = {
        "page_id": page_id,
        "field_ids": deepcopy(page_fields),
    }
    for key in PAGE_KEYS:
        if key in page_data:
            replacement[key] = deepcopy(page_data[key])
    for collection in PAGE_COLLECTIONS:
        replacement.setdefault(collection, [])
    replacement.setdefault("background_path", None)
    replacement.setdefault("guidelines", [])

    # O estado atual do editor é a autoridade para propriedades compartilhadas.
    for key, value in page_data.items():
        if key not in PAGE_KEYS and key not in DOCUMENT_ONLY_KEYS and not key.startswith("__"):
            normalized[key] = deepcopy(value)
    normalized["pages"][page_index] = replacement
    _reconcile_document_fields(normalized, page_data.get("placeholders", []))
    normalized.pop("__source_schema_version", None)
    validate_model_document(normalized)
    return normalized


def _blank_page(document: dict, page_id: str) -> dict:
    canvas = document["canvas_size"]
    background = {
        "object_id": "shape:0", "layer_id": 0,
        "custom_name": "Plano de fundo", "shape_type": "rectangle",
        "x": 0.0, "y": 0.0,
        "width": float(canvas["w"]), "height": float(canvas["h"]),
        "rotation": 0.0, "z_value": -100.0,
        "visible": True, "opacity": 1.0, "locked": True,
        "keep_proportion": False, "is_document_background": True,
        "fill_color": "#ffffff", "fill_opacity": 1.0,
        "outline_enabled": False, "outline_color": "#000000",
        "outline_opacity": 1.0, "outline_width": 0.0,
        "outline_position": "inside", "outline_join": "miter",
        "corner_radius": 0.0,
        "corner_radii": {
            "top_left": 0.0, "top_right": 0.0,
            "bottom_right": 0.0, "bottom_left": 0.0,
        },
        "corner_radii_linked": True,
    }
    return {
        "page_id": page_id, "field_ids": [],
        "boxes": [], "images": [], "signatures": [], "shapes": [background],
        "background_path": None, "guidelines": [],
        "layer_order": [background["object_id"]],
        "editable_background_initialized": True,
    }


def add_blank_back_page(document: dict) -> dict:
    normalized = normalize_model_document(document)
    if len(normalized["pages"]) != 1:
        raise ModelValidationError("O documento já possui duas páginas.")
    normalized["pages"].append(_blank_page(normalized, "back"))
    normalized.pop("__source_schema_version", None)
    validate_model_document(normalized)
    return normalized


def clear_model_page(document: dict, page_id: str) -> dict:
    normalized = normalize_model_document(document)
    index = next((i for i, page in enumerate(normalized["pages"])
                  if page["page_id"] == page_id), None)
    if index is None:
        raise ModelValidationError(f"Página inexistente: {page_id!r}.")
    normalized["pages"][index] = _blank_page(normalized, page_id)
    _reconcile_document_fields(normalized, normalized.get("placeholders", []))
    normalized.pop("__source_schema_version", None)
    validate_model_document(normalized)
    return normalized


def remove_model_page(document: dict, page_id: str) -> dict:
    normalized = normalize_model_document(document)
    if len(normalized["pages"]) == 1:
        raise ModelValidationError("A única página do documento não pode ser removida.")
    remaining = [deepcopy(page) for page in normalized["pages"] if page["page_id"] != page_id]
    if len(remaining) != 1:
        raise ModelValidationError(f"Página inexistente: {page_id!r}.")
    remaining[0]["page_id"] = "front"
    normalized["pages"] = remaining
    _reconcile_document_fields(normalized, normalized.get("placeholders", []))
    normalized.pop("__source_schema_version", None)
    validate_model_document(normalized)
    return normalized


def persistent_model_document(document: dict) -> dict:
    """Remove somente metadados internos e retorna um documento pronto para JSON."""
    normalized = normalize_model_document(document)
    if normalized.get("__source_schema_version") == LEGACY_SCHEMA_VERSION:
        from core.document_layers import layer_entries, upgrade_layers

        # A tolerância v3 termina ao persistir v4. Materializar a ordem histórica
        # antes de remover o marcador; incluir também o antigo fundo, que o
        # renderer desenhava separadamente antes das demais camadas.
        for index, page in enumerate(normalized["pages"]):
            scene = deepcopy(page)
            scene["canvas_size"] = normalized["canvas_size"]
            if scene.get("layer_order") is None:
                scene.pop("layer_order", None)
            if "layer_order" not in scene and not scene.get("shapes"):
                upgraded = upgrade_layers(scene)
            else:
                # Documentos com ordenação/formas já usam o renderer por
                # camadas, que não pinta o background_path legado separado.
                upgraded = scene
                upgraded["layer_order"] = [key for key, _, _ in layer_entries(scene)]
            upgraded.pop("canvas_size", None)
            normalized["pages"][index] = upgraded

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if not key.startswith("__")}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return deepcopy(value)

    result = clean(normalized)
    result.pop("source_schema_version", None)
    validate_model_document(result)
    return result


def without_signatures(document: dict) -> dict:
    """Retorna uma cópia persistente sem objetos nem estado de assinaturas."""
    result = persistent_model_document(document)
    signature_paths = {
        item.get("path")
        for page in result["pages"]
        for item in page.get("signatures", [])
        if isinstance(item.get("path"), str) and item.get("path")
    }
    retained_paths = {
        reference
        for page in result["pages"]
        for reference in (
            [page.get("background_path")]
            + [item.get("path") for item in page.get("images", [])]
        )
        if isinstance(reference, str) and reference
    }
    for page in result["pages"]:
        signature_ids = {
            item["object_id"] for item in page.get("signatures", [])
        }
        page["signatures"] = []
        page["layer_order"] = [
            object_id for object_id in page.get("layer_order", [])
            if object_id not in signature_ids
        ]
    result.pop("protection_preferences", None)
    exclusive_names = {
        Path(reference).name for reference in signature_paths - retained_paths
    }
    origin = result.get("origin_info")
    if exclusive_names and isinstance(origin, dict) and isinstance(origin.get("assets"), list):
        origin["assets"] = [
            item for item in origin["assets"]
            if not isinstance(item, dict) or item.get("name") not in exclusive_names
        ]
    validate_model_document(result)
    return result


def save_model_document(document: dict, model_dir: str | Path) -> Path:
    """Publica o v4 atomicamente e conserva a última versão válida para recuperação."""
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / V4_FILENAME
    from core.model_info import ensure_origin_info
    payload = persistent_model_document(ensure_origin_info(document))
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    temporary_path = None
    backup_temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{V4_FILENAME}.", suffix=".tmp",
            dir=directory, delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if target.is_file():
            backup = directory / V4_BACKUP_FILENAME
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{V4_BACKUP_FILENAME}.", suffix=".tmp",
                dir=directory, delete=False,
            ) as backup_stream:
                backup_temporary_path = Path(backup_stream.name)
                with target.open("rb") as current_stream:
                    shutil.copyfileobj(current_stream, backup_stream)
                backup_stream.flush()
                os.fsync(backup_stream.fileno())
            backup_temporary_path.replace(backup)
            backup_temporary_path = None
        temporary_path.replace(target)
        temporary_path = None
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Nem todo sistema de arquivos permite fsync em diretórios.
            pass
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if backup_temporary_path is not None:
            try:
                backup_temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return target


def load_recovery_documents(model_dir: str | Path) -> list[dict]:
    """Lê estados auxiliares válidos usados para preservar assets recuperáveis."""
    directory = Path(model_dir)
    documents = []
    for filename in (V4_BACKUP_FILENAME, V3_FILENAME):
        path = directory / filename
        if not path.is_file():
            continue
        try:
            documents.append(normalize_model_document(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, UnicodeError, json.JSONDecodeError, ModelDocumentError):
            continue
    return documents


def install_model_directory(source_dir: str | Path, target_dir: str | Path) -> Path:
    """Instala um modelo completo e restaura o anterior se a troca falhar."""
    source = Path(source_dir)
    target = Path(target_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.import-", dir=target.parent))
    backup = None
    try:
        staging.rmdir()
        shutil.copytree(source, staging)
        document = load_model_document(staging)
        save_model_document(document, staging)

        if target.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=target.parent))
            backup.rmdir()
            target.replace(backup)
        try:
            staging.replace(target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.replace(target)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def iter_page_asset_paths(document: dict):
    """Percorre referências gráficas de todas as páginas, sem resolver caminhos."""
    normalized = normalize_model_document(document)
    for page in normalized["pages"]:
        background = page.get("background_path")
        if background:
            yield page["page_id"], "background", background
        for collection in ("images", "signatures"):
            for item in page.get(collection, []):
                path = item.get("path")
                if path:
                    yield page["page_id"], collection, path


def iter_page_link_items(document: dict):
    """Percorre objetos com links ativos em todas as páginas."""
    normalized = normalize_model_document(document)
    for page in normalized["pages"]:
        for collection in ("boxes", "images", "shapes"):
            for item in page.get(collection, []):
                if (
                    item.get("has_link")
                    and item.get("link_key")
                    and not (collection == "images" and item.get("mask_shape_id"))
                ):
                    yield page["page_id"], collection, item


def resolve_model_file(model_dir: str | Path) -> Path:
    """Escolhe v4 antes de v3. A validade é verificada somente após a escolha."""
    directory = Path(model_dir)
    if directory.is_file():
        return directory
    v4 = directory / V4_FILENAME
    if v4.is_file():
        return v4
    v3 = directory / V3_FILENAME
    if v3.is_file():
        return v3
    raise FileNotFoundError(f"Nenhum {V4_FILENAME} ou {V3_FILENAME} encontrado em {directory}.")


def load_model_document(path: str | Path) -> dict:
    """Lê e normaliza um arquivo ou diretório de modelo, sem fallback silencioso."""
    model_path = resolve_model_file(path)
    try:
        source = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelDocumentError(f"Não foi possível ler {model_path.name}: {exc}") from exc
    document = normalize_model_document(source)
    document["__model_dir"] = str(model_path.parent.resolve())
    document["__model_file"] = str(model_path.resolve())
    return document
