"""Trocas de página com entradas públicas e determinísticas."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json

from editor_scenarios import Scenario, make_document, page_document, synthetic_assets
from core.model_document import add_blank_back_page, normalize_model_document
from paint_cases import settle, screen_image, image_hash, close_window


@dataclass(frozen=True)
class PageCase:
    id: str
    size: int
    board: bool = False
    edit: bool = False


def cases():
    return tuple([PageCase(f'duplex-{n}', n) for n in (20, 60, 200)] +
                 [PageCase(f'board-{n}', n, True) for n in (5, 40, 100)] +
                 [PageCase('duplex-edit', 60, edit=True), PageCase('board-edit', 40, True, True)])


def document(case):
    if case.board:
        return make_document(Scenario('pages', 'switch_board', 'connected', case.size))
    doc = add_blank_back_page(page_document(case.size, mixed=case.size != 20))
    back = deepcopy(doc['pages'][0]); back['page_id'] = 'back'
    for box in back['boxes']:
        box['html'] = '<p>Verso <b>{Nome}</b></p>'
    for signature in back['signatures']:
        signature['signature_id'] += '-back'
    doc['pages'][1] = back
    return normalize_model_document(doc), synthetic_assets().__getitem__


class PageSession:
    def __init__(self, window, case, app):
        self.window, self.case, self.app = window, case, app
        self.document, self.provider = document(case)
        window.load_starter_document(deepcopy(self.document), self.provider)
        window.resize(1280, 800); window.show(); window._autosave_timer.stop()
        self.other = 'organogram' if case.board else 'back'
        settle(app)
        self.initial_x = self.edit_box().x() if case.edit else None

    def edit_box(self):
        from features.editor.canvas_items import DesignerBox
        identity = 2 if self.case.board else 6
        return next(i for i in self.window.scene.items()
                    if isinstance(i, DesignerBox) and i.layer_id == identity)

    def prepare(self):
        if self.case.edit:
            # Fora do cronômetro: entrada geométrica idêntica e cena dependente
            # correspondente a ela, para cada edição voltar a invalidá-la.
            self.edit_box().setX(self.initial_x)
            self.window.save_snapshot()
            self.window.switch_model_page(self.other); settle(self.app)
            self.window.switch_model_page('front'); settle(self.app)

    def perform(self):
        if self.case.edit:
            self.edit_box().moveBy(1, 0)
        self.window.switch_model_page(self.other)
        settle(self.app)
        self.window.switch_model_page('front')
        settle(self.app)

    def verify(self, *, all_pages=False):
        w = self.window
        result = {'document': w._document_with_active_page(),
                  'history': w.history._undo_stack, 'index': w.history._current_index,
                  'buttons': [w.btn_undo.isEnabled(), w.btn_redo.isEnabled()],
                  'pages': {}}
        # Mesmo enquadramento nas duas versões; lê pintura real, sem render forçado.
        for page in ((self.other, 'front') if all_pages else ('front',)):
            w.switch_model_page(page); w._zoom_to_fit(); settle(self.app)
            result['pages'][page] = {'state': w.get_current_scene_state(),
                                    'pixels': image_hash(screen_image(w, workspace=True)),
                                    'selection': sorted(map(str, w._selection_keys()))}
        return {key: sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                for key, value in result.items()}
