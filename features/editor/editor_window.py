import json
import re
import copy
import shutil
import math
from contextlib import contextmanager
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QGraphicsView, QWidget,
                               QHBoxLayout, QFrame, QLabel, QPushButton,
                               QMessageBox,
                               QListWidgetItem, QDoubleSpinBox, QComboBox, QGraphicsItem,
                               QFileDialog, QGraphicsOpacityEffect, QApplication,
                               QSizePolicy, QLineEdit, QDialog, QFormLayout,
                               QDialogButtonBox, QVBoxLayout)
from PySide6.QtGui import (QPainter, QBrush, QPen, QColor, QShortcut, QIcon, QImage,
                           QKeySequence, QTextCursor, QTextCharFormat, QImageReader, QPixmap,
                           QFont, QTextDocument)
from PySide6.QtCore import Qt, Signal, QEvent, QRectF, QSize, QPointF, QTimer, QSignalBlocker, QModelIndex, QItemSelectionModel
from shiboken6 import isValid

from .canvas_items import (DesignerBox, Guideline, px_to_mm, mm_to_px, SignatureItem, RectangleItem,
                           ImageItem, BackgroundItem, SelectionTransformFrame, SelectionResizeHandle,
                           _reader_logical_size, _set_resize_handles_visible,
                           _board_item_center, _board_snap_step)
from .properties import CaixaDeTextoPanel
from .document_session import DocumentSessionMixin
from .organogram_editor import OrganogramEditorMixin, BoardGroupItem
from .model_adapter import prepare_scene_page
from .visual_cache import EditorVisualCache
from .history_capture import history_inputs
from .recovery_worker import RecoveryTask, RecoveryWorker
from .controls import initialize_editor_controls, create_canvas_paper
from core.template_manager import slugify_model_name
from core.history_manager import HistoryManager
from core.paths import get_models_dir
from core.render_cache import ensure_background_proxy, publish_thumbnail_cache
from core.resources import action_icon_path, app_icon_path, state_icon_path, navigation_icon_path, object_icon_path
from core.theme_icons import themed_svg_icon
from core.themes import themed_style, theme_color
from core.i18n import tr
from core.dialog_buttons import (get_text as dialog_get_text, style_message_box,
                                 style_dialog_button_box, NEUTRAL_STYLE)
from core.fornax_container import (
    FULL_MODE, PUBLIC_MODE, SIGNATURES_MODE, FornaxError,
    open_public_fornax, password_bytes, save_protected_fornax,
    save_public_fornax, unlock_fornax, reencrypt_fornax,
)
from core.fornax_session import FornaxExternalChangeError
from core.ui_font import DOCUMENT_FONT_FAMILY
from core.html_utils import TextOnlyDocument, sanitize_text_html
from core.model_document import (
    adapt_model_page,
    document_signatures,
    iter_page_asset_paths,
    load_model_document,
    load_recovery_documents,
    normalize_model_document,
    new_signature_id,
    replace_model_page,
    save_model_document,
)


_VISIBILITY_ICONS = {}
_BOARD_LAYER_ROLE = Qt.ItemDataRole.UserRole + 1


def _scaled_rich_text_html(html, factor):
    """Escala somente tamanhos explícitos; a fonte padrão vem do TextState."""
    document = TextOnlyDocument()
    document.setHtml(sanitize_text_html(html))
    fragments = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                size = fragment.charFormat().fontPointSize()
                if size > 0:
                    fragments.append((fragment.position(), fragment.length(), size))
            iterator += 1
        block = block.next()
    for position, length, size in reversed(fragments):
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        char_format = QTextCharFormat()
        char_format.setFontPointSize(max(1.0, size * factor))
        cursor.mergeCharFormat(char_format)
    return document.toHtml()


class LayerReconciliationError(RuntimeError):
    """O modelo da lista não conseguiu reconciliar suas linhas."""


class LayerGroupBadge(QPushButton):
    """Badge clicável que também inicia o arraste das linhas do grupo."""

    def __init__(self, text, layer_list, layer_item, select_callback, parent=None):
        super().__init__(text, parent)
        self._layer_list = layer_list
        self._layer_item = layer_item
        self._select_callback = select_callback
        self._press_global = None
        self._dragging = False
        self.clicked.connect(select_callback)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._dragging = False
            self._layer_list.setCurrentItem(self._layer_item)
            self._select_callback()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_global is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            if ((event.globalPosition().toPoint() - self._press_global).manhattanLength()
                    >= QApplication.startDragDistance()):
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging:
                viewport = self._layer_list.viewport()
                local = viewport.mapFromGlobal(event.globalPosition().toPoint())
                target = self._layer_list.itemAt(local)
                if target is not None:
                    rect = self._layer_list.visualItemRect(target)
                    after = local.y() >= rect.center().y()
                    window = self._layer_list.window()
                    if hasattr(window, 'show_layer_group_drop_indicator'):
                        window.show_layer_group_drop_indicator(
                            self._layer_item, target, after=after
                        )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                viewport = self._layer_list.viewport()
                local = viewport.mapFromGlobal(event.globalPosition().toPoint())
                target = self._layer_list.itemAt(local)
                if target is not None:
                    rect = self._layer_list.visualItemRect(target)
                    after = local.y() >= rect.center().y()
                    window = self._layer_list.window()
                    if hasattr(window, 'move_layer_group_from_badge'):
                        window.move_layer_group_from_badge(
                            self._layer_item, target, after=after
                        )
            window = self._layer_list.window()
            if hasattr(window, 'hide_layer_group_drop_indicator'):
                window.hide_layer_group_drop_indicator()
            self._press_global = None
            self._dragging = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _visibility_icon(visible):
    """Alterna o desenho do olho; a opacidade é aplicada pelo botão da camada."""
    key = (visible, theme_color('icon'))
    if key not in _VISIBILITY_ICONS:
        if any(stored[1] != key[1] for stored in _VISIBILITY_ICONS):
            _VISIBILITY_ICONS.clear()
        _VISIBILITY_ICONS[key] = themed_svg_icon(
            state_icon_path("eye" if visible else "eye-off")
        )
    return _VISIBILITY_ICONS[key]


class ElidedLayerLabel(QLabel):
    """Nome de camada que aproveita a largura disponível sem criar rolagem."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = str(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._update_visible_text()

    def set_full_text(self, text):
        text = str(text)
        if self._full_text != text:
            self._full_text = text
            self._update_visible_text()

    def _update_visible_text(self):
        available = max(0, self.contentsRect().width())
        visible = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, available
        )
        self.setText(visible)
        self.setToolTip(self._full_text if visible != self._full_text else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_visible_text()




class EditorWindow(OrganogramEditorMixin, DocumentSessionMixin, QMainWindow):
    closed = Signal()
    modelSaved = Signal(str, list, str)

    def _apply_tooltip(self, widget, text):
        """Aplica tooltip e garante que labels estáticos capturem o evento no motor customizado."""
        if isinstance(widget, QLabel):
            widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        widget.setToolTip(text)

    def __init__(self, parent=None):
        # Janela independente: ocultar o workspace não deve ocultar o editor.
        super().__init__()
        self._workspace_window = parent
        self._workspace_session_active = False
        self._current_model_name = None
        self._current_model_dir = None
        self._fornax_path = None
        self._fornax_mode = None
        self._fornax_model_id = None
        self._fornax_asset_provider = None
        self._fornax_session_manager = getattr(parent, "_fornax_sessions", None)
        self._fornax_save_as_required = False
        self._pending_protection_mode = None
        self._pending_protection_password = None
        self._recovery_source_path = None
        self._recovered_unsaved = False
        self._recovery_worker = None
        self._recovery_task = None
        self._recovery_pending = None
        self._recovery_success = None
        self._recovery_epoch = 0
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60_000)
        self._autosave_timer.timeout.connect(self._write_fornax_recovery)
        self._model_document = None
        self._history_capture_cache = None
        self._active_page_id = "front"
        self._board_grid_mm = 5.0
        self._board_margin_mm = 10.0
        self._loading_board = False
        self._visual_cache = EditorVisualCache()
        QApplication.instance().fontDatabaseChanged.connect(self._clear_visual_cache)
        self._page_selection = {"front": set(), "back": set()}
        self._object_clipboard = []
        self._clipboard_source_page = None
        self._mask_edit_session = None
        self._changing_mask_selection = False
        self._changing_group_selection = False
        self._selecting_from_layer_list = False
        self._group_resize_session = None
        self._layer_group_drop_indicator = None
        self._active_scene_baseline = None
        self._inactive_page_scene = None
        self._active_page_dependencies = None
        self._page_scene_budget = 64 * 1024 * 1024
        self._page_font_epoch = 0
        self.setWindowTitle(tr("Editor de modelos — FORNAX Forge"))
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1200, 800)

        initialize_editor_controls(self)

        self._scene_signals(self.scene, connect=True)

        
        # O histórico não deve registrar a inicialização em branco, deixaremos para 
        # registrar o Estado #0 logo após carregar o JSON ou criar novos itens.

        self.shortcut_dup = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_dup.activated.connect(self.duplicate_selected)

        self.shortcut_copy = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.shortcut_copy.activated.connect(self.copy_selected_items)
        self.shortcut_paste = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.shortcut_paste.activated.connect(self.paste_copied_items)
        self.shortcut_select_all = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        self.shortcut_select_all.activated.connect(self.select_all_items)
        self.shortcut_group = QShortcut(QKeySequence("Ctrl+G"), self)
        self.shortcut_group.activated.connect(self.group_selected_items)
        self.shortcut_ungroup = QShortcut(QKeySequence("Ctrl+Shift+G"), self)
        self.shortcut_ungroup.activated.connect(self.ungroup_selected_items)

        self.shortcut_finish_mask = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.shortcut_finish_mask.setEnabled(False)
        self.shortcut_finish_mask.activated.connect(lambda: self.finish_mask_edit(True))
        self.shortcut_cancel_mask = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_cancel_mask.setEnabled(False)
        self.shortcut_cancel_mask.activated.connect(lambda: self.finish_mask_edit(False))

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.export_to_json)

        self.shortcut_placeholder = QShortcut(QKeySequence("Ctrl+1"), self)
        self.shortcut_placeholder.activated.connect(lambda: self.editor_texto_panel.make_placeholder() if self.editor_texto_panel.isEnabled() else None)

        self.shortcut_optional = QShortcut(QKeySequence("Ctrl+2"), self)
        self.shortcut_optional.activated.connect(lambda: self.editor_texto_panel.make_optional_section() if self.editor_texto_panel.isEnabled() else None)
        
        self.shortcut_bold = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_bold.activated.connect(lambda: self.editor_texto_panel.btn_bold.click() if self.editor_texto_panel.isEnabled() else None)

        self.shortcut_italic = QShortcut(QKeySequence("Ctrl+I"), self)
        self.shortcut_italic.activated.connect(lambda: self.editor_texto_panel.btn_italic.click() if self.editor_texto_panel.isEnabled() else None)

        self.shortcut_underline = QShortcut(QKeySequence("Ctrl+U"), self)
        self.shortcut_underline.activated.connect(lambda: self.editor_texto_panel.btn_underline.click() if self.editor_texto_panel.isEnabled() else None)
        self.shortcut_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.shortcut_delete.activated.connect(self.delete_selected_items)

        # --- SISTEMA DE UNDO/REDO ---
        self.history = HistoryManager(max_steps=100, max_bytes=64 * 1024 * 1024)
        
        # Conecta o estado da pilha aos novos botões da UI
        self.history.canUndoChanged.connect(self.btn_undo.setEnabled)
        self.history.canRedoChanged.connect(self.btn_redo.setEnabled)
        
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.undo)

        # Atalho para renomear camada
        self.shortcut_rename = QShortcut(QKeySequence("F2"), self)
        # Só executa se houver um item atual na lista
        self.shortcut_rename.activated.connect(
            lambda: self.rename_layer() if self.layer_list.currentItem() else None
        )
        
        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.shortcut_redo.activated.connect(self.redo)
        self.shortcut_redo_alt = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.shortcut_redo_alt.activated.connect(self.redo)

        # Ativa/Desativa o botão de renomear conforme a seleção na lista
        self.layer_list.itemSelectionChanged.connect(
            lambda: self.btn_ren_layer.setEnabled(self.layer_list.currentItem() is not None)
        )        

        # --- FORÇA A SINCRONIA INICIAL ---
        # Faz o quadrado branco (1000x1000) se transformar no retângulo exato ditado pelas caixas (100x150mm) a 300 DPI
        self._on_physical_size_changed()
        self._ensure_background_rectangle()
        self.refresh_layer_list()
        self.save_snapshot()
        self._last_saved_state = self.get_current_scene_state()
        self._last_saved_document_state = self._capture_document_history_state()

        from .frontend import install_frontend
        install_frontend(self)
        from .canvas_edit import CanvasEdit
        self.canvas_edit = CanvasEdit(self)
        self.refresh_layer_list()


    def setVisible(self, visible):
        workspace = self._workspace_window
        starting_session = visible and workspace is not None and not self._workspace_session_active
        if starting_session:
            from core.window_geometry import transfer_window_geometry

            self._workspace_session_active = True
            transfer_window_geometry(workspace, self)
        super().setVisible(visible)
        if starting_session:
            workspace.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self._zoom_to_fit()

    def _release_workspace_window(self):
        workspace = self._workspace_window
        if workspace is None or not self._workspace_session_active:
            return
        from core.window_geometry import transfer_window_geometry

        self._workspace_session_active = False
        transfer_window_geometry(self, workspace)
        workspace.show()
        workspace.raise_()
        workspace.activateWindow()

    def _state_item_sort_key(self, item):
        """Chave estável para comparar estados recriados via undo/redo."""
        return (
            item.get("z_value", 0),
            item.get("layer_id", 999999),
            item.get("vertical", False),
            item.get("pos", 0),
            item.get("x", 0),
            item.get("y", 0),
            item.get("custom_name", ""),
            item.get("path", ""),
            item.get("html", ""),
        )

    def _normalize_state_for_compare(self, state):
        normalized = copy.deepcopy(state)
        normalized.pop("__active_page_id", None)
        normalized.pop("__action_page_id", None)
        for key in ("boxes", "images", "signatures", "guidelines"):
            if isinstance(normalized.get(key), list):
                normalized[key].sort(key=self._state_item_sort_key)
        return normalized

    def _states_equal_for_close(self, current_state, saved_state):
        return (
            self._normalize_state_for_compare(current_state)
            == self._normalize_state_for_compare(saved_state)
        )

    def closeEvent(self, event):
        self._finish_page_interaction()
        saved_document_state = getattr(self, '_last_saved_document_state', None)
        current_has_multiple_pages = bool(
            self._model_document and (len(self._model_document.get("pages", [])) > 1
                                     or self._model_document.get("organogram") is not None)
        )
        saved_had_multiple_pages = bool(
            saved_document_state
            and (len(saved_document_state.get("document", {}).get("pages", [])) > 1
                 or saved_document_state.get("document", {}).get("organogram") is not None)
        )
        if current_has_multiple_pages or saved_had_multiple_pages:
            current_state = self._capture_document_history_state()
            saved_state = saved_document_state
        else:
            # Compatibilidade para integrações antigas que ainda atribuem o
            # estado plano diretamente antes de fechar a janela.
            current_state = self.get_current_scene_state()
            saved_state = self._last_saved_state
        if hasattr(self, '_last_saved_state') and self._last_saved_state is not None:
            if self._recovered_unsaved or not self._states_equal_for_close(current_state, saved_state):
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(tr("Alterações não salvas"))
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setText(tr("<b>Você tem alterações não salvas neste modelo.</b><br><br>Gostaria de salvá-las antes de sair?"))
                
                btn_save = msg_box.addButton(tr("Salvar e Sair"), QMessageBox.ButtonRole.AcceptRole)
                btn_discard = msg_box.addButton(tr("Sair sem salvar"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg_box.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
                msg_box.setDefaultButton(btn_save)
                style_message_box(msg_box)
                msg_box.exec()
                
                if msg_box.clickedButton() == btn_save:
                    event.ignore()
                    self.export_to_json(skip_close_dialog=True)
                    return
                elif msg_box.clickedButton() != btn_discard:
                    event.ignore()
                    return
                else:
                    self._remove_fornax_recovery()
            else:
                self._remove_fornax_recovery()
        else:
            self._remove_fornax_recovery()
        self._autosave_timer.stop()
        self._cleanup_unused_assets_on_close()
        super().closeEvent(event)
        if event.isAccepted():
            self._history_capture_cache = None
            self._clear_visual_cache()
            self._release_workspace_window()
            if self._fornax_mode in {FULL_MODE, SIGNATURES_MODE}:
                self._discard_protected_editor_content()
            self.closed.emit()

    def _clear_visual_cache(self):
        cache = getattr(self, '_starter_preview_cache', None)
        if cache is not None:
            cache.clear()
        self._visual_cache.clear()
        self._page_font_epoch += 1
        self._clear_page_scenes()

    def _discard_protected_editor_content(self):
        """Descarta referências de uma janela protegida que já foi encerrada."""
        self._invalidate_recovery()
        self.scene.blockSignals(True)
        self.scene.clear()
        self._clear_visual_cache()
        self.fallback_bg = self.bg_item = self._selection_frame = None
        self._board_card_preview = None
        self._board_item_refs = {}
        self._board_artwork_refs = []
        self._board_path_cache = self._board_bounds_cache = self._board_cutouts_cache = None
        self._active_page_dependencies = None
        self.history.clear()
        self._object_clipboard.clear()
        self._clipboard_source_page = None
        self._fornax_asset_provider = None
        self._model_document = None
        self._history_capture_cache = None
        self._active_scene_baseline = None
        self._last_saved_state = None
        self._last_saved_document_state = None
        self._mask_edit_session = None
        self._group_resize_session = None
        # A janela encerrada não deve ser reutilizada com itens C++ destruídos.
        if self._recovery_worker is None:
            self.deleteLater()
        else:
            self._recovery_worker.finished.connect(self.deleteLater)

    def _current_model_directory(self) -> Path | None:
        if self._fornax_path is not None:
            return None
        if self._current_model_dir:
            return Path(self._current_model_dir)
        if self._current_model_name:
            return get_models_dir() / slugify_model_name(self._current_model_name)
        return None

    def _resolve_model_asset_path(self, raw_path: str, model_dir: Path) -> Path | None:
        if not raw_path:
            return None

        try:
            path = Path(raw_path)
        except TypeError:
            return None

        if not path.is_absolute():
            path = model_dir / path

        try:
            return path.resolve()
        except OSError:
            return path.absolute()

    def _collect_used_asset_paths(self, template_data: dict, model_dir: Path) -> set[Path]:
        assets_dir = (model_dir / "assets").resolve()
        used_assets = set()

        def add_if_local_asset(raw_path):
            resolved = self._resolve_model_asset_path(raw_path, model_dir)
            if not resolved:
                return
            if resolved == assets_dir or assets_dir in resolved.parents:
                used_assets.add(resolved)

        for _page_id, _kind, raw_path in iter_page_asset_paths(template_data):
            add_if_local_asset(raw_path)

        return used_assets

    def _cleanup_unused_assets_on_close(self):
        model_dir = self._current_model_directory()
        if not model_dir:
            return

        assets_dir = model_dir / "assets"
        if not assets_dir.exists():
            return

        try:
            template_data = load_model_document(model_dir)
        except Exception as e:
            print(f"[WARN] Limpeza de assets cancelada: não foi possível ler o modelo. {e}")
            return

        try:
            documents = [template_data, *load_recovery_documents(model_dir)]
            used_assets = set().union(*(
                self._collect_used_asset_paths(document, model_dir)
                for document in documents
            ))
            asset_paths = list(assets_dir.rglob("*"))
        except OSError as e:
            print(f"[WARN] Limpeza de assets cancelada: não foi possível varrer a pasta assets. {e}")
            return

        removed = 0

        for asset_path in asset_paths:
            try:
                is_file = asset_path.is_file()
                resolved = asset_path.resolve()
            except OSError as e:
                print(f"[WARN] Não foi possível verificar asset '{asset_path}': {e}")
                continue

            if not is_file:
                continue

            if resolved in used_assets:
                continue

            try:
                asset_path.unlink()
                removed += 1
            except OSError as e:
                print(f"[WARN] Não foi possível remover asset órfão '{asset_path}': {e}")

        # Remove apenas subpastas vazias dentro de assets; a pasta assets permanece.
        for folder in sorted(
            [p for p in assets_dir.rglob("*") if p.is_dir()],
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                folder.rmdir()
            except OSError:
                pass

        if removed:
            print(f"[INFO] Limpeza de assets: {removed} arquivo(s) órfão(s) removido(s).")

    def _remember_saved_asset_path(self, updates: dict[str, str], original_path: str, saved_path: str, model_dir: Path):
        if not original_path or not saved_path:
            return

        saved = Path(saved_path)
        if saved.is_absolute() or not saved.parts or saved.parts[0] != "assets":
            return

        updates[str(original_path)] = str(model_dir / saved)

    def _rewrite_state_asset_paths(self, state: dict, updates: dict[str, str]):
        if state.get("__document_history__") and isinstance(state.get("document"), dict):
            for page in state["document"].get("pages", []):
                page_state = {
                    "background_path": page.get("background_path"),
                    "signatures": page.get("signatures", []),
                    "images": page.get("images", []),
                }
                self._rewrite_state_asset_paths(page_state, updates)
                page["background_path"] = page_state["background_path"]
            return
        bg_path = state.get("background_path")
        if bg_path in updates:
            state["background_path"] = updates[bg_path]

        for sig in state.get("signatures", []):
            path = sig.get("path")
            if path in updates:
                sig["path"] = updates[path]

        for img in state.get("images", []):
            path = img.get("path")
            if path in updates:
                img["path"] = updates[path]

    def _apply_saved_asset_paths(self, updates: dict[str, str]):
        if not updates:
            return

        if self.background_path in updates:
            self.background_path = updates[self.background_path]
            if self.bg_item:
                self.bg_item._original_path = self.background_path

        for item in self.scene.items():
            if isinstance(item, BackgroundItem):
                continue
            if isinstance(item, (ImageItem, SignatureItem)):
                original_path = getattr(item, "_original_path", "")
                if original_path in updates:
                    item._original_path = updates[original_path]

        for state in getattr(self.history, "_undo_stack", []):
            if isinstance(state, dict):
                self._rewrite_state_asset_paths(state, updates)

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, 'view'):
            self._finish_canvas_pointer_interaction(leave_pan=True)
        return super().event(event)

    def _finish_canvas_pointer_interaction(self, *, leave_pan=False):
        if getattr(self, '_finishing_canvas_pointer', False):
            return
        self._finishing_canvas_pointer = True
        try:
            active = bool(self.view._pointer_buttons or self.scene.mouseGrabberItem())
            self.view.release_pointer()
            grabber = self.scene.mouseGrabberItem()
            if grabber is not None:
                grabber.ungrabMouse()
            # Uma perda de grab pode impedir até a entrega da soltura sintética.
            # Limpe as sessões remanescentes sem desfazer o trabalho já feito.
            for item in self.scene.items():
                for flag in ('_is_mouse_dragging', '_is_resizing'):
                    if getattr(item, flag, False):
                        active = True
                        setattr(item, flag, False)
                if isinstance(item, SelectionResizeHandle):
                    item._active = False
                if hasattr(item, '_anchor_scene'):
                    item._anchor_scene = None
                    item._shift_proportion = False
            if self._group_resize_session:
                active = True
                self.end_group_resize()
                self._refresh_selection_frame()
            # Como na soltura normal, mantenha as referências aos itens do
            # último arraste. Alguns itens Qt dependem delas para preservar a
            # subclasse Python; as posições são substituídas no próximo press.
            # Os flags acima impedem reutilizar esse estado como arraste ativo.
            self.scene._group_raw_delta = None
            self.scene._board_drag_anchor = None
            self._is_middle_panning = False
            drawing = getattr(self, 'shape_drawing', None)
            if drawing and drawing.start is not None:
                drawing.cancel()
            if leave_pan:
                self._leave_space_pan_mode()
            if leave_pan or self.view.dragMode() != QGraphicsView.DragMode.ScrollHandDrag:
                self.view.viewport().unsetCursor()
            if active:
                self.save_snapshot()
        finally:
            self._finishing_canvas_pointer = False

    def _recover_canvas_mouse_grab(self, generation):
        if generation == self.view._pointer_generation and self.view._pointer_buttons:
            self._finish_canvas_pointer_interaction(leave_pan=True)

    def eventFilter(self, source, event):
        if source in (self.view, self.view.viewport()) and getattr(self, "_board_connection_sources", None):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                position = self.view.mapToScene(event.position().toPoint())
                group = next((item for item in self.scene.items(position) if isinstance(item, BoardGroupItem)), None)
                if group:
                    self._connect_to_board_target(group.data["id"])
                return True
            if event.type() in (QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonRelease) and event.button() == Qt.MouseButton.LeftButton:
                return True
        if getattr(self, 'canvas_edit', None) and self.canvas_edit.box and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        # Escuta tanto a view principal quanto o viewport das barras de rolagem
        if source in (self.view, self.view.viewport()):
            # --- 1. Zoom com Ctrl + Scroll ou Mouse (Wayland/X11) ---
            if event.type() == QEvent.Type.Wheel and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                delta = event.angleDelta().y()
                if delta == 0:
                    delta = event.pixelDelta().y()
                
                if delta != 0:
                    zoom_factor = 1.15 if delta > 0 else 1 / 1.15
                    self._apply_zoom(zoom_factor)
                event.accept() # Mata o evento nativo de rolagem
                return True

            # --- 1.5. Zoom com Gesto de Pinça (Touchpad) ---
            if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                zoom_factor = 1.0 + event.value()
                if zoom_factor > 0:
                    self._apply_zoom(zoom_factor)
                event.accept()
                return True

            if event.type() == QEvent.Type.Resize:
                self._update_workspace_scene_rect()
                self._apply_zoom(1.0)

            if event.type() == QEvent.Type.FocusOut:
                self._finish_canvas_pointer_interaction(leave_pan=True)
            elif event.type() == QEvent.Type.UngrabMouse:
                # Uma soltura normal também pode liberar o grab. Aguarde o Qt
                # terminar de processá-la antes de procurar uma sessão presa.
                generation = self.view._pointer_generation
                QTimer.singleShot(0, self, lambda: self._recover_canvas_mouse_grab(generation))

            if (event.type() == QEvent.Type.MouseMove
                    and self.view._pointer_buttons & ~event.buttons()):
                self._finish_canvas_pointer_interaction()
                return True

            if (event.type() == QEvent.Type.ShortcutOverride
                    and event.key() == Qt.Key.Key_Escape
                    and (self.view._pointer_buttons or getattr(self, '_is_middle_panning', False)
                         or self.view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag)):
                event.accept()
                return True

            # --- Eventos de Mouse (Botão do Meio) ---
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._is_middle_panning = True
                    self._last_pan_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                    self.view.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
                    
            elif event.type() == QEvent.Type.MouseMove:
                if getattr(self, '_is_middle_panning', False):
                    if not event.buttons() & Qt.MouseButton.MiddleButton:
                        self._finish_canvas_pointer_interaction()
                        return True
                    current_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                    delta = current_pos - self._last_pan_pos
                    self.view.horizontalScrollBar().setValue(self.view.horizontalScrollBar().value() - delta.x())
                    self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().value() - delta.y())
                    self._last_pan_pos = current_pos
                    return True
                    
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._is_middle_panning = False
                    self.view.viewport().unsetCursor()
                    return True

            # --- Eventos de Teclado (Pressionar) ---
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()

                if key == Qt.Key.Key_Escape:
                    self._finish_canvas_pointer_interaction(leave_pan=True)
                    return True
                
                # 2. Ativar Pan (Mãozinha) ao segurar Espaço
                if key == Qt.Key.Key_Space and not event.isAutoRepeat():
                    self._enter_space_pan_mode()
                    return True
                
                if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                    zoom = self.view.transform().m11()
                    rect = self._get_document_rect()
                    ref = min(rect.width(), rect.height()) / 300
                    step = max(1, round(ref / zoom))
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        step = max(1, step * 10)
                    dx = -step if key == Qt.Key.Key_Left else (step if key == Qt.Key.Key_Right else 0)
                    dy = -step if key == Qt.Key.Key_Up else (step if key == Qt.Key.Key_Down else 0)
                    sel_items = self.scene.selectedItems()
                    if sel_items:
                        if self._active_page_id == "organogram":
                            step = _board_snap_step(self.scene, [i for i in sel_items if hasattr(i, 'rect')])
                            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                                step *= 10
                            self._move_board_items(sel_items, QPointF(
                                -step if key == Qt.Key.Key_Left else step if key == Qt.Key.Key_Right else 0,
                                -step if key == Qt.Key.Key_Up else step if key == Qt.Key.Key_Down else 0))
                        else:
                            for item in sel_items:
                                if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                                    item._keyboard_move = True
                                    item.moveBy(dx, dy)
                                    item._keyboard_move = False
                        # A seleção não mudou: recarregar o editor de texto aqui
                        # pode transferir o foco e consumir as próximas setas.
                        self.update_position_ui()
                        self._refresh_selection_frame()
                        return True

            # --- Eventos de Teclado (Soltar) ---
            elif event.type() == QEvent.Type.KeyRelease:
                # 3. Desativar Pan (Voltar para seleção) ao soltar Espaço
                if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                    self._leave_space_pan_mode()
                    return True
                if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and not event.isAutoRepeat():
                    if self.scene.selectedItems():
                        self.save_snapshot()
                    return True
        
        return super().eventFilter(source, event)
    










    
    def _authorized_asset_bytes(self, reference: str):
        if self._fornax_asset_provider is None:
            return None
        try:
            return bytes(self._fornax_asset_provider(str(reference)))
        except Exception:
            return None

    def _save_asset_provider(self, reference: str) -> bytes:
        protected = self._authorized_asset_bytes(reference)
        if protected is not None:
            return protected
        path = Path(reference)
        if not path.is_file():
            raise FileNotFoundError(f"Asset não encontrado: {reference}")
        return path.read_bytes()

    def load_from_fornax(
        self, document, *, path, mode, model_id, asset_provider,
        session_manager, save_as_required=False, recovered=False,
    ):
        """Abre um snapshot autorizado sem extrair seus assets para o disco."""
        self._fornax_path = Path(path).resolve()
        self._fornax_mode = mode
        self._fornax_model_id = model_id
        self._fornax_asset_provider = self._detached_asset_provider(document, asset_provider)
        self._fornax_session_manager = session_manager
        self._fornax_save_as_required = bool(save_as_required)
        self._recovery_source_path = self._fornax_path
        self._recovered_unsaved = bool(recovered)
        self._current_model_dir = None
        self._load_document_into_scene(document)
        self.refresh_protection_control()
        self._autosave_timer.start()

    @staticmethod
    def _detached_asset_provider(document, provider):
        assets = {
            reference: bytes(provider(reference))
            for _page, _kind, reference in iter_page_asset_paths(document)
        }

        def resolve(reference):
            try:
                return assets[str(reference)]
            except KeyError as error:
                raise FileNotFoundError(f"Asset não encontrado: {reference}") from error

        return resolve

    @staticmethod
    def _combined_asset_provider(primary, fallback):
        def resolve(reference):
            try:
                return primary(reference)
            except (FileNotFoundError, KeyError):
                if fallback is None:
                    raise
                return fallback(reference)
        return resolve

    @staticmethod
    def fornax_recovery_path(path):
        source = Path(path)
        return source.with_name(f".{source.name}.autosave.fornax")

    def _invalidate_recovery(self):
        """Revoga publicação antes de salvar, trocar, remover ou fechar."""
        self._recovery_epoch += 1
        self._recovery_success = None
        if self._recovery_task is not None:
            self._recovery_task.authorization.cancel()
        if self._recovery_pending is not None:
            self._recovery_pending.clear()
            self._recovery_pending = None

    def _remove_fornax_recovery(self):
        self._invalidate_recovery()
        source = self._recovery_source_path or self._fornax_path
        if source is not None:
            recovery = self.fornax_recovery_path(source)
            recovery.unlink(missing_ok=True)
            recovery.with_name(recovery.name + ".bak").unlink(missing_ok=True)

    def _recovery_gesture_active(self):
        return bool(
            self.view._pointer_buttons or self.scene.mouseGrabberItem() is not None
            or self._mask_edit_session or self._group_resize_session
            or getattr(getattr(self, 'shape_drawing', None), 'start', None) is not None
        )

    def _write_fornax_recovery(self):
        if (
            self._fornax_path is None or self._fornax_session_manager is None
            or self._fornax_save_as_required or self._recovery_gesture_active()
        ):
            return
        authorization = None
        try:
            current = self._capture_document_history_state()
            if self._states_equal_for_close(current, self._last_saved_document_state):
                # Returning to the saved state also revokes a stale active job.
                if self._recovery_task is not None:
                    self._invalidate_recovery()
                return
            document = current["document"]
            document["name"] = self._current_model_name
            authorization = self._fornax_session_manager.prepare_recovery(self._fornax_path)
            task = RecoveryTask.capture(
                document, self._authorized_asset_bytes, authorization,
                self.fornax_recovery_path(self._fornax_path), self._recovery_epoch,
                self._recovery_success,
            )
            if self._recovery_worker is not None:
                self._recovery_task.authorization.cancel()
                if self._recovery_pending is not None:
                    self._recovery_pending.clear()
                self._recovery_pending = task
            else:
                self._start_recovery(task)
        except Exception as error:
            if authorization is not None:
                authorization.cancel()
            print(f"[WARN] Falha ao salvar recuperação protegida: {error}")

    def _start_recovery(self, task):
        worker = RecoveryWorker(task)
        self._recovery_worker, self._recovery_task = worker, task
        worker.commit_requested.connect(self._commit_recovery)
        worker.finished.connect(self._recovery_finished)
        # This callback retains only the independent authorization, not the UI.
        worker.on_window_destroyed = lambda *_args, a=task.authorization: a.cancel()
        self.destroyed.connect(worker.on_window_destroyed)
        worker.start()

    def _commit_recovery(self, worker):
        task = worker.task
        authorization = task.authorization
        try:
            if (
                worker is not self._recovery_worker or task.epoch != self._recovery_epoch
                or authorization.cancelled.is_set()
                or self._fornax_session_manager is None
                or not self._fornax_session_manager.token_is_current(authorization.token)
                or self._fornax_save_as_required or self._recovery_gesture_active()
            ):
                authorization.cancel()
                return
            current = self._capture_document_history_state()["document"]
            current["name"] = self._current_model_name
            if current != task.document or not task.external_is_current():
                authorization.cancel()
                # Keep only the latest consistent snapshot after this worker ends.
                self._write_fornax_recovery()
                return
            # No event processing between validation and the short rename/fsync.
            # All expensive file/content checks have already run on the worker.
            with authorization.publication():
                worker.commit_action(authorization.check_publication)
                worker.committed = True
        except Exception as error:
            worker.commit_error = error.with_traceback(None)
        finally:
            authorization.answer.set()

    def _recovery_finished(self):
        worker = self._recovery_worker
        if worker is None:
            return
        task = worker.task
        self.destroyed.disconnect(worker.on_window_destroyed)
        if task.epoch == self._recovery_epoch:
            if worker.result is not None:
                self._recovery_success = worker.result
            if worker.error is not None:
                print(f"[WARN] Falha ao salvar recuperação protegida: {worker.error}")
        self._recovery_worker = self._recovery_task = None
        pending, self._recovery_pending = self._recovery_pending, None
        if pending is not None:
            if pending.epoch == self._recovery_epoch and not pending.authorization.cancelled.is_set():
                self._start_recovery(pending)
            else:
                pending.clear()

    def load_starter_document(self, document, asset_provider=None):
        """Inicia uma cópia sem nome/destino de gravação e mantém o aviso de salvar."""
        saved_scene = copy.deepcopy(self._last_saved_state)
        saved_document = copy.deepcopy(self._last_saved_document_state)
        self._fornax_asset_provider = self._detached_asset_provider(document, asset_provider) if asset_provider else None
        self._load_document_into_scene(copy.deepcopy(document))
        self._current_model_name = None
        self.setWindowTitle(tr("Editor de modelos — FORNAX Forge"))
        self._last_saved_state = saved_scene
        self._last_saved_document_state = saved_document

    def _load_document_into_scene(self, document):
        self._invalidate_recovery()
        self._history_capture_cache = None
        data = prepare_scene_page(adapt_model_page(document, "front"))
        self._clear_visual_cache()
        self._current_model_name = data.get("name", "")
        self._model_document = document
        self._active_page_id = "front"
        self._page_selection = {"front": set(), "back": set()}
        self.setWindowTitle(tr("Editor de modelos — {modelo}").format(modelo=self._current_model_name))
        self.apply_scene_state(data, is_undo_redo=False)
        self._active_scene_baseline = self.get_current_scene_state()
        self._zoom_to_fit()
        self.history.clear()
        self.save_snapshot()
        self._last_saved_state = self.get_current_scene_state()
        self._last_saved_document_state = self._capture_document_history_state()
        self._refresh_page_controls()

    def load_from_json(self, file_path):
        path = Path(file_path)
        model_dir = path if path.is_dir() else path.parent
        try:
            document = load_model_document(model_dir)
        except FileNotFoundError:
            return
        self._current_model_dir = model_dir
        self._load_document_into_scene(document)

    def export_to_json(self, skip_close_dialog=False):
        self._finish_page_interaction()
        data = self.get_current_scene_state()
        
        if not self._current_model_name:
            novo_nome, ok = dialog_get_text(
                self, tr("Salvar modelo"), tr("Nome do modelo:")
            )
            if not ok or not novo_nome.strip(): return
            self._current_model_name = novo_nome.strip()
            self.setWindowTitle(tr("Editor de modelos — {modelo}").format(modelo=self._current_model_name))
            
        data["name"] = self._current_model_name
        model_name = self._current_model_name

        if self._fornax_path is not None or self._current_model_dir is None:
            self._export_to_fornax(data, skip_close_dialog=skip_close_dialog)
            return

        slug = slugify_model_name(model_name)
        model_dir = get_models_dir() / slug
        model_dir.mkdir(parents=True, exist_ok=True)
        self._current_model_dir = model_dir
        saved_asset_paths = {}
        
        if self.background_path:
            rel_bg = self._import_asset(self.background_path, model_dir)
            if rel_bg:
                data["background_path"] = rel_bg
                self._remember_saved_asset_path(saved_asset_paths, self.background_path, rel_bg, model_dir)

        for sig in data["signatures"]:
            original_path = sig["path"]
            rel_sig = self._import_asset(sig["path"], model_dir)
            if rel_sig:
                sig["path"] = rel_sig
                self._remember_saved_asset_path(saved_asset_paths, original_path, rel_sig, model_dir)

        for img in data.get("images", []):
            original_path = img["path"]
            rel_img = self._import_asset(img["path"], model_dir)
            if rel_img:
                img["path"] = rel_img
                self._remember_saved_asset_path(saved_asset_paths, original_path, rel_img, model_dir)

        ensure_background_proxy(model_dir, data)

        document = self._model_document
        if document is None:
            try:
                document = load_model_document(model_dir)
            except FileNotFoundError:
                document = normalize_model_document(data)
            except Exception as e:
                print(f"Aviso: Não foi possível preservar os metadados antigos. {e}")
                document = normalize_model_document(data)

        document = replace_model_page(document, data, self._active_page_id)
        document["name"] = model_name
        file_path = save_model_document(document, model_dir)
        document["__model_dir"] = str(model_dir.resolve())
        document["__model_file"] = str(file_path.resolve())
        self._model_document = document

        self._apply_saved_asset_paths(saved_asset_paths)

        try:
            from features.generator.renderer import NativeRenderer
            
            # Instancia o renderizador com os dados fresquinhos do modelo
            thumb_renderer = NativeRenderer(data)
            
            # Gera o Pixmap estático (sem row_rich para manter placeholders brutos)
            preview_image = thumb_renderer.render_preview_image(row_rich=None, max_side=1600)
            if publish_thumbnail_cache(
                model_dir, file_path, preview_image, self._active_page_id,
            ) is None:
                raise OSError("Não foi possível gravar a miniatura.")
        except Exception as e:
            print(f"[WARN] Falha ao atualizar a miniatura do modelo: {e}")

        # Emite o sinal depois do cache visual ser atualizado.
        self.modelSaved.emit(model_name, document["placeholders"], str(file_path))

        self._last_saved_state = self.get_current_scene_state()
        self._last_saved_document_state = self._capture_document_history_state()
        
        if skip_close_dialog:
            self.close()
            return
        
        # Criação do Diálogo de Decisão Customizado
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(tr("Sucesso"))
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(tr("Deseja sair do editor?"))
        
        btn_exit = msg_box.addButton(tr("Encerrar edição"), QMessageBox.ButtonRole.AcceptRole)
        btn_stay = msg_box.addButton(tr("Continuar editando"), QMessageBox.ButtonRole.ActionRole)
        msg_box.setDefaultButton(btn_stay)
        style_message_box(msg_box)
        themed_style(btn_stay, NEUTRAL_STYLE)
        button_width = max(96, btn_exit.sizeHint().width(), btn_stay.sizeHint().width())
        for button in (btn_exit, btn_stay):
            button.setFixedSize(button_width, 30)
        msg_box.exec()

        if msg_box.clickedButton() == btn_exit:
            self.close() # Fecha a janela do editor

    def _choose_fornax_protection(self, has_signatures: bool):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Proteção do modelo"))
        if has_signatures:
            dialog.setText(tr(
                "Este modelo possui assinaturas. Recomendamos protegê-las com senha para "
                "evitar o uso não autorizado. Você também pode continuar sem senha; nesse "
                "caso, as assinaturas ficarão acessíveis dentro do arquivo do modelo."
            ))
            primary = dialog.addButton(
                tr("Proteger assinaturas"), QMessageBox.ButtonRole.AcceptRole,
            )
            public = dialog.addButton(
                tr("Salvar sem senha"), QMessageBox.ButtonRole.ActionRole,
            )
        else:
            dialog.setText(tr("Escolha como este modelo deve ser salvo."))
            primary = dialog.addButton(
                tr("Sem proteção"), QMessageBox.ButtonRole.AcceptRole,
            )
            public = primary
        full = dialog.addButton(tr("Proteger modelo inteiro"), QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        style_message_box(dialog)
        dialog.exec()
        if dialog.clickedButton() is primary:
            return (SIGNATURES_MODE, False) if has_signatures else (PUBLIC_MODE, False)
        if has_signatures and dialog.clickedButton() is public:
            return PUBLIC_MODE, True
        if dialog.clickedButton() is full:
            return FULL_MODE, False
        return None

    def _request_new_fornax_password(self):
        first, accepted = dialog_get_text(
            self, tr("Criar senha"),
            tr("Digite uma senha de 8 a 64 caracteres:"),
            echo=QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return None
        second, accepted = dialog_get_text(
            self, tr("Confirmar senha"), tr("Digite novamente a senha:"),
            echo=QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return None
        try:
            first_normalized = password_bytes(first)
            second_normalized = password_bytes(second)
        except FornaxError as error:
            QMessageBox.warning(self, tr("Senha inválida"), str(error))
            return None
        if first_normalized != second_normalized:
            QMessageBox.warning(self, tr("Senha inválida"), tr("As senhas informadas não coincidem."))
            return None
        return first

    def _protection_mode_for_ui(self):
        return self._pending_protection_mode or self._fornax_mode or PUBLIC_MODE

    def refresh_protection_control(self):
        mode = self._protection_mode_for_ui()
        icons = {
            PUBLIC_MODE: "shield",
            SIGNATURES_MODE: "shield-ass",
            FULL_MODE: "shield-full",
        }
        labels = {
            PUBLIC_MODE: tr("Sem proteção"),
            SIGNATURES_MODE: tr("Proteger assinaturas"),
            FULL_MODE: tr("Proteger modelo inteiro"),
        }
        if hasattr(self, "btn_save_security"):
            self.btn_save_security.setIcon(themed_svg_icon(state_icon_path(icons[mode])))
            self.btn_save_security.setToolTip(labels[mode])
        if hasattr(self, "protection_actions"):
            for action_mode, action in self.protection_actions.items():
                action.setChecked(action_mode == mode)
            # Abrir o menu não encerra uma interação nem modifica o documento.
            data = self.get_current_scene_state()
            document = self._model_document or normalize_model_document(data)
            document = replace_model_page(document, data, self._active_page_id)
            has_signatures = bool(document_signatures(document))
            self.protection_actions[SIGNATURES_MODE].setEnabled(has_signatures)
        if hasattr(self, "action_change_password"):
            self.action_change_password.setEnabled(
                self._fornax_path is not None and self._fornax_mode in {SIGNATURES_MODE, FULL_MODE}
            )

    def _document_with_active_page(self):
        self._finish_page_interaction()
        data = self.get_current_scene_state()
        data["name"] = self._current_model_name
        document = self._model_document or normalize_model_document(data)
        document = replace_model_page(document, data, self._active_page_id)
        document["name"] = self._current_model_name
        return document

    def request_protection_mode(self, mode):
        if mode not in {PUBLIC_MODE, SIGNATURES_MODE, FULL_MODE}:
            return
        if mode == SIGNATURES_MODE and not document_signatures(
            self._document_with_active_page()
        ):
            QMessageBox.information(
                self, tr("Proteção do modelo"),
                tr("Este modelo não possui assinaturas para proteger."),
            )
            self.refresh_protection_control()
            return
        if mode == self._protection_mode_for_ui():
            return

        password = None
        current_mode = self._fornax_mode or PUBLIC_MODE
        if current_mode == PUBLIC_MODE and mode != PUBLIC_MODE:
            password = self._request_new_fornax_password()
            if password is None:
                self.refresh_protection_control()
                return

        # Modelos ainda sem arquivo guardam a escolha até o primeiro salvamento.
        if self._fornax_path is None:
            self._pending_protection_mode = mode
            self._pending_protection_password = password
            self.refresh_protection_control()
            return

        document = self._document_with_active_page()
        document = copy.deepcopy(document)
        if mode == PUBLIC_MODE and document_signatures(document):
            document["protection_preferences"] = {
                "public_signatures_acknowledged": True,
            }
        else:
            document.pop("protection_preferences", None)
        destination = Path(self._fornax_path)
        self._invalidate_recovery()
        try:
            manager = self._fornax_session_manager
            if current_mode in {SIGNATURES_MODE, FULL_MODE}:
                if manager is None:
                    raise FornaxError(tr("A sessão protegida não está disponível."))
                status = manager.save(
                    document, path=destination, destination=destination, mode=mode,
                    asset_provider=self._save_asset_provider,
                )
                descriptor = status.descriptor
            elif mode == PUBLIC_MODE:
                return
            else:
                descriptor = save_protected_fornax(
                    document, destination, password, mode=mode,
                    asset_provider=self._save_asset_provider,
                    model_id=self._fornax_model_id,
                )
                if manager is not None:
                    manager.forget(destination)
                    manager.unlock(destination, password)

            if manager is not None:
                opened_document = manager.document(destination)
                provider = lambda reference, p=destination: manager.asset(reference, p)
            else:
                opened = unlock_fornax(descriptor, password)
                opened_document, provider = opened.document(), opened.asset
        except Exception as error:
            QMessageBox.critical(
                self, tr("Erro"),
                tr("Falha ao alterar a proteção do modelo:\n{erro}").format(erro=error),
            )
            self.refresh_protection_control()
            return

        previous_provider = self._fornax_asset_provider
        self._fornax_mode = descriptor.mode
        self._fornax_model_id = descriptor.model_id
        self._model_document = opened_document
        fresh_provider = self._detached_asset_provider(opened_document, provider)
        self._fornax_asset_provider = self._combined_asset_provider(
            fresh_provider, previous_provider,
        )
        self._remove_fornax_recovery()
        self._last_saved_state = self.get_current_scene_state()
        self._last_saved_document_state = self._capture_document_history_state()
        self.modelSaved.emit(
            self._current_model_name, opened_document["placeholders"], str(destination),
        )
        self.refresh_protection_control()

    def change_fornax_password(self):
        if self._fornax_path is None or self._fornax_mode not in {SIGNATURES_MODE, FULL_MODE}:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Alterar senha"))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        current = QLineEdit(dialog)
        new = QLineEdit(dialog)
        confirmation = QLineEdit(dialog)
        for field in (current, new, confirmation):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("Senha atual"), current)
        form.addRow(tr("Nova senha"), new)
        form.addRow(tr("Confirmar nova senha"), confirmation)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        style_dialog_button_box(buttons)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if password_bytes(new.text()) != password_bytes(confirmation.text()):
                raise FornaxError(tr("As senhas informadas não coincidem."))
            destination = Path(self._fornax_path)
            self._invalidate_recovery()
            descriptor = reencrypt_fornax(
                destination, current.text(), destination, new.text(), mode=self._fornax_mode,
            )
            manager = self._fornax_session_manager
            if manager is not None:
                manager.forget(destination)
                manager.unlock(destination, new.text())
                opened_document = manager.document(destination)
                provider = lambda reference, p=destination: manager.asset(reference, p)
                self._model_document = opened_document
                fresh_provider = self._detached_asset_provider(opened_document, provider)
                self._fornax_asset_provider = self._combined_asset_provider(
                    fresh_provider, self._fornax_asset_provider,
                )
            self._fornax_model_id = descriptor.model_id
            self._remove_fornax_recovery()
        except Exception as error:
            QMessageBox.warning(self, tr("Senha inválida"), str(error))
            return
        QMessageBox.information(
            self, tr("Alterar senha"), tr("A senha do modelo foi alterada."),
        )

    def _show_save_success_dialog(self, skip_close_dialog=False):
        if skip_close_dialog:
            self.close()
            return
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(tr("Sucesso"))
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(tr("Deseja sair do editor?"))
        btn_exit = msg_box.addButton(tr("Encerrar edição"), QMessageBox.ButtonRole.AcceptRole)
        btn_stay = msg_box.addButton(tr("Continuar editando"), QMessageBox.ButtonRole.ActionRole)
        msg_box.setDefaultButton(btn_stay)
        style_message_box(msg_box)
        themed_style(btn_stay, NEUTRAL_STYLE)
        button_width = max(96, btn_exit.sizeHint().width(), btn_stay.sizeHint().width())
        for button in (btn_exit, btn_stay):
            button.setFixedSize(button_width, 30)
        msg_box.exec()
        if msg_box.clickedButton() == btn_exit:
            self.close()

    def _export_to_fornax(self, data, *, skip_close_dialog=False):
        save_as = self._fornax_save_as_required or self._fornax_path is None
        model_name = self._current_model_name
        if self._fornax_save_as_required:
            suggested = tr("{nome} (Cópia)").format(nome=model_name)
            new_name, accepted = dialog_get_text(
                self, tr("Salvar como novo modelo"), tr("Nome do novo modelo:"),
                text=suggested,
            )
            if not accepted or not new_name.strip():
                return
            model_name = new_name.strip()
            data["name"] = model_name

        document = self._model_document
        if document is None:
            document = normalize_model_document(data)
        document = replace_model_page(document, data, self._active_page_id)
        document["name"] = model_name
        has_signatures = bool(document_signatures(document))

        # Uma nova identidade precisa de uma decisão local. A cópia usada para
        # gravar pode receber o aceite; o estado vivo do editor só é substituído
        # pelo documento reaberto depois de a publicação ser verificada.
        if save_as:
            document = copy.deepcopy(document)
            document.pop("protection_preferences", None)
        acknowledged = (
            document.get("protection_preferences", {})
            .get("public_signatures_acknowledged") is True
        )

        mode = self._pending_protection_mode or self._fornax_mode
        password = self._pending_protection_password
        protection_transition = (
            mode is None
            or (mode == PUBLIC_MODE and has_signatures and not acknowledged)
            or (mode == SIGNATURES_MODE and not has_signatures)
        )
        if (save_as or protection_transition) and self._pending_protection_mode is None:
            choice = self._choose_fornax_protection(has_signatures)
            if choice is None:
                return
            mode, acknowledge_public_signatures = choice
            needs_new_password = (
                mode != PUBLIC_MODE
                and (save_as or self._fornax_mode in {None, PUBLIC_MODE})
            )
            if needs_new_password:
                password = password or self._request_new_fornax_password()
                if password is None:
                    return
            document = copy.deepcopy(document)
            if mode == PUBLIC_MODE and has_signatures and acknowledge_public_signatures:
                document["protection_preferences"] = {
                    "public_signatures_acknowledged": True,
                }
            else:
                document.pop("protection_preferences", None)

        destination = (
            get_models_dir() / f"{slugify_model_name(model_name)}.fornax"
            if save_as else Path(self._fornax_path)
        )
        if save_as and destination.exists():
            QMessageBox.warning(self, tr("Erro"), tr("Já existe um modelo com esse nome."))
            return

        self._invalidate_recovery()
        try:
            manager = self._fornax_session_manager
            can_use_session = (
                not save_as and manager is not None and self._fornax_path is not None
                and not (self._fornax_mode == PUBLIC_MODE and mode != PUBLIC_MODE)
            )
            if can_use_session:
                status = manager.save(
                    document, path=self._fornax_path, destination=destination,
                    mode=mode, asset_provider=self._save_asset_provider,
                )
                opened_document = manager.document(destination)
                provider = lambda reference, p=destination: manager.asset(reference, p)
                descriptor = status.descriptor
            elif mode == PUBLIC_MODE:
                descriptor = save_public_fornax(
                    document, destination, asset_provider=self._save_asset_provider,
                    model_id=None if save_as else self._fornax_model_id,
                )
                if manager is not None:
                    status = manager.select(destination)
                    opened_document = manager.document(destination)
                    provider = lambda reference, p=destination: manager.asset(reference, p)
                else:
                    opened = open_public_fornax(descriptor)
                    opened_document, provider = opened.document(), opened.asset
            else:
                descriptor = save_protected_fornax(
                    document, destination, password, mode=mode,
                    asset_provider=self._save_asset_provider,
                    model_id=None if save_as else self._fornax_model_id,
                )
                if manager is not None:
                    manager.forget(destination)
                    manager.unlock(destination, password)
                    opened_document = manager.document(destination)
                    provider = lambda reference, p=destination: manager.asset(reference, p)
                else:
                    opened = unlock_fornax(descriptor, password)
                    opened_document, provider = opened.document(), opened.asset
        except FornaxExternalChangeError:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("Modelo alterado externamente"))
            dialog.setText(tr("O arquivo mudou enquanto este modelo estava aberto. Salve seu trabalho como uma nova cópia ou recarregue a versão do disco."))
            copy_button = dialog.addButton(tr("Salvar como nova cópia"), QMessageBox.ButtonRole.AcceptRole)
            reload_button = dialog.addButton(tr("Recarregar arquivo"), QMessageBox.ButtonRole.ActionRole)
            dialog.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            style_message_box(dialog)
            dialog.exec()
            if dialog.clickedButton() is copy_button:
                self._fornax_save_as_required = True
                self._export_to_fornax(data, skip_close_dialog=skip_close_dialog)
            elif dialog.clickedButton() is reload_button:
                self._remove_fornax_recovery()
                self._last_saved_state = self.get_current_scene_state()
                self._last_saved_document_state = self._capture_document_history_state()
                self.close()
                workspace = self._workspace_window
                if workspace is not None:
                    workspace._on_model_changed(workspace.preview_panel.cbo_models.currentText())
            return
        except Exception as error:
            QMessageBox.critical(
                self, tr("Erro"), tr("Falha ao salvar modelo:\n{erro}").format(erro=error),
            )
            return

        self._fornax_path = destination.resolve()
        self._fornax_mode = descriptor.mode
        self._fornax_model_id = descriptor.model_id
        self._fornax_asset_provider = self._detached_asset_provider(
            opened_document, provider,
        )
        self._fornax_save_as_required = False
        self._pending_protection_mode = None
        self._pending_protection_password = None
        self._recovered_unsaved = False
        self._remove_fornax_recovery()
        self._recovery_source_path = self._fornax_path
        self._autosave_timer.start()
        self._current_model_name = model_name
        self._current_model_dir = None
        self._load_document_into_scene(opened_document)
        self.refresh_protection_control()
        self.modelSaved.emit(model_name, opened_document["placeholders"], str(destination))
        self._show_save_success_dialog(skip_close_dialog)
    
    def load_background_image(
        self, path, update_ui=True, props=None, force_document_resize=False,
        *, asset_data=None, asset_reference=None,
    ):
        original_size = None
        if asset_data is not None:
            image = QImage.fromData(bytes(asset_data))
            if image.isNull():
                QMessageBox.warning(self, tr("Erro de leitura"), tr("A imagem está corrompida ou em um formato não suportado (ex.: CMYK sem plugin)."))
                return
            original_size = image.size()
        elif path:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            raw_size = reader.size()
            original_size = _reader_logical_size(reader, raw_size) if not raw_size.isEmpty() else raw_size
            
            if not reader.canRead() and QPixmap(path).isNull():
                QMessageBox.warning(self, tr("Erro de leitura"), tr("A imagem está corrompida ou em um formato não suportado (ex.: CMYK sem plugin)."))
                return
                
            if original_size.isEmpty():
                original_size = QPixmap(path).size()
        
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
            
        self.background_path = asset_reference or path
        
        # Instancia o fundo livre em vez de um Pixmap cimentado
        self.bg_item = BackgroundItem(
            path, pixmap_data=asset_data, asset_reference=asset_reference,
        )
        self.scene.addItem(self.bg_item)
        self.refresh_layer_list()
        
        if props:
            # Se for carregado via JSON, recupera posições e bloqueios
            self.bg_item.setPos(props.get("x", 0), props.get("y", 0))
            if "w" in props and "h" in props:
                self.bg_item.resize_custom(props["w"], props["h"])
            self.bg_item.setVisible(props.get("visible", True))
            self.bg_item.setOpacity(props.get("opacity", 1.0))
            self.bg_item.keep_proportion = props.get("keep_proportion", True)
            if props.get("locked", False):
                self.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                self.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                self.bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        elif not update_ui:
            # Fallback para JSONs antigos: estica para o tamanho da tela para não quebrar layout
            w_px = mm_to_px(self.spin_phys_w.value())
            h_px = mm_to_px(self.spin_phys_h.value())
            self.bg_item.resize_custom(w_px, h_px)

        if force_document_resize and original_size:
                # Lê o tamanho original da imagem ao importar manualmente e molda a "Prancheta"
                w_mm = px_to_mm(original_size.width())
                h_mm = px_to_mm(original_size.height())

                # Trava: se qualquer lado ultrapassar 1000mm, redimensiona proporcionalmente
                MAX_MM = 1000.0
                if w_mm > MAX_MM or h_mm > MAX_MM:
                    scale = MAX_MM / max(w_mm, h_mm)
                    w_mm = w_mm * scale
                    h_mm = h_mm * scale
                
                self.spin_phys_w.blockSignals(True)
                self.spin_phys_h.blockSignals(True)
                self.spin_phys_w.setValue(w_mm)
                self.spin_phys_h.setValue(h_mm)
                self.spin_phys_w.blockSignals(False)
                self.spin_phys_h.blockSignals(False)
                
                self._on_physical_size_changed()
                self._zoom_to_fit()
            
                if update_ui:
                    self.save_snapshot()

    def get_current_page_placeholders(self):
        placeholders = []

        def add(value):
            if value and value not in placeholders:
                placeholders.append(value)

        for item in self.scene.items():
            if isinstance(item, DesignerBox):
                for name in item.get_placeholders():
                    add(name)
                if getattr(item.state, 'has_link', False):
                    add(self._link_key_for_item(item))
            elif isinstance(item, RectangleItem) and not getattr(item, 'is_document_background', False):
                add(getattr(item, 'dynamic_image_field', ''))
                if getattr(item, 'has_link', False):
                    add(self._link_key_for_item(item))
            elif isinstance(item, ImageItem) and not isinstance(item, BackgroundItem):
                if getattr(item, 'has_link', False):
                    add(self._link_key_for_item(item))
        return placeholders

    def _link_key_for_item(self, item):
        owner = item.state if isinstance(item, DesignerBox) else item
        key = str(getattr(owner, 'link_key', '') or '').strip()
        if key:
            return key
        name = self._generate_layer_name(getattr(item, 'layer_id', 99), item)
        return f"Link - {name}"

    def get_all_model_placeholders(self):
        current = self.get_current_page_placeholders()
        inactive = []
        if self._model_document:
            inactive = [
                field_id
                for page in [*self._model_document.get("pages", []), *([self._model_document["organogram"]] if self._model_document.get("organogram") else [])]
                if page.get("page_id") != self._active_page_id
                for field_id in page.get("field_ids", [])
            ]
        required = set(current + inactive)
        preferred = (
            [self.lst_placeholders.item(i).text() for i in range(self.lst_placeholders.count())]
            if hasattr(self, "lst_placeholders") else []
        )
        return list(dict.fromkeys([
            *(value for value in preferred if value in required),
            *(value for value in current + inactive if value in required),
        ]))
    
    def add_new_box(self):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        w, h = 300, 60
        x = center.x() - (w / 2)
        y = center.y() - (h / 2)
        
        box = DesignerBox(x, y, w, h, "{campo}")
        box.keep_proportion = False
        box.custom_name = self._unique_layer_name("Texto")
        
        # Força o Z-Value para o topo do grupo de Textos
        base_z = 101
        for item in self.scene.items():
            if isinstance(item, DesignerBox) and item.zValue() >= base_z:
                base_z = int(item.zValue()) + 1
        box.setZValue(self._next_object_z())
        
        self.scene.addItem(box)
        if self._active_page_id == "organogram":
            box.setPos(box.pos())
        self.scene.clearSelection()
        box.setSelected(True)
        self.sync_placeholders_list()
        self.refresh_layer_list()
        self.save_snapshot()

    def add_guide(self, vertical, position=None):
        rect = self._get_document_rect()
        if vertical:
            pos = rect.center().x()
        else:
            pos = rect.center().y()
        guide = Guideline(pos if position is None else position, is_vertical=vertical)
        # Respeita o estado de visibilidade e bloqueio ao criar
        is_locked = self.btn_lock_guides.isChecked()
        guide.setVisible(self.btn_toggle_guides.isChecked())
        guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_locked)
        guide.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not is_locked)
        guide.setOpacity(0.4 if is_locked else 1.0)
        
        self.scene.addItem(guide)
        self.save_snapshot()

    def toggle_guides_visibility(self, checked):
        self.op_eye.setOpacity(1.0 if checked else 0.2)
        self.btn_toggle_guides.setIcon(_visibility_icon(checked))
        for item in self.scene.items():
            if isinstance(item, Guideline):
                item.setVisible(checked)
        self.save_snapshot()

    def toggle_guides_lock(self, locked):
        self.btn_lock_guides.setText("")
        self.btn_lock_guides.setIcon(themed_svg_icon(
            state_icon_path("lock" if locked else "unlock")
        ))
        self.op_lock.setOpacity(1.0 if locked else 0.2)
        for item in self.scene.items():
            if isinstance(item, Guideline):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not locked)
                # Feedback visual: reduz a opacidade quando bloqueado
                item.setOpacity(0.4 if locked else 1.0)
        self.save_snapshot()

    def clear_all_guides(self):
        # Proteção contra exclusão acidental: ignora se o cadeado estiver fechado
        if self.btn_lock_guides.isChecked():
            return

        removed = False
        for item in self.scene.items():
            if isinstance(item, Guideline):
                self.scene.removeItem(item)
                removed = True
        if removed:
            self.save_snapshot()

    def _group_root(self, item):
        if self._is_mask_image(item) and isinstance(item.parentItem(), RectangleItem):
            return item.parentItem()
        return item

    def _groupable_items(self):
        return [
            item for item in self.scene.items()
            if isinstance(item, (DesignerBox, ImageItem, SignatureItem))
            and not getattr(item, 'is_document_background', False)
            and not isinstance(item.parentItem(), RectangleItem)
        ]

    def _group_members(self, group_id):
        if group_id is None:
            return []
        return [
            item for item in self._groupable_items()
            if getattr(item, 'group_id', None) == group_id
        ]

    @contextmanager
    def _selection_batch(self):
        """Publica somente a seleção concluída, preservando bloqueios externos."""
        self._selection_batch_depth = getattr(self, '_selection_batch_depth', 0) + 1
        blocker = QSignalBlocker(self.scene)
        try:
            yield
        finally:
            self._selection_batch_depth -= 1
            blocker.unblock()
            if not self._selection_batch_depth and not self.scene.signalsBlocked():
                self.scene.selectionChanged.emit()

    def _selected_transform_roots(self, *, groupable=None):
        selected = self.scene.selectedItems()
        if not selected:
            return []
        available = set(self._groupable_items() if groupable is None else groupable)
        roots = []
        seen = set()
        for item in selected:
            if not isinstance(item, (DesignerBox, ImageItem, SignatureItem)):
                continue
            root = self._group_root(item)
            if (
                root not in seen
                and root in available
                and root.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            ):
                roots.append(root)
                seen.add(root)
        return roots

    def _ensure_selection_frame(self):
        frame = getattr(self, '_selection_frame', None)
        if frame is None or not isValid(frame):
            frame = SelectionTransformFrame(self)
            self._selection_frame = frame
            self.scene.addItem(frame)
        elif frame.scene() is None:
            self.scene.addItem(frame)
        return frame

    def _queue_selection_frame_refresh(self, *_):
        if hasattr(self, '_selection_frame_timer') and not self._selection_frame_timer.isActive():
            self._selection_frame_timer.start(0)

    def _refresh_selection_frame(self, *_, groupable=None):
        frame = self._ensure_selection_frame()
        members = self._selected_transform_roots(groupable=groupable)
        active = len(members) >= 2
        self.scene._multi_selection_active = active
        if not active:
            frame.hide()
            if len(members) == 1 and hasattr(members[0], 'resize_handles'):
                parent = members[0].parentItem()
                mask_blocks_handles = (
                    isinstance(parent, RectangleItem)
                    and not getattr(parent, '_mask_editing', False)
                )
                _set_resize_handles_visible(
                    members[0],
                    not mask_blocks_handles
                    and bool(members[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                )
            for item in members:
                item.update()
            return
        bounds = QRectF()
        for item in members:
            item.hide_resize_handles()
            rect = item.sceneBoundingRect()
            bounds = rect if bounds.isNull() else bounds.united(rect)
        frame.update_bounds(bounds)
        frame.show()
        for item in members:
            item.update()

    def _next_group_id(self):
        ids = [
            int(group_id) for item in self._groupable_items()
            if (group_id := getattr(item, 'group_id', None)) is not None
            and str(group_id).isdigit()
        ]
        ids.extend(
            int(mask_id) for item in self._mask_shapes()
            if (mask_id := getattr(item, 'mask_group_id', None)) is not None
            and str(mask_id).isdigit()
        )
        return max(ids, default=0) + 1

    def select_group(self, group_id):
        members = self._group_members(group_id)
        if not members:
            return
        with self._selection_batch():
            self.scene.clearSelection()
            self.canvas_edit.finish()
            for item in members:
                if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)

    def select_mask_group(self, shape):
        if not isinstance(shape, RectangleItem) or not shape.masked_images():
            return
        members = [shape, *shape.masked_images()]
        # No canvas apenas o pai é selecionado; selecionar os filhos também
        # deslocaria as imagens duas vezes. As camadas mostram toda a máscara.
        with self._selection_batch():
            self.scene.clearSelection()
            self.canvas_edit.finish()
            if shape.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                shape.setSelected(True)
        with QSignalBlocker(self.layer_list):
            member_set = set(members)
            for index in range(self.layer_list.count()):
                row = self.layer_list.item(index)
                row.setSelected(row.data(Qt.ItemDataRole.UserRole) in member_set)

    def group_selected_items(self):
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        roots = []
        available = set(self._groupable_items())
        seen = set()
        for item in self.scene.selectedItems():
            root = self._group_root(item)
            if root in available and root not in seen:
                roots.append(root)
                seen.add(root)
        if len(roots) < 2:
            return False
        group_id = self._next_group_id()
        for item in roots:
            item.group_id = group_id
        self.refresh_layer_list()
        self.select_group(group_id)
        self.save_snapshot()
        return True

    def ungroup_selected_items(self):
        group_ids = {
            getattr(self._group_root(item), 'group_id', None)
            for item in self.scene.selectedItems()
        }
        group_ids.discard(None)
        if not group_ids:
            return False
        members = [
            item for item in self._groupable_items()
            if getattr(item, 'group_id', None) in group_ids
        ]
        for item in members:
            item.group_id = None
        self._changing_group_selection = True
        try:
            with self._selection_batch():
                self.scene.clearSelection()
                self.canvas_edit.finish()
                for item in members:
                    if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                        item.setSelected(True)
                self.refresh_layer_list()
        finally:
            self._changing_group_selection = False
        self.save_snapshot()
        return True

    def toggle_selected_group(self):
        selected = [self._group_root(item) for item in self.scene.selectedItems()]
        group_ids = {getattr(item, 'group_id', None) for item in selected}
        group_ids.discard(None)
        if len(group_ids) == 1 and selected and all(
            getattr(item, 'group_id', None) in group_ids for item in selected
        ):
            return self.ungroup_selected_items()
        return self.group_selected_items()

    def _capture_resize_snapshots(self, members):
        snapshots = {}
        for item in members:
            rect = item.rect()
            snapshots[item] = {
                'center': item.mapToScene(item.transformOriginPoint()),
                'width': float(rect.width()),
                'height': float(rect.height()),
            }
            if isinstance(item, DesignerBox):
                snapshots[item]['text'] = {
                    'font_size': float(item.state.font_size),
                    'indent_px': float(item.state.indent_px),
                    'html': item.state.html_content,
                    'rich': item.state.rich_text_version == 1,
                }
            if isinstance(item, RectangleItem):
                snapshots[item]['shape_style'] = {
                    'outline_width': float(item.outline_width),
                    'corner_radius': float(item.corner_radius),
                    'corner_radii': dict(item.corner_radii),
                }
        return snapshots

    def _apply_resize_session_scale(self, scale):
        session = self._group_resize_session
        if not session:
            return
        scale = max(float(scale), 0.001)
        angle = session['angle']
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        anchor = session['anchor']
        for item, snapshot in session['snapshots'].items():
            if item.scene() is not self.scene:
                continue
            vector = snapshot['center'] - anchor
            local_x = vector.x() * cos_a + vector.y() * sin_a
            local_y = -vector.x() * sin_a + vector.y() * cos_a
            scaled = QPointF(local_x * scale, local_y * scale)
            desired_center = anchor + QPointF(
                scaled.x() * cos_a - scaled.y() * sin_a,
                scaled.x() * sin_a + scaled.y() * cos_a,
            )
            new_w = max(1.0, snapshot['width'] * scale)
            new_h = max(1.0, snapshot['height'] * scale)
            if isinstance(item, DesignerBox):
                item.setRect(0, 0, new_w, new_h)
                text = snapshot['text']
                item.state.font_size = max(1, round(text['font_size'] * scale))
                item.state.indent_px = text['indent_px'] * scale
                if text['rich']:
                    item.state.html_content = _scaled_rich_text_html(text['html'], scale)
                item.apply_state()
                item.update_center()
            elif hasattr(item, 'resize_custom'):
                if isinstance(item, RectangleItem):
                    style = snapshot['shape_style']
                    item.prepareGeometryChange()
                    item.outline_width = max(0.1, style['outline_width'] * scale)
                    item.corner_radius = max(0.0, style['corner_radius'] * scale)
                    item.corner_radii = {
                        key: max(0.0, float(value) * scale)
                        for key, value in style['corner_radii'].items()
                    }
                item.resize_custom(new_w, new_h)
            current_center = item.mapToScene(item.transformOriginPoint())
            delta = desired_center - current_center
            self._move_for_transform(item, delta)

    def begin_group_resize(self, leader, anchor_scene, initial_w, initial_h):
        group_id = getattr(self._group_root(leader), 'group_id', None)
        members = [
            item for item in self._group_members(group_id)
            if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        ]
        selected_roots = {self._group_root(item) for item in self.scene.selectedItems()}
        if (
            group_id is None
            or leader not in members
            or len(members) < 2
            or any(item not in selected_roots for item in members)
        ):
            self._group_resize_session = None
            return
        self._group_resize_session = {
            'leader': leader,
            'anchor': QPointF(anchor_scene),
            'initial_w': max(float(initial_w), 0.001),
            'initial_h': max(float(initial_h), 0.001),
            'angle': math.radians(float(leader.rotation())),
            'rotation': float(leader.rotation()),
            'snapshots': self._capture_resize_snapshots(members),
        }

    def update_group_resize(self, leader, width, height):
        session = self._group_resize_session
        if not session or session['leader'] is not leader:
            return
        scale_x = max(float(width), 0.001) / session['initial_w']
        scale_y = max(float(height), 0.001) / session['initial_h']
        # Um grupo é sempre escalado uniformemente. A maior variação indica a
        # dimensão conduzida pela alça lateral ou de canto.
        scale = scale_x if abs(scale_x - 1.0) >= abs(scale_y - 1.0) else scale_y
        scale = max(scale, 0.001)
        self._apply_resize_session_scale(scale)

    def end_group_resize(self):
        self._group_resize_session = None

    def begin_multi_selection_resize(self, anchor_scene, bounds):
        members = self._selected_transform_roots()
        if len(members) < 2:
            return False
        self._group_resize_session = {
            'leader': None,
            'anchor': QPointF(anchor_scene),
            'initial_w': max(float(bounds.width()), 0.001),
            'initial_h': max(float(bounds.height()), 0.001),
            'angle': 0.0,
            'rotation': 0.0,
            'snapshots': self._capture_resize_snapshots(members),
            'multi_selection': True,
        }
        return True

    def update_multi_selection_resize(self, scale):
        session = self._group_resize_session
        if not session or not session.get('multi_selection'):
            return
        self._apply_resize_session_scale(scale)
        self._refresh_selection_frame()

    def end_multi_selection_resize(self):
        session = self._group_resize_session
        if not session or not session.get('multi_selection'):
            return
        self._group_resize_session = None
        self._refresh_selection_frame()
        self.save_snapshot()

    def duplicate_selected(self):
        if self.duplicate_board_selection():
            return
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        selected_items = self.scene.selectedItems()
        if any(getattr(self._group_root(item), 'group_id', None) is not None
               for item in selected_items) or any(
            (isinstance(item, RectangleItem) and item.masked_images())
            or (self._is_mask_image(item) and isinstance(item.parentItem(), RectangleItem))
            for item in selected_items
        ):
            previous_clipboard = copy.deepcopy(self._object_clipboard)
            previous_page = self._clipboard_source_page
            try:
                self.copy_selected_items()
                self.paste_copied_items()
            finally:
                self._object_clipboard = previous_clipboard
                self._clipboard_source_page = previous_page
            return
        valid_items = [
            i for i in selected_items
            if isinstance(i, (DesignerBox, SignatureItem))
            or (isinstance(i, ImageItem) and not isinstance(i, BackgroundItem))
        ]
        
        if not valid_items: 
            return

        with self._selection_batch():
            self.scene.clearSelection()

            inserted_items = []
            for original in valid_items:
                if getattr(original, 'is_document_background', False):
                    continue
                if isinstance(original, DesignerBox):
                    rect = original.rect()
                    new_item = DesignerBox(original.x(), original.y(), rect.width(), rect.height(), "")
                    new_item.state = copy.deepcopy(original.state)
                    new_item.setRotation(original.rotation())
                    new_item.apply_state()
                    new_item.update_center()
                
                elif isinstance(original, (ImageItem, SignatureItem)):
                    if isinstance(original, RectangleItem):
                        new_item = RectangleItem(original.rect().width(), original.rect().height(), original.fill_color)
                        for key, value in original.style_data().items():
                            setattr(new_item, key, value)
                        new_item.has_link = getattr(original, 'has_link', False)
                        new_item.link_key = getattr(original, 'link_key', '')
                    elif isinstance(original, ImageItem):
                        new_item = self._create_asset_item(ImageItem, getattr(original, '_original_path', ''), self._current_model_name)
                        if new_item is None:
                            continue
                        new_item.has_link = getattr(original, 'has_link', False)
                        new_item.link_key = getattr(original, 'link_key', '')
                    else:
                        new_item = self._create_asset_item(SignatureItem, getattr(original, '_original_path', ''), self._current_model_name)
                        if new_item is None:
                            continue
                
                    rect = original.rect() if hasattr(original, 'rect') else original.pixmap().rect()
                    new_item.resize_custom(rect.width(), rect.height())
                    new_item.setRotation(original.rotation())
                    new_item.setPos(original.x(), original.y())

                new_item.setZValue(original.zValue() + 0.01)
                if self._active_page_id == "organogram":
                    new_item.board_behind = getattr(original, 'board_behind', False)
            
                # Propriedades Comuns
                new_item.layer_id = None
                new_item.keep_proportion = getattr(original, 'keep_proportion', True)
                base_name = self._generate_layer_name(getattr(original, 'layer_id', None), original)
                numbered = re.fullmatch(r'(.+?)\s+(\d+)', base_name)
                if numbered:
                    possible_base = numbered.group(1).strip()
                    existing_names = {
                        str(getattr(i, 'custom_name', '')).strip().casefold()
                        for i in self.scene.items()
                    }
                    if possible_base.casefold() in existing_names:
                        base_name = possible_base
                new_item.custom_name = self._unique_layer_name(base_name)

                inserted_items.append(new_item)
                self.scene.addItem(new_item)
                new_item.setSelected(True)

            self.refresh_layer_list()
            self.sync_placeholders_list()
            self.save_snapshot()

    def copy_selected_items(self):
        """Copia objetos como dados de página, sem duplicar os arquivos de asset."""
        if self.copy_board_selection():
            return
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        selected = self._selection_keys()
        if not selected:
            return
        state = self.get_current_scene_state()
        selected_object_ids = {
            entry.get('object_id')
            for kind, collection in (
                ('text', 'boxes'), ('image', 'images'),
                ('signature', 'signatures'), ('shape', 'shapes'),
            )
            for entry in state.get(collection, [])
            if (kind, entry.get('layer_id')) in selected
        }
        images_by_mask = {}
        for image in state.get('images', []):
            if image.get('mask_shape_id'):
                images_by_mask.setdefault(image['mask_shape_id'], []).append(image)
        expanded = set(selected_object_ids)
        for object_id in tuple(selected_object_ids):
            if object_id in images_by_mask:
                expanded.update(image['object_id'] for image in images_by_mask[object_id])
            image = next((value for value in state.get('images', [])
                          if value.get('object_id') == object_id), None)
            if image and image.get('mask_shape_id'):
                expanded.add(image['mask_shape_id'])
                expanded.update(value['object_id'] for value in images_by_mask[image['mask_shape_id']])
        candidates = {}
        for kind, collection in (
            ("text", "boxes"), ("image", "images"),
            ("signature", "signatures"), ("shape", "shapes"),
        ):
            for entry in state.get(collection, []):
                if entry.get('object_id') not in expanded:
                    continue
                if entry.get("is_document_background"):
                    continue
                candidates[entry.get("object_id")] = (kind, copy.deepcopy(entry))

        # `layer_order` está da camada inferior para a superior. Preservar essa
        # sequência evita que uma seleção mista mude sua sobreposição ao colar.
        clipboard = [
            candidates[object_id]
            for object_id in state.get("layer_order", [])
            if object_id in candidates
        ]
        copied_ids = {entry.get("object_id") for _kind, entry in clipboard}
        clipboard.extend(
            pair for object_id, pair in sorted(
                candidates.items(), key=lambda item: float(item[1][1].get("z_value", 0))
            )
            if object_id not in copied_ids
        )
        if clipboard:
            self._object_clipboard = clipboard
            self._clipboard_source_page = self._active_page_id

    def paste_copied_items(self):
        """Cola a seleção na página ativa como objetos independentes."""
        if self.paste_board_selection():
            return
        if self._active_page_id == "organogram" and any(kind == "signature" for kind, _source in self._object_clipboard):
            return
        if not self._object_clipboard:
            return
        self._finish_page_interaction()
        state = self.get_current_scene_state()
        collections = {
            "text": "boxes", "image": "images",
            "signature": "signatures", "shape": "shapes",
        }
        used_ids = {
            entry.get("layer_id")
            for collection in collections.values()
            for entry in state.get(collection, [])
            if isinstance(entry.get("layer_id"), int)
        }
        used_object_ids = {
            entry.get("object_id")
            for collection in collections.values()
            for entry in state.get(collection, [])
        }
        used_names = {
            str(entry.get("custom_name", "")).strip().casefold()
            for collection in collections.values()
            for entry in state.get(collection, [])
            if str(entry.get("custom_name", "")).strip()
        }
        next_id = 0
        max_z = max(
            (float(entry.get("z_value", 0))
             for collection in collections.values()
             for entry in state.get(collection, [])),
            default=0.0,
        )
        pasted_ids = []
        object_id_map = {}
        used_group_ids = {
            int(entry.get('group_id'))
            for collection in collections.values()
            for entry in state.get(collection, [])
            if entry.get('group_id') is not None and str(entry.get('group_id')).isdigit()
        }
        used_group_ids.update(
            int(entry.get('mask_group_id'))
            for collection in collections.values()
            for entry in state.get(collection, [])
            if entry.get('mask_group_id') is not None
            and str(entry.get('mask_group_id')).isdigit()
        )
        next_group_id = max(used_group_ids, default=0) + 1
        group_id_map = {}
        for _kind, source in self._object_clipboard:
            source_group = source.get('group_id')
            if source_group is not None and source_group not in group_id_map:
                group_id_map[source_group] = next_group_id
                next_group_id += 1
        mask_group_id_map = {}
        for _kind, source in self._object_clipboard:
            source_mask_group = source.get('mask_group_id')
            if source_mask_group is not None and source_mask_group not in mask_group_id_map:
                mask_group_id_map[source_mask_group] = next_group_id
                next_group_id += 1
        offset = 12.0 if self._clipboard_source_page == self._active_page_id else 0.0

        def free_name(raw):
            base = str(raw or "Objeto").strip() or "Objeto"
            if base.casefold() not in used_names:
                used_names.add(base.casefold())
                return base
            numbered = re.fullmatch(r"(.+?)\s+(\d+)", base)
            if numbered and numbered.group(1).strip().casefold() in used_names:
                base = numbered.group(1).strip()
            suffix = 2
            while f"{base} {suffix}".casefold() in used_names:
                suffix += 1
            result = f"{base} {suffix}"
            used_names.add(result.casefold())
            return result

        for order, (kind, source) in enumerate(self._object_clipboard, start=1):
            while next_id in used_ids:
                next_id += 1
            entry = copy.deepcopy(source)
            entry["layer_id"] = next_id
            used_ids.add(next_id)
            object_id = f"{kind}:{next_id}"
            while object_id in used_object_ids:
                object_id += "-copy"
            used_object_ids.add(object_id)
            object_id_map[source.get('object_id')] = object_id
            entry["object_id"] = object_id
            if kind == "signature":
                entry["signature_id"] = new_signature_id()
            entry["custom_name"] = free_name(entry.get("custom_name"))
            entry["z_value"] = max_z + order * 0.01
            if entry.get('group_id') is not None:
                entry['group_id'] = group_id_map[entry['group_id']]
            if entry.get('mask_group_id') is not None:
                entry['mask_group_id'] = mask_group_id_map[entry['mask_group_id']]
            old_mask_id = entry.get('mask_shape_id')
            if old_mask_id:
                entry['mask_shape_id'] = object_id_map.get(old_mask_id)
            if "x" in entry and not entry.get('mask_shape_id'):
                entry["x"] = float(entry["x"]) + offset
            if "y" in entry and not entry.get('mask_shape_id'):
                entry["y"] = float(entry["y"]) + offset
            state.setdefault(collections[kind], []).append(entry)
            state.setdefault("layer_order", []).append(object_id)
            pasted_ids.append((kind, next_id))
            next_id += 1

        from core.document_layers import upgrade_layers
        state = upgrade_layers(state)
        pasted_keys = set(pasted_ids)
        insertion = {"name": state.get("name", ""), "canvas_size": state["canvas_size"]}
        existing_z = {}
        for kind, collection in collections.items():
            insertion[collection] = []
            for entry in state.get(collection, []):
                if (kind, entry.get("layer_id")) in pasted_keys:
                    insertion[collection].append(entry)
                else:
                    existing_z[(kind, entry.get("layer_id"))] = entry["z_value"]

        with self._selection_batch():
            self.scene.clearSelection()
            previous_loading = self._loading_board
            previous_grid = self.scene._board_grid
            self._loading_board = True
            self.scene._board_grid = 0
            try:
                # A carga anterior normalizava a pilha inteira. Mantém essa ordem
                # sem reconstruir os objetos existentes nem alterar os filhos da máscara.
                for item in self.scene.items():
                    kind = ("text" if isinstance(item, DesignerBox) else
                            "signature" if isinstance(item, SignatureItem) else
                            "shape" if isinstance(item, RectangleItem) else
                            "image" if isinstance(item, ImageItem) else None)
                    z = existing_z.get((kind, getattr(item, "layer_id", None)))
                    # parentItem() em uma guia sem pai pode devolver sua posse
                    # ao Python. Não toca nos itens auxiliares ao reordenar cópias.
                    if z is not None and not isinstance(item.parentItem(), RectangleItem):
                        item.setZValue(z)
                loaded_items = self._insert_scene_items(insertion)
            finally:
                self.scene._board_grid = previous_grid
                self._loading_board = previous_loading
            self.sync_placeholders_list()
            self.refresh_layer_list()
            for item in loaded_items:
                item.setSelected(True)
            if self._active_page_id == "organogram":
                self._update_board_connections()
                self._update_board_extent(refresh_panel=False)
            self.save_snapshot()

    def select_all_items(self):
        """Seleciona todas as camadas visíveis e editáveis da página ativa."""
        with self._selection_batch():
            if self._mask_edit_session:
                self.finish_mask_edit(True)
            self.scene.clearSelection()
            self.canvas_edit.finish()
            for item in self.scene.items():
                if not isinstance(item, (DesignerBox, ImageItem, SignatureItem, RectangleItem, BoardGroupItem)):
                    continue
                if getattr(item, "is_document_background", False) or not item.isVisible():
                    continue
                if not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    continue
                item.setSelected(True)

    def delete_selected_items(self):
        if getattr(self, "_board_connection_sources", None):
            self.cancel_board_connection()
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        selected = self.scene.selectedItems()
        if not selected: return

        for item in list(selected):
            if isinstance(item, RectangleItem) and item.masked_images():
                self.remove_mask(item, record=False)
        for item in selected: 
            if getattr(item, 'is_document_background', False):
                continue
            self.scene.removeItem(item)
        if self._active_page_id == "organogram":
            self._update_board_connections()
            self._update_board_extent()
            
        self.on_selection_changed()
        self.sync_placeholders_list()
        self.refresh_layer_list()
        self.save_snapshot()

    def apply_position_x(self, val):
        sel = self.scene.selectedItems()
        if sel:
            if self._active_page_id == "organogram" and all(hasattr(i, 'rect') and not i.parentItem() for i in sel):
                bounds = QRectF()
                for item in sel:
                    bounds = bounds.united(item.mapRectToScene(item.rect()))
                self._move_board_items(sel, QPointF(mm_to_px(val) - bounds.center().x(), 0))
                return
            item = sel[0]
            delta = mm_to_px(val) - item.pos().x()
            group_id = getattr(self._group_root(item), 'group_id', None)
            targets = self._group_members(group_id) if group_id is not None else [item]
            for target in targets:
                target.moveBy(delta, 0)

    def apply_position_y(self, val):
        sel = self.scene.selectedItems()
        if sel:
            if self._active_page_id == "organogram" and all(hasattr(i, 'rect') and not i.parentItem() for i in sel):
                bounds = QRectF()
                for item in sel:
                    bounds = bounds.united(item.mapRectToScene(item.rect()))
                self._move_board_items(sel, QPointF(0, mm_to_px(val) - bounds.center().y()))
                return
            item = sel[0]
            delta = mm_to_px(val) - item.pos().y()
            group_id = getattr(self._group_root(item), 'group_id', None)
            targets = self._group_members(group_id) if group_id is not None else [item]
            for target in targets:
                target.moveBy(0, delta)

    def _move_for_transform(self, item, delta):
        previous = getattr(item, '_resizing_from_handle', False)
        item._resizing_from_handle = True
        try:
            item.moveBy(delta.x(), delta.y())
        finally:
            item._resizing_from_handle = previous

    def update_width(self, width_mm):
        item = self._get_selected()
        width_px = mm_to_px(width_mm)
        if item:
            # 1. Foto do Antes (Captura o centro absoluto na cena)
            old_center = item.mapToScene(item.transformOriginPoint())
            
            if isinstance(item, DesignerBox):
                r = item.rect()
                item.setRect(0, 0, width_px, r.height())
                item.recalculate_text_position()
                item.update_center() 
            elif isinstance(item, (ImageItem, SignatureItem)):
                h_px = mm_to_px(self.caixa_texto_panel.spin_h.value())
                item.resize_custom(width_px, h_px)
                
            # 2. Foto do Depois e Compensação (Calcula o delta e move o item de volta)
            new_center = item.mapToScene(item.transformOriginPoint())
            delta = old_center - new_center
            self._move_for_transform(item, delta)
            
            # 3. Atualiza a UI para refletir o recuo da coordenada X/Y
            self.update_position_ui()

    def update_height(self, height_mm):
        item = self._get_selected()
        height_px = mm_to_px(height_mm)
        if item:
            # 1. Foto do Antes (Captura o centro absoluto na cena)
            old_center = item.mapToScene(item.transformOriginPoint())
            
            if isinstance(item, DesignerBox):
                r = item.rect()
                item.setRect(0, 0, r.width(), height_px)
                item.recalculate_text_position()
                item.update_center()
            elif isinstance(item, (ImageItem, SignatureItem)):
                w_px = mm_to_px(self.caixa_texto_panel.spin_w.value())
                item.resize_custom(w_px, height_px)
                
            # 2. Foto do Depois e Compensação (Calcula o delta e move o item de volta)
            new_center = item.mapToScene(item.transformOriginPoint())
            delta = old_center - new_center
            self._move_for_transform(item, delta)
            
            # 3. Atualiza a UI para refletir o recuo da coordenada X/Y
            self.update_position_ui()

    def update_rotation(self, angle):
        items = self._get_selected_items()
        group_ids = {getattr(self._group_root(item), 'group_id', None) for item in items}
        group_ids.discard(None)
        if len(group_ids) == 1 and len(items) >= 2:
            leader = items[0]
            requested = -angle if getattr(leader, 'shape_type', '') == 'line' else angle
            delta_angle = requested - leader.rotation()
            bounds = QRectF()
            for item in items:
                bounds = bounds.united(item.sceneBoundingRect()) if not bounds.isNull() else item.sceneBoundingRect()
            center = bounds.center()
            radians = math.radians(delta_angle)
            cos_a, sin_a = math.cos(radians), math.sin(radians)
            for item in items:
                item_center = item.mapToScene(item.transformOriginPoint())
                vector = item_center - center
                desired_center = center + QPointF(
                    vector.x() * cos_a - vector.y() * sin_a,
                    vector.x() * sin_a + vector.y() * cos_a,
                )
                item.setRotation(item.rotation() + delta_angle)
                current_center = item.mapToScene(item.transformOriginPoint())
                movement = desired_center - current_center
                self._move_for_transform(item, movement)
            return
        for item in items:
            if hasattr(item, 'update_center'):
                item.update_center()
            item.setRotation(-angle if getattr(item, 'shape_type', '') == 'line' else angle)

    def update_proportion_lock(self, locked):
        item = self._get_selected()
        if item:
            item.keep_proportion = locked

    def update_link_state(self, has_link):
        session = self._mask_edit_session
        inspector_item = session.get('inspector_item') if session else None
        items = [inspector_item] if inspector_item is not None else self._get_selected_items()
        if items:
            for item in items:
                if isinstance(item, DesignerBox):
                    item.state.has_link = has_link
                elif isinstance(item, ImageItem):
                    item.has_link = has_link
            self.sync_placeholders_list()
            self.refresh_layer_list()

    def update_opacity(self, value):
        items = self._get_selected_items()
        for item in items:
            item.setOpacity(value)

    def update_text_html(self, html_content):
        box = self._get_selected()
        if box: 
            box.state.html_content = html_content
            box.apply_state()
    
    def update_font_family(self, font):
        if self.canvas_edit.format('family', font.family()):
            self.canvas_edit.checkpoint()
            return
        box = self._get_selected()
        if box:
            box.state.font_family = font.family()
            box.apply_state()

    def update_font_size(self, size):
        if self.canvas_edit.format('size', size):
            self.canvas_edit.checkpoint()
            return
        box = self._get_selected()
        if box:
            box.state.font_size = size
            box.apply_state()

    def update_font_color(self, color_hex):
        if self.canvas_edit.format('color', color_hex):
            self.canvas_edit.checkpoint()
            return
        box = self._get_selected()
        if box:
            box.state.font_color = color_hex
            box.apply_state()

    def update_align(self, align_str):
        box = self._get_selected()
        if box: box.set_alignment(align_str)

    def update_vertical_align(self, align_str):
        box = self._get_selected()
        if box: box.set_vertical_alignment(align_str)

    def update_indent(self, val):
        box = self._get_selected()
        if box: box.set_block_format(indent=val)

    def update_line_height(self, val):
        box = self._get_selected()
        if box: box.set_block_format(line_height=val)

    def restore_item_state(self):
        item = self._get_selected()
        if not item: return
        
        item.setRotation(0)
        
        if isinstance(item, (ImageItem, SignatureItem)):
            if hasattr(item, '_logical_w'):
                w_px = item._logical_w
                h_px = item._logical_h
                item.resize_custom(w_px, h_px)
                item.setTransformOriginPoint(w_px / 2, h_px / 2) # Corrige o pivô de giro
            self.caixa_texto_panel.load_from_image(item) # Recarrega a UI com os dados puros
            
        elif isinstance(item, DesignerBox):
            item.update_center()
            self.caixa_texto_panel.load_from_item(item)
        self.save_snapshot()

    def on_selection_changed(self):
        """Normaliza a seleção e sincroniza os painéis uma vez, no estado final."""
        if (getattr(self, '_selection_batch_depth', 0)
                or getattr(self, '_syncing_selection', False)):
            return
        try:
            sel = self.scene.selectedItems()
        except RuntimeError:
            return
        self._syncing_selection = True
        try:
            # A expansão de grupos e a prioridade das guias não devem publicar
            # seleções intermediárias nem carregar propriedades recursivamente.
            with QSignalBlocker(self.scene):
                if self.canvas_edit.box and not self.canvas_edit.box.isSelected():
                    self.canvas_edit.finish()
                if self._mask_edit_session and not self._changing_mask_selection:
                    active = self._mask_edit_session['image']
                    if set(sel) != {active}:
                        self.finish_mask_edit(True)
                        sel = self.scene.selectedItems()
                groupable = self._groupable_items() if any(
                    isinstance(item, (DesignerBox, ImageItem, SignatureItem)) for item in sel
                ) else []
                if not self._changing_group_selection and not self._selecting_from_layer_list:
                    group_ids = {
                        getattr(self._group_root(item), 'group_id', None)
                        for item in sel
                        if isinstance(item, (DesignerBox, ImageItem, SignatureItem))
                    }
                    group_ids.discard(None)
                    selected = set(sel)
                    for member in groupable:
                        if (getattr(member, 'group_id', None) in group_ids
                                and member not in selected
                                and member.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                            member.setSelected(True)
                    sel = self.scene.selectedItems()
                if any(not isinstance(item, Guideline) for item in sel):
                    for item in sel:
                        if isinstance(item, Guideline):
                            item.setSelected(False)
                    sel = self.scene.selectedItems()
            self._sync_selection_panels(sel, groupable)
        finally:
            self._syncing_selection = False

    def _sync_selection_panels(self, sel, groupable):
        boxes = [i for i in sel if isinstance(i, DesignerBox)]
        images = [i for i in sel if isinstance(i, ImageItem)]
        signatures = [i for i in sel if isinstance(i, SignatureItem)]
        valid_items = [i for i in sel if isinstance(i, (DesignerBox, ImageItem, SignatureItem))]

        if hasattr(self, 'btn_group_layer'):
            selected_groups = {getattr(self._group_root(i), 'group_id', None) for i in valid_items}
            selected_groups.discard(None)
            is_complete_group = len(selected_groups) == 1 and bool(valid_items) and all(
                getattr(self._group_root(item), 'group_id', None) in selected_groups
                for item in valid_items
            )
            self.btn_group_layer.setEnabled(len(valid_items) >= 2 or bool(selected_groups))
            self.btn_group_layer.setIcon(themed_svg_icon(action_icon_path(
                'lock ratio' if is_complete_group else 'unlock ratio'
            )))
            self.btn_group_layer.setToolTip(
                tr('Desagrupar objetos selecionados (Ctrl+Shift+G)')
                if is_complete_group else tr('Agrupar objetos selecionados (Ctrl+G)')
            )
        self._refresh_selection_frame(groupable=groupable)
        
        self.update_position_ui()

        # Sincroniza a seleção na lista de camadas (UI) — suporta múltipla seleção
        if not getattr(self, '_selecting_board_layer', False):
            self.layer_list.blockSignals(True)
            if sel:
                sel_set = set(sel)
                for i in range(self.layer_list.count()):
                    list_item = self.layer_list.item(i)
                    is_selected = list_item.data(Qt.ItemDataRole.UserRole) in sel_set
                    list_item.setSelected(is_selected)
            else:
                self.layer_list.clearSelection()
            self.layer_list.blockSignals(False)

        if len(valid_items) >= 2:
            target = valid_items[0]
            group_link_available = any(
                isinstance(i, DesignerBox)
                or (isinstance(i, ImageItem) and not isinstance(i, BackgroundItem))
                for i in valid_items
            )
            self.editor_texto_panel.setEnabled(False)
            if isinstance(target, DesignerBox):
                self.caixa_texto_panel.load_from_item(target)
            else:
                self.caixa_texto_panel.load_from_image(target)
            self.caixa_texto_panel.set_group_mode(True)
            self.caixa_texto_panel.set_link_available(group_link_available)
            self.caixa_texto_panel.setEnabled(True)
        elif boxes:
            target_box = boxes[0]
            self.editor_texto_panel.load_from_item(target_box)
            self.editor_texto_panel.setEnabled(True)
            self.caixa_texto_panel.load_from_item(target_box)
            self.caixa_texto_panel.set_group_mode(False)
            self.caixa_texto_panel.setEnabled(True)
        elif images or signatures:
            target = images[0] if images else signatures[0]
            self.editor_texto_panel.setEnabled(False)
            self.caixa_texto_panel.load_from_image(target)
            self.caixa_texto_panel.set_group_mode(False)
            self.caixa_texto_panel.setEnabled(True)
        else:
            self.editor_texto_panel.setEnabled(False)
            self.caixa_texto_panel.clear_selection_state()
            self.caixa_texto_panel.setEnabled(False)
        if self._active_page_id == "organogram" and hasattr(self, "organogram_panel"):
            self.organogram_panel.refresh(refresh_inspector=False)
        inspector = getattr(self, '_refresh_board_inspector', None)
        if inspector:
            inspector()

    _DOC_PROPORTION_OFF_BG      = "rgba(220, 53, 69, 102)"
    _DOC_PROPORTION_OFF_HOVER   = "rgba(220, 53, 69, 130)"

    def _doc_proportion_button_style(self, active: bool):
        return CaixaDeTextoPanel._proportion_button_style(active)

    def _refresh_doc_proportion_button(self):
        checked = self.chk_doc_proporcao.isChecked()
        self.chk_doc_proporcao.setIcon(themed_svg_icon(action_icon_path(
            "lock ratio" if checked else "unlock ratio"
        )))
        self.chk_doc_proporcao.setIconSize(QSize(20, 20))
        themed_style(self.chk_doc_proporcao, self._doc_proportion_button_style(checked))
        self.op_doc_proporcao.setOpacity(1.0 if checked else 0.2)

    def _on_doc_proportion_toggled(self, checked):
        self._refresh_doc_proportion_button()
        if checked:
            h = self.spin_phys_h.value()
            self._doc_aspect_ratio = self.spin_phys_w.value() / h if h > 0 else 1.0

    def _on_doc_w_changed(self, val):
        if self.chk_doc_proporcao.isChecked() and self._doc_aspect_ratio > 0:
            new_h = val / self._doc_aspect_ratio
            self.spin_phys_h.blockSignals(True)
            self.spin_phys_h.setValue(new_h)
            self.spin_phys_h.blockSignals(False)
        self._on_physical_size_changed()

    def _on_doc_h_changed(self, val):
        if self.chk_doc_proporcao.isChecked() and self._doc_aspect_ratio > 0:
            new_w = val * self._doc_aspect_ratio
            self.spin_phys_w.blockSignals(True)
            self.spin_phys_w.setValue(new_w)
            self.spin_phys_w.blockSignals(False)
        self._on_physical_size_changed()

    def _fit_background_to_doc(self):
        if not getattr(self, 'background_path', None) or not self.bg_item:
            QMessageBox.information(self, tr("Sem fundo"), tr("Nenhum arquivo de imagem de fundo carregado para ajustar."))
            return

        doc_w_px = mm_to_px(self.spin_phys_w.value())
        doc_h_px = mm_to_px(self.spin_phys_h.value())

        scale_w = doc_w_px / self.bg_item._logical_w
        scale_h = doc_h_px / self.bg_item._logical_h
        
        # Preenchimento total (cover)
        scale_cover = max(scale_w, scale_h)
        
        new_w = self.bg_item._logical_w * scale_cover
        new_h = self.bg_item._logical_h * scale_cover
        
        self.bg_item.resize_custom(new_w, new_h)
        
        # Centralizar o excedente (Bleed)
        center_x = (doc_w_px - new_w) / 2.0
        center_y = (doc_h_px - new_h) / 2.0
        self.bg_item.setPos(center_x, center_y)
        
        self.update_position_ui()
        self.save_snapshot()

    def _on_physical_size_changed(self, _=None, *, document_rect=None):
        """Redimensiona APENAS a prancheta (papel branco). A imagem de fundo agora é livre."""
        if not hasattr(self, 'scene'): return
        
        w_px = mm_to_px(self.spin_phys_w.value())
        h_px = mm_to_px(self.spin_phys_h.value())
        
        rect = QRectF(document_rect) if document_rect is not None else QRectF(0, 0, w_px, h_px)
        
        self._set_document_rect(rect)
        
        if self.fallback_bg:
            self.fallback_bg.setRect(rect)
            tile = QPixmap(16, 16)
            tile.fill(QColor(theme_color('canvas')))
            painter = QPainter(tile)
            painter.fillRect(0, 0, 8, 8, QColor(theme_color('alternate')))
            painter.fillRect(8, 8, 8, 8, QColor(theme_color('alternate')))
            painter.end()
            self.fallback_bg.setBrush(QBrush(tile))
            self.fallback_bg.show() # Garante que o papel branco esteja visível como base
        for item in self.scene.items():
            if getattr(item, 'is_document_background', False):
                item.bind_document(rect)

    def _on_click_load_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar fundo"), "", tr("Imagens (*.png *.jpg *.jpeg)"))
        if path:
            self.load_background_image(path, force_document_resize=True)


    def _on_click_add_signature(self):
        if self._active_page_id == "organogram":
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar assinatura"), "", tr("Imagens (*.png)"))
        if path:
            sig = SignatureItem(path)
            sig.custom_name = self._unique_layer_name(Path(path).stem or "Assinatura")
            center = self.view.mapToScene(self.view.viewport().rect().center())
            sig.setPos(center.x() - (sig._current_w / 2), center.y() - (sig._current_h / 2))
            
            # Força o Z-Value para o topo do grupo de Assinaturas
            base_z = 201
            for item in self.scene.items():
                if isinstance(item, SignatureItem) and item.zValue() >= base_z:
                    base_z = int(item.zValue()) + 1
            sig.setZValue(self._next_object_z())
            
            self.scene.addItem(sig) # Bug fix: a assinatura não estava sendo adicionada à cena
            self.refresh_layer_list()
            self.save_snapshot()

    def _on_click_add_image(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selecionar imagem"), "", tr("Imagens (*.png *.jpg *.jpeg)"))
        if path:
            img = ImageItem(path)
            img.custom_name = self._unique_layer_name(Path(path).stem or "Imagem")
            center = self.view.mapToScene(self.view.viewport().rect().center())
            img.setPos(center.x() - (img._current_w / 2), center.y() - (img._current_h / 2))
            
            # Trava automática no Z-Value topo da faixa de Imagens
            base_z = 1
            for item in self.scene.items():
                if isinstance(item, ImageItem) and not isinstance(item, BackgroundItem) and item.zValue() >= base_z:
                    base_z = int(item.zValue()) + 1
            img.setZValue(self._next_object_z())
            
            self.scene.addItem(img)
            self.refresh_layer_list()
            self.save_snapshot()

    def _on_content_updated(self, html):
        self.update_text_html(html)
        self.sync_placeholders_list()
        self.refresh_layer_list()

    def _on_layer_selection_changed(self):
        selected_list_items = self.layer_list.selectedItems()
        if not selected_list_items:
            return
        target_items = [
            entry.data(Qt.ItemDataRole.UserRole)
            for entry in selected_list_items
            if entry.data(Qt.ItemDataRole.UserRole) is not None
        ]
        selecting_board_layer = not target_items and any(
            entry.data(_BOARD_LAYER_ROLE) for entry in selected_list_items
        )

        if self._mask_edit_session and not self._changing_mask_selection:
            active = self._mask_edit_session['image']
            targets = set(target_items)
            if targets != {active}:
                self.finish_mask_edit(True)

        self._selecting_from_layer_list = True
        self._selecting_board_layer = selecting_board_layer
        try:
            # Os observadores recebem a seleção final, mantendo a escolha
            # parcial de grupos permitida pela lista de camadas.
            with self._selection_batch():
                self.scene.clearSelection()
                for target_item in target_items:
                    if target_item.scene() is self.scene:
                        target_item.setSelected(True)
        finally:
            self._selecting_from_layer_list = False
            self._selecting_board_layer = False

        self.view.setFocus()

    def _on_layer_item_changed(self, list_item):
        target_item = list_item.data(Qt.ItemDataRole.UserRole)
        if target_item:
            is_visible = (list_item.checkState() == Qt.CheckState.Checked)
            target_item.setVisible(is_visible)
            self.save_snapshot()

    def move_layer_group_from_badge(self, anchor_item, target_item, after=False):
        """Reposiciona as linhas selecionadas como bloco, guiadas pelo badge."""
        plan = self._layer_group_drop_plan(anchor_item, target_item, after)
        self.hide_layer_group_drop_indicator()
        if plan is None:
            return False
        rows, selected_items, reordered = plan

        previous_sync = getattr(self, '_syncing_layer_rows', False)
        self._syncing_layer_rows = True
        try:
            with QSignalBlocker(self.layer_list):
                self._order_layer_rows(reordered)
                self.layer_list.setCurrentItem(anchor_item)
                for item in reordered:
                    item.setSelected(item in selected_items)
        except LayerReconciliationError:
            # A ordem da cena ainda não mudou; recuperar a lista a partir dela.
            self.refresh_layer_list(force=True)
            return False
        finally:
            self._syncing_layer_rows = previous_sync

        self._on_layer_reordered(None, 0, 0, None, 0)
        return True

    def _layer_group_drop_plan(self, anchor_item, target_item, after=False):
        selected_items = self.layer_list.selectedItems()
        if anchor_item not in selected_items or len(selected_items) < 2:
            return None
        if target_item in selected_items:
            return None

        rows = [self.layer_list.item(index) for index in range(self.layer_list.count())]
        selected = [item for item in rows if item in selected_items]
        remaining = [item for item in rows if item not in selected_items]
        if target_item not in remaining:
            return None

        # O membro arrastado comanda o bloco. Os integrantes anteriores e
        # posteriores permanecem na mesma ordem ao redor dele.
        anchor_offset = selected.index(anchor_item)
        boundary = remaining.index(target_item) + (1 if after else 0)
        insertion = max(0, min(len(remaining), boundary - anchor_offset))
        reordered = remaining[:insertion] + selected + remaining[insertion:]
        if reordered == rows:
            return None
        return rows, selected_items, reordered

    def show_layer_group_drop_indicator(self, anchor_item, target_item, after=False):
        plan = self._layer_group_drop_plan(anchor_item, target_item, after)
        if plan is None:
            self.hide_layer_group_drop_indicator()
            return
        _rows, selected_items, reordered = plan
        first_group_row = next(item for item in reordered if item in selected_items)
        insertion = reordered.index(first_group_row)
        remaining = [item for item in _rows if item not in selected_items]
        if insertion < len(remaining):
            y = self.layer_list.visualItemRect(remaining[insertion]).top()
        elif remaining:
            y = self.layer_list.visualItemRect(remaining[-1]).bottom()
        else:
            y = 1

        viewport = self.layer_list.viewport()
        if self._layer_group_drop_indicator is None:
            indicator = QFrame(viewport)
            indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            indicator.setStyleSheet(
                f'background: {theme_color("accent")}; border: none;'
            )
            self._layer_group_drop_indicator = indicator
        self._layer_group_drop_indicator.setGeometry(
            3, max(0, y - 1), max(1, viewport.width() - 6), 3
        )
        self._layer_group_drop_indicator.raise_()
        self._layer_group_drop_indicator.show()

    def hide_layer_group_drop_indicator(self):
        if self._layer_group_drop_indicator is not None:
            self._layer_group_drop_indicator.hide()

    def _on_layer_reordered(self, parent, start, end, destination, row):
        if getattr(self, '_syncing_layer_rows', False):
            return
        count = self.layer_list.count()
        items_in_order = []
        board_row = None
        object_rows = {}
        
        for i in range(count):
            list_item = self.layer_list.item(i)
            if list_item.data(_BOARD_LAYER_ROLE):
                board_row = i
            target = list_item.data(Qt.ItemDataRole.UserRole)
            if target:
                items_in_order.append(target)
                object_rows[target] = i
                
        for shape in self._mask_shapes():
            displayed_children = [item for item in items_in_order if item.parentItem() is shape]
            for mask_order, child in enumerate(reversed(displayed_children)):
                child.mask_order = mask_order
                child.setZValue(mask_order + 1)
        objects = [
            item for item in items_in_order
            if not isinstance(item, BackgroundItem)
            and not getattr(item, 'is_document_background', False)
            and not isinstance(item.parentItem(), RectangleItem)
        ]
        for index, item in enumerate(reversed(objects)):
            if self._active_page_id == 'organogram' and board_row is not None:
                item.board_behind = object_rows[item] > board_row
            item.setZValue(index)
        
        # Redesenha forçadamente para que o item "pule" de volta para a sua seção correta caso tenha sido arrastado pra fora dela
        self.refresh_layer_list()
        if self._active_page_id == 'organogram':
            self._update_board_connections()
            self.organogram_panel.refresh()
        self.save_snapshot()

    @staticmethod
    def _is_mask_image(item):
        return (
            isinstance(item, ImageItem)
            and not isinstance(item, (RectangleItem, BackgroundItem, SignatureItem))
        )

    def _mask_shapes(self):
        return [
            item for item in self.scene.items()
            if isinstance(item, RectangleItem)
            and not getattr(item, 'is_document_background', False)
            and getattr(item, 'shape_type', '') in ('rectangle', 'ellipse', 'circle')
            and not getattr(item, 'dynamic_image_field', '')
        ]

    def _free_mask_images(self):
        return [
            item for item in self.scene.items()
            if self._is_mask_image(item) and not isinstance(item.parentItem(), RectangleItem)
        ]

    def create_mask(self, image, shape):
        """Vincula uma imagem a uma forma e abre o enquadramento não destrutivo."""
        if not self._is_mask_image(image) or shape not in self._mask_shapes():
            return False
        if isinstance(image.parentItem(), RectangleItem):
            return False
        before = self.get_current_scene_state()
        if getattr(shape, 'mask_group_id', None) is None:
            shape.mask_group_id = self._next_group_id()
        shape_center = shape.rect().center()
        # O link pertence à forma que delimita a máscara. Um segundo link na
        # imagem interna criaria regiões clicáveis concorrentes.
        image.has_link = False
        image.link_key = ''
        image.setParentItem(shape)
        image.mask_shape_id = f"shape:{shape.layer_id}"
        image.mask_order = len(shape.masked_images()) - 1
        image.setPos(
            shape_center.x() - image.rect().width() / 2,
            shape_center.y() - image.rect().height() / 2,
        )
        image.setZValue(image.mask_order + 1)
        shape.refresh_mask_structure()
        self.sync_placeholders_list()
        self.refresh_layer_list()
        self.begin_mask_edit(image, before_state=before)
        return True

    def begin_mask_edit(self, image, before_state=None):
        shape = image.parentItem() if self._is_mask_image(image) else None
        if not isinstance(shape, RectangleItem):
            return False
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        inspector_item = self._get_selected()
        if inspector_item not in (image, shape):
            inspector_item = image
        before_state = copy.deepcopy(before_state or self.get_current_scene_state())
        tracked = [shape, *shape.masked_images()]
        flags = {
            item: (
                bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable),
                item.acceptedMouseButtons(),
            )
            for item in tracked
        }
        self._mask_edit_session = {
            'image': image,
            'shape': shape,
            'before': before_state,
            'flags': flags,
            'inspector_item': inspector_item,
        }
        self._changing_mask_selection = True
        try:
            shape._mask_editing = True
            shape.refresh_mask_structure()
            for child in shape.masked_images():
                active = child is image
                child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, active)
                child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, active)
                child.setAcceptedMouseButtons(
                    Qt.MouseButton.LeftButton if active else Qt.MouseButton.NoButton
                )
            shape.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            shape.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            shape.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.clearSelection()
            image.setSelected(True)
        finally:
            self._changing_mask_selection = False
        self.shortcut_finish_mask.setEnabled(True)
        self.shortcut_cancel_mask.setEnabled(True)
        self.on_selection_changed()
        if hasattr(self, '_refresh_mask_controls'):
            self._refresh_mask_controls()
        self.scene.update()
        return True

    def finish_mask_edit(self, commit=True):
        session = self._mask_edit_session
        if not session:
            return False
        self._mask_edit_session = None
        self.shortcut_finish_mask.setEnabled(False)
        self.shortcut_cancel_mask.setEnabled(False)
        shape = session['shape']
        if shape.scene() is self.scene:
            shape._mask_editing = False
            for item, (movable, selectable, buttons) in session['flags'].items():
                if item.scene() is self.scene:
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
                    item.setAcceptedMouseButtons(buttons)
            shape.refresh_mask_structure()
        if not commit:
            selected_id = getattr(session['image'], 'layer_id', None)
            self._switching_page = True
            try:
                self.apply_scene_state(copy.deepcopy(session['before']), is_undo_redo=True)
            finally:
                self._switching_page = False
            for item in self.scene.items():
                if getattr(item, 'layer_id', None) == selected_id:
                    item.setSelected(True)
                    break
        else:
            self.save_snapshot()
        self.refresh_layer_list()
        self.on_selection_changed()
        if hasattr(self, '_refresh_mask_controls'):
            self._refresh_mask_controls()
        self.scene.update()
        return True

    def remove_mask(self, selected=None, record=True):
        selected = selected or self._get_selected()
        if selected is None:
            return False
        if self._mask_edit_session:
            self.finish_mask_edit(True)
        if self._is_mask_image(selected) and isinstance(selected.parentItem(), RectangleItem):
            shape = selected.parentItem()
            images = [selected]
            release_above = True
        elif isinstance(selected, RectangleItem):
            shape = selected
            images = shape.masked_images()
            release_above = False
        else:
            return False
        if not images:
            return False
        image_count = len(images)
        for index, image in enumerate(images):
            was_selected = image.isSelected()
            scene_origin = image.mapToScene(QPointF(0, 0))
            scene_rotation = shape.rotation() + image.rotation()
            image.setParentItem(None)
            image.mask_shape_id = None
            image.mask_order = 0
            image.setPos(scene_origin)
            image.setRotation(scene_rotation)
            if release_above:
                image.setZValue(shape.zValue() + 0.01)
            else:
                # Ao desfazer a máscara pela forma, preserva a composição logo
                # abaixo dela e mantém a ordem relativa que existia no grupo.
                image.setZValue(shape.zValue() - (image_count - index) * 0.01)
            # Enquanto pertence à máscara, a imagem deixa de receber eventos do
            # mouse para que o arraste no canvas mova a forma. Ao soltá-la, esse
            # estado precisa ser restaurado; as flags de movimento, sozinhas,
            # não fazem o item voltar a responder ao mouse.
            interactive = bool(
                image.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                and image.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            image.setAcceptedMouseButtons(
                Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
                if interactive else Qt.MouseButton.NoButton
            )
            if was_selected:
                image.setSelected(False)
                image.setSelected(True)
        for order, child in enumerate(shape.masked_images()):
            child.mask_order = order
            child.setZValue(order + 1)
        if not shape.masked_images():
            shape.mask_group_id = None
        shape.refresh_mask_structure()
        self.refresh_layer_list()
        if record:
            self.save_snapshot()
        self.on_selection_changed()
        return True

    def _next_object_z(self):
        highest = max((item.zValue() for item in self.scene.items()
                    if isinstance(item, (DesignerBox, ImageItem, SignatureItem))
                    and not isinstance(item, BackgroundItem)
                    and not isinstance(item.parentItem(), RectangleItem)), default=-1)
        return max(highest, -1) + 1 if self._active_page_id == "organogram" else highest + 1

    def _ensure_background_rectangle(self):
        rect = self._get_document_rect()
        for existing in self.scene.items():
            if getattr(existing, 'is_document_background', False):
                existing.bind_document(rect)
                return
        item = RectangleItem(rect.width(), rect.height())
        item.bind_document(rect)
        self.scene.addItem(item)
        self.refresh_layer_list()

    def rename_layer(self, list_item=None):
        """Abre a janela de renomeação e preserva a seleção após o refresh."""
        if list_item is None or isinstance(list_item, bool):
            list_item = self.layer_list.currentItem()
            
        if not list_item:
            return

        item = list_item.data(Qt.ItemDataRole.UserRole)
        if not item:
            return

        # 1. Guardar o ID da camada selecionada para recuperar depois
        selected_id = getattr(item, 'layer_id', None)

        current_name = self._generate_layer_name(selected_id, item)
        new_name, ok = dialog_get_text(
            self, tr("Renomear camada"),
            tr("Novo nome para a camada:"),
            text=current_name
        )
        
        if ok and new_name.strip():
            item.custom_name = self._unique_layer_name(new_name.strip(), exclude=item)
            
            # 2. Atualizar a lista (isso limpa a seleção)
            self.refresh_layer_list()
            
            # 3. Recuperar a seleção automaticamente
            if selected_id is not None:
                for i in range(self.layer_list.count()):
                    li = self.layer_list.item(i)
                    obj = li.data(Qt.ItemDataRole.UserRole)
                    if obj and getattr(obj, 'layer_id', None) == selected_id:
                        self.layer_list.setCurrentItem(li)
                        break
            
            self.sync_placeholders_list()
            self.save_snapshot()

    def update_position_ui(self):
        """Atualiza os campos X e Y no topo em tempo real."""
        try:
            sel = self.scene.selectedItems()
        except RuntimeError:
            return # Aborta silenciosamente se a cena já foi destruída (ao fechar o app)
            
        if not sel:
            self.spin_pos_x.setEnabled(False)
            self.spin_pos_y.setEnabled(False)
            return

        item = sel[0]
        board_items = [i for i in sel if hasattr(i, 'rect') and not isinstance(i, Guideline) and not i.parentItem()]
        if self._active_page_id == "organogram" and len(board_items) == len(sel):
            bounds = QRectF()
            for selected in board_items:
                bounds = bounds.united(selected.mapRectToScene(selected.rect()))
            with QSignalBlocker(self.spin_pos_x), QSignalBlocker(self.spin_pos_y):
                for control, value, axis in ((self.spin_pos_x, bounds.center().x(), 'X'), (self.spin_pos_y, bounds.center().y(), 'Y')):
                    control.setEnabled(True)
                    control.setValue(px_to_mm(value))
                    control.setSingleStep(px_to_mm(_board_snap_step(self.scene, board_items)))
                    control.setToolTip(tr("Centro do elemento ou da seleção — {eixo}").format(eixo=axis))
        else:
            self.spin_pos_x.setToolTip(tr("Posição X"))
            self.spin_pos_y.setToolTip(tr("Posição Y"))
            self.spin_pos_x.setSingleStep(1)
            self.spin_pos_y.setSingleStep(1)
            self.spin_pos_x.blockSignals(True)
            self.spin_pos_y.blockSignals(True)
        
            self.spin_pos_x.setEnabled(True)
            self.spin_pos_y.setEnabled(True)

            if isinstance(item, Guideline):
                if item.is_vertical:
                    self.spin_pos_x.setValue(px_to_mm(item.pos().x()))
                    self.spin_pos_y.setEnabled(False)
                else:
                    self.spin_pos_y.setValue(px_to_mm(item.pos().y()))
                    self.spin_pos_x.setEnabled(False)
            else:
                self.spin_pos_x.setValue(px_to_mm(item.pos().x()))
                self.spin_pos_y.setValue(px_to_mm(item.pos().y()))

        # Sincroniza Largura e Altura no painel
        if isinstance(item, DesignerBox):
            self.caixa_texto_panel.blockSignals(True)
            self.caixa_texto_panel.spin_w.setValue(px_to_mm(item.rect().width()))
            self.caixa_texto_panel.spin_h.setValue(px_to_mm(item.rect().height()))
            self.caixa_texto_panel.blockSignals(False)
        elif isinstance(item, (ImageItem, SignatureItem)):
            self.caixa_texto_panel.blockSignals(True)
            rect = item.rect() if hasattr(item, 'rect') else item.pixmap().rect()
            self.caixa_texto_panel.spin_w.setValue(px_to_mm(rect.width()))
            self.caixa_texto_panel.spin_h.setValue(px_to_mm(rect.height()))
            self.caixa_texto_panel.blockSignals(False)

        self.spin_pos_x.blockSignals(False)
        self.spin_pos_y.blockSignals(False)

    def sync_placeholders_list(self):
        current_vars = set(self.get_all_model_placeholders())
        existing_items_map = {} 
        for i in range(self.lst_placeholders.count()):
            existing_items_map[self.lst_placeholders.item(i).text()] = i

        for i in range(self.lst_placeholders.count() - 1, -1, -1):
            txt = self.lst_placeholders.item(i).text()
            if txt not in current_vars:
                self.lst_placeholders.takeItem(i)

        for var in sorted(list(current_vars)):
            if var not in existing_items_map:
                self.lst_placeholders.addItem(var)

    def refresh_layer_list(self, *, force=False):
        """Reconcilia as linhas vivas, sem reaproveitar objetos de outra cena."""
        self._sync_board_artwork_layers()
        current = self.layer_list.currentItem()
        current_object = getattr(current, '_layer_owner', None) if current else None
        current_board = bool(current and current.data(_BOARD_LAYER_ROLE))
        selected = self.layer_list.selectedItems()
        selected_ids = {id(row._layer_owner) for row in selected
                        if getattr(row, '_layer_owner', None) is not None}
        selected_board = any(row.data(_BOARD_LAYER_ROLE) for row in selected)
        scroll = self.layer_list.verticalScrollBar().value()
        previous_sync = getattr(self, '_syncing_layer_rows', False)
        self._syncing_layer_rows = True
        try:
            with QSignalBlocker(self.layer_list):
                try:
                    self._refresh_layer_rows(force)
                except LayerReconciliationError:
                    # Um modelo incapaz de mover as linhas usa a reconstrução
                    # completa, com callbacks ligados aos objetos atuais.
                    self._refresh_layer_rows(True)
                for index in range(self.layer_list.count()):
                    row = self.layer_list.item(index)
                    item = row.data(Qt.ItemDataRole.UserRole)
                    board = bool(row.data(_BOARD_LAYER_ROLE))
                    if (current_object is not None and item is current_object) or (current_board and board):
                        self.layer_list.setCurrentItem(row, QItemSelectionModel.SelectionFlag.NoUpdate)
                    row.setSelected(id(item) in selected_ids if item is not None else selected_board and board)
                self.layer_list.verticalScrollBar().setValue(scroll)
        finally:
            self._syncing_layer_rows = previous_sync

    def _order_layer_rows(self, rows):
        # Os sinais do modelo ficam ativos: a view precisa deles para manter
        # seus índices persistentes e widgets durante moveRows.
        model = self.layer_list.model()
        for destination, item in enumerate(rows):
            source = self.layer_list.row(item)
            if source == destination:
                continue
            insertion = destination + 1 if source < destination else destination
            if source < 0 or not model.moveRows(QModelIndex(), source, 1, QModelIndex(), insertion):
                raise LayerReconciliationError('Não foi possível reconciliar a ordem das camadas.')

    def _update_layer_row(self, row, widget, item, display_name):
        label, visible, visible_effect, locked, locked_effect = widget._layer_controls
        is_visible = item.isVisible()
        is_locked = not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        signature = (display_name, is_visible, is_locked, widget.font().key(),
                     theme_color('icon'), theme_color('disabled'), theme_color('accent'), theme_color('selection'))
        if getattr(widget, '_layer_visual_signature', None) == signature:
            return
        label.set_full_text(display_name)
        themed_style(label, 'color: @disabled@; font-style: italic;' if is_locked else '')
        if widget._layer_link_icon is not None:
            widget._layer_link_icon.setPixmap(themed_svg_icon(navigation_icon_path('layer-child')).pixmap(14, 14))
        visible.setIcon(_visibility_icon(is_visible))
        visible_effect.setOpacity(1.0 if is_visible else 0.15)
        locked.setIcon(themed_svg_icon(state_icon_path('lock' if is_locked else 'unlock')))
        locked_effect.setOpacity(1.0 if is_locked else 0.15)
        for badge in widget.findChildren(LayerGroupBadge):
            badge.setStyleSheet(
                f"QPushButton {{ border: 1px solid {theme_color('accent')}; border-radius: 5px; "
                f"padding: 0; background: transparent; color: {theme_color('accent')}; "
                "font-family: Inter; font-size: 10px; font-weight: 700; } "
                f"QPushButton:hover {{ background: {theme_color('selection')}; }}"
            )
        row.setSizeHint(QSize(widget.sizeHint().width(), max(24, widget.sizeHint().height())))
        widget._layer_visual_signature = signature

    def _refresh_layer_rows(self, force=False):
        scene_items = self.scene.items()
        scene_ids = {id(item) for item in scene_items}
        existing = [self.layer_list.item(i) for i in range(self.layer_list.count())]
        # Não converter o QVariant de um QGraphicsItem já destruído pela cena:
        # o binding pode acessar memória liberada antes mesmo de isValid().
        objects = [row._layer_owner for row in existing
                   if getattr(row, '_layer_owner', None) is not None]
        if force or (objects and not any(isValid(item) and id(item) in scene_ids for item in objects)):
            self.layer_list.clear()
            existing = []
        available = {id(row._layer_owner): row for row in existing
                     if getattr(row, '_layer_owner', None) is not None
                     and isValid(row._layer_owner)}
        board_row = next((row for row in existing if row.data(_BOARD_LAYER_ROLE)), None)
        desired = []
        
        assinaturas = []
        textos = []
        imagens = []
        fundo = None
        
        for item in scene_items:
            if isinstance(item, BackgroundItem): fundo = item
            elif isinstance(item, SignatureItem): assinaturas.append(item)
            elif isinstance(item, DesignerBox): textos.append(item)
            elif isinstance(item, ImageItem): imagens.append(item)
            
            if not hasattr(item, 'layer_id') or item.layer_id is None:
                item.layer_id = self._get_next_layer_id()

        assinaturas.sort(key=lambda x: (x.zValue(), -(x.layer_id or 0)), reverse=True)
        textos.sort(key=lambda x: (x.zValue(), -(x.layer_id or 0)), reverse=True)
        imagens.sort(key=lambda x: (x.zValue(), -(x.layer_id or 0)), reverse=True)

        def toggle_item_visibility(item, effect, button):
            if not isValid(item) or item.scene() is not self.scene:
                return
            new_vis = not item.isVisible()
            item.setVisible(new_vis)
            # Aplica opacidade 1.0 (visível) ou 0.15 (oculto)
            effect.setOpacity(1.0 if new_vis else 0.15)
            button.setIcon(_visibility_icon(new_vis))
            button.parentWidget()._layer_visual_signature = None
            self.save_snapshot()

        def toggle_item_lock(item, effect, label, button):
            if not isValid(item) or item.scene() is not self.scene:
                return
            is_locked = not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            new_locked = not is_locked
            
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not new_locked)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not new_locked)
            
            if new_locked:
                item.setSelected(False) # Força a perda de seleção imediata
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton) # Fica invisível aos cliques
                if hasattr(item, 'hide_resize_handles'):
                    item.hide_resize_handles()
            else:
                item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton) # Restaura a detecção de cliques
            if isinstance(item, RectangleItem):
                for child in item.masked_images():
                    child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not new_locked)
                    child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not new_locked)
                    child.setAcceptedMouseButtons(
                        Qt.MouseButton.NoButton if new_locked
                        else Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
                    )
                
            # Aplica opacidade 1.0 (trancado) ou 0.15 (destrancado)
            effect.setOpacity(1.0 if new_locked else 0.15)
            button.setIcon(themed_svg_icon(state_icon_path("lock" if new_locked else "unlock")))
            themed_style(label, "color: @disabled@; font-style: italic;" if new_locked else "")
            button.parentWidget()._layer_visual_signature = None
            self.save_snapshot()

        def add_header(title):
            header = QListWidgetItem(f"--- {title} ---")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setBackground(QBrush(QColor(theme_color('panel'))))
            header.setForeground(QBrush(QColor(theme_color('muted'))))
            self.layer_list.addItem(header)

        def add_items(item_list):
            for item in item_list:
                name = self._generate_layer_name(item.layer_id, item)
                display_name = tr("Plano de fundo") if getattr(item, 'is_document_background', False) else name
                is_mask_child = self._is_mask_image(item) and isinstance(item.parentItem(), RectangleItem)
                mask_shape = (item.parentItem() if is_mask_child else
                              item if isinstance(item, RectangleItem) and item.masked_images() else None)
                mask_group_id = getattr(mask_shape, 'mask_group_id', None)
                group_id = getattr(self._group_root(item), 'group_id', None)
                structure = (is_mask_child, id(mask_shape) if mask_shape is not None else None,
                             mask_group_id, group_id if not is_mask_child else None,
                             bool(getattr(item, 'is_document_background', False)))
                list_item = available.get(id(item))
                old_widget = self.layer_list.itemWidget(list_item) if list_item is not None else None
                if old_widget is not None and isValid(old_widget) and getattr(old_widget, '_layer_structure', None) == structure:
                    self._update_layer_row(list_item, old_widget, item, display_name)
                    desired.append(list_item)
                    continue
                if list_item is None:
                    list_item = QListWidgetItem()
                list_item.setData(Qt.ItemDataRole.UserRole, item)
                list_item._layer_owner = item
                
                # Removemos Qt.ItemFlag.ItemIsUserCheckable para sumir com a checkbox nativa
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled
                list_item.setFlags(flags)
                if getattr(item, 'is_document_background', False):
                    list_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                
                w = QWidget()
                ly = QHBoxLayout(w)
                ly.setContentsMargins(5, 0, 5, 0)
                ly.setSpacing(2) # Espaçamento curto entre os elementos
                
                # --- Botão Visibilidade (Olho - ESQUERDA) ---
                btn_vis = QPushButton()
                btn_vis.setIcon(_visibility_icon(item.isVisible()))
                btn_vis.setIconSize(QSize(16, 16))
                btn_vis.setFixedSize(24, 24)
                btn_vis.setStyleSheet("border: none; background: transparent; padding: 0; min-height: 0; font-size: 14px;")
                btn_vis.setToolTip(
                    tr("Exibir ou ocultar esta camada no editor e no arquivo final"))
                
                effect_vis = QGraphicsOpacityEffect()
                is_visible = item.isVisible()
                effect_vis.setOpacity(1.0 if is_visible else 0.15)
                btn_vis.setGraphicsEffect(effect_vis)
                
                btn_vis.clicked.connect(lambda checked=False, itm=item, eff=effect_vis, b=btn_vis: toggle_item_visibility(itm, eff, b))
                ly.addWidget(btn_vis)

                is_mask_child = self._is_mask_image(item) and isinstance(item.parentItem(), RectangleItem)
                if is_mask_child:
                    link_icon = QLabel()
                    link_icon.setFixedSize(16, 20)
                    link_icon.setPixmap(themed_svg_icon(
                        navigation_icon_path('layer-child')
                    ).pixmap(14, 14))
                    link_icon.setToolTip(tr('Imagem vinculada a esta máscara'))
                    ly.addWidget(link_icon)
                
                # --- Nome da Camada (CENTRO) ---
                lbl = ElidedLayerLabel(display_name)
                is_locked = not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                if is_locked:
                    themed_style(lbl, "color: @disabled@; font-style: italic;")
                ly.addWidget(lbl, 1) # Toma todo o espaço restante

                def add_group_badge(number, tooltip, callback):
                    badge = LayerGroupBadge(
                        str(number), self.layer_list, list_item, callback
                    )
                    badge.setFixedSize(20, 20)
                    badge.setToolTip(tooltip)
                    badge.setStyleSheet(
                        f"QPushButton {{ border: 1px solid {theme_color('accent')}; border-radius: 5px; "
                        f"padding: 0; background: transparent; color: {theme_color('accent')}; "
                        "font-family: Inter; font-size: 10px; font-weight: 700; } "
                        f"QPushButton:hover {{ background: {theme_color('selection')}; }}"
                    )
                    ly.addWidget(badge)

                mask_shape = (
                    item.parentItem() if is_mask_child else
                    item if isinstance(item, RectangleItem) and item.masked_images() else None
                )
                mask_group_id = getattr(mask_shape, 'mask_group_id', None)
                if mask_group_id is not None:
                    add_group_badge(
                        mask_group_id,
                        tr('Máscara {numero}').format(numero=mask_group_id),
                        lambda checked=False, shape=mask_shape: self.select_mask_group(shape)
                        if isValid(shape) and shape.scene() is self.scene else None,
                    )

                group_id = getattr(self._group_root(item), 'group_id', None)
                if group_id is not None and not is_mask_child:
                    add_group_badge(
                        group_id,
                        tr('Grupo {numero}').format(numero=group_id),
                        lambda checked=False, gid=group_id, owner=item: self.select_group(gid)
                        if isValid(owner) and owner.scene() is self.scene
                        and getattr(self._group_root(owner), 'group_id', None) == gid else None,
                    )
                
                # --- Botão Bloqueio (Cadeado - DIREITA) ---
                btn_lock = QPushButton()
                btn_lock.setIcon(themed_svg_icon(state_icon_path("lock" if is_locked else "unlock")))
                btn_lock.setIconSize(QSize(14, 14))
                btn_lock.setFixedSize(24, 24)
                if getattr(item, 'is_document_background', False):
                    btn_lock.setEnabled(False)
                btn_lock.setStyleSheet("border: none; background: transparent; padding: 0; min-height: 0; font-size: 14px;")
                btn_lock.setToolTip(
                    tr("Bloquear ou desbloquear a edição desta camada"))
                
                effect_lock = QGraphicsOpacityEffect()
                effect_lock.setOpacity(1.0 if is_locked else 0.15) # Sincroniza com sua personalização
                btn_lock.setGraphicsEffect(effect_lock)
                
                btn_lock.clicked.connect(lambda checked=False, itm=item, eff=effect_lock, l=lbl, b=btn_lock: toggle_item_lock(itm, eff, l, b))
                ly.addWidget(btn_lock)
                                
                # --- Finalização ---
                # Os controles têm 24 px; calcular antes da aplicação do tema
                # pode produzir uma sizeHint menor e recortar olho/nome/cadeado.
                list_item.setSizeHint(QSize(w.sizeHint().width(), max(24, w.sizeHint().height())))
                if self.layer_list.row(list_item) < 0:
                    self.layer_list.addItem(list_item)
                self.layer_list.setItemWidget(list_item, w)
                w._layer_link_icon = link_icon if is_mask_child else None
                w._layer_structure = structure
                w._layer_controls = (lbl, btn_vis, effect_vis, btn_lock, effect_lock)
                self._update_layer_row(list_item, w, item, display_name)
                desired.append(list_item)

        def add_board_layer():
            if board_row is not None:
                widget = self.layer_list.itemWidget(board_row)
                if widget is not None and hasattr(widget, '_layer_board_icon'):
                    widget._layer_board_icon.setPixmap(themed_svg_icon(object_icon_path('organogram')).pixmap(16, 16))
                    widget.findChildren(ElidedLayerLabel)[0].set_full_text(tr('Organograma'))
                    desired.append(board_row)
                    return
            # Referência da composição inteira; não é um objeto da Página 1.
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.AccessibleTextRole, tr("Organograma"))
            list_item.setData(_BOARD_LAYER_ROLE, True)
            list_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled |
                               Qt.ItemFlag.ItemIsDragEnabled)
            tooltip = tr("Cartões e conectores do organograma. Camadas acima aparecem à frente; camadas abaixo ficam atrás.")
            list_item.setToolTip(tooltip)
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 0, 5, 0)
            layout.setSpacing(2)
            icon = QLabel()
            icon.setFixedSize(24, 24)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setPixmap(themed_svg_icon(object_icon_path('organogram')).pixmap(16, 16))
            layout.addWidget(icon)
            layout.addWidget(ElidedLayerLabel(tr("Organograma")), 1)
            widget.setToolTip(tooltip)
            list_item.setSizeHint(QSize(widget.sizeHint().width(), max(24, widget.sizeHint().height())))
            self.layer_list.addItem(list_item)
            self.layer_list.setItemWidget(list_item, widget)
            widget._layer_board_icon = icon
            desired.append(list_item)

        objects = [
            item for item in assinaturas + textos + imagens
            if not isinstance(item.parentItem(), RectangleItem)
        ]
        board_layer_added = self._active_page_id != 'organogram'
        for item in sorted(objects, key=lambda value: (value.zValue(), -(value.layer_id or 0)), reverse=True):
            if not board_layer_added and getattr(item, 'board_behind', False):
                add_board_layer()
                board_layer_added = True
            add_items([item])
            if isinstance(item, RectangleItem):
                add_items(sorted(item.masked_images(),
                                 key=lambda child: child.mask_order,
                                 reverse=True))
        if not board_layer_added:
            add_board_layer()
        if fundo:
            # A base branca é parte do documento e nunca um objeto editável.
            fundo.setVisible(False)
            fundo.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            fundo.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            fundo.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        wanted = {id(row) for row in desired}
        for row in existing:
            if id(row) not in wanted:
                self.layer_list.removeItemWidget(row)
                self.layer_list.takeItem(self.layer_list.row(row))
                row.setData(Qt.ItemDataRole.UserRole, None)
                row._layer_owner = None
        self._order_layer_rows(desired)

    def get_current_scene_state(self) -> dict:
        """Captura uma 'foto' de tudo o que está na cena agora e retorna como um dicionário."""
        boxes_data = []
        signatures_data = []
        images_data = []
        guidelines_data = []
        
        for item in self.scene.items():
            if isinstance(item, Guideline):
                guidelines_data.append({
                    "pos": round(float(item.pos().x() if item.is_vertical else item.pos().y()), 2),
                    "vertical": item.is_vertical,
                    "visible": item.isVisible()
                })
            
            elif isinstance(item, DesignerBox):
                pos = item.pos()
                r = item.rect()
                boxes_data.append({
                    "custom_name": getattr(item, "custom_name", ""),
                    "id": item.text_item.toPlainText().replace("{", "").replace("}", "").strip(),
                    "html": item.state.html_content,
                    "rich_text_version": getattr(item.state, 'rich_text_version', 0),
                    "visible": item.isVisible(),
                    "opacity": round(float(item.opacity()), 2),
                    "locked": not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                    "x": round(float(pos.x()), 2),
                    "y": round(float(pos.y()), 2),
                    "w": round(float(r.width()), 2),
                    "h": round(float(r.height()), 2),
                    "rotation": round(float(item.rotation()), 2),
                    "font_family": item.state.font_family,
                    "font_size": item.state.font_size,
                    "font_color": getattr(item.state, 'font_color', '#000000'),
                    "has_link": getattr(item.state, 'has_link', False),
                    "link_key": self._link_key_for_item(item),
                    "align": item.state.align,
                    "vertical_align": item.state.vertical_align,
                    "indent_px": item.state.indent_px,
                    "line_height": item.state.line_height,
                    "layer_id": getattr(item, 'layer_id', None),
                    "group_id": getattr(item, 'group_id', None),
                    "keep_proportion": getattr(item, 'keep_proportion', True),
                    "z_value": round(float(item.zValue()), 2)
                })
            
            elif isinstance(item, SignatureItem):
                pos = item.pos()
                pix_rect = item.rect() if hasattr(item, 'rect') else item.pixmap().rect()
                signature_id = getattr(item, "signature_id", None) or new_signature_id()
                item.signature_id = signature_id
                signatures_data.append({
                    "signature_id": signature_id,
                    "custom_name": getattr(item, "custom_name", ""),
                    "path": getattr(item, "_original_path", ""), 
                    "visible": item.isVisible(),
                    "opacity": round(float(item.opacity()), 2),
                    "locked": not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                    "x": round(float(pos.x()), 2),
                    "y": round(float(pos.y()), 2),
                    "width": round(float(pix_rect.width()), 2),
                    "height": round(float(pix_rect.height()), 2),
                    "longest_side": round(float(max(pix_rect.width(), pix_rect.height())), 2),
                    "rotation": round(float(item.rotation()), 2),
                    "layer_id": getattr(item, 'layer_id', None),
                    "group_id": getattr(item, 'group_id', None),
                    "keep_proportion": getattr(item, 'keep_proportion', True),
                    "z_value": round(float(item.zValue()), 2)
                })

            elif isinstance(item, ImageItem) and not isinstance(item, BackgroundItem):
                pos = item.pos()
                pix_rect = item.rect() if hasattr(item, 'rect') else item.pixmap().rect()
                mask_parent = item.parentItem() if self._is_mask_image(item) else None
                images_data.append({
                    "custom_name": getattr(item, "custom_name", ""),
                    "path": getattr(item, "_original_path", ""), 
                    "visible": item.isVisible(),
                    "opacity": round(float(item.opacity()), 2),
                    "locked": not bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                    "x": round(float(pos.x()), 2),
                    "y": round(float(pos.y()), 2),
                    "width": round(float(pix_rect.width()), 2),
                    "height": round(float(pix_rect.height()), 2),
                    "longest_side": round(float(max(pix_rect.width(), pix_rect.height())), 2),
                    "rotation": round(float(item.rotation()), 2),
                    "has_link": (
                        getattr(item, "has_link", False)
                        if not isinstance(mask_parent, RectangleItem) else False
                    ),
                    "link_key": (
                        self._link_key_for_item(item)
                        if not isinstance(mask_parent, RectangleItem) else ''
                    ),
                    "layer_id": getattr(item, 'layer_id', None),
                    "group_id": getattr(item, 'group_id', None),
                    "keep_proportion": getattr(item, 'keep_proportion', True),
                    "z_value": round(float(item.zValue()), 4),
                    "mask_shape_id": (
                        f"shape:{mask_parent.layer_id}"
                        if isinstance(mask_parent, RectangleItem) else None
                    ),
                    "mask_order": int(getattr(item, 'mask_order', 0)),
                })

        ordered_placeholders = [self.lst_placeholders.item(i).text() for i in range(self.lst_placeholders.count())]
        document_rect = self._get_document_rect()

        data = {
            "name": self._current_model_name or "",
            "canvas_size": {"w": int(document_rect.width()), "h": int(document_rect.height())},
            "target_w_mm": self.spin_phys_w.value(),
            "target_h_mm": self.spin_phys_h.value(),
            "background_path": self.background_path,
            "placeholders": ordered_placeholders,
            "__page_field_ids": self.get_current_page_placeholders(),
            "__page_fields_authoritative": True,
            "signatures": signatures_data,
            "images": images_data,
            "boxes": boxes_data,
            "guidelines": guidelines_data,
            "guidelines_locked": self.btn_lock_guides.isChecked(),
            "guidelines_visible": self.btn_toggle_guides.isChecked(),
            "doc_proportion_locked": self.chk_doc_proporcao.isChecked(),
            "doc_aspect_ratio": self._doc_aspect_ratio
        }
        
        if self.bg_item and isinstance(self.bg_item, BackgroundItem):
            bg_rect = self.bg_item.rect() if hasattr(self.bg_item, 'rect') else self.bg_item.pixmap().rect()
            data["bg_props"] = {
                "custom_name": getattr(self.bg_item, "custom_name", ""),
                "x": round(float(self.bg_item.pos().x()), 2),
                "y": round(float(self.bg_item.pos().y()), 2),
                "w": round(float(bg_rect.width()), 2),
                "h": round(float(bg_rect.height()), 2),
                "visible": self.bg_item.isVisible(),
                "opacity": round(float(self.bg_item.opacity()), 2),
                "locked": not bool(self.bg_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),
                "layer_id": getattr(self.bg_item, 'layer_id', None),
                "keep_proportion": getattr(self.bg_item, 'keep_proportion', True),
                "z_value": round(float(self.bg_item.zValue()), 2)
            }
            
        shapes = []
        for item in self.scene.items():
            if isinstance(item, RectangleItem):
                entry = next(entry for entry in data['images'] if entry['layer_id'] == item.layer_id)
                data['images'].remove(entry)
                entry.pop('path', None)
                entry.update(item.style_data())
                entry['is_document_background'] = getattr(item, 'is_document_background', False)
                entry['mask_group_id'] = getattr(item, 'mask_group_id', None)
                shapes.append(entry)
        data['shapes'] = shapes
        data['editable_background_initialized'] = True
        data['background_path'] = None
        data.pop('bg_props', None)
        entries = []
        live_items = {getattr(item, 'layer_id', None): item for item in self.scene.items()
                      if isinstance(item, (DesignerBox, ImageItem, SignatureItem))}
        for kind, group in [('text', 'boxes'), ('image', 'images'), ('signature', 'signatures'), ('shape', 'shapes')]:
            for index, entry in enumerate(data[group]):
                entry['object_id'] = f"{kind}:{entry.get('layer_id', index)}"
                if self._active_page_id == "organogram":
                    item = live_items.get(entry.get('layer_id'))
                    if item is not None:
                        root = item.parentItem() if isinstance(item.parentItem(), RectangleItem) else item
                        entry['board_behind'] = getattr(root, 'board_behind', False)
                        entry['z_value'] = item.zValue()
                entries.append(entry)
        by_mask = {}
        for entry in data['images']:
            if entry.get('mask_shape_id'):
                by_mask.setdefault(entry['mask_shape_id'], []).append(entry)
        masked_ids = {entry['object_id'] for values in by_mask.values() for entry in values}
        roots = [entry for entry in entries if entry['object_id'] not in masked_ids]
        order = []
        for entry in sorted(roots, key=lambda value: value['z_value']):
            order.append(entry['object_id'])
            children = sorted(by_mask.get(entry['object_id'], []),
                              key=lambda value: value.get('mask_order', 0))
            order.extend(child['object_id'] for child in children)
        data['layer_order'] = order
        return self._append_board_state(data)

    def _create_asset_item(self, item_class, raw_path, model_name=""):
        """Usa o mesmo provedor autorizado e proxy em cargas e inserções."""
        asset_data = self._authorized_asset_bytes(raw_path)
        path = Path(raw_path)
        if asset_data is None and not path.is_absolute():
            model_dir = getattr(self, '_current_model_dir', None)
            if model_dir and (Path(model_dir) / path).is_file():
                path = Path(model_dir) / path
            else:
                path = get_models_dir() / slugify_model_name(model_name) / path
        if asset_data is None and not path.exists():
            return None
        return item_class(
            str(path) if asset_data is None else None,
            pixmap_data=asset_data, asset_reference=raw_path if asset_data is not None else None,
            loaded_proxy=self._visual_cache.proxy(str(path), data=asset_data),
        )

    def _insert_scene_items(self, data, *, include_guides=False):
        """Constrói apenas os itens recebidos; conserva os wrappers até publicar camadas.

        A página completa e a colagem usam a mesma restauração de propriedades e
        máscaras. Relações são aplicadas após construir todos os novos objetos.
        """
        loaded_items = []
        canvas_w = data.get("canvas_size", {}).get("w", 1000)
        canvas_h = data.get("canvas_size", {}).get("h", 1000)
        # Assinaturas
        for sig_data in data.get("signatures", []):
            sig = self._create_asset_item(SignatureItem, sig_data["path"], data.get("name", ""))
            if sig is not None:
                loaded_items.append(sig)
                sig.signature_id = sig_data.get("signature_id") or sig.signature_id
                sig.custom_name = sig_data.get("custom_name", "")
                sig.layer_id = sig_data.get("layer_id")
                sig.group_id = sig_data.get("group_id")
                sig.setPos(sig_data["x"], sig_data["y"])
                if "width" in sig_data and "height" in sig_data:
                    sig.resize_custom(sig_data["width"], sig_data["height"])
                else:
                    sig.resize_by_longest_side(sig_data.get("longest_side", 100))
                sig.setRotation(sig_data.get("rotation", 0))
                self.scene.addItem(sig)
                sig.keep_proportion = sig_data.get("keep_proportion", True)
                sig.setZValue(sig_data.get("z_value", 201))
                sig.setVisible(sig_data.get("visible", True))
                sig.setOpacity(sig_data.get("opacity", 1.0))
                if sig_data.get("locked", False):
                    sig.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                    sig.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                    sig.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        # Imagens
        for img_data in data.get("images", []):
            img = self._create_asset_item(ImageItem, img_data["path"], data.get("name", ""))
            if img is not None:
                loaded_items.append(img)
                img.custom_name = img_data.get("custom_name", "")
                img.layer_id = img_data.get("layer_id")
                if self._active_page_id == "organogram":
                    img.board_behind = img_data.get("board_behind", False)
                img.group_id = img_data.get("group_id")
                img.setPos(img_data.get("x", 0), img_data.get("y", 0))
                
                if "width" in img_data and "height" in img_data:
                    img.resize_custom(img_data["width"], img_data["height"])
                else:
                    img.resize_by_longest_side(img_data.get("longest_side", 100))
                    
                img.setRotation(img_data.get("rotation", 0))
                self.scene.addItem(img)
                img.keep_proportion = img_data.get("keep_proportion", True)
                img.setZValue(img_data.get("z_value", 1))
                img.has_link = img_data.get("has_link", False)
                img.link_key = str(img_data.get("link_key") or "").strip()
                img.mask_shape_id = img_data.get("mask_shape_id")
                img.mask_order = int(img_data.get("mask_order", 0))
                img.setVisible(img_data.get("visible", True))
                img.setOpacity(img_data.get("opacity", 1.0))
                if img_data.get("locked", False):
                    img.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                    img.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                    img.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        # Caixas de Texto
        for b in data.get("boxes", []):
            box = DesignerBox(
                x=b.get("x", 0), 
                y=b.get("y", 0), 
                w=b.get("w", 300), 
                h=b.get("h", 60), 
                text=b.get("id", "Placeholder") 
            )
            loaded_items.append(box)
            box.custom_name = b.get("custom_name", "")
            box.state.rich_text_version = b.get('rich_text_version', 0)
            box.layer_id = b.get("layer_id")
            if self._active_page_id == "organogram":
                box.board_behind = b.get("board_behind", False)
            box.group_id = b.get("group_id")
            
            if "html" in b:
                box.state.html_content = b["html"]
                
            # Qt may render with a local fallback, but the saved family belongs
            # to the document and must survive copying/reopening on another PC.
            box.state.font_family = (
                str(b.get("font_family") or DOCUMENT_FONT_FAMILY).strip()
                or DOCUMENT_FONT_FAMILY
            )
            box.state.font_size = b.get("font_size", 16)
            box.state.font_color = b.get("font_color", "#000000")
            box.state.vertical_align = b.get("vertical_align", "top")
            box.state.align = b.get("align", "left")
            box.state.indent_px = b.get("indent_px", 0)
            box.state.line_height = b.get("line_height", 1.15)
            box.state.has_link = b.get("has_link", False)
            box.state.link_key = str(b.get("link_key") or "").strip()

            box.setRotation(b.get("rotation", 0))
            box.apply_state()
            box.keep_proportion = b.get("keep_proportion", True)
            box.update_center() 

            self.scene.addItem(box)
            box.setZValue(b.get("z_value", 101))
            box.setVisible(b.get("visible", True))
            box.setOpacity(b.get("opacity", 1.0))
            if b.get("locked", False):
                box.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                box.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                box.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                if hasattr(box, 'hide_resize_handles'):
                    box.hide_resize_handles()
        if include_guides:
            for g in data.get("guidelines", []):
                guide = Guideline(g["pos"], is_vertical=g.get("vertical", True))
                loaded_items.append(guide)
                guide.setVisible(g.get("visible", True))
                self.scene.addItem(guide)

        from core.object_style import normalize_line_body
        for entry in data.get('shapes', []):
            entry = normalize_line_body(entry)
            item = RectangleItem(entry.get('width', canvas_w), entry.get('height', canvas_h), entry.get('fill_color', '#ffffff'))
            loaded_items.append(item)
            for key in item.style_data():
                if key in entry:
                    setattr(item, key, entry[key])
            item.has_link = entry.get('has_link', False)
            item.link_key = str(entry.get('link_key') or '').strip()
            if 'corner_radii' not in entry:
                radius = max(0.0, float(entry.get('corner_radius', 0)))
                item.corner_radii = {key: radius for key in (
                    'top_left', 'top_right', 'bottom_right', 'bottom_left')}
            item.layer_id = entry.get('layer_id')
            if self._active_page_id == "organogram":
                item.board_behind = entry.get('board_behind', False)
            item.group_id = entry.get('group_id')
            item.mask_group_id = entry.get('mask_group_id')
            item.dynamic_image_field = str(entry.get('dynamic_image_field') or '').strip()
            item.dynamic_image_fit = entry.get('dynamic_image_fit', 'cover')
            item.custom_name = entry.get('custom_name', 'Plano de fundo')
            item.setPos(entry.get('x', 0), entry.get('y', 0))
            item.setRotation(entry.get('rotation', 0))
            item.setZValue(entry.get('z_value', -1))
            item.setOpacity(entry.get('opacity', 1))
            item.setVisible(entry.get('visible', True))
            item.keep_proportion = entry.get('keep_proportion', False)
            if entry.get('locked', False):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(item)
            if (entry.get('is_document_background') or
                    ('is_document_background' not in entry and entry.get('custom_name') == 'Plano de fundo')):
                if not any(getattr(other, 'is_document_background', False) for other in self.scene.items() if other is not item):
                    item.bind_document(self._get_document_rect())
        inserted_items = set(loaded_items)
        shapes_by_id = {
            f"shape:{item.layer_id}": item
            for item in self.scene.items()
            if item in inserted_items and isinstance(item, RectangleItem)
        }
        for image in [item for item in self.scene.items() if item in inserted_items and self._is_mask_image(item)]:
            shape = shapes_by_id.get(getattr(image, 'mask_shape_id', None))
            if shape is None:
                image.mask_shape_id = None
                continue
            stored_pos = QPointF(image.pos())
            image.setParentItem(shape)
            image.has_link = False
            image.link_key = ''
            image.setPos(stored_pos)
            image.setZValue(image.mask_order + 1)
        for shape in shapes_by_id.values():
            if shape.masked_images() and getattr(shape, 'mask_group_id', None) is None:
                shape.mask_group_id = self._next_group_id()
            shape.refresh_mask_structure()
        return loaded_items

    def apply_scene_state(self, data: dict, is_undo_redo: bool = False):
        """Limpa a cena e recria tudo com base no dicionário fornecido."""
        self._clear_page_scenes()
        self._history_capture_cache = None
        # Salva qual layer estava selecionada antes de limpar
        # Identifica o fundo atual antes de limpar a cena
        self._loading_board = True
        if getattr(self, "_board_connection_sources", None):
            self.cancel_board_connection()
        self.scene._board_grid = 0
        from core.document_layers import upgrade_layers
        data = upgrade_layers(data)
        # Arquivos abertos pelo inicializador podem estar fora da biblioteca.
        model_dir = getattr(self, '_current_model_dir', None)
        if model_dir:
            for group in ('images', 'signatures'):
                for entry in data.get(group, []):
                    asset = Path(entry.get('path', ''))
                    if not asset.is_absolute() and (Path(model_dir) / asset).is_file():
                        entry['path'] = str(Path(model_dir) / asset)
        old_bg = self.background_path
        selected_layer_ids = set()
        if not getattr(self, '_switching_page', False):
            sel = self.scene.selectedItems()
            for s in sel:
                if isinstance(s, (DesignerBox, ImageItem, SignatureItem)) and getattr(s, 'layer_id', None) is not None:
                    selected_layer_ids.add(s.layer_id)

        self.scene.clearSelection()
        # Libera a referência ao papel antes de substituir a cena.
        self.fallback_bg = None
        self.scene.clear()
        self.bg_item = None
        # Guarda referências às subclasses Python até concluir a reconstrução.
        # Ao restaurar máscaras, chamadas do Qt podem liberar wrappers de itens
        # que ainda não foram registrados na lista de camadas.
        loaded_items = []

        canvas_w = data.get("canvas_size", {}).get("w", 1000)
        canvas_h = data.get("canvas_size", {}).get("h", 1000)
        self._set_document_rect(QRectF(0, 0, canvas_w, canvas_h))

        # Sincroniza os valores de milímetros na UI (Sempre ocorre, mesmo no Undo/Redo)
        self.spin_phys_w.blockSignals(True)
        self.spin_phys_h.blockSignals(True)
        for control in (self.spin_phys_w, self.spin_phys_h):
            control.setRange(0.1, 50000) if self._active_page_id == "organogram" else control.setRange(10, 1000)
        self.spin_phys_w.setValue(data.get("target_w_mm", 100.0))
        self.spin_phys_h.setValue(data.get("target_h_mm", 150.0))
        self.spin_phys_w.blockSignals(False)
        self.spin_phys_h.blockSignals(False)

        proportion_locked = data.get("doc_proportion_locked", False)
        self.chk_doc_proporcao.blockSignals(True)
        self.chk_doc_proporcao.setChecked(proportion_locked)
        self.chk_doc_proporcao.blockSignals(False)
        self._doc_aspect_ratio = data.get("doc_aspect_ratio", self._doc_aspect_ratio)
        self._refresh_doc_proportion_button()

        self.fallback_bg = create_canvas_paper(self.scene, QRectF(0, 0, canvas_w, canvas_h))

        # Atualiza as labels informativas e o rect de fundo
        self._on_physical_size_changed(document_rect=QRectF(0, 0, canvas_w, canvas_h))

        # Fundo
        bg_path_raw = data.get("background_path")
        if bg_path_raw:
            asset_data = self._authorized_asset_bytes(bg_path_raw)
            bg_path = Path(bg_path_raw)
            if asset_data is not None:
                self.load_background_image(
                    None, update_ui=not is_undo_redo, props=data.get("bg_props"),
                    asset_data=asset_data, asset_reference=bg_path_raw,
                )
                if self.bg_item and "bg_props" in data:
                    self.bg_item.setZValue(data["bg_props"].get("z_value", -100))
            else:
                # Tenta resolver o caminho se não for absoluto (procura no próprio modelo)
                if not bg_path.is_absolute():
                    slug = slugify_model_name(data.get("name", ""))
                    bg_path = get_models_dir() / slug / bg_path_raw
            if asset_data is None and bg_path.exists():
                self.load_background_image(str(bg_path), update_ui=not is_undo_redo, props=data.get("bg_props"))
                if self.bg_item and "bg_props" in data:
                    self.bg_item.setZValue(data["bg_props"].get("z_value", -100))
            elif asset_data is None:
                self.load_background_image(None, update_ui=not is_undo_redo, props=data.get("bg_props"))
        else:
            self.load_background_image(None, update_ui=not is_undo_redo, props=data.get("bg_props"))

        if self.bg_item and "bg_props" in data:
            self.bg_item.custom_name = data["bg_props"].get("custom_name", "")
            self.bg_item.layer_id = data["bg_props"].get("layer_id")
            self.bg_item.setZValue(data["bg_props"].get("z_value", -100))

        loaded_items = self._insert_scene_items(data, include_guides=True)
        # Linhas Guia
        guides_data = data.get("guidelines", [])
        # Sincroniza o estado global de visibilidade das guias (independente de haver guias na lista)
        if "guidelines_visible" in data:
            is_visible = data.get("guidelines_visible", True)
        elif guides_data:
            is_visible = guides_data[0].get("visible", True)
        else:
            is_visible = True
        self.btn_toggle_guides.blockSignals(True)
        self.btn_toggle_guides.setChecked(is_visible)
        self.btn_toggle_guides.setIcon(_visibility_icon(is_visible))
        self.op_eye.setOpacity(1.0 if is_visible else 0.2)
        self.btn_toggle_guides.blockSignals(False)

        # Restaura o estado do cadeado das guias
        is_locked = data.get("guidelines_locked", False)
        self.btn_lock_guides.blockSignals(True)
        self.btn_lock_guides.setChecked(is_locked)
        self.btn_lock_guides.setIcon(themed_svg_icon(
            state_icon_path("lock" if is_locked else "unlock")
        ))
        self.btn_lock_guides.setText("")
        self.op_lock.setOpacity(1.0 if is_locked else 0.2)
        self.btn_lock_guides.blockSignals(False)

        # Reaplica visibilidade e bloqueio globais nos itens recém-criados.
        for item in self.scene.items():
            if isinstance(item, Guideline):
                item.setVisible(is_visible)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_locked)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not is_locked)
                item.setOpacity(0.4 if is_locked else 1.0)

        if self._active_page_id != "organogram":
            self._ensure_background_rectangle()
        self._load_board_items(data)

        # Atualiza Placeholders e Lista de Camadas
        saved_placeholders = data.get("placeholders", [])
        self.lst_placeholders.clear()
        for p in saved_placeholders:
            self.lst_placeholders.addItem(p)
        # Retrocompatibilidade: garante layer_id em itens de modelos antigos
        for item in self.scene.items():
            if hasattr(item, 'layer_id') and item.layer_id is None:
                item.layer_id = self._get_next_layer_id()
        self.sync_placeholders_list()
        self.refresh_layer_list()

        # Restaura a seleção múltipla dos itens que estavam ativos
        if selected_layer_ids:
            for item in self.scene.items():
                if (
                    isinstance(item, (DesignerBox, ImageItem, SignatureItem))
                    and getattr(item, 'layer_id', None) in selected_layer_ids
                ):
                    item.setSelected(True)

        # Se for um Undo/Redo e o fundo mudou, reaplica o enquadramento (Zoom to Fit)
        if is_undo_redo and old_bg != data.get("background_path"):
            self._zoom_to_fit()
        self._loading_board = False
        self.refresh_board_context()
        self._active_page_dependencies = self._page_dependencies(self._active_page_id, data)

    def _history_capture_token(self):
        if self.history._current_index < 0 or self._active_scene_baseline is None:
            return None
        current = self.history._undo_stack[self.history._current_index]
        if not current.get("__document_history__") or self._model_document is None:
            return None
        # Inclui páginas inativas e mudanças globais feitas sem sinais Qt.
        if self._model_document != current.get("document"):
            return None
        return (id(current), id(current["document"]), id(self._model_document),
                self.history._current_index, self._active_page_id)

    def _history_snapshot_is_current(self):
        token = self._history_capture_token()
        cached = self._history_capture_cache
        if token is None or cached is None or cached[0] != token:
            return False
        inputs = history_inputs(self)
        return inputs is not None and inputs == cached[1]

    def _remember_history_inputs(self):
        token = self._history_capture_token()
        inputs = history_inputs(self) if token is not None else None
        self._history_capture_cache = (token, inputs) if inputs is not None else None

    def save_snapshot(self):
        """Dispara um salvamento na memória (chamado ao soltar o mouse ou terminar uma edição)."""
        if getattr(self, '_restoring_history', False) or self._mask_edit_session or self._loading_board:
            return
        if self._active_page_id == "organogram":
            self._update_board_extent(refresh_panel=False)
        if self._history_snapshot_is_current():
            if hasattr(self, "_pending_history_page_id"):
                del self._pending_history_page_id
            return
        state = self._capture_document_history_state()
        if self.history._current_index >= 0:
            current = self.history._undo_stack[self.history._current_index]
            if (
                current.get("__document_history__")
                and current.get("document") == state.get("document")
            ):
                self._remember_history_inputs()
                if hasattr(self, "_pending_history_page_id"):
                    del self._pending_history_page_id
                return
        self.history.push(state)
        self._remember_history_inputs()
        if hasattr(self, "_pending_history_page_id"):
            del self._pending_history_page_id

    def undo(self):
        self._finish_page_interaction()
        # Controles numéricos podem ter aplicado um valor sem perder o foco.
        # Registra essa edição para que o redo consiga recuperá-la.
        self.save_snapshot()
        current = None
        if self.history._current_index >= 0:
            current = self.history._undo_stack[self.history._current_index]
        state = self.history.undo()
        if state:
            preferred = current.get("__action_page_id") if current else None
            self._restore_history_state(state, preferred_page=preferred)

    def redo(self):
        self._finish_page_interaction()
        # Uma nova edição após undo invalida o futuro, mesmo antes do blur.
        self.save_snapshot()
        state = self.history.redo()
        if state:
            self._restore_history_state(state, preferred_page=state.get("__action_page_id"))

    def _restore_history_state(self, state, preferred_page=None):
        sections = getattr(self, '_inspector_sections', {})
        inspector_state = {
            name: section.header.isChecked()
            for name, section in sections.items()
        }
        self._restoring_history = True
        scene_blocker = QSignalBlocker(self.scene)
        updates_enabled = self.view.updatesEnabled()
        self.view.setUpdatesEnabled(False)
        try:
            if state.get("__document_history__"):
                self._page_selection[self._active_page_id] = self._selection_keys()
                self._model_document = copy.deepcopy(state["document"])
                requested_page = preferred_page or state.get("__active_page_id", self._active_page_id)
                available = {page["page_id"] for page in self._model_document["pages"]}
                if self._model_document.get("organogram") is not None:
                    available.add("organogram")
                self._active_page_id = requested_page if requested_page in available else "front"
                self._switching_page = True
                try:
                    page = adapt_model_page(self._model_document, self._active_page_id)
                    self.apply_scene_state(prepare_scene_page(page), is_undo_redo=True)
                finally:
                    self._switching_page = False
                self._active_scene_baseline = self.get_current_scene_state()
                self._restore_page_selection()
                self._refresh_page_controls()
            else:
                self.apply_scene_state(state, is_undo_redo=True)
        finally:
            self._restoring_history = False
            scene_blocker.unblock()
            self.view.setUpdatesEnabled(updates_enabled)
        # Nenhum painel deve observar uma cena ou seleção parcialmente montada.
        self.scene.selectionChanged.emit()
        if self._active_page_id != 'organogram' and hasattr(self, 'organogram_panel'):
            self.organogram_panel.refresh()
        restore_inspector = getattr(self, '_restore_inspector_state', None)
        if restore_inspector:
            restore_inspector(inspector_state)
        self._remember_history_inputs()

    def _get_selected(self):
        valid_items = self._get_selected_items()
        return valid_items[0] if valid_items else None

    def _get_selected_items(self):
        sel = self.scene.selectedItems()
        return [i for i in sel if isinstance(i, (DesignerBox, ImageItem, SignatureItem))]

    def _enter_space_pan_mode(self):
        if self.view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            return

        self._finish_canvas_pointer_interaction()

        self._space_pan_items = []
        for item in self.scene.items():
            buttons = item.acceptedMouseButtons()
            if buttons != Qt.MouseButton.NoButton:
                self._space_pan_items.append((item, buttons))
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def _leave_space_pan_mode(self):
        self.view.release_pointer()
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        for item, buttons in getattr(self, "_space_pan_items", []):
            try:
                item.setAcceptedMouseButtons(buttons)
            except RuntimeError:
                pass
        self._space_pan_items = []

    def _get_document_rect(self):
        return QRectF(getattr(self, "_document_rect", self.scene.sceneRect()))

    def _set_document_rect(self, rect):
        self._document_rect = QRectF(rect)
        self.scene._document_rect = QRectF(self._document_rect)
        self._update_workspace_scene_rect()

    def _get_content_rect(self):
        total_rect = self._get_document_rect()
        for item in self.scene.items():
            # Ignora as linhas guia infinitas e o papel branco de fallback
            if (isinstance(item, Guideline)
                    or item == getattr(self, 'fallback_bg', None)
                    or getattr(item, '_is_selection_overlay', False)):
                continue
            total_rect = total_rect.united(item.sceneBoundingRect())
        return total_rect

    def _workspace_scene_rect(self):
        total_rect = self._get_content_rect()
        
        if total_rect.isEmpty() or not hasattr(self, "view"):
            return total_rect

        zoom = max(0.001, self.view.transform().m11())
        viewport_size = self.view.viewport().size()
        
        # Mantém uma margem de segurança baseada no tamanho da tela
        margin_x = max(100.0, (viewport_size.width() / zoom) * 0.5)
        margin_y = max(100.0, (viewport_size.height() / zoom) * 0.5)
        
        return total_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)

    def _update_workspace_scene_rect(self):
        if not hasattr(self, "scene") or not hasattr(self, "view"):
            return
        workspace_rect = self._workspace_scene_rect()
        if workspace_rect.isEmpty():
            return
        self.scene.setSceneRect(workspace_rect)
        self.view.setSceneRect(workspace_rect)

    def _zoom_to_fit(self):
        total_rect = self._get_content_rect()
        
        if not total_rect.isEmpty():
            margin = 50
            view_rect = total_rect.adjusted(-margin, -margin, margin, margin)
            self.view.fitInView(view_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self._update_workspace_scene_rect()

    def _apply_zoom(self, zoom_factor):
        """Aplica zoom respeitando os limites mínimo dinâmico e máximo fixo."""
        current_scale = self.view.transform().m11()
        new_scale = current_scale * zoom_factor

        # Limite máximo: 1000% (escala 10.0x)
        MAX_SCALE = 10.0

        # Limite mínimo dinâmico: a área total (doc + itens) deve ser visível
        total_rect = self._get_content_rect()
        
        viewport = self.view.viewport().size()
        if not total_rect.isEmpty() and viewport.width() > 0 and viewport.height() > 0:
            # Garante que mesmo o item mais longe ainda possa ser visto no menor zoom
            min_scale_w = (viewport.width() * 0.5) / total_rect.width()
            min_scale_h = (viewport.height() * 0.5) / total_rect.height()
            MIN_SCALE = min(min_scale_w, min_scale_h)
        else:
            MIN_SCALE = 0.01

        new_scale = max(MIN_SCALE, min(MAX_SCALE, new_scale))

        if abs(new_scale - current_scale) < 1e-9:
            return

        corrected_factor = new_scale / current_scale
        self.view.scale(corrected_factor, corrected_factor)
        self._update_workspace_scene_rect()

    def _import_asset(self, source_path: str, model_dir: Path) -> str | None:
        if not source_path: 
            return None
        
        src = Path(source_path)
        if not src.exists():
            existing_asset = model_dir / "assets" / src.name
            if existing_asset.exists():
                return f"assets/{src.name}"
            return None
            
        if "assets" in src.parts and model_dir in src.parents:
            return f"assets/{src.name}"

        assets_dir = model_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        dest = assets_dir / src.name
        
        try:
            shutil.copy2(src, dest)
            return f"assets/{src.name}"
        except Exception as e:
            print(f"Erro ao copiar asset: {e}")
            if dest.exists():
                return f"assets/{src.name}"
            return source_path 
    
    def _get_next_layer_id(self):
        used = set()
        for item in self.scene.items():
            if hasattr(item, 'layer_id') and item.layer_id is not None:
                used.add(item.layer_id)
        i = 0
        while i in used:
            i += 1
        return i

    def _unique_layer_name(self, base_name, exclude=None):
        """Retorna um nome de exibição livre, sem usar o ID interno da camada."""
        base = str(base_name or "Objeto").strip() or "Objeto"
        used = {
            str(getattr(item, 'custom_name', '')).strip().casefold()
            for item in self.scene.items()
            if item is not exclude and str(getattr(item, 'custom_name', '')).strip()
        }
        if base.casefold() not in used:
            return base
        suffix = 2
        while f"{base} {suffix}".casefold() in used:
            suffix += 1
        return f"{base} {suffix}"

    def _default_layer_name(self, item):
        if getattr(item, 'is_document_background', False) or isinstance(item, BackgroundItem):
            return "Plano de fundo"
        if isinstance(item, DesignerBox):
            return "Texto"
        if isinstance(item, RectangleItem):
            return {
                'rectangle': 'Quadrado',
                'ellipse': 'Círculo',
                'circle': 'Círculo',
                'line': 'Linha',
            }.get(getattr(item, 'shape_type', 'rectangle'), 'Forma')
        if isinstance(item, (SignatureItem, ImageItem)):
            path_name = Path(getattr(item, '_original_path', '') or '').stem.strip()
            return path_name or ('Assinatura' if isinstance(item, SignatureItem) else 'Imagem')
        return "Objeto"

    def _generate_layer_name(self, layer_id, item):
        if hasattr(item, 'custom_name') and item.custom_name:
            return item.custom_name

        if layer_id is None:
            layer_id = self._get_next_layer_id()
            if hasattr(item, 'layer_id'):
                item.layer_id = layer_id

        name = self._unique_layer_name(self._default_layer_name(item), exclude=item)
        if hasattr(item, 'custom_name'):
            item.custom_name = name
        return name
