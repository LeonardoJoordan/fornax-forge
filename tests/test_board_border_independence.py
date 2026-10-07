"""Cartões, conjuntos e conexões preservam aparência e geometria próprias."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
import unittest

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem
from pypdf import PdfReader

from core.board_borders import (border_style, bordered_group_bounds, card_clip_path,
                                group_border_path, paint_group_borders)
from core.model_document import normalize_model_document, ModelValidationError
from core.organogram import UNITS_PER_MM, slot_rect
from core.fornax_container import (save_public_fornax, open_public_fornax,
                                   save_protected_fornax, unlock_fornax, FULL_MODE)
from features.editor.organogram_editor import BoardConnectorItem
from features.generator.organogram import OrganogramRenderer
import test_organogram as fixtures


class BoardBorderIndependenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    setUp = fixtures.OrganogramTest.setUp
    editor = fixtures.OrganogramTest.editor
    chart_with_three_blocks = fixtures.OrganogramTest.chart_with_three_blocks

    def scope(self, panel, target):
        panel.border_scope.setCurrentIndex(panel.border_scope.findData(target))
        panel.border_scope.activated.emit(panel.border_scope.currentIndex())

    def test_scope_changes_actual_visible_borders_and_keeps_each_saved_appearance(self):
        document = fixtures.board_document(1, 1)
        group = document['organogram']['groups'][0]
        group['border'] = {
            'cards': True, 'group': True, 'target': 'both', 'padding_mm': 4,
            'cards_position': 'outside', 'group_position': 'outside',
            'cards_style': {'color': '#ff0000', 'width_mm': 1, 'radius_mm': 0},
            'group_style': {'color': '#0000ff', 'width_mm': 1, 'radius_mm': 0},
        }
        appearance_keys = ('color', 'width_mm', 'radius_mm', 'opacity', 'join', 'corner_radii_mm')
        expected_styles = {target: {key: border_style(group, target).get(key) for key in appearance_keys}
                           for target in ('cards', 'group')}
        window = self.editor(document)
        window.switch_model_page('organogram')
        item = window._board_items()[0]
        identifier = item.data['id']
        item.setSelected(True)
        panel = window.organogram_panel

        def verify(target):
            item = next(item for item in window._board_items() if item.data['id'] == identifier)
            item.setSelected(True)
            self.assertEqual(item.data['border']['cards'], target in ('cards', 'both'))
            self.assertEqual(item.data['border']['group'], target in ('group', 'both'))
            self.assertEqual(panel.border_scope.currentData(), target)
            for part in ('cards', 'group'):
                actual = {key: border_style(item.data, part).get(key) for key in appearance_keys}
                self.assertEqual(actual, expected_styles[part])
            # Confere a saída real: vermelho no cartão e azul no conjunto.
            renderer = OrganogramRenderer(window._model_document, [{'Nome': 'Ana'}])
            image = renderer.preview(max_side=1600)
            def pixel(x_mm):
                x = round((x_mm * UNITS_PER_MM - renderer.bounds.left()) * image.width() / renderer.bounds.width())
                y = round((item.data['card_h'] / 2 - renderer.bounds.top()) * image.height() / renderer.bounds.height())
                return image.pixelColor(x, y)
            self.assertEqual(pixel(-.5), QColor('red' if target in ('cards', 'both') else 'white'))
            self.assertEqual(pixel(-4.5), QColor('blue' if target in ('group', 'both') else 'white'))

        for target in ('cards', 'both', 'group', 'both'):
            with self.subTest(target=target):
                self.scope(panel, target)
                verify(target)
        window.undo()
        verify('group')
        window.redo()
        verify('both')
        path = self.root / 'aplicacao-contornos.fornax'
        save_public_fornax(window._model_document, path)
        window._load_document_into_scene(open_public_fornax(path).document())
        window.switch_model_page('organogram')
        window._board_items()[0].setSelected(True)
        verify('both')

    def test_scope_change_preserves_disabled_blocks_in_a_mixed_selection(self):
        window, first, second, third = self.chart_with_three_blocks()
        window.scene.clearSelection()
        second.setSelected(True)
        window.change_board_border(cards=True, color='#0000ff')
        first.setSelected(True)
        self.scope(window.organogram_panel, 'group')
        self.assertFalse(first.data['border']['cards'])
        self.assertFalse(first.data['border']['group'])
        self.assertFalse(second.data['border']['cards'])
        self.assertTrue(second.data['border']['group'])
        self.assertNotIn('border', third.data)
        self.scope(window.organogram_panel, 'both')
        self.assertFalse(first.data['border']['cards'])
        self.assertFalse(first.data['border']['group'])
        self.assertTrue(second.data['border']['cards'])
        self.assertTrue(second.data['border']['group'])
        self.assertEqual(border_style(second.data, 'cards')['color'], '#0000ff')

    def test_sidebar_edits_three_colors_independently_and_preserves_them_in_files(self):
        window, parent, child, _other = self.chart_with_three_blocks()
        window.set_board_parent(child.data['id'], parent.data['id'])
        window.scene.clearSelection()
        parent.setSelected(True)
        panel = window.organogram_panel
        panel.border_enabled.click()
        panel.border_color_hex.setText('#ff0000')
        panel.border_color_hex.editingFinished.emit()
        window.change_board_border(width_mm=1, radius_mm=6)
        card = deepcopy(border_style(parent.data, 'cards'))
        self.scope(panel, 'group')
        self.assertFalse(parent.data['border']['cards'])
        self.assertTrue(parent.data['border']['group'])
        panel.border_color_hex.setText('#0000ff')
        panel.border_color_hex.editingFinished.emit()
        window.change_board_border(width_mm=2, opacity=.6, radius_mm=20, padding_mm=5)
        self.assertEqual(border_style(parent.data, 'cards')['color'], card['color'])
        self.assertEqual(border_style(parent.data, 'cards')['width_mm'], card['width_mm'])
        self.assertEqual(border_style(parent.data, 'cards')['radius_mm'], card['radius_mm'])
        self.assertEqual(border_style(parent.data, 'cards')['opacity'], card['opacity'])
        self.scope(panel, 'cards')
        self.assertEqual(panel.border_color_hex.text(), '#FF0000')
        self.assertEqual(panel.border_width.value(), 1)
        panel.border_enabled.click()
        self.assertFalse(parent.data['border']['cards'])
        self.assertFalse(parent.data['border']['group'])
        panel.border_enabled.click()
        self.scope(panel, 'both')
        expected = deepcopy(parent.data['border'])
        window.change_board_border(color='#ffff00')
        window.undo()
        parent = next(item for item in window._board_items() if item.data['id'] == parent.data['id'])
        self.assertEqual(parent.data['border'], expected)
        window.scene.clearSelection()
        edge = next(item for item in window.scene.items() if isinstance(item, BoardConnectorItem))
        edge.setSelected(True)
        panel.color_hex.setText('#00ff00')
        panel.color_hex.editingFinished.emit()
        self.assertEqual(parent.data['border'], expected)
        self.assertEqual(edge.board_edge['style']['color'], '#00ff00')
        document = window._model_document
        for mode in ('public', 'protected'):
            with self.subTest(mode=mode):
                path = self.root / f'{mode}.fornax'
                if mode == 'public':
                    save_public_fornax(document, path)
                    reopened = open_public_fornax(path).document()
                else:
                    save_protected_fornax(document, path, password='teste-bordas', mode=FULL_MODE)
                    reopened = unlock_fornax(path, 'teste-bordas').document()
                self.assertEqual(reopened['organogram']['groups'][0]['border'], expected)
                self.assertEqual(reopened['organogram']['connections'][0]['style']['color'], '#00ff00')
        rows = [{'Nome': 'Diretor', '__board_block__': parent.data['name']},
                {'Nome': 'Equipe', '__board_block__': child.data['name']}]
        renderer = OrganogramRenderer(document, rows)
        pdf = self.root / 'cores.pdf'
        renderer.export_pdf(pdf)
        operations = PdfReader(pdf).pages[0].get_contents().operations
        colors = [list(args) for args, op in operations if op in (b'RG', b'rg', b'SCN', b'scn')]
        for rgb in ([1, 0, 0], [0, 0, 1], [0, 1, 0]):
            self.assertIn(rgb, colors)

    def test_switching_contours_keeps_individual_corners_positions_and_transparency(self):
        window, item, _second, _third = self.chart_with_three_blocks()
        window.scene.clearSelection()
        item.setSelected(True)
        panel = window.organogram_panel
        panel.border_enabled.click()
        window.change_board_border(radius_mm=4, corner_radii_linked=False)
        window.change_board_corner_radii({'top_left': 8}, linked=False)
        self.scope(panel, 'group')
        window.change_board_border(opacity=.25, radius_mm=12)
        window.change_board_corner_radii({'bottom_right': 3}, linked=False)
        window.change_board_border_position('center')
        group_style = deepcopy(border_style(item.data, 'group'))
        self.scope(panel, 'cards')
        self.assertEqual(panel.border_corners.spins['top_left'].value(), 8)
        self.assertEqual(panel.border_corners.spins['bottom_right'].value(), 4)
        self.assertEqual(panel.border_opacity.value(), 100)
        self.assertEqual(panel.border_position.currentData(), 'inside')
        window.change_board_border(radius_mm=0)
        window.change_board_border_position('outside')
        self.scope(panel, 'group')
        self.assertEqual(panel.border_corners.spins['bottom_right'].value(), 3)
        self.assertEqual(panel.border_position.currentData(), 'center')
        self.assertEqual(panel.border_opacity.value(), 25)
        self.assertEqual(border_style(item.data, 'cards')['radius_mm'], 0)
        self.assertNotIn('corner_radii_mm', border_style(item.data, 'cards'))
        self.assertEqual(border_style(item.data, 'group')['corner_radii_mm'], group_style['corner_radii_mm'])
        self.scope(panel, 'both')
        window.change_board_corner_radii({'top_left': 5}, linked=False)
        for target in ('cards', 'group'):
            self.assertEqual(border_style(item.data, target)['corner_radii_mm']['top_left'], 5)
        self.assertEqual(border_style(item.data, 'cards')['corner_radii_mm']['bottom_right'], 0)
        self.assertEqual(border_style(item.data, 'group')['corner_radii_mm']['bottom_right'], 3)

    def test_legacy_border_keeps_both_styles_and_rejects_invalid_individual_styles(self):
        document = fixtures.board_document(1, 1)
        group = document['organogram']['groups'][0]
        group['border'] = {'cards': True, 'group': True, 'color': '#aa2255',
                           'width_mm': 2, 'radius_mm': 5, 'opacity': .6}
        original = deepcopy(group['border'])
        reopened = normalize_model_document(document)
        self.assertEqual(reopened['organogram']['groups'][0]['border'], original)
        for target in ('cards', 'group'):
            self.assertEqual(border_style(group, target)['color'], '#aa2255')
        for bad in (None, {'color': 'invalid'}, {'opacity': 2}, {'width_mm': -1},
                    {'corner_radii_mm': {'top_left': float('nan')}}, {'cards': True}):
            with self.subTest(bad=bad):
                invalid = deepcopy(document)
                invalid['organogram']['groups'][0]['border']['cards_style'] = bad
                with self.assertRaises(ModelValidationError):
                    normalize_model_document(invalid)

    def test_rounded_card_clips_actual_card_content_in_editor_preview_png_and_pdf(self):
        document = fixtures.board_document(1, 1)
        group = document['organogram']['groups'][0]
        group['border'] = {'cards': True, 'cards_position': 'outside',
                           'color': '#ff0000', 'width_mm': 1,
                           'corner_radii_mm': {'top_left': 20, 'top_right': 0,
                                               'bottom_left': 0, 'bottom_right': 0}}
        window = self.editor(document)
        window.switch_model_page('organogram')
        item = window._board_items()[0]
        renderer = OrganogramRenderer(document, [{'Nome': 'Ana'}])
        bounds = renderer.bounds
        editor = QImage(round(bounds.width()), round(bounds.height()), QImage.Format.Format_ARGB32)
        editor.fill(Qt.GlobalColor.white)
        painter = QPainter(editor)
        painter.translate(-bounds.topLeft())
        item.paint(painter, QStyleOptionGraphicsItem())
        painter.end()
        preview = renderer.preview(max_side=1200)
        path = self.root / 'cartao.png'
        renderer.export_png(path, dpi=150)
        def pixel(image, x, y):
            return image.pixelColor(round((x - bounds.left()) * image.width() / bounds.width()),
                                    round((y - bounds.top()) * image.height() / bounds.height()))
        for image in (editor, preview, QImage(str(path))):
            self.assertEqual(pixel(image, 8, 8), QColor('white'))
            self.assertEqual(pixel(image, group['card_w'] - 8, 8), QColor('#dcecf4'))
            self.assertEqual(pixel(image, group['card_w'] / 2, 100), QColor('#dcecf4'))
        clip = card_clip_path(group, slot_rect(group, 0))
        self.assertFalse(clip.contains(QPointF(8, 8)))
        self.assertTrue(clip.contains(QPointF(group['card_w'] - 8, 8)))
        pdf = self.root / 'cartao.pdf'
        renderer.export_pdf(pdf)
        operations = PdfReader(pdf).pages[0].get_contents().operations
        self.assertTrue(any(op in (b'W', b'W*') for _args, op in operations))
        self.assertIn('Ana', PdfReader(pdf).pages[0].extract_text())

    def test_group_radius_and_thick_internal_stroke_never_cover_cards(self):
        group = fixtures.board_document(1, 1)['organogram']['groups'][0]
        for position in ('inside', 'center', 'outside'):
            for width, padding in ((.3, 2), (20, 0), (20, 2)):
                with self.subTest(position=position, width=width, padding=padding):
                    group['border'] = {'group': True, 'group_position': position,
                                       'width_mm': width, 'padding_mm': padding,
                                       'radius_mm': 1000, 'color': '#ff0000'}
                    bounds = bordered_group_bounds(group).adjusted(-2, -2, 2, 2)
                    image = QImage(round(bounds.width()) + 1, round(bounds.height()) + 1, QImage.Format.Format_ARGB32)
                    image.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(image)
                    painter.translate(-bounds.topLeft())
                    paint_group_borders(painter, group, [slot_rect(group, 0)])
                    painter.end()
                    for x in (2, 20, group['card_w'] / 2, group['card_w'] - 2):
                        for y in (2, 20, group['card_h'] / 2, group['card_h'] - 2):
                            self.assertEqual(image.pixelColor(round(x - bounds.left()), round(y - bounds.top())).alpha(), 0)
        # O limite considera também a expansão externa do contorno do cartão.
        group['border'] = {'cards': True, 'group': True, 'cards_position': 'outside',
                           'padding_mm': 2, 'cards_style': {'width_mm': 3},
                           'group_style': {'radius_mm': 1000, 'width_mm': .3}}
        group['border']['group_style']['radius_mm'] = 0
        square = group_border_path(group)
        group['border']['group_style']['radius_mm'] = 1000
        self.assertEqual(group_border_path(group), square)


if __name__ == '__main__':
    unittest.main()
