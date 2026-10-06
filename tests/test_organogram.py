"""Cenários de quadro: persistência, edição, dados parciais e saída física."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPointF, QSettings, QMimeData, QSignalBlocker
from PySide6.QtGui import QImage, QColor, QDropEvent, QPainter, QPainterPath, QTextCursor
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QStyleOptionGraphicsItem
from PySide6.QtTest import QTest
from pypdf import PdfReader

from core.model_document import (
    normalize_model_document, persistent_model_document, add_blank_back_page,
    remove_model_page, adapt_model_page, replace_model_page, ModelValidationError,
)
from core.organogram import (
    add_organogram, new_group, assigned_slots, row_is_valid, UNITS_PER_MM,
)
from core.board_connectors import connector_style, connector_path, text_cutouts
from core.board_routing import board_routes
from features.editor.canvas_items import DesignerBox
from features.editor.organogram_editor import BoardConnectorItem, StructureTree
from core.fornax_container import (
    save_public_fornax, open_public_fornax, save_protected_fornax,
    unlock_fornax, FULL_MODE,
)
from features.editor.editor_window import EditorWindow
from features.generator.organogram import OrganogramRenderer, OrganogramWorker


def card_document():
    return normalize_model_document({
        "canvas_size": {"w": 590, "h": 826}, "target_w_mm": 50, "target_h_mm": 70,
        "placeholders": ["Nome", "Funcao"], "name": "Quadro de teste",
        "boxes": [{"x": 25, "y": 200, "w": 540, "h": 90, "font_size": 30,
                   "html": "<p>{Nome}</p>", "layer_id": 2, "rich_text_version": 1},
                  {"x": 25, "y": 300, "w": 540, "h": 90, "font_size": 20,
                   "html": "<p>{Funcao}</p>", "layer_id": 3, "rich_text_version": 1}],
        "shapes": [{"x": 0, "y": 0, "width": 590, "height": 826,
                    "shape_type": "rectangle", "fill_color": "#dcecf4", "layer_id": 1}],
        "images": [], "signatures": [],
        "layer_order": ["shape:1", "text:2", "text:3"],
    })


def board_document(columns=4, rows=10):
    document = add_organogram(card_document())
    document["organogram"]["groups"] = [new_group(document, columns=columns, rows=rows)]
    return document


class OrganogramTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(patch("core.paths._data_home", return_value=self.root / "data"))

    def editor(self, document=None):
        window = EditorWindow()
        if document:
            window._load_document_into_scene(document)
        def cleanup():
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def test_page_and_board_are_mutually_exclusive(self):
        with self.assertRaises(ModelValidationError):
            add_organogram(add_blank_back_page(card_document()))
        with self.assertRaises(ModelValidationError):
            add_blank_back_page(board_document())
        removed = remove_model_page(board_document(), "organogram")
        self.assertEqual(len(add_blank_back_page(removed)["pages"]), 2)
        self.assertEqual(removed["schema_version"], 4)

    def test_version_requires_explicit_support_and_rejects_cycles(self):
        document = board_document()
        self.assertEqual(document["schema_version"], 5)
        document["schema_version"] = 4
        with self.assertRaises(ModelValidationError):
            normalize_model_document(document)
        document["schema_version"] = 5
        other = new_group(document, columns=1, rows=1)
        document["organogram"]["groups"].append(other)
        first = document["organogram"]["groups"][0]["id"]
        document["organogram"]["connections"] = [
            {"source": first, "target": other["id"]}, {"source": other["id"], "target": first}]
        with self.assertRaises(ModelValidationError):
            normalize_model_document(document)

    def test_34_records_hide_six_slots_and_static_content_does_not_activate(self):
        document = board_document()
        rows = [{"Nome": f"Aluno {index}"} for index in range(34)] + [{}] * 6
        slots = list(assigned_slots(document, rows))
        self.assertEqual(len(slots), 34)
        self.assertEqual([slot[1] for slot in slots], list(range(34)))
        self.assertFalse(row_is_valid(document, {"Nome": " \n", "modelo": "automatico"}))
        self.assertTrue(row_is_valid(document, {"Funcao": "Aluno"}))
        self.assertTrue(row_is_valid(document, {"Nome": 0}))

    def test_empty_middle_slot_preserves_other_positions(self):
        document = board_document(3, 1)
        slots = list(assigned_slots(document, [{"Nome": "A"}, {}, {"Nome": "C"}]))
        self.assertEqual([slot[1] for slot in slots], [0, 2])
        self.assertGreater(slots[1][2].left(), slots[0][2].right())

    def test_filters_and_start_rows_assign_the_right_people(self):
        document = board_document(2, 1)
        group = document["organogram"]["groups"][0]
        group.update(filter_field="Funcao", filter_value="Equipe B", start_row=1)
        slots = list(assigned_slots(document, [
            {"Nome": "A", "Funcao": "Equipe A"}, {"Nome": "B", "Funcao": "Equipe B"},
            {"Nome": "C", "Funcao": "Equipe B"}, {"Nome": "D", "Funcao": "Equipe B"}]))
        self.assertEqual([slot[3]["Nome"] for slot in slots], ["C", "D"])

    def test_dynamic_photo_only_requires_a_resolved_image(self):
        document = board_document(1, 1)
        document["pages"][0]["boxes"] = []
        document["pages"][0]["shapes"][0]["dynamic_image_field"] = "Foto"
        image = QImage(16, 16, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        image.save(str(self.root / "foto.png"))
        self.assertFalse(row_is_valid(document, {"Foto": "ausente.png"}, self.root))
        self.assertTrue(row_is_valid(document, {"Foto": "foto.png"}, self.root))

    def test_artwork_and_board_assets_round_trip_public_and_protected(self):
        document = persistent_model_document(board_document(1, 1))
        image = QImage(10, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("blue"))
        logo = self.root / "logo.png"
        image.save(str(logo))
        board = document["organogram"]
        board["images"] = [{"object_id": "image:10", "layer_id": 10, "path": str(logo),
                            "x": 0, "y": -50, "width": 20, "height": 20}]
        board["layer_order"] = ["image:10"]
        public_path = self.root / "public.fornax"
        save_public_fornax(document, public_path)
        opened = open_public_fornax(public_path)
        reference = opened.document()["organogram"]["images"][0]["path"]
        self.assertEqual(opened.asset(reference), logo.read_bytes())
        self.assertEqual(opened.document()["organogram"]["groups"], board["groups"])
        private_path = self.root / "private.fornax"
        save_protected_fornax(document, private_path, mode=FULL_MODE, password="teste-quadro")
        unlocked = unlock_fornax(private_path, "teste-quadro")
        self.assertEqual(unlocked.document()["organogram"]["groups"], board["groups"])

    def test_editor_menu_blocks_snap_history_and_page_dimensions(self):
        window = self.editor(card_document())
        window.add_model_organogram()
        item = window.add_board_group(new_group(window._model_document))
        identifier = item.data["id"]
        initial = item.pos()
        item.setPos(123, 187)
        grid = 5 * UNITS_PER_MM
        self.assertAlmostEqual((item.pos().x() + item.rect().center().x()) / grid,
                               round((123 + item.rect().center().x()) / grid))
        window.save_snapshot()
        self.assertIs(window.btn_add_sig.menu(), window._board_tool_menu)
        window.switch_model_page("front")
        self.assertIsNone(window.btn_add_sig.menu())
        self.assertEqual(window._model_document["canvas_size"], {"w": 590, "h": 826})
        window.switch_model_page("organogram")
        self.assertEqual(window._board_items()[0].data["id"], identifier)
        window.undo()
        self.assertEqual(window._board_items()[0].pos(), initial)
        window.redo()
        item = window._board_items()[0]
        self.assertAlmostEqual(item.pos().x() + item.rect().center().x(), round((123 + item.rect().center().x()) / grid) * grid)

    def test_editor_connections_follow_moves_and_delete_with_target(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page("organogram")
        first = window._board_items()[0]
        other = window.add_board_group(new_group(window._model_document, columns=1, rows=1, y=2000))
        window.set_board_parent(other.data["id"], first.data["id"])
        edge = next(item for item in window.scene.items() if hasattr(item, "board_edge"))
        before = edge.path().boundingRect()
        other.moveBy(500, 0)
        self.assertNotEqual(edge.path().boundingRect(), before)
        window.scene.clearSelection()
        other.setSelected(True)
        window.delete_selected_items()
        self.assertEqual(window._board_connections_data(), [])
        window.undo()
        self.assertEqual(len(window._board_connections_data()), 1)

    def chart_with_three_blocks(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page("organogram")
        first = window._board_items()[0]
        second = window.add_board_group(new_group(window._model_document, columns=1, rows=1, x=1000, y=2000))
        third = window.add_board_group(new_group(window._model_document, columns=1, rows=1, x=-1000, y=2000))
        return window, first, second, third

    def test_connect_mode_links_multiple_blocks_with_real_click_and_restores_them(self):
        window, parent, one, two = self.chart_with_three_blocks()
        window.show()
        self.app.processEvents()
        with QSignalBlocker(window.scene):
            window.scene.clearSelection()
            one.setSelected(True)
            two.setSelected(True)
        window.on_selection_changed()
        QTest.mouseClick(window.organogram_panel.connect_button, Qt.MouseButton.LeftButton)
        self.assertEqual(window._board_connection_sources, {one.data["id"], two.data["id"]})
        for item in (one, two):
            self.assertEqual(item.opacity(), 0.35)
            self.assertEqual(item.acceptedMouseButtons(), Qt.MouseButton.NoButton)
        self.assertEqual(window._board_connections_data(), [])
        window.view.centerOn(one)
        QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=window.view.mapFromScene(one.sceneBoundingRect().center()))
        self.assertEqual(window._board_connections_data(), [])
        window.view.centerOn(parent)
        QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=window.view.mapFromScene(parent.sceneBoundingRect().center()))
        self.assertEqual({edge["target"] for edge in window._board_connections_data()}, {one.data["id"], two.data["id"]})
        self.assertTrue(all(edge["source"] == parent.data["id"] for edge in window._board_connections_data()))
        self.assertFalse(window._board_connection_sources)
        for item in (one, two):
            self.assertEqual(item.opacity(), 1)
            self.assertNotEqual(item.acceptedMouseButtons(), Qt.MouseButton.NoButton)
        window.undo()
        self.assertEqual(window._board_connections_data(), [], "A conexão múltipla deve ser uma só operação de desfazer.")

    def test_connect_mode_escape_page_switch_and_cycle_leave_no_transient_state(self):
        window, parent, one, two = self.chart_with_three_blocks()
        window.show()
        self.app.processEvents()
        window.scene.clearSelection()
        one.setSelected(True)
        window.start_board_connection()
        window.view.setFocus()
        QTest.keyClick(window.view.viewport(), Qt.Key.Key_Escape)
        self.assertFalse(window._board_connection_sources)
        self.assertEqual(one.opacity(), 1)
        window.set_board_parent(one.data["id"], parent.data["id"])
        window.scene.clearSelection()
        parent.setSelected(True)
        window.start_board_connection()
        before = window._board_connections_data()
        self.assertFalse(window._connect_to_board_target(one.data["id"]))
        self.assertEqual(window._board_connections_data(), before)
        self.assertTrue(window._board_connection_sources)
        window.switch_model_page("front")
        self.assertFalse(window._board_connection_sources)
        window.switch_model_page("organogram")
        self.assertTrue(all(item.opacity() == 1 for item in window._board_items()))

    def test_tree_selection_keeps_qt_items_alive_and_supports_multiple_blocks(self):
        window, parent, one, two = self.chart_with_three_blocks()
        window.show()
        self.app.processEvents()
        tree = window.organogram_panel.tree
        nodes = [tree.topLevelItem(index) for index in range(3)]
        window.organogram_panel.refresh()
        self.assertIs(nodes[0], tree.topLevelItem(0))
        for index, modifier in ((1, Qt.KeyboardModifier.NoModifier), (2, Qt.KeyboardModifier.ControlModifier)):
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, modifier,
                             tree.visualItemRect(nodes[index]).center())
        selected = {item.data["id"] for item in window.scene.selectedItems() if hasattr(item, "preview")}
        self.assertEqual(selected, {one.data["id"], two.data["id"]})
        self.assertIs(nodes[1], tree.topLevelItem(1))
        self.assertEqual(nodes[1].data(0, Qt.ItemDataRole.UserRole), one.data["id"])
        window.start_board_connection()
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(nodes[0]).center())
        self.app.processEvents()
        self.assertEqual(len(window._board_connections_data()), 2)

    def test_tree_drop_is_deferred_atomic_and_does_not_remove_source_rows(self):
        import json
        window, parent, one, two = self.chart_with_three_blocks()
        window.show()
        self.app.processEvents()
        tree = window.organogram_panel.tree
        node = tree.topLevelItem(0)
        mime = QMimeData()
        mime.setData(StructureTree.MIME_TYPE, json.dumps([one.data["id"], two.data["id"]]).encode())
        class InternalDrop(QDropEvent):
            def source(self):
                return tree
        event = InternalDrop(QPointF(tree.visualItemRect(node).center()), Qt.DropAction.MoveAction,
                             mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tree.dropEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(node.childCount(), 0, "Não reconstrua os itens dentro do evento de drop.")
        self.assertEqual(window._board_connections_data(), [])
        self.app.processEvents()
        self.assertEqual(len(window._board_items()), 3)
        self.assertEqual(tree.topLevelItemCount(), 1)
        self.assertEqual(tree.topLevelItem(0).childCount(), 2)
        before = window._board_connections_data()
        mime.setData(StructureTree.MIME_TYPE, json.dumps([parent.data["id"]]).encode())
        child = tree.topLevelItem(0).child(0)
        invalid = InternalDrop(QPointF(tree.visualItemRect(child).center()), Qt.DropAction.MoveAction,
                               mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tree.dropEvent(invalid)
        self.app.processEvents()
        self.assertEqual(window._board_connections_data(), before)
        self.assertEqual(len(window._board_items()), 3)
        # Soltar na área vazia remove os superiores de toda a seleção.
        mime.setData(StructureTree.MIME_TYPE, json.dumps([one.data["id"], two.data["id"]]).encode())
        root_drop = InternalDrop(QPointF(10, tree.viewport().height() - 3), Qt.DropAction.MoveAction,
                                mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tree.dropEvent(root_drop)
        self.app.processEvents()
        self.assertEqual(window._board_connections_data(), [])
        self.assertEqual(tree.topLevelItemCount(), 3)
        # O início customizado do drag não usa a remoção automática do Qt.
        tree.topLevelItem(1).setSelected(True)
        with patch("features.editor.organogram_editor.QDrag") as drag:
            tree.startDrag(Qt.DropAction.MoveAction)
            drag.return_value.exec.assert_called_once_with(Qt.DropAction.MoveAction)
            self.assertTrue(drag.return_value.setMimeData.call_args.args[0].hasFormat(StructureTree.MIME_TYPE))

    def test_connector_styles_persist_copy_paste_and_undo(self):
        window, parent, one, two = self.chart_with_three_blocks()
        window.scene.clearSelection()
        window.change_board_connector_style(color="#cc2255", width_mm=1.25, opacity=0.4, radius_mm=5)
        window.set_board_parents([one.data["id"], two.data["id"]], parent.data["id"])
        self.assertTrue(all(edge["style"]["radius_mm"] == 5 for edge in window._board_connections_data()))
        window.scene.clearSelection()
        one.setSelected(True)
        window.change_board_connector_style(radius_mm=25)
        saved = persistent_model_document(window._model_document)
        edge = next(edge for edge in saved["organogram"]["connections"] if edge["target"] == one.data["id"])
        self.assertEqual(edge["style"], {"color": "#cc2255", "width_mm": 1.25, "opacity": 0.4, "radius_mm": 25})
        window.undo()
        self.assertTrue(all(edge["style"]["radius_mm"] == 5 for edge in window._board_connections_data()))
        window.redo()
        window.select_all_items()
        window.copy_selected_items()
        window.paste_copied_items()
        self.assertEqual(sum(edge["style"]["radius_mm"] == 25 for edge in window._board_connections_data()), 2)
        target = self.root / "styles.fornax"
        save_public_fornax(window._model_document, target)
        reopened = open_public_fornax(target).document()
        self.assertEqual(reopened["organogram"]["connections"], window._model_document["organogram"]["connections"])
        invalid = deepcopy(reopened)
        invalid["organogram"]["connections"][0]["style"]["width_mm"] = float("nan")
        with self.assertRaises(ModelValidationError):
            normalize_model_document(invalid)

    def test_connector_modes_use_square_rounded_and_continuous_curve_geometry(self):
        doc = board_document(1, 1)
        source = doc["organogram"]["groups"][0]
        target = new_group(doc, columns=1, rows=1, x=1000, y=2000)
        paths = {mode: connector_path(source, target, connector_style({"style": {"mode": mode}}))
                 for mode in ("square", "rounded", "curved")}
        self.assertTrue(all(paths["square"].elementAt(i).type != QPainterPath.ElementType.CurveToElement
                            for i in range(paths["square"].elementCount())))
        self.assertGreater(paths["rounded"].elementCount(), paths["square"].elementCount())
        self.assertNotEqual(paths["curved"], paths["rounded"])
        self.assertTrue(any(paths["curved"].elementAt(i).type == QPainterPath.ElementType.CurveToElement
                            for i in range(paths["curved"].elementCount())))
        for path in paths.values():
            self.assertEqual(path.pointAtPercent(0), paths["square"].pointAtPercent(0))
            self.assertEqual(path.pointAtPercent(1), paths["square"].pointAtPercent(1))

    def test_text_selection_is_cleared_after_exit_without_changing_formatting(self):
        window = self.editor(card_document())
        box = next(item for item in window.scene.items() if isinstance(item, DesignerBox))
        window.canvas_edit.begin(box)
        cursor = box.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        box.text_item.setTextCursor(cursor)
        window.canvas_edit.format('bold', True)
        html, text = box.text_item.toHtml(), box.text_item.toPlainText()
        self.assertTrue(box.text_item.textCursor().hasSelection())
        window.scene.clearSelection()
        self.assertIsNone(window.canvas_edit.box)
        self.assertFalse(box.text_item.textCursor().hasSelection())
        self.assertFalse(box.text_item.hasFocus())
        self.assertEqual(box.text_item.toHtml(), html)
        self.assertEqual(box.text_item.toPlainText(), text)

    def test_duplicate_and_repeated_paste_assign_unique_names_and_keep_data_and_ports(self):
        window, first, second, third = self.chart_with_three_blocks()
        first.data['name'] = 'Bloco 2'
        second.data['name'] = 'Bloco 10'
        third.data['name'] = 'Comando'
        second.data['exit_sides'] = ['left', 'top']
        window.scene.clearSelection()
        second.setSelected(True)
        window.duplicate_selected()
        duplicate = window._selected_board_group()
        self.assertEqual(duplicate.data['name'], 'Bloco 11')
        self.assertEqual(duplicate.data['start_row'], second.data['start_row'])
        self.assertEqual(duplicate.data['exit_sides'], ['left', 'top'])
        window.copy_board_selection()
        window.paste_board_selection()
        self.assertEqual(window._selected_board_group().data['name'], 'Bloco 12')
        window.paste_board_selection()
        self.assertEqual(window._selected_board_group().data['name'], 'Bloco 13')
        window.scene.clearSelection()
        third.setSelected(True)
        window.copy_board_selection()
        window.paste_board_selection()
        self.assertEqual(window._selected_board_group().data['name'], 'Comando — cópia')
        window.paste_board_selection()
        self.assertEqual(window._selected_board_group().data['name'], 'Comando — cópia 2')
        names = [item.data['name'] for item in window._board_items()]
        self.assertEqual(len(names), len(set(names)))

    def test_board_centers_snap_independently_of_dimensions_and_text_uses_half_grid(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page('organogram')
        group = window.add_board_group(new_group(window._model_document, columns=1, rows=1, card_width_mm=8))
        target = QPointF(100 * UNITS_PER_MM, 200 * UNITS_PER_MM)
        group.setPos(target - group.rect().center())
        text = DesignerBox(0, 0, 13 * UNITS_PER_MM, 7 * UNITS_PER_MM, 'Texto')
        window.scene.addItem(text)
        text.setPos(target - text.rect().center())
        self.assertEqual(group.mapToScene(group.rect().center()), text.mapToScene(text.rect().center()))
        text.moveBy(2.5 * UNITS_PER_MM, 0)
        self.assertAlmostEqual(text.mapToScene(text.rect().center()).x(), target.x() + 2.5 * UNITS_PER_MM)
        window.scene.clearSelection()
        group.setSelected(True)
        window.update_position_ui()
        self.assertAlmostEqual(window.spin_pos_x.value(), 100)
        self.assertAlmostEqual(window.spin_pos_y.value(), 200)
        window.apply_position_x(110)
        self.assertAlmostEqual(group.mapToScene(group.rect().center()).x(), 110 * UNITS_PER_MM)
        window.scene.clearSelection()
        text.setSelected(True)
        window.apply_position_x(110)
        window.apply_position_y(200)
        self.assertEqual(group.mapToScene(group.rect().center()), text.mapToScene(text.rect().center()))
        window.show()
        window.view.setFocus()
        self.app.processEvents()
        before = text.pos()
        QTest.keyClick(window.view.viewport(), Qt.Key.Key_Right)
        self.assertAlmostEqual((text.pos() - before).x(), 2.5 * UNITS_PER_MM)

    def test_board_loading_and_history_preserve_existing_off_grid_coordinates(self):
        document = board_document(1, 1)
        original = document['organogram']['groups'][0]
        original.update(x=17.3, y=-29.7)
        original.pop('entry_sides')
        original.pop('exit_sides')
        window = self.editor(document)
        window.switch_model_page('organogram')
        self.assertEqual(window._board_items()[0].pos(), QPointF(17.3, -29.7))
        window.switch_model_page('front')
        window.switch_model_page('organogram')
        self.assertEqual(window._board_items()[0].pos(), QPointF(17.3, -29.7))
        window._board_items()[0].moveBy(100, 100)
        window.save_snapshot()
        window.undo()
        self.assertEqual(window._board_items()[0].pos(), QPointF(17.3, -29.7))

    def test_dragging_and_arrow_movement_preserve_mixed_selection_distances(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page('organogram')
        group = window._board_items()[0]
        text = DesignerBox(800, 50, 137, 83, 'Texto')
        window.scene.addItem(text)
        group.setSelected(True)
        text.setSelected(True)
        before = text.pos() - group.pos()
        window.scene._drag_start_positions = {group: group.pos(), text: text.pos()}
        window.scene._board_drag_anchor = None
        group._is_mouse_dragging = True
        starts = dict(window.scene._drag_start_positions)
        for item in (group, text):
            item.setPos(starts[item] + QPointF(143, 217))
        group._is_mouse_dragging = False
        self.assertEqual(text.pos() - group.pos(), before)
        window._move_board_items([group, text], QPointF(5 * UNITS_PER_MM, 0))
        self.assertEqual(text.pos() - group.pos(), before)
        window.save_snapshot()
        window.show()
        self.app.processEvents()
        window._zoom_to_fit()
        window.view.centerOn(group)
        start = window.view.mapFromScene(group.mapToScene(group.rect().center()))
        end = start + type(start)(55, 30)
        initial = group.pos()
        QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.view.viewport(), end, delay=20)
        QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertNotEqual(group.pos(), initial)
        self.assertEqual(text.pos() - group.pos(), before)

    def test_port_checkboxes_defaults_multiple_selection_and_persistence(self):
        window, parent, child, other = self.chart_with_three_blocks()
        window.show()
        self.app.processEvents()
        window.set_board_parent(child.data['id'], parent.data['id'])
        window.scene.clearSelection()
        child.setSelected(True)
        panel = window.organogram_panel
        self.assertTrue(panel.entry_sides.checks['bottom'].isChecked())
        self.assertTrue(panel.exit_sides.checks['top'].isChecked())
        QTest.mouseClick(panel.exit_sides.checks['top'], Qt.MouseButton.LeftButton)
        self.assertEqual(child.data['exit_sides'], ['top'], 'Não permita remover o último lado.')
        QTest.mouseClick(panel.exit_sides.checks['right'], Qt.MouseButton.LeftButton)
        QTest.mouseClick(panel.exit_sides.checks['top'], Qt.MouseButton.LeftButton)
        self.assertEqual(child.data['exit_sides'], ['right'])
        window.scene.clearSelection()
        parent.setSelected(True)
        window.change_board_ports('entry_sides', 'left', True)
        window.change_board_ports('entry_sides', 'bottom', False)
        edge = next(item for item in window.scene.items() if isinstance(item, BoardConnectorItem))
        self.assertEqual(edge.path().pointAtPercent(0), parent.sceneBoundingRect().center() - QPointF(parent.rect().width() / 2, 0))
        self.assertAlmostEqual(edge.path().pointAtPercent(1).x(), child.data['x'] + child.rect().width())
        saved = window._model_document
        renderer = OrganogramRenderer(saved, [{'Nome': 'A'}])
        self.assertEqual(edge.path(), renderer.paths[(parent.data['id'], child.data['id'])])
        target = self.root / 'portas.fornax'
        save_public_fornax(saved, target)
        reopened = open_public_fornax(target).document()
        self.assertEqual(reopened['organogram']['groups'][0]['entry_sides'], ['left'])
        self.assertEqual(reopened['organogram']['groups'][1]['exit_sides'], ['right'])
        window.undo()
        self.assertIn('bottom', window._board_items()[0].data['entry_sides'])
        window.scene.clearSelection()
        child, other = window._board_items()[1:]
        child.setSelected(True)
        other.setSelected(True)
        window.change_board_ports('exit_sides', 'left', True)
        self.assertTrue(all('left' in item.data['exit_sides'] for item in (child, other)))
        invalid = deepcopy(reopened)
        invalid['organogram']['groups'][0]['entry_sides'] = []
        with self.assertRaises(ModelValidationError):
            normalize_model_document(invalid)

    def test_routes_use_outward_ports_when_superior_is_below_and_avoid_other_blocks(self):
        document = board_document(1, 1)
        parent = document['organogram']['groups'][0]
        parent.update(y=2200)
        child = new_group(document, columns=1, rows=1, y=0)
        document['organogram']['groups'].append(child)
        obstacle = new_group(document, columns=1, rows=1, y=1000)
        board = document['organogram']
        board['groups'].append(obstacle)
        board['connections'] = [{'source': parent['id'], 'target': child['id']}]
        points, crowded = board_routes(board)[(parent['id'], child['id'])]
        self.assertFalse(crowded)
        self.assertGreater(points[1].y(), points[0].y(), 'A entrada inferior deve ser alcançada por fora do superior.')
        self.assertGreater(points[-1].y(), points[-2].y(), 'A saída superior do subordinado precisa apontar para cima.')
        from core.organogram import group_rect
        for a, b in zip(points, points[1:]):
            for i in range(1, 10):
                self.assertFalse(group_rect(obstacle).contains(a + (b - a) * (i / 10)))

    def test_routes_separate_different_superiors_and_allow_shared_trunks(self):
        document = board_document(1, 1)
        board = document['organogram']
        board['groups'] = []
        for x, y in ((0, 0), (1000, 0), (0, 1800), (1000, 1800)):
            board['groups'].append(new_group(document, columns=1, rows=1, card_width_mm=20, x=x, y=y))
        a, b, c, d = board['groups']
        board['connections'] = [{'source': a['id'], 'target': d['id']}, {'source': b['id'], 'target': c['id']}]
        routes = board_routes(board)
        self.assertFalse(any(crowded for _, crowded in routes.values()))
        lines = [routes[(edge['source'], edge['target'])][0] for edge in board['connections']]
        def overlap(first, second):
            for p, q in zip(first, first[1:]):
                for r, s in zip(second, second[1:]):
                    for axis in (0, 1):
                        coords = lambda point: (point.x(), point.y())
                        p0, q0, r0, s0 = map(coords, (p, q, r, s))
                        if abs(p0[axis] - q0[axis]) < 1e-6 and abs(r0[axis] - s0[axis]) < 1e-6 and abs(p0[axis] - r0[axis]) < 1e-6:
                            low = max(min(p0[1-axis], q0[1-axis]), min(r0[1-axis], s0[1-axis]))
                            high = min(max(p0[1-axis], q0[1-axis]), max(r0[1-axis], s0[1-axis]))
                            if high - low > 1e-6:
                                return True
            return False
        self.assertFalse(overlap(*lines))
        board['connections'][1]['source'] = a['id']
        routes = board_routes(board)
        lines = [routes[(edge['source'], edge['target'])][0] for edge in board['connections']]
        self.assertTrue(overlap(*lines), 'Conexões para o mesmo superior podem compartilhar a chegada.')

    def test_rotated_text_boxes_cut_connectors_in_editor_preview_and_vector_pdf(self):
        doc = persistent_model_document(board_document(1, 1))
        board = doc["organogram"]
        parent = board["groups"][0]
        child = new_group(doc, columns=1, rows=1, y=2000, start_row=1)
        board["groups"].append(child)
        board["connections"] = [{"source": parent["id"], "target": child["id"],
                                 "style": {"color": "#ee0000", "width_mm": 2}}]
        center_x = parent["card_w"] / 2
        # Texto pequeno no topo: o centro da caixa fica vazio e deve mostrar o fundo.
        board["boxes"] = [{"x": center_x - 100, "y": 1300, "w": 200, "h": 200,
                           "html": "<p>Texto</p>", "font_size": 10, "rotation": 30,
                           "layer_id": 20, "object_id": "text:20", "rich_text_version": 1}]
        board["shapes"] = [{"x": center_x - 150, "y": 1100, "width": 300, "height": 600,
                            "shape_type": "rectangle", "fill_color": "#33cc77", "layer_id": 21, "object_id": "shape:21"}]
        board["layer_order"] = ["shape:21", "text:20"]
        # Os recortes são polígonos girados, não sua caixa delimitadora.
        holes = text_cutouts(board["boxes"])
        self.assertTrue(holes.contains(QPointF(center_x, 1400)))
        self.assertFalse(holes.contains(QPointF(center_x - 125, 1280)))
        window = self.editor(doc)
        window.switch_model_page("organogram")
        edge = next(item for item in window.scene.items() if isinstance(item, BoardConnectorItem))
        self.assertTrue(edge.cutouts().contains(QPointF(center_x, 1400)))
        self.assertFalse(edge.shape().contains(QPointF(center_x, 1400)))
        self.assertTrue(edge.shape().contains(QPointF(center_x, 1000)))
        # Uma pintura isolada em ARGB prova que é um recorte transparente, não branco.
        image = QImage(700, 2200, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        edge.paint(painter, QStyleOptionGraphicsItem())
        painter.end()
        self.assertEqual(image.pixelColor(round(center_x), 1400).alpha(), 0)
        self.assertGreater(image.pixelColor(round(center_x), 1000).alpha(), 0)
        renderer = OrganogramRenderer(doc, [{"Nome": "A"}, {"Nome": "B"}])
        output = QImage(700, 2200, QImage.Format.Format_ARGB32)
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        renderer.paint(painter)
        painter.end()
        self.assertEqual(output.pixelColor(round(center_x), 1400), QColor("#33cc77"))
        self.assertEqual(output.pixelColor(round(center_x), 1000), QColor("#ee0000"))
        preview = renderer.preview(max_side=2200)
        scale = preview.height() / renderer.bounds.height()
        self.assertEqual(preview.pixelColor(round((center_x - renderer.bounds.left()) * scale),
                                           round((1400 - renderer.bounds.top()) * scale)), QColor("#33cc77"))
        path = self.root / "recorte.pdf"
        renderer.export_pdf(path)
        self.assertIn("Texto", PdfReader(path).pages[0].extract_text())

    def test_copy_paste_keeps_internal_connections_and_undo_removes_whole_copy(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page("organogram")
        first = window._board_items()[0]
        other = window.add_board_group(new_group(window._model_document, columns=1, rows=1, y=2000))
        window.set_board_parent(other.data["id"], first.data["id"])
        window.select_all_items()
        window.copy_selected_items()
        window.paste_copied_items()
        self.assertEqual(len(window._board_items()), 4)
        self.assertEqual(len(window._board_connections_data()), 2)
        window.undo()
        self.assertEqual(len(window._board_items()), 2)
        self.assertEqual(len(window._board_connections_data()), 1)

    def test_workspace_paste_keeps_one_slot_per_row_and_refreshes_entire_chart(self):
        from test_signature_preview import PreviewWorkspace
        from core.fornax_session import FornaxSessionManager
        from PySide6.QtTest import QTest
        target = self.root / "workspace.fornax"
        save_public_fornax(board_document(), target)
        sessions = FornaxSessionManager()
        self.addCleanup(sessions.close)
        sessions.select(target)
        settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        window = PreviewWorkspace(target, sessions, settings)
        def cleanup():
            window._preview_refresh_timer.stop()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(cleanup)
        table = window.table_panel.table
        table.setCurrentCell(0, 1)
        name = window.cached_model_document['organogram']['groups'][0]['name']
        self.app.clipboard().setText("\n".join(f"{name}\tAluno {i}" for i in range(34)))
        table._paste_from_clipboard()
        table.setItem(0, 0, QTableWidgetItem("5"))
        QTest.qWait(200)
        plain, rich = window._scrape_table_data()
        self.assertEqual(len(plain), 34)
        renderer = OrganogramRenderer(window.cached_model_document, plain, rich)
        self.assertEqual(len(renderer.slots), 34)
        self.assertIsNotNone(window.preview_panel.preview._pixmap)
        table.item(0, 2).setText("")
        QTest.qWait(200)
        plain, rich = window._scrape_table_data()
        self.assertEqual(len(OrganogramRenderer(window.cached_model_document, plain, rich).slots), 33)

    def test_editor_can_save_chart_text_without_altering_card(self):
        window = self.editor(board_document(1, 1))
        window.switch_model_page("organogram")
        window.add_new_box()
        window.save_snapshot()
        self.assertEqual(len(window._model_document["organogram"]["boxes"]), 1)
        self.assertEqual(len(window._model_document["pages"][0]["boxes"]), 2)
        persistent_model_document(window._model_document)

    def test_pdf_has_physical_size_searchable_text_and_mosaic_pages(self):
        renderer = OrganogramRenderer(board_document(), [{"Nome": f"Aluno {i}"} for i in range(34)])
        preview = renderer.preview(max_side=1600)
        self.assertTrue(any(channel < 90 for channel in preview.constBits()), "O texto precisa aparecer visualmente, além de existir no PDF.")
        path = self.root / "quadro.pdf"
        renderer.export_pdf(path)
        pdf = PdfReader(path)
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text().replace("\t", " ")
        self.assertIn("Aluno 33", text)
        self.assertNotIn("Aluno 34", text)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width) * 25.4 / 72,
                               renderer.bounds.width() / UNITS_PER_MM, delta=0.5)
        mosaic = self.root / "mosaico.pdf"
        renderer.export_pdf(mosaic, paper=(210, 297))
        pages = PdfReader(mosaic).pages
        self.assertEqual(len(pages), len(renderer.mosaic_regions()))
        self.assertGreater(len(pages), 1)
        self.assertAlmostEqual(float(pages[0].mediabox.width) * 25.4 / 72, 210, delta=0.1)

    def test_links_survive_vector_pdf_and_large_png_is_rejected(self):
        document = board_document(1, 1)
        box = document["pages"][0]["boxes"][0]
        box.update(has_link=True, link_key="URL")
        renderer = OrganogramRenderer(document, [{"Nome": "Pessoa", "URL": "https://example.org"}])
        pdf = self.root / "link.pdf"
        renderer.export_pdf(pdf)
        self.assertEqual(PdfReader(pdf).pages[0]["/Annots"][0].get_object()["/A"]["/URI"], "https://example.org")
        document["organogram"]["groups"][0].update(card_w=12000, card_h=12000)
        large = OrganogramRenderer(document, [{"Nome": "Pessoa"}])
        with self.assertRaisesRegex(ValueError, "PDF"):
            large.export_png(self.root / "large.png", dpi=300)
        self.assertFalse((self.root / "large.png").exists())

    def test_worker_generates_one_board_and_removes_partial_on_error(self):
        worker = OrganogramWorker(board_document(2, 1), [{"Nome": "A"}, {"Nome": "B"}],
                                 [{"Nome": "A"}, {"Nome": "B"}], self.root, "pdf")
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(len(PdfReader(self.root / "organograma.pdf").pages), 1)
        self.assertFalse((self.root / ".organograma.partial.pdf").exists())
        broken = OrganogramWorker(board_document(), [{}], [{}], self.root, "png")
        broken.error_occurred.connect(errors.append)
        broken.run()
        self.assertEqual(len(errors), 1)
        self.assertFalse((self.root / "organograma.png").exists())


if __name__ == "__main__":
    unittest.main()
