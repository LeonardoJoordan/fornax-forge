"""Cenários determinísticos para captura do histórico, sem arquivos pessoais."""
from dataclasses import dataclass
from copy import deepcopy
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem
from paint_cases import PaintCase, PaintSession, settle, screen_image, image_hash, close_window
from copy_cases import canonical_copy_document

@dataclass(frozen=True)
class HistoryCase:
    id: str
    fixture: str = 'mixed'
    size: int = 60
    operation: str = 'unchanged'

def cases():
    return (HistoryCase('snapshot-20',size=20), HistoryCase('snapshot-60'), HistoryCase('snapshot-200',size=200),
            HistoryCase('snapshot-connected-40','connected',40), HistoryCase('snapshot-connected-100','connected',100),
            HistoryCase('snapshot-grid-2500','grid',2500), HistoryCase('snapshot-duplex-60','duplex',60),
            HistoryCase('snapshot-after-undo',operation='after_undo'), HistoryCase('snapshot-return-origin',operation='return'),
            HistoryCase('snapshot-move',operation='move'), HistoryCase('snapshot-numeric',operation='numeric'),
            HistoryCase('snapshot-board-style','connected',40,'style'))

class HistorySession:
    def __init__(self, w, case, app):
        self.window, self.case, self.app = w, case, app
        self.base = PaintSession(w, PaintCase('history','local',case.fixture,case.size),app)
        self.document, self.provider = self.base.document,self.base.provider
        self.restore()

    def restore(self):
        from features.editor.canvas_items import DesignerBox
        w,case=self.window,self.case
        w._finish_page_interaction()
        w._load_document_into_scene(deepcopy(self.document))
        if case.fixture in ('connected','grid'):
            w.switch_model_page('organogram')
        w.scene.clearSelection()
        w.history.clear()
        w.save_snapshot()
        self.box=min((i for i in w.scene.items() if isinstance(i,DesignerBox) and i.isVisible() and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),key=lambda i:i.layer_id)
        if case.operation=='numeric':
            self.box.setSelected(True)
        elif case.operation=='after_undo':
            self.box.moveBy(60,0);w.save_snapshot();w.undo()
            self.box=min((i for i in w.scene.items() if isinstance(i,DesignerBox) and i.isVisible() and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable),key=lambda i:i.layer_id)
        settle(self.app)
        self.before=canonical_copy_document(w._document_with_active_page())
        self.before_history=deepcopy(w.history._undo_stack)
        self.before_index=w.history._current_index
        self.origin=QPointF(self.box.pos())
        # Capturar a referência não aplica edição. A última conclusão já foi
        # aquecida por save_snapshot/undo, sem alterar o cenário medido.

    def perform(self):
        w,case=self.window,self.case
        if case.operation=='return':
            self.box.moveBy(60,0);self.box.setPos(self.origin)
        elif case.operation=='move':self.box.moveBy(60,0)
        elif case.operation=='numeric':w.caixa_texto_panel.spin_w.setValue(40)
        elif case.operation=='style':
            group=w._board_items()[0];group.prepareGeometryChange()
            group.data.setdefault('border',{})['color']='#2468ac';group.update()
        w.save_snapshot()

    def verify(self):
        w=self.window
        document=canonical_copy_document(w._document_with_active_page())
        unchanged=self.case.operation in ('unchanged','after_undo','return')
        if unchanged:
            assert document==self.before
            assert w.history._current_index==self.before_index
            assert w.history._undo_stack==self.before_history
        else:
            assert document!=self.before
            assert w.history._current_index==self.before_index+1
            assert not w.history.can_redo()
        return {'document':document,'history':w.history._undo_stack,'index':w.history._current_index,
                'sizes':w.history._state_sizes,'undo':w.history.can_undo(),'redo':w.history.can_redo(),
                'buttons':[w.btn_undo.isEnabled(),w.btn_redo.isEnabled()],
                'pixels':image_hash(screen_image(w,workspace=True))}
