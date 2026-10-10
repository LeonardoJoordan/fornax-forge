"""Uma cena inativa por editor, validada por conteúdo e recursos da sessão."""
from dataclasses import dataclass
from hashlib import sha256
import json

from PySide6.QtCore import QSignalBlocker, QRectF
from PySide6.QtWidgets import QApplication, QGraphicsScene
from shiboken6 import isValid

from core.i18n import current_locale
from core.model_document import adapt_model_page
from core.themes import theme_manager
from .model_adapter import prepare_scene_page
from .table_item import TableItem

# Estado exclusivo da página. Controles, histórico, autorização e view são globais.
PAGE_ATTRIBUTES = (
    'fallback_bg', 'bg_item', 'background_path', '_selection_frame',
    '_document_rect', '_doc_aspect_ratio', '_board_grid_mm', '_board_margin_mm',
    '_board_connector_style', '_board_item_refs', '_board_artwork_refs',
    '_board_card_preview', '_board_path_cache', '_board_bounds_cache',
    '_board_cutouts_cache', '_board_cutout_revision', '_board_routes_crowded',
    '_board_workspace_dirty',
)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).digest()


@dataclass
class PageScene:
    page_id: str
    scene: QGraphicsScene
    key: bytes
    dependencies: bytes
    attributes: dict
    state: dict
    # Mantém inclusive guias e filhos de máscaras sob propriedade segura do Qt.
    items: list
    estimated_bytes: int

    def dispose(self):
        if isValid(self.scene):
            self.scene.blockSignals(True)
            self.scene.clear()
            self.scene.deleteLater()
        self.items.clear(); self.attributes.clear(); self.state.clear()


class PageScenesMixin:
    def _clear_page_scenes(self):
        cached, self._inactive_page_scene = self._inactive_page_scene, None
        if cached is not None:
            cached.dispose()

    def _scene_signals(self, scene, *, connect):
        pairs = [(scene.selectionChanged, self.on_selection_changed),
                 (scene.changed, self.update_position_ui)]
        if getattr(self, 'canvas_edit', None):
            pairs.append((scene.selectionChanged, self.canvas_edit.selection_changed))
        if getattr(self, 'table_edit', None):
            pairs.append((scene.selectionChanged, self.table_edit.selection_changed))
        for signal, slot in pairs:
            if connect:
                signal.connect(slot)
            else:
                signal.disconnect(slot)

    def _page_dependencies(self, page_id, data):
        templates = [data]
        # O organograma também depende do desenho e assets da Página 1.
        front = adapt_model_page(self._model_document, 'front') if page_id == 'organogram' else None
        if front is not None:
            templates.append(front)
        references = set()
        for template in templates:
            references.update(entry['path'] for collection in ('images', 'signatures')
                              for entry in template.get(collection, []) if entry.get('path'))
            if template.get('background_path'):
                references.add(template['background_path'])
        assets = []
        for reference in sorted(references):
            try:
                payload = self._editor_asset_provider(reference)
                stamp = sha256(payload).hexdigest()
            except (OSError, KeyError, ValueError):
                stamp = None
            assets.append((reference, stamp))
        manager = self._fornax_session_manager
        token = manager.issue_token(self._fornax_path) if manager and self._fornax_path else None
        # O nonce de cada token é deliberadamente ignorado; geração e revisão não.
        authorization = (token.model_id, token.revision_id, token.generation) if token else None
        return digest([front, assets, QApplication.font().key(), current_locale(),
                       self._page_font_epoch, theme_manager().current['colors'],
                       self._fornax_mode, authorization])

    def _retain_page_scene(self, page_id):
        data = prepare_scene_page(adapt_model_page(self._model_document, page_id))
        # Fundos legados são convertidos pelo carregador, que atribui uma
        # identidade à imagem criada. Até a persistência dessa conversão,
        # não há correspondência estável para reativar os objetos da cena.
        if data.get('background_path'):
            return None
        items = self.scene.items()
        estimate = len(items) * 8192
        pixmaps = set()
        for item in items:
            if isinstance(item, TableItem):
                # Cada célula retém um QTextDocument, não só bytes de JSON.
                estimate += len(item.layout.cells) * 16384
                estimate += sum(len(c['html'].encode()) * 4 for c in item.data['cells'])
            if hasattr(item, 'pixmap'):
                pixmap = item.pixmap()
                if pixmap.cacheKey() not in pixmaps:
                    pixmaps.add(pixmap.cacheKey())
                    estimate += pixmap.width() * pixmap.height() * pixmap.depth() // 8
            text = getattr(item, 'text_item', None)
            if text is not None:
                estimate += len(text.toHtml().encode()) * 4
        preview = getattr(self, '_board_card_preview', None)
        if page_id == 'organogram' and preview is not None:
            estimate += preview.sizeInBytes()
        if len(items) > 5000 or estimate > self._page_scene_budget:
            return None
        # Só examina os assets depois de saber que a cena cabe no orçamento.
        # Um arquivo/fonte pode ter mudado enquanto esta página estava aberta;
        # a conferência de conteúdo continua obrigatória antes de reter a cena.
        dependencies = self._page_dependencies(page_id, data)
        if dependencies != self._active_page_dependencies:
            return None
        return PageScene(page_id, self.scene, digest([data, dependencies.hex()]), dependencies,
                         {name:getattr(self,name,None) for name in PAGE_ATTRIBUTES},
                         self.get_current_scene_state(), items, estimate)

    def _activate_model_page_scene(self, page_id):
        """Único caminho de troca: cena válida ou reconstrução conservadora."""
        data = prepare_scene_page(adapt_model_page(self._model_document, page_id))
        dependencies = self._page_dependencies(page_id, data)
        key = digest([data, dependencies.hex()])
        target, self._inactive_page_scene = self._inactive_page_scene, None
        if target and (target.page_id != page_id or target.key != key
                       or not isValid(target.scene) or not all(isValid(i) for i in target.items)):
            target.dispose(); target = None
        previous = self._retain_page_scene(self._active_page_id)
        old_scene = self.scene
        self._scene_signals(old_scene, connect=False)
        self._selection_frame_timer.stop()
        self._history_capture_cache = None
        self._loading_board = True
        center = self.view.mapToScene(self.view.viewport().rect().center())
        updates = self.view.updatesEnabled(); self.view.setUpdatesEnabled(False)
        try:
            self._active_page_id = page_id
            if target:
                self.scene = target.scene
                for name, value in target.attributes.items():
                    setattr(self, name, value)
            else:
                self.scene = QGraphicsScene(self)
                self._selection_frame = self.fallback_bg = self.bg_item = None
                self._board_card_preview = None
            self.view.setScene(self.scene)
            with QSignalBlocker(self.scene):
                if target:
                    self._restore_page_scene_order(data)
                    self._restore_page_scene_controls(target.state, data)
                else:
                    self.apply_scene_state(data, is_undo_redo=False)
                self._active_page_dependencies = dependencies
                self.scene.clearSelection()
                self._restore_page_selection()
                self.view.centerOn(center)
        finally:
            # Também limita a retenção se uma reconstrução falhar.
            self._inactive_page_scene = previous
            if previous is None and old_scene is not self.scene:
                old_scene.blockSignals(True); old_scene.clear(); old_scene.deleteLater()
            self._loading_board = False
            self._scene_signals(self.scene, connect=True)
            self.view.setUpdatesEnabled(updates)
        self.scene.selectionChanged.emit()

    def _restore_page_scene_order(self, data):
        """Aplica a mesma ordenação do carregador, conservando os objetos vivos."""
        from core.document_layers import upgrade_layers
        from .canvas_items import DesignerBox, ImageItem, SignatureItem, Guideline
        ordered = upgrade_layers(data)
        entries = {entry['layer_id']: entry for group in ('boxes', 'images', 'signatures', 'shapes', 'tables')
                   for entry in ordered.get(group, [])}
        guides = []
        for item in self.scene.items():
            if isinstance(item, Guideline):
                guides.append(item)
            elif isinstance(item, (DesignerBox, ImageItem, SignatureItem, TableItem)):
                entry = entries.get(item.layer_id)
                if entry is not None:
                    z = (-100 if getattr(item, 'is_document_background', False)
                         else item.mask_order + 1 if entry.get('mask_shape_id')
                         else entry['z_value'])
                    item.setZValue(z)
        # A inserção do carregador deixa a última guia acima da primeira.
        # stackBefore reproduz essa ordem sem reconstruir nem perder wrappers.
        sequence = []
        for entry in reversed(ordered.get('guidelines', [])):
            match = next((item for item in guides
                          if item.is_vertical == entry.get('vertical', True)
                          and (item.pos().x() if item.is_vertical else item.pos().y()) == entry['pos']), None)
            if match is not None:
                guides.remove(match); sequence.append(match)
        for high, low in zip(sequence, sequence[1:]):
            low.stackBefore(high)

    def _restore_page_scene_controls(self, state, data):
        from .editor_window import _visibility_icon
        from core.theme_icons import themed_svg_icon
        from core.resources import state_icon_path
        for control, value in ((self.spin_phys_w,state['target_w_mm']),
                               (self.spin_phys_h,state['target_h_mm'])):
            with QSignalBlocker(control):
                control.setRange(.1,50000) if self._active_page_id=='organogram' else control.setRange(10,1000)
                control.setValue(value)
        with QSignalBlocker(self.chk_doc_proporcao):
            self.chk_doc_proporcao.setChecked(state['doc_proportion_locked'])
        self._refresh_doc_proportion_button()
        visible, locked = state['guidelines_visible'], state['guidelines_locked']
        with QSignalBlocker(self.btn_toggle_guides):
            self.btn_toggle_guides.setChecked(visible); self.btn_toggle_guides.setIcon(_visibility_icon(visible))
        with QSignalBlocker(self.btn_lock_guides):
            self.btn_lock_guides.setChecked(locked)
            self.btn_lock_guides.setIcon(themed_svg_icon(state_icon_path('lock' if locked else 'unlock')))
        self.op_eye.setOpacity(1 if visible else .2); self.op_lock.setOpacity(1 if locked else .2)
        self.lst_placeholders.clear(); self.lst_placeholders.addItems(state['placeholders'])
        self.sync_placeholders_list(); self.refresh_layer_list()
        self._on_physical_size_changed(document_rect=QRectF(self._document_rect))
        # Alças e caneta textual são adornos dependentes do zoom, atualizados
        # durante a pintura. Reativa com a geometria inicial do carregador,
        # evitando que alças ampliadas na página anterior alterem o enquadramento.
        from .canvas_items import DesignerBox
        loaded_background = any(entry.get('is_document_background') or
                                ('is_document_background' not in entry and
                                 entry.get('custom_name') == 'Plano de fundo')
                                for entry in data.get('shapes', []))
        for item in self.scene.items():
            for handle in getattr(item, 'resize_handles', {}).values():
                if loaded_background and getattr(item, 'is_document_background', False):
                    # bind_document é chamado com a forma já na cena quando
                    # o fundo vem do arquivo; suas alças acompanham o zoom.
                    handle.update_handle_size()
                else:
                    handle.setRect(-6, -6, 12, 12)
            if isinstance(item, DesignerBox):
                pen = item.pen(); pen.setWidthF(2); item.setPen(pen)
        self.ruler_workspace.update()
