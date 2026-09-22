from core.themes import themed_style, theme_color, theme_manager
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QComboBox, QPushButton, QSpinBox)
from PySide6.QtCore import Qt, Signal, QSignalBlocker, QSize
from PySide6.QtGui import QPixmap, QResizeEvent, QImageReader
from pathlib import Path
from core.resources import navigation_icon_path
from core.theme_icons import themed_svg_icon
from core.i18n import tr

class ResizingLabel(QLabel):
    """QLabel que redimensiona a imagem interna automaticamente mantendo proporção."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(200)
        self._pixmap = None

    def set_image_path(self, path: str):
        image_path = Path(path) if path else None
        if not image_path or not image_path.exists():
            self._pixmap = None
            self.setText(tr("Sem imagem"))
            return

        reader = QImageReader(str(image_path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self._pixmap = None
            self.setText(tr("Erro na prévia"))
            return

        self._pixmap = QPixmap.fromImage(image)
        self._update_view()

    def set_pixmap_direct(self, pixmap: QPixmap):
        if not pixmap or pixmap.isNull():
            self._pixmap = None
            self.setText(tr("Erro na prévia"))
        else:
            self._pixmap = pixmap
            self._update_view()

    def set_message(self, text: str):
        self._pixmap = None
        self.setText(text)

    def resizeEvent(self, event: QResizeEvent):
        self._update_view()
        super().resizeEvent(event)

    def _update_view(self):
        if self._pixmap and not self._pixmap.isNull():
            w = self.width()
            h = self.height()
            scaled = self._pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled)
        elif not self.text():
            self.setText(tr("Sem prévia"))

    
class PreviewPanel(QWidget):
    modeChanged = Signal(str)
    indexRequested = Signal(int)
    pageChanged = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.cbo_models = QComboBox()
        self.cbo_models.setMinimumHeight(34)

        self.page_selector = QWidget()
        page_selector_layout = QHBoxLayout(self.page_selector)
        # Repete a folga inferior da navegação para os seletores de face.
        # Como a prévia ocupa o espaço elástico, ela é quem cede esses pixels;
        # o topo do painel continua alinhado com a tabela de dados.
        page_selector_layout.setContentsMargins(0, 8, 0, 8)
        page_selector_layout.setSpacing(5)
        page_selector_layout.addStretch(1)
        self.btn_front = QPushButton(tr("Frente"))
        self.btn_back = QPushButton(tr("Verso"))
        for index, button in enumerate((self.btn_front, self.btn_back)):
            button.setObjectName("previewPageButton")
            button.setCheckable(True)
            button.setFixedSize(76, 22)
            button.clicked.connect(lambda checked=False, value=index: self.pageChanged.emit(value))
            page_selector_layout.addWidget(button)
        page_selector_layout.addStretch(1)
        layout.addWidget(self.page_selector)

        self.preview = ResizingLabel()
        self.preview.setText(tr("Nenhum modelo selecionado"))
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        themed_style(self.preview, "background-color: @canvas@; border-radius: 10px;")
        layout.addWidget(self.preview, 1)

        navigation_bar = QHBoxLayout()
        navigation_bar.setContentsMargins(14, 0, 14, 8)
        navigation_bar.setSpacing(8)

        # Reserva, à esquerda, exatamente o mesmo espaço da ação contextual.
        # Assim os controles de navegação permanecem no centro do preview.
        self.unlock_balance_spacer = QWidget()
        self.unlock_balance_spacer.setObjectName("modelLockBalance")
        self.unlock_balance_spacer.setFixedWidth(144)
        self.unlock_balance_spacer.setEnabled(False)
        navigation_bar.addWidget(self.unlock_balance_spacer)

        navigation_stack = QVBoxLayout()
        navigation_stack.setContentsMargins(0, 0, 0, 0)
        navigation_stack.setSpacing(4)

        page_navigation = QHBoxLayout()
        page_navigation.setContentsMargins(0, 0, 0, 0)
        page_navigation.setSpacing(5)
        page_navigation.addStretch(1)

        self.btn_previous = QPushButton()
        self.btn_previous.setObjectName("previewPrevious")
        self.btn_previous.setFixedSize(24, 22)
        self.btn_previous.setToolTip(tr("Item anterior"))
        page_navigation.addWidget(self.btn_previous)

        self.lbl_navigation_kind = QLabel(tr("Item"))
        self.lbl_navigation_kind.setObjectName("previewNavigationLabel")
        self.lbl_navigation_kind.setFixedWidth(50)
        self.lbl_navigation_kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_navigation.addWidget(self.lbl_navigation_kind)

        self.spin_navigation = QSpinBox()
        self.spin_navigation.setObjectName("previewNavigationIndex")
        self.spin_navigation.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin_navigation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_navigation.setFixedSize(52, 22)
        self.spin_navigation.setRange(1, 1)
        self.spin_navigation.valueChanged.connect(lambda value: self.indexRequested.emit(value - 1))
        page_navigation.addWidget(self.spin_navigation)

        self.lbl_navigation_total = QLabel(tr("de {total}").format(total=0))
        self.lbl_navigation_total.setObjectName("previewNavigationLabel")
        self.lbl_navigation_total.setFixedWidth(50)
        self.lbl_navigation_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_navigation.addWidget(self.lbl_navigation_total)

        self.btn_next = QPushButton()
        self.btn_next.setObjectName("previewNext")
        self.btn_next.setFixedSize(24, 22)
        self.btn_next.setToolTip(tr("Próximo item"))
        page_navigation.addWidget(self.btn_next)
        page_navigation.addStretch(1)
        navigation_stack.addLayout(page_navigation)

        mode_navigation = QHBoxLayout()
        mode_navigation.setContentsMargins(0, 0, 0, 0)
        mode_navigation.addStretch(1)
        self.cbo_preview_mode = QComboBox()
        self.cbo_preview_mode.setObjectName("previewMode")
        self.cbo_preview_mode.addItem(tr("Item"), "item")
        self.cbo_preview_mode.setFixedSize(166, 22)
        self.cbo_preview_mode.currentIndexChanged.connect(self._emit_mode)
        mode_navigation.addWidget(self.cbo_preview_mode)
        mode_navigation.addStretch(1)
        navigation_stack.addLayout(mode_navigation)
        navigation_bar.addLayout(navigation_stack, 1)

        self.unlock_action_slot = QWidget()
        self.unlock_action_slot.setObjectName("modelLockActionSlot")
        self.unlock_action_slot.setFixedWidth(144)
        unlock_action_layout = QHBoxLayout(self.unlock_action_slot)
        unlock_action_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_unlock_model = QPushButton(tr("Desbloquear modelo"))
        self.btn_unlock_model.setObjectName("unlockModel")
        self.btn_unlock_model.setFixedSize(144, 30)
        self.btn_unlock_model.setVisible(False)
        unlock_action_layout.addWidget(self.btn_unlock_model)
        navigation_bar.addWidget(
            self.unlock_action_slot, 0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addLayout(navigation_bar)

        self.btn_previous.clicked.connect(lambda: self.indexRequested.emit(self.spin_navigation.value() - 2))
        self.btn_next.clicked.connect(lambda: self.indexRequested.emit(self.spin_navigation.value()))
        def refresh_navigation_icons():
            self.btn_previous.setIcon(themed_svg_icon(navigation_icon_path("left-arrow")))
            self.btn_previous.setIconSize(QSize(14, 14))
            self.btn_next.setIcon(themed_svg_icon(navigation_icon_path("right-arrow")))
            self.btn_next.setIconSize(QSize(14, 14))
        refresh_navigation_icons()
        manager = theme_manager()
        manager.changed.connect(refresh_navigation_icons)
        def disconnect_navigation_icons():
            try:
                manager.changed.disconnect(refresh_navigation_icons)
            except (RuntimeError, TypeError):
                pass
        self.destroyed.connect(disconnect_navigation_icons)
        self.set_navigation("item", 0, 0, sheet_available=False)
        self.set_page_navigation(1, 0)

    def set_model_lock_state(self, visible: bool, *, unlocked: bool = False):
        """Alterna a ação de segurança sem deslocar a navegação central."""
        self.btn_unlock_model.setVisible(visible)
        self.btn_unlock_model.setEnabled(True)
        self.btn_unlock_model.setText(
            tr("Bloquear modelo") if unlocked else tr("Desbloquear modelo")
        )
        self.btn_unlock_model.setToolTip(
            tr("Remover imediatamente o acesso ao conteúdo protegido") if unlocked else
            tr("Digite a senha para acessar o modelo completo")
        )

    def _emit_mode(self):
        self.modeChanged.emit(self.cbo_preview_mode.currentData() or "item")

    def set_navigation(self, mode: str, index: int, total: int, *, sheet_available: bool):
        current_mode = self.cbo_preview_mode.currentData()
        with QSignalBlocker(self.cbo_preview_mode):
            self.cbo_preview_mode.clear()
            self.cbo_preview_mode.addItem(tr("Item"), "item")
            if sheet_available:
                self.cbo_preview_mode.addItem(tr("Folha de impressão"), "sheet")
            wanted = mode if mode == "item" or sheet_available else "item"
            selected = self.cbo_preview_mode.findData(wanted)
            self.cbo_preview_mode.setCurrentIndex(max(0, selected))

        total = max(0, total)
        index = min(max(0, index), max(0, total - 1))
        with QSignalBlocker(self.spin_navigation):
            self.spin_navigation.setRange(1, max(1, total))
            self.spin_navigation.setValue(index + 1)
        self.lbl_navigation_kind.setText(tr("Folha") if wanted == "sheet" else tr("Item"))
        self.lbl_navigation_total.setText(tr("de {total}").format(total=total))
        self.spin_navigation.setToolTip(
            tr("Número da folha física") if wanted == "sheet" else
            tr("Cada cópia é contada como um item")
        )
        enabled = total > 0
        self.spin_navigation.setEnabled(enabled)
        self.btn_previous.setEnabled(enabled and index > 0)
        self.btn_next.setEnabled(enabled and index + 1 < total)
        if current_mode != wanted:
            self.cbo_preview_mode.setToolTip(
                tr("Visualize um item ou a folha final conforme a predefinição de impressão.")
            )

    def set_page_navigation(self, page_count: int, current_page: int):
        visible = page_count > 1
        self.page_selector.setVisible(visible)
        current_page = 1 if visible and current_page == 1 else 0
        with QSignalBlocker(self.btn_front):
            self.btn_front.setChecked(current_page == 0)
        with QSignalBlocker(self.btn_back):
            self.btn_back.setChecked(current_page == 1)

    def set_preview_text(self, text: str):
        self.preview.set_message(text)

    def set_preview_image(self, path: str):
        self.preview.set_image_path(path)

    def set_preview_pixmap(self, pixmap: QPixmap):
        self.preview.set_pixmap_direct(pixmap)
