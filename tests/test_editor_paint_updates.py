"""Invalidação real: pixels do backing store contra uma pintura completa."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QStyleOptionGraphicsItem

from features.editor.canvas_items import DesignerBox, ImageItem, RectangleItem
from features.editor.organogram_editor import BoardConnectorItem, BoardGroupItem
from features.generator.organogram import OrganogramRenderer
from core.organogram import UNITS_PER_MM
from copy_cases import canonical_copy_document
from paint_cases import PaintCase, PaintSession, image_hash, screen_image, settle
import test_editor_performance_contracts as contracts


class PaintBehaviorTest(unittest.TestCase):
    setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp = contracts.PerformanceContractsTest.setUp
    editor = contracts.PerformanceContractsTest.editor

    def session(self, case):
        w = self.editor('simple', 1)
        return PaintSession(w, case, self.app)

    def record(self, w, key):
        settle(self.app)
        image = screen_image(w, workspace=True)
        partial = image_hash(image)
        w.view.viewport().update()
        w.ruler_workspace.top.update()
        w.ruler_workspace.left.update()
        settle(self.app)
        full = screen_image(w, workspace=True)
        self.assertEqual(partial, image_hash(full), key + ': rastros/recorte na pintura incremental')
        from core.model_document import persistent_model_document
        state = {'pixels': partial, 'size': [image.width(), image.height()],
                 'document': canonical_copy_document(persistent_model_document(w._document_with_active_page()))}
        if output := os.environ.get('FORNAX_PAINT_EVIDENCE'):
            path = Path(output)
            values = json.loads(path.read_text()) if path.exists() else {}
            values[key] = state
            path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
            image.save(str(path.with_name(path.stem + '-' + key + '.png')))
        return state

    def test_grid_views_keep_all_visible_content(self):
        for count in (40, 400, 2500):
            for near in (True, False):
                session = self.session(PaintCase('grid', 'repaint', size=count, near=near))
                session.perform()
                self.record(session.window, f'grid-{count}-{near}')

    def test_page_movement_resize_rotation_visibility_delete_and_history(self):
        session = self.session(PaintCase('page', 'rotate', 'mixed', 60))
        w = session.window
        box = session.box
        box.setSelected(True)
        self.record(w, 'page-select')
        w.save_snapshot()
        box.moveBy(90, 45)
        w.save_snapshot()
        self.record(w, 'page-move')
        box.resize_from_handle(340, 90)
        self.record(w, 'page-resize')
        box.setRotation(31)
        box.setOpacity(.45)
        self.record(w, 'page-rotate-opacity')
        shape = next(i for i in w.scene.items() if isinstance(i, RectangleItem)
                     and not getattr(i, 'is_document_background', False))
        shape.prepareGeometryChange()
        shape.outline_width = 55
        shape.outline_position = 'outside'
        shape.update()
        self.record(w, 'page-thick-outline')
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(15)
        effect.setOffset(9, 7)
        shape.setGraphicsEffect(effect)
        shape.moveBy(30, 0)
        self.record(w, 'page-shadow')
        box.setVisible(False)
        self.record(w, 'page-hide')
        shape.setGraphicsEffect(None)
        w.scene.clearSelection()
        box.setVisible(True)
        box.setSelected(True)
        w.delete_selected_items()
        self.record(w, 'page-delete')
        w.undo()
        self.record(w, 'page-undo')
        w.redo()
        self.record(w, 'page-redo')

    def test_connections_borders_cutouts_and_group_history(self):
        session = self.session(PaintCase('board', 'select', 'connected', 10))
        w = session.window
        group = w._board_items()[0]
        group.setSelected(True)
        w.save_snapshot()
        self.record(w, 'board-select')
        w.change_board_border(cards=True, group=True, width_mm=2.5, radius_mm=12)
        self.record(w, 'board-border-grow')
        w.change_board_border(cards=True, group=True, width_mm=.2, radius_mm=0)
        self.record(w, 'board-border-shrink')
        w._move_board_items([group], QPointF(15 * UNITS_PER_MM, 5 * UNITS_PER_MM))
        w.save_snapshot()
        self.record(w, 'board-move')
        w.scene.clearSelection()
        edge = next(i for i in w.scene.items() if isinstance(i, BoardConnectorItem))
        edge.setSelected(True)
        self.record(w, 'connector-select')
        w.change_board_connector_style(width_mm=2, radius_mm=6, opacity=.5)
        self.record(w, 'connector-style')
        edge.setSelected(False)
        self.record(w, 'connector-deselect')
        session.box.setRotation(23)
        session.box.moveBy(40, 70)
        self.record(w, 'board-text-cutout')
        w.scene.clearSelection()
        group.setSelected(True)
        w.delete_selected_items()
        self.record(w, 'board-delete')
        w.undo()
        self.record(w, 'board-undo')
        w.redo()
        self.record(w, 'board-redo')

    def test_navigation_and_rulers_follow_the_view(self):
        session = self.session(PaintCase('navigation', 'zoom', size=400))
        w = session.window
        for index, scale in enumerate((.2, .7, 2)):
            w.view.setTransform(QTransform.fromScale(scale, scale))
            w.view.centerOn(QPointF(420 + index * 100, 300))
            self.record(w, 'scale-' + str(scale))
        w.view.verticalScrollBar().setValue(w.view.verticalScrollBar().value() + 120)
        self.record(w, 'scroll')
        w.resize(1180, 750)
        self.record(w, 'resize-window')
        w._zoom_to_fit()
        self.record(w, 'fit')

    def test_mask_edit_drag_selection_and_paste_leave_no_residue(self):
        session = self.session(PaintCase('mask', 'local', 'mixed', 60))
        w = session.window
        shape = next(i for i in w.scene.items() if isinstance(i, RectangleItem) and i.masked_images())
        image = shape.masked_images()[0]
        w.scene.clearSelection()
        shape.setSelected(True)
        self.record(w, 'mask-select')
        self.assertTrue(w.begin_mask_edit(image))
        image.moveBy(12, 5)
        self.record(w, 'mask-edit')
        w.finish_mask_edit()
        self.record(w, 'mask-finish')
        w.scene.clearSelection()
        shape.setSelected(True)
        w.copy_selected_items()
        w.paste_copied_items()
        self.record(w, 'mask-paste')

    def test_full_preview_and_png_keep_every_slot(self):
        for count in (40, 2500):
            session = self.session(PaintCase('export', 'repaint', size=count))
            renderer = OrganogramRenderer(session.document, [], asset_provider=session.provider, layout_preview=True)
            self.assertEqual(len(renderer.slots), count)
            if count == 40:
                preview = renderer.preview(max_side=500)
                path = self.root/'board.png'
                renderer.export_png(path, dpi=30)
                self.assertTrue(path.is_file())
                evidence = {'preview': image_hash(preview), 'png': image_hash(QImage(str(path))), 'slots': count}
                if output := os.environ.get('FORNAX_PAINT_EVIDENCE'):
                    output = Path(output)
                    values = json.loads(output.read_text()) if output.exists() else {}
                    values['generator'] = evidence
                    output.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
                    preview.save(str(output.with_name(output.stem + '-generator-preview.png')))
                    QImage(str(path)).save(str(output.with_name(output.stem + '-generator-png.png')))


class PaintWorkTest(PaintBehaviorTest):
    def paint_probe(self, w, *, widget, exposed):
        group = w._board_items()[0]
        image = QImage(300, 250, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.scale(.5, .5)
        option = QStyleOptionGraphicsItem()
        option.exposedRect = exposed
        class CountingPainter:
            draws = 0
            def __getattr__(self, name):
                return getattr(painter, name)
            def drawImage(self, *args):
                self.draws += 1
                return painter.drawImage(*args)
        proxy = CountingPainter()
        try:
            group.paint(proxy, option, widget)
        finally:
            painter.end()
        return proxy.draws

    def test_visible_area_draws_a_subset_of_the_dense_group(self):
        session = self.session(PaintCase('dense', 'local', size=2500))
        count = self.paint_probe(session.window, widget=session.window.view.viewport(), exposed=QRectF(160, 180, 12, 12))
        self.assertGreater(count, 0)
        self.assertLess(count, 100)

    def test_non_view_render_does_not_drop_offscreen_cards(self):
        session = self.session(PaintCase('render', 'repaint', size=2500))
        count = self.paint_probe(session.window, widget=None, exposed=QRectF(160, 180, 12, 12))
        self.assertEqual(count, 2500)

    def test_local_changes_do_not_repaint_the_whole_view(self):
        session = self.session(PaintCase('dirty', 'local', size=400))
        w = session.window
        class Observer(QObject):
            areas = []
            def eventFilter(self, source, event):
                if event.type() == QEvent.Type.Paint:
                    rect = event.region().boundingRect()
                    self.areas.append(rect.width() * rect.height())
                return False
        observer = Observer(w.view.viewport())
        w.view.viewport().installEventFilter(observer)
        session.perform()
        settle(self.app)
        self.assertTrue(observer.areas)
        self.assertLess(max(observer.areas), w.view.viewport().width() * w.view.viewport().height() / 2)

    def test_rulers_skip_content_only_paints_but_follow_zoom(self):
        session = self.session(PaintCase('rulers', 'local', size=40))
        w = session.window
        w.ruler_workspace.refresh()
        settle(self.app)
        with patch.object(w.ruler_workspace.top, 'update', wraps=w.ruler_workspace.top.update) as update:
            for _ in range(10):
                w.ruler_workspace.refresh()
            self.assertEqual(update.call_count, 0)
            w._apply_zoom(1.15)
            settle(self.app)
            self.assertGreater(update.call_count, 0)

    def test_exposure_accounts_for_wide_outside_borders(self):
        session = self.session(PaintCase('outside', 'local', size=400))
        group = session.window._board_items()[0]
        group.data['border'].update(width_mm=10, cards_position='outside')
        # Só o contorno do primeiro cartão entra nessa área, não seu conteúdo.
        count = self.paint_probe(session.window, widget=session.window.view.viewport(), exposed=QRectF(-80, 40, 10, 10))
        self.assertGreater(count, 0)
        self.assertLess(count, 100)


for name in PaintBehaviorTest.__dict__:
    if name.startswith('test_'):
        setattr(PaintWorkTest, name, None)
