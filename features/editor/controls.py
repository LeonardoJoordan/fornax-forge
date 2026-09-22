"""Criação dos controles funcionais usados pelo editor."""

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QGraphicsItem, QGraphicsOpacityEffect, QGraphicsScene,
    QGraphicsView, QListWidget, QPushButton,
)

from core.custom_widgets import MathDoubleSpinBox
from core.themes import theme_color

from .canvas_items import BackgroundItem, SelectionTransformFrame, mm_to_px
from .properties import CaixaDeTextoPanel, EditorDeTextoPanel


def initialize_editor_controls(window):
    """Cria somente os controles consumidos pela interface atual."""
    window.btn_toggle_guides = QPushButton(window)
    window.btn_toggle_guides.setCheckable(True)
    window.btn_toggle_guides.setChecked(True)
    window.btn_toggle_guides.toggled.connect(window.toggle_guides_visibility)
    window.op_eye = QGraphicsOpacityEffect(window.btn_toggle_guides)
    window.btn_toggle_guides.setGraphicsEffect(window.op_eye)
    window.op_eye.setOpacity(1.0)

    window.btn_lock_guides = QPushButton(window)
    window.btn_lock_guides.setCheckable(True)
    window.btn_lock_guides.toggled.connect(window.toggle_guides_lock)
    window.op_lock = QGraphicsOpacityEffect(window.btn_lock_guides)
    window.btn_lock_guides.setGraphicsEffect(window.op_lock)
    window.op_lock.setOpacity(0.2)

    window.btn_add = QPushButton(window)
    window.btn_add.clicked.connect(window.add_new_box)
    window.btn_add_img = QPushButton(window)
    window.btn_add_img.clicked.connect(window._on_click_add_image)
    window.btn_add_sig = QPushButton(window)
    window.btn_add_sig.clicked.connect(window._on_click_add_signature)

    window.btn_undo = QPushButton(window)
    window.btn_undo.setEnabled(False)
    window.btn_undo.clicked.connect(window.undo)
    window.btn_redo = QPushButton(window)
    window.btn_redo.setEnabled(False)
    window.btn_redo.clicked.connect(window.redo)
    window.btn_ren_layer = QPushButton(window)
    window.btn_ren_layer.setEnabled(False)
    window.btn_ren_layer.clicked.connect(lambda: window.rename_layer())
    window.btn_dup_layer = QPushButton(window)
    window.btn_dup_layer.clicked.connect(window.duplicate_selected)
    window.btn_group_layer = QPushButton(window)
    window.btn_group_layer.setEnabled(False)
    window.btn_group_layer.clicked.connect(window.toggle_selected_group)
    window.btn_del_layer = QPushButton(window)
    window.btn_del_layer.clicked.connect(window.delete_selected_items)

    window.layer_list = QListWidget(window)
    window.layer_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    window.layer_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    window.layer_list.itemSelectionChanged.connect(window._on_layer_selection_changed)
    window.layer_list.itemChanged.connect(window._on_layer_item_changed)
    window.layer_list.itemDoubleClicked.connect(window.rename_layer)
    window.layer_list.model().rowsMoved.connect(window._on_layer_reordered)

    window.scene = QGraphicsScene(0, 0, 1000, 1000, window)
    window._document_rect = QRectF(0, 0, 1000, 1000)
    window.scene._document_rect = QRectF(window._document_rect)
    window.view = QGraphicsView(window.scene, window)
    window.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
    window.view.setRenderHint(QPainter.RenderHint.Antialiasing)
    window.view.setBackgroundBrush(QBrush(QColor(theme_color('canvas'))))
    window.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    window.view.setRubberBandSelectionMode(Qt.ItemSelectionMode.ContainsItemShape)
    window.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    window.view.installEventFilter(window)
    window.view.viewport().installEventFilter(window)

    window._selection_frame = SelectionTransformFrame(window)
    window.scene.addItem(window._selection_frame)
    window.scene._multi_selection_active = False
    window._selection_frame_timer = QTimer(window)
    window._selection_frame_timer.setSingleShot(True)
    window._selection_frame_timer.timeout.connect(window._refresh_selection_frame)

    window.bg_item = None
    window.background_path = None
    window._space_pan_items = []
    window.fallback_bg = window.scene.addRect(
        0, 0, 1000, 1000, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.white)
    )
    window.fallback_bg.setZValue(-200)
    window.bg_item = BackgroundItem(None)
    window.bg_item.resize_custom(mm_to_px(148.0), mm_to_px(105.0))
    window.bg_item.setPos(0, 0)
    window.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    window.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
    window.bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    window.scene.addItem(window.bg_item)

    window.spin_pos_x = MathDoubleSpinBox(window)
    window.spin_pos_y = MathDoubleSpinBox(window)
    for control in (window.spin_pos_x, window.spin_pos_y):
        control.setRange(-5000, 20000)
        control.setDecimals(2)
        control.setKeyboardTracking(False)
        control.setEnabled(False)
    window.spin_pos_x.valueChanged.connect(window.apply_position_x)
    window.spin_pos_x.editingFinished.connect(window.save_snapshot)
    window.spin_pos_y.valueChanged.connect(window.apply_position_y)
    window.spin_pos_y.editingFinished.connect(window.save_snapshot)

    window.spin_phys_w = MathDoubleSpinBox(window)
    window.spin_phys_h = MathDoubleSpinBox(window)
    for control, value in ((window.spin_phys_w, 148.0), (window.spin_phys_h, 105.0)):
        control.setRange(10.0, 1000.0)
        control.setDecimals(2)
        control.setKeyboardTracking(False)
        control.setValue(value)
    window.spin_phys_w.valueChanged.connect(window._on_doc_w_changed)
    window.spin_phys_h.valueChanged.connect(window._on_doc_h_changed)
    window.spin_phys_w.editingFinished.connect(window.save_snapshot)
    window.spin_phys_h.editingFinished.connect(window.save_snapshot)
    window._doc_aspect_ratio = 148.0 / 105.0

    window.chk_doc_proporcao = QPushButton(window)
    window.chk_doc_proporcao.setCheckable(True)
    window.chk_doc_proporcao.setChecked(True)
    window.chk_doc_proporcao.toggled.connect(window._on_doc_proportion_toggled)
    window.op_doc_proporcao = QGraphicsOpacityEffect(window.chk_doc_proporcao)
    window.chk_doc_proporcao.setGraphicsEffect(window.op_doc_proporcao)
    window.op_doc_proporcao.setOpacity(1.0)
    window._refresh_doc_proportion_button()

    window.caixa_texto_panel = CaixaDeTextoPanel()
    window.caixa_texto_panel.setParent(window)
    window.caixa_texto_panel.hide()
    window.caixa_texto_panel.setEnabled(False)
    window.caixa_texto_panel.widthChanged.connect(window.update_width)
    window.caixa_texto_panel.heightChanged.connect(window.update_height)
    window.caixa_texto_panel.rotationChanged.connect(window.update_rotation)
    window.caixa_texto_panel.proportionToggled.connect(window.update_proportion_lock)
    window.caixa_texto_panel.linkToggled.connect(window.update_link_state)
    window.caixa_texto_panel.restoreRequested.connect(window.restore_item_state)
    window.caixa_texto_panel.opacityChanged.connect(window.update_opacity)
    window.caixa_texto_panel.snapshotRequested.connect(window.save_snapshot)

    window.lst_placeholders = QListWidget(window)
    window.lst_placeholders.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    window.lst_placeholders.setDefaultDropAction(Qt.DropAction.MoveAction)
    window.lst_placeholders.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.lst_placeholders.model().rowsMoved.connect(lambda: window.save_snapshot())

    window.editor_texto_panel = EditorDeTextoPanel()
    window.editor_texto_panel.setParent(window)
    window.editor_texto_panel.hide()
    window.editor_texto_panel.setEnabled(False)
    window.editor_texto_panel.htmlChanged.connect(window.update_text_html)
    window.editor_texto_panel.htmlChanged.connect(window._on_content_updated)
    window.editor_texto_panel.fontFamilyChanged.connect(window.update_font_family)
    window.editor_texto_panel.fontSizeChanged.connect(window.update_font_size)
    window.editor_texto_panel.fontColorChanged.connect(window.update_font_color)
    window.editor_texto_panel.alignChanged.connect(window.update_align)
    window.editor_texto_panel.verticalAlignChanged.connect(window.update_vertical_align)
    window.editor_texto_panel.indentChanged.connect(window.update_indent)
    window.editor_texto_panel.lineHeightChanged.connect(window.update_line_height)
    window.editor_texto_panel.snapshotRequested.connect(window.save_snapshot)

    window.btn_save = QPushButton(window)
    window.btn_save.clicked.connect(window.export_to_json)
