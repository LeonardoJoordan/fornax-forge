"""Operações do documento multipágina usadas pela janela do editor."""

from __future__ import annotations

import copy

from PySide6.QtWidgets import QMessageBox

from core.i18n import tr
from core.model_document import (
    adapt_model_page,
    add_blank_back_page,
    clear_model_page as clear_document_page,
    normalize_model_document,
    remove_model_page as remove_document_page,
    replace_model_page,
)

from .canvas_items import DesignerBox, ImageItem, RectangleItem, SignatureItem
from .model_adapter import prepare_scene_page


class DocumentSessionMixin:
    """Mantém página ativa, seleção por página e histórico do documento."""

    def _selection_keys(self) -> set[tuple[str, int]]:
        keys = set()
        for item in self.scene.selectedItems():
            layer_id = getattr(item, "layer_id", None)
            if layer_id is None:
                continue
            if isinstance(item, DesignerBox):
                kind = "text"
            elif isinstance(item, SignatureItem):
                kind = "signature"
            elif isinstance(item, RectangleItem):
                kind = "shape"
            elif isinstance(item, ImageItem):
                kind = "image"
            else:
                continue
            keys.add((kind, layer_id))
        return keys

    def _restore_page_selection(self):
        wanted = self._page_selection.get(self._active_page_id, set())
        if not wanted:
            return
        for item in self.scene.items():
            layer_id = getattr(item, "layer_id", None)
            kind = (
                "text" if isinstance(item, DesignerBox) else
                "signature" if isinstance(item, SignatureItem) else
                "shape" if isinstance(item, RectangleItem) else
                "image" if isinstance(item, ImageItem) else None
            )
            if (kind, layer_id) in wanted:
                item.setSelected(True)

    def _synchronize_document_backgrounds(self, document: dict) -> dict:
        canvas = document["canvas_size"]
        for page in document["pages"]:
            for shape in page.get("shapes", []):
                if not shape.get("is_document_background"):
                    continue
                shape.update({
                    "x": 0.0, "y": 0.0,
                    "width": float(canvas["w"]), "height": float(canvas["h"]),
                    "rotation": 0.0, "z_value": -100.0,
                    "locked": True, "keep_proportion": False,
                    "outline_position": "inside",
                })
        return document

    def _capture_document_history_state(self) -> dict:
        page_data = self.get_current_scene_state()
        previous_canvas = (
            copy.deepcopy(self._model_document.get("canvas_size"))
            if self._model_document is not None else None
        )
        if self._model_document is None:
            document = normalize_model_document(page_data)
        elif (
            self._active_scene_baseline is None
            or self._normalize_state_for_compare(page_data)
            != self._normalize_state_for_compare(self._active_scene_baseline)
        ):
            document = replace_model_page(self._model_document, page_data, self._active_page_id)
        else:
            document = self._model_document
        current_canvas = document.get("canvas_size")
        dimensions_changed = previous_canvas is not None and (
            float(previous_canvas.get("w", 0)) != float(current_canvas.get("w", 0))
            or float(previous_canvas.get("h", 0)) != float(current_canvas.get("h", 0))
        )
        self._model_document = (
            self._synchronize_document_backgrounds(document)
            if dimensions_changed else document
        )
        self._active_scene_baseline = copy.deepcopy(page_data)
        return {
            "__document_history__": True,
            "__active_page_id": self._active_page_id,
            "__action_page_id": getattr(self, "_pending_history_page_id", self._active_page_id),
            "document": copy.deepcopy(self._model_document),
        }

    def _refresh_page_controls(self):
        refresh = getattr(self, "_update_page_controls", None)
        if refresh:
            refresh()

    def _finish_page_interaction(self):
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        if getattr(self, "canvas_edit", None):
            self.canvas_edit.finish()
        if getattr(self, "shape_drawing", None):
            self.shape_drawing.cancel()

    def switch_model_page(self, page_id: str):
        if page_id == self._active_page_id:
            return
        if not self._model_document or page_id not in {
            page["page_id"] for page in self._model_document["pages"]
        }:
            return
        self._finish_page_interaction()
        self.save_snapshot()
        self._page_selection[self._active_page_id] = self._selection_keys()
        self._active_page_id = page_id
        self._switching_page = True
        try:
            data = prepare_scene_page(adapt_model_page(self._model_document, page_id))
            self.apply_scene_state(data, is_undo_redo=False)
        finally:
            self._switching_page = False
        self._active_scene_baseline = self.get_current_scene_state()
        self._restore_page_selection()
        self.save_snapshot()
        self._refresh_page_controls()

    def add_model_page(self):
        self._finish_page_interaction()
        self.save_snapshot()
        self._page_selection[self._active_page_id] = self._selection_keys()
        self._model_document = add_blank_back_page(self._model_document)
        self._active_page_id = "back"
        self._page_selection["back"] = set()
        self._switching_page = True
        try:
            self.apply_scene_state(
                prepare_scene_page(adapt_model_page(self._model_document, "back")),
                is_undo_redo=False,
            )
        finally:
            self._switching_page = False
        self._active_scene_baseline = self.get_current_scene_state()
        self._pending_history_page_id = "back"
        self.save_snapshot()
        self._refresh_page_controls()

    def clear_model_page(self, page_id: str):
        answer = QMessageBox.question(
            self, tr("Limpar página"),
            tr("Remover todo o conteúdo desta página e deixá-la em branco?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._finish_page_interaction()
        self.save_snapshot()
        self._model_document = clear_document_page(self._model_document, page_id)
        self._page_selection[page_id] = set()
        if page_id == self._active_page_id:
            self._switching_page = True
            try:
                self.apply_scene_state(
                    prepare_scene_page(adapt_model_page(self._model_document, page_id)),
                    is_undo_redo=False,
                )
            finally:
                self._switching_page = False
            self._active_scene_baseline = self.get_current_scene_state()
        self._pending_history_page_id = page_id
        self.save_snapshot()
        self._refresh_page_controls()

    def remove_model_page(self, page_id: str):
        if not self._model_document or len(self._model_document["pages"]) < 2:
            return
        answer = QMessageBox.question(
            self, tr("Remover página"),
            tr("Remover esta página do modelo? Esta ação pode ser desfeita."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._finish_page_interaction()
        self.save_snapshot()
        self._page_selection[self._active_page_id] = self._selection_keys()
        old_back_selection = self._page_selection.get("back", set())
        self._model_document = remove_document_page(self._model_document, page_id)
        self._active_page_id = "front"
        self._page_selection = {
            "front": old_back_selection if page_id == "front" else self._page_selection.get("front", set()),
            "back": set(),
        }
        self._switching_page = True
        try:
            self.apply_scene_state(
                prepare_scene_page(adapt_model_page(self._model_document, "front")),
                is_undo_redo=False,
            )
        finally:
            self._switching_page = False
        self._active_scene_baseline = self.get_current_scene_state()
        self._restore_page_selection()
        self._pending_history_page_id = page_id
        self.save_snapshot()
        self._refresh_page_controls()
