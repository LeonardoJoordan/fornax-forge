"""Entradas síncronas da captura do histórico, sem copiar o documento inteiro.

A comparação não usa hashes nem sinais de pintura/seleção como prova de que o
conteúdo permaneceu igual. Tipos ou atributos não cobertos exigem a captura
completa. Novas propriedades persistentes nativas também precisam ser incluídas
nesta leitura. Ela não decide sobre conteúdo ou autorização de assets externos.
"""
import math

from PySide6.QtWidgets import QGraphicsItem

from .canvas_items import (
    DesignerBox, ImageItem, RectangleItem, SignatureItem, BackgroundItem,
    Guideline, ResizeHandle, BleedTextItem, MaskOutlineOverlay,
    SelectionResizeHandle, SelectionTransformFrame,
)
from .organogram_editor import BoardGroupItem, BoardConnectorItem
from .table_item import TableItem


class UnsupportedInput(ValueError):
    pass


def _freeze(value, depth=0):
    """Conserva tipos e valores; não retém objetos Qt nem dicionários mutáveis."""
    if depth > 12:
        raise UnsupportedInput("Estrutura não coberta")
    if value is None or type(value) in (str, bool, int):
        return (type(value).__name__, value)
    if type(value) is float and math.isfinite(value):
        return ("float", value)
    if type(value) in (list, tuple):
        return (type(value).__name__, tuple(_freeze(v, depth + 1) for v in value))
    if type(value) is dict and all(type(k) is str for k in value):
        return ("dict", tuple((k, _freeze(v, depth + 1)) for k, v in sorted(value.items())))
    raise UnsupportedInput("Valor não coberto")


# Referências nativas, relações de UI e caches de desenho não são estado salvo.
# Geometria, parentagem e conteúdo de texto nativos são lidos separadamente.
_NATIVE_FIELDS = {
    "text_item", "resize_handles", "handle_br", "_proxy_pixmap", "_mask_overlay",
    "window", "preview", "_shape_cache", "_clip_cache", "_board_cutout_owner",
}
_TRANSIENT_FIELDS = {
    "_is_mouse_dragging", "_resizing_from_handle", "_mask_editing",
    "_text_layout_depth", "_text_layout_pending", "_syncing_document",
}
_IGNORED_TYPES = (
    ResizeHandle, BleedTextItem, MaskOutlineOverlay,
    SelectionResizeHandle, SelectionTransformFrame,
)
_CONTENT_TYPES = (
    DesignerBox, ImageItem, RectangleItem, SignatureItem, BackgroundItem,
    Guideline, BoardGroupItem, BoardConnectorItem, TableItem,
)


def history_inputs(window):
    """Retorna None quando a equivalência não pode ser comprovada com segurança."""
    try:
        values = []
        items = window.scene.items()
        # Lê a relação usada por máscaras a partir do pai. Em PySide 6.11,
        # consultar parentItem() de um item sem pai pode transferir sua
        # propriedade para Python, mesmo quando a cena ainda o possui.
        # Guias sem outras referências acabavam removidas ao sair da função.
        mask_parents = {
            id(child): id(parent)
            for parent in items if type(parent) is RectangleItem
            for child in parent.childItems()
        }
        for item in items:
            kind = type(item)
            if kind in _IGNORED_TYPES or item is window.fallback_bg:
                continue
            # Subclasses desconhecidas também usam a captura original.
            if kind not in _CONTENT_TYPES:
                return None
            attrs = []
            if kind is TableItem:
                session = getattr(window, 'table_edit', None)
                if session and session.item is item:
                    return None  # Rascunho aceito/native cursor exige captura completa.
                known = {'data', 'window', 'layout', 'presentation_revision', 'selected_range',
                         'selection_anchor', 'selection_cursor', 'editing_cell', '_selecting_cells',
                         '_is_mouse_dragging', 'overlays_enabled', 'custom_name', 'layer_id', 'group_id',
                         'board_behind', 'keep_proportion', '_drag_start', '_resizing_from_handle',
                         '_board_cutout_owner', 'resize_handles', 'handle_br',
                         '_pending_cell', '_overlays_enabled'}
                if set(vars(item)) - known:
                    return None
                # Toda a fonte persistente, não a revisão nem o cache Qt. Assim,
                # alterações Python sem sinal também invalidam a comparação.
                for name in ('data','custom_name','layer_id','group_id','board_behind','keep_proportion'):
                    attrs.append((name, _freeze(getattr(item,name))))
            for name, value in (() if kind is TableItem else vars(item).items()):
                if name in _NATIVE_FIELDS or name in _TRANSIENT_FIELDS:
                    continue
                if name == "state" and kind is DesignerBox:
                    value = vars(value)
                attrs.append((name, _freeze(value)))
            point = item.pos()
            native = (
                point.x(), point.y(), item.rotation(), item.zValue(), item.opacity(),
                item.isVisible(),
                bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                mask_parents.get(id(item)),
            )
            rect = item.rect() if kind not in (Guideline, BoardConnectorItem) else None
            detail = (rect.width(), rect.height()) if rect is not None else None
            text = (
                item.text_item.toPlainText(), item.text_item.document().revision()
            ) if kind is DesignerBox else None
            values.append((id(item), kind.__name__, native, detail, text, tuple(sorted(attrs))))
        rect = window._get_document_rect()
        global_values = (
            window._active_page_id, window._current_model_name,
            rect.x(), rect.y(), rect.width(), rect.height(),
            window.spin_phys_w.value(), window.spin_phys_h.value(), window.background_path,
            tuple(window.lst_placeholders.item(i).text()
                  for i in range(window.lst_placeholders.count())),
            window.btn_lock_guides.isChecked(), window.btn_toggle_guides.isChecked(),
            window.chk_doc_proporcao.isChecked(), window._doc_aspect_ratio,
            getattr(window, "_board_margin_mm", None), getattr(window, "_board_grid_mm", None),
            _freeze(getattr(window, "_board_connector_style", None)),
        )
        # Conserva a ordem nativa: stackBefore pode mudar a ordem de camadas
        # sem modificar posição, zValue ou qualquer atributo Python.
        return (global_values, tuple(values))
    except (UnsupportedInput, RuntimeError, AttributeError, TypeError):
        return None
