from core.themes import themed_style
from core.dialog_buttons import get_text as dialog_get_text, style_dialog_button_box
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                               QPushButton, QHBoxLayout, QGridLayout,
                               QDialogButtonBox, QGroupBox, QDoubleSpinBox,
                               QWidget, QScrollArea, QTabWidget,
                               QComboBox, QMessageBox)
from copy import deepcopy
from PySide6.QtCore import Qt
from .output_layout import from_legacy_preset, effective_settings
from .preset_warnings import warning_display_name, warning_tooltip, with_model_ratio_snapshot
from core.i18n import tr

class ConfigDialog(QDialog):
    def __init__(self, parent, model_slug: str, available_vars: list[str],
                 current_pattern: str = "", model_size_px: tuple[int, int] = (1000, 1000),
                 model_print_size_mm: tuple[float, float] = None,
                 current_imposition: dict = None, tile_renderer=None, current_tiling=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Configurar saída"))

        self.model_slug = model_slug
        self.result_pattern = current_pattern
        self.model_w, self.model_h = model_size_px
        fallback_w_mm = (self.model_w / 300.0) * 25.4
        fallback_h_mm = (self.model_h / 300.0) * 25.4
        if model_print_size_mm and model_print_size_mm[0] > 0 and model_print_size_mm[1] > 0:
            self.model_print_w_mm, self.model_print_h_mm = model_print_size_mm
        else:
            self.model_print_w_mm, self.model_print_h_mm = fallback_w_mm, fallback_h_mm

        self.imposition_settings = current_imposition or {
            "enabled": False, "sheet_w_mm": 210.0, "sheet_h_mm": 297.0,
            "crop_marks": True, "bleed_margin": True, "target_w_mm": 0, "target_h_mm": 0,
            "presets": {}, "active_preset_name": ""
        }
        self.presets = deepcopy(self.imposition_settings.get("presets", {}) or {})
        self._initial_tiling = current_tiling or {}
        self.tiling_panel = None
        self.active_preset_name = self.imposition_settings.get("active_preset_name", "") or self.SYSTEM_PRESET_NAME
        if self.active_preset_name not in self.presets:
            self.active_preset_name = self.SYSTEM_PRESET_NAME

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        # --- ABA 1: Nomenclatura ---
        tab_naming = QWidget()
        ly_naming = QVBoxLayout(tab_naming)
        ly_naming.setSpacing(15)
        ly_naming.setContentsMargins(15, 15, 15, 15)

        lbl_patern_title = QLabel(tr("<b>Padrão de nomenclatura:</b>"))
        lbl_patern_title.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        lbl_patern_title.setToolTip(tr("Define o nome dos arquivos usando campos como {Nome}."))
        ly_naming.addWidget(lbl_patern_title)
        ly_preview = QHBoxLayout()

        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText(tr("Ex.: {modelo}_{nome}"))
        self.txt_pattern.setText(current_pattern)
        self.txt_pattern.setMinimumHeight(34)

        lbl_ext = QLabel(".png / .jpg / .pdf")
        themed_style(lbl_ext, "font-size: 14px; opacity: 0.7;")

        ly_preview.addWidget(self.txt_pattern)
        ly_preview.addWidget(lbl_ext)
        ly_naming.addLayout(ly_preview)

        lbl_vars_title = QLabel(tr("Variáveis disponíveis:"))
        lbl_vars_title.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        lbl_vars_title.setToolTip(tr("Clique em um campo para inseri-lo no padrão de nomenclatura."))
        ly_naming.addWidget(lbl_vars_title)
        grid_vars = QGridLayout()
        col, row = 0, 0
        if not available_vars:
            ly_naming.addWidget(QLabel(tr("<i>(Nenhuma coluna encontrada)</i>")))
        else:
            for var in available_vars:
                btn = QPushButton(f"{{{var}}}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(30)
                btn.setToolTip(tr("Inserir este campo no padrão de nomenclatura"))
                btn.clicked.connect(lambda checked, v=var: self._insert_variable(v))
                grid_vars.addWidget(btn, row, col)
                col += 1
                if col > 3: col, row = 0, row + 1
            ly_naming.addLayout(grid_vars)
        naming_group = QGroupBox(tr("Nomenclatura"))
        naming_layout = QVBoxLayout(naming_group)
        naming_layout.setContentsMargins(8, 10, 8, 8)
        naming_layout.addWidget(tab_naming)
        naming_layout.addStretch(1)
        naming_scroll = QScrollArea()
        naming_scroll.setWidgetResizable(True)
        naming_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        naming_scroll.setWidget(naming_group)

        # Banner de Aviso para Hiperlinks
        self.lbl_link_warning = QLabel(tr("⚠️ Links ativos detectados. Use PDF por item para preservá-los."))
        themed_style(self.lbl_link_warning, "color: @warning@; font-weight: bold; padding: 5px; border: 1px solid @warning@; border-radius: 4px;")
        self.lbl_link_warning.setVisible(False)
        ly_naming.insertWidget(0, self.lbl_link_warning)

        # --- ABA 2: Impressão e Imposição ---
        tab_print = QWidget()
        ly_print = QVBoxLayout(tab_print)
        ly_print.setSpacing(10)

        # --- PRESETS UI (No topo da aba de Impressão) ---
        ly_presets_v = QVBoxLayout()
        ly_combo_row = QHBoxLayout()
        self.cmb_presets = QComboBox()
        self.cmb_presets.currentIndexChanged.connect(self._on_preset_selected)
        lbl_preset = QLabel(tr("<b>Predefinição:</b>"))
        lbl_preset.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        lbl_preset.setToolTip(tr("Selecionar ou gerenciar configurações de saída salvas"))
        ly_combo_row.addWidget(lbl_preset)
        self._preset_combo_base_tooltip = tr("Selecionar uma predefinição de saída")
        self.cmb_presets.setToolTip(self._preset_combo_base_tooltip)
        ly_combo_row.addWidget(self.cmb_presets, 1)

        ly_buttons_row = QHBoxLayout()
        self.btn_new_preset = QPushButton(tr("Criar nova predefinição"))
        self.btn_new_preset.clicked.connect(self._save_new_preset)
        self.btn_rename_preset = QPushButton(tr("Renomear"))
        self.btn_rename_preset.clicked.connect(self._rename_preset)
        self.btn_del_preset = QPushButton(tr("Excluir"))
        self.btn_del_preset.clicked.connect(self._delete_preset)

        ly_buttons_row.addWidget(self.btn_new_preset)
        ly_buttons_row.addStretch()
        ly_buttons_row.addWidget(self.btn_rename_preset)
        ly_buttons_row.addWidget(self.btn_del_preset)

        ly_presets_v.addLayout(ly_combo_row)
        ly_presets_v.addLayout(ly_buttons_row)
        ly_print.addLayout(ly_presets_v)
        ly_print.addSpacing(10) # Respiro visual

        from .tiling_panel import TilingPanel
        if tile_renderer is None:
            from .tiled_document import PageTilingRenderer
            tile_renderer = PageTilingRenderer(dict(canvas_size=dict(w=self.model_w, h=self.model_h),
                target_w_mm=self.model_print_w_mm, target_h_mm=self.model_print_h_mm))
        self._tile_renderer = tile_renderer
        initial = self._initial_tiling
        if initial.get('tiling') and initial.get('layout_mode') != 'auto':
            # A opção antiga de ladrilhos era independente do preset de cartões.
            # Salve a conversão como outra predefinição, preservando a anterior.
            self.active_preset_name = self.SYSTEM_PRESET_NAME
        if not (initial.get('tiling') or initial.get('layout_mode') == 'auto'):
            initial = self._preset_configuration(self.active_preset_name)
        self.resize(980, 740)
        self.tiling_panel = TilingPanel(tile_renderer, initial=initial, automatic=True)
        ly_print.addWidget(self.tiling_panel)
        output_group = QGroupBox(tr("Disposição dos arquivos"))
        output_layout = QVBoxLayout(output_group)
        output_layout.addWidget(tab_print)
        self.tabs.addTab(output_group, tr('Disposição'))
        self.tabs.addTab(naming_scroll, tr('Nomes dos arquivos'))
        self._load_presets_ui()

        # Botões
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self._on_accept)
        self.buttonBox.rejected.connect(self.reject)
        style_dialog_button_box(self.buttonBox)
        main_layout.addWidget(self.buttonBox)

        self.tiling_panel.changed.connect(self._update_capacity_preview)
        # Enter nos campos confirma a edição, sem acionar o botão do diálogo.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self._update_capacity_preview()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus = self.focusWidget()
            if isinstance(focus, (QLineEdit, QDoubleSpinBox, QComboBox)):
                if self.tiling_panel:
                    self.tiling_panel.interpret_controls()
                event.accept()
                return
            if isinstance(focus, QPushButton) and focus.isEnabled():
                focus.click()
                event.accept()
                return
        super().keyPressEvent(event)

    def get_pattern(self):
        return self.result_pattern

    def get_tiling_settings(self):
        return effective_settings(self._tile_renderer.document, self.tiling_panel.configuration())

    def get_imposition_settings(self):
        layout = self.tiling_panel.output_layout
        settings = dict(layout.imposition or {}) if layout else {}
        settings.setdefault('enabled', False)
        settings.update(presets=deepcopy(self.presets), active_preset_name=self.active_preset_name)
        return settings

    def _preset_configuration(self, name):
        if name == self.SYSTEM_PRESET_NAME:
            return dict(layout_mode='auto', enabled=False, paper_index=0, paper=[210, 297],
                        target_size_mm=[self._tile_renderer.bounds.width() / (300 / 25.4),
                                        self._tile_renderer.bounds.height() / (300 / 25.4)])
        return from_legacy_preset(self.presets.get(name, {}), self._tile_renderer.bounds)

    def _update_capacity_preview(self):
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.tiling_panel.valid)

    def _on_accept(self):
        self.tiling_panel.interpret_controls()
        if not self.tiling_panel.valid:
            return
        if self.active_preset_name == self.SYSTEM_PRESET_NAME and self.tiling_panel.tiling.isChecked():
            name, ok = dialog_get_text(self, tr("Configurações personalizadas"),
                tr("Dê um nome para salvar esta predefinição:"), QLineEdit.EchoMode.Normal, tr("Personalizada"))
            new_name = name.strip() if ok and name.strip() else "Personalizada"
            if new_name == self.SYSTEM_PRESET_NAME:
                new_name = "Personalizada"
            final_name, counter = new_name, 2
            while final_name in self.presets:
                final_name = f"{new_name} {counter}"
                counter += 1
            self.active_preset_name = final_name
        if self.active_preset_name != self.SYSTEM_PRESET_NAME:
            self.presets[self.active_preset_name] = self._get_current_settings()
        self.result_pattern = self.txt_pattern.text().strip()
        self.accept()

    SYSTEM_PRESET_NAME = "Definição do Modelo"

    def _load_presets_ui(self):
        self.cmb_presets.blockSignals(True)
        self.cmb_presets.clear()

        self.cmb_presets.addItem(tr(self.SYSTEM_PRESET_NAME), self.SYSTEM_PRESET_NAME)

        user_presets = sorted(k for k in self.presets.keys() if k != self.SYSTEM_PRESET_NAME)
        for name in user_presets:
            preset = self.presets.get(name, {}) or {}
            label = warning_display_name(name, preset, self.model_print_w_mm, self.model_print_h_mm)
            self.cmb_presets.addItem(label, name)
            idx = self.cmb_presets.count() - 1
            tooltip = warning_tooltip(name, preset, self.model_print_w_mm, self.model_print_h_mm)
            if tooltip:
                self.cmb_presets.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)

        if self.active_preset_name and self.active_preset_name in self.presets:
            idx = self.cmb_presets.findData(self.active_preset_name, Qt.ItemDataRole.UserRole)
            if idx >= 0:
                self.cmb_presets.setCurrentIndex(idx)
            else:
                self.cmb_presets.setCurrentIndex(0)
                self.active_preset_name = self.SYSTEM_PRESET_NAME
        else:
            self.cmb_presets.setCurrentIndex(0)
            self.active_preset_name = self.SYSTEM_PRESET_NAME

        is_system = (self.active_preset_name == self.SYSTEM_PRESET_NAME)
        self.btn_rename_preset.setEnabled(not is_system)
        self.btn_del_preset.setEnabled(not is_system)

        self.cmb_presets.blockSignals(False)
        self._refresh_preset_combo_tooltip()

    def _on_preset_selected(self, index):
        if index < 0 or not self.tiling_panel:
            return
        self.active_preset_name = self._preset_name_at(index)
        self.tiling_panel.apply_configuration(self._preset_configuration(self.active_preset_name))
        is_system = self.active_preset_name == self.SYSTEM_PRESET_NAME
        self.btn_rename_preset.setEnabled(not is_system)
        self.btn_del_preset.setEnabled(not is_system)
        self._refresh_preset_combo_tooltip()

    def _get_current_settings(self):
        self.tiling_panel.interpret_controls()
        config = self.tiling_panel.configuration()
        settings = dict(enabled=config['enabled'], sheet_w=config['paper'][0], sheet_h=config['paper'][1],
                        w=config['target_size_mm'][0], h=config['target_size_mm'][1],
                        crop=config['crop_marks'], bleed=config['margin_enabled'], output_layout=config)
        return with_model_ratio_snapshot(settings, self.model_print_w_mm, self.model_print_h_mm)

    def _preset_name_at(self, index):
        name = self.cmb_presets.itemData(index, Qt.ItemDataRole.UserRole)
        return name if name else self.cmb_presets.itemText(index)

    def _refresh_preset_combo_tooltip(self):
        name = self._preset_name_at(self.cmb_presets.currentIndex())
        preset = self.presets.get(name, {}) if name != self.SYSTEM_PRESET_NAME else {}
        tooltip = warning_tooltip(name, preset, self.model_print_w_mm, self.model_print_h_mm)
        self.cmb_presets.setToolTip(tooltip or self._preset_combo_base_tooltip)

    def _save_new_preset(self, default_name=""):
        # Se chamado pelo clique do botão, default_name será um booleano (checked state)
        if isinstance(default_name, bool):
            default_name = ""

        name, ok = dialog_get_text(
            self, tr("Nova predefinição"), tr("Nome da predefinição:"),
            QLineEdit.EchoMode.Normal, default_name
        )
        if ok and name.strip():
            name = name.strip()
            if name == self.SYSTEM_PRESET_NAME:
                QMessageBox.warning(self, tr("Nome reservado"), tr("O nome '{nome}' é reservado pelo sistema.").format(nome=self.SYSTEM_PRESET_NAME))
                return False

            if name in self.presets:
                reply = QMessageBox.question(self, tr("Sobrescrever"), tr("A predefinição '{nome}' já existe. Deseja sobrescrevê-la?").format(nome=name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    return self._save_new_preset(name) # Repete o prompt para o usuário tentar outro nome

            self.presets[name] = self._get_current_settings()
            self.active_preset_name = name
            self._load_presets_ui()
            return True
        return False

    def _delete_preset(self):
        if not self.active_preset_name or self.active_preset_name == self.SYSTEM_PRESET_NAME: return

        reply = QMessageBox.question(self, tr("Excluir predefinição"), tr("Tem certeza de que deseja excluir '{nome}'?").format(nome=self.active_preset_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            del self.presets[self.active_preset_name]
            self.active_preset_name = self.SYSTEM_PRESET_NAME
            self._load_presets_ui()
            self._on_preset_selected(0)

    def _rename_preset(self):
        if not self.active_preset_name or self.active_preset_name == self.SYSTEM_PRESET_NAME: return

        new_name, ok = dialog_get_text(
            self, tr("Renomear predefinição"), tr("Novo nome:"),
            QLineEdit.EchoMode.Normal, self.active_preset_name
        )
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name == self.active_preset_name: return
            if new_name == self.SYSTEM_PRESET_NAME:
                QMessageBox.warning(self, tr("Nome reservado"), tr("O nome '{nome}' é reservado pelo sistema.").format(nome=self.SYSTEM_PRESET_NAME))
                return
            if new_name in self.presets:
                QMessageBox.warning(self, tr("Nome já existe"), tr("Já existe uma predefinição com o nome '{nome}'.").format(nome=new_name))
                return

            self.presets[new_name] = self.presets.pop(self.active_preset_name)
            self.active_preset_name = new_name
            self._load_presets_ui()

    def done(self, result):
        if self.tiling_panel:
            self.tiling_panel.stop_preview()
        super().done(result)

    def _insert_variable(self, var_name):
        self.txt_pattern.insert(f"{{{var_name}}}")
        self.txt_pattern.setFocus()

    def set_link_warning_visible(self, visible):
        self.lbl_link_warning.setVisible(visible)


