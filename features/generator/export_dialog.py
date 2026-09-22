from core.themes import themed_style, theme_color, theme_manager
from core.dialog_buttons import get_text as dialog_get_text, style_dialog_button_box
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                               QPushButton, QHBoxLayout, QFrame, QGridLayout, 
                               QDialogButtonBox, QCheckBox, QGroupBox, QDoubleSpinBox,
                               QWidget, QScrollArea,
                               QComboBox, QMessageBox)
from PySide6.QtCore import Qt
from .imposition import SheetAssembler
from .preset_warnings import warning_display_name, warning_tooltip, with_model_ratio_snapshot
from core.i18n import tr

class ConfigDialog(QDialog):
    def __init__(self, parent, model_slug: str, available_vars: list[str], 
                 current_pattern: str = "", model_size_px: tuple[int, int] = (1000, 1000),
                 model_print_size_mm: tuple[float, float] = None,
                 current_imposition: dict = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Configurações de exportação"))
        self.resize(640, 760)
        
        self.model_slug = model_slug
        self.result_pattern = current_pattern
        self.model_w, self.model_h = model_size_px
        fallback_w_mm = (self.model_w / 300.0) * 25.4
        fallback_h_mm = (self.model_h / 300.0) * 25.4
        if model_print_size_mm and model_print_size_mm[0] > 0 and model_print_size_mm[1] > 0:
            self.model_print_w_mm, self.model_print_h_mm = model_print_size_mm
        else:
            self.model_print_w_mm, self.model_print_h_mm = fallback_w_mm, fallback_h_mm
        self.ratio = self.model_print_w_mm / self.model_print_h_mm if self.model_print_h_mm > 0 else 1.0
        
        self.imposition_settings = current_imposition or {
            "enabled": False, "sheet_w_mm": 210.0, "sheet_h_mm": 297.0,
            "crop_marks": True, "bleed_margin": True, "target_w_mm": 0, "target_h_mm": 0,
            "presets": {}, "active_preset_name": ""
        }
        self._original_enabled = self.imposition_settings.get("enabled", False)
        self.presets = self.imposition_settings.get("presets", {}) or {}
        self.active_preset_name = self.imposition_settings.get("active_preset_name", "") or self.SYSTEM_PRESET_NAME
        if self.active_preset_name not in self.presets:
            self.active_preset_name = self.SYSTEM_PRESET_NAME
        initial_print = self._settings_for_active_preset()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)
        self._export_scroll = scroll
        self._export_content = content

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
        
        lbl_ext = QLabel(".png")
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
        content_layout.addWidget(naming_group)

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
        lbl_preset.setToolTip(tr("Selecionar ou gerenciar configurações de impressão salvas"))
        ly_combo_row.addWidget(lbl_preset)
        self._preset_combo_base_tooltip = tr("Selecionar uma predefinição de impressão")
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
        
        self.chk_imposition = QCheckBox(tr("Habilitar múltiplos itens por página"))
        self.chk_imposition.setChecked(initial_print["enabled"])
        self.chk_imposition.setToolTip(tr("Organizar vários itens em cada folha de saída"))
        self.chk_imposition.toggled.connect(self._toggle_imposition_ui)
        ly_print.addWidget(self.chk_imposition)

        # Label de aviso dinâmico (abaixo do checkbox)
        self.lbl_imposition_hint = QLabel()
        self.lbl_imposition_hint.setWordWrap(True)
        themed_style(self.lbl_imposition_hint, "color: gray; font-style: italic; padding-left: 4px;")
        ly_print.addWidget(self.lbl_imposition_hint)

        self.container_imposition = QWidget()
        self.container_imposition.setVisible(self.chk_imposition.isChecked())
        ly_imp = QVBoxLayout(self.container_imposition)
        ly_imp.setContentsMargins(10, 0, 0, 0)

        # Folha de Saída agora está dentro do container de imposição
        lbl_sheet_title = QLabel(tr("Folha de saída (largura × altura):"))
        lbl_sheet_title.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        lbl_sheet_title.setToolTip(tr("Definir o tamanho físico da folha de saída"))
        ly_imp.addWidget(lbl_sheet_title)
        ly_sheet = QHBoxLayout()
        self.spin_sheet_w_mm = QDoubleSpinBox()
        self.spin_sheet_w_mm.setRange(50, 2000)
        self.spin_sheet_w_mm.setSuffix(" mm")
        self.spin_sheet_w_mm.setDecimals(2)
        self.spin_sheet_w_mm.setValue(initial_print["sheet_w"])
        self.spin_sheet_h_mm = QDoubleSpinBox()
        self.spin_sheet_h_mm.setRange(50, 2000)
        self.spin_sheet_h_mm.setSuffix(" mm")
        self.spin_sheet_h_mm.setDecimals(2)
        self.spin_sheet_h_mm.setValue(initial_print["sheet_h"])
        ly_sheet.addWidget(self.spin_sheet_w_mm)
        ly_sheet.addWidget(QLabel("x"))
        ly_sheet.addWidget(self.spin_sheet_h_mm)
        ly_sheet.addStretch()
        ly_imp.addLayout(ly_sheet)

        ly_imp.addSpacing(6)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        ly_imp.addWidget(sep)
        
        lbl_model_dims_title = QLabel(tr("Dimensões do modelo na folha (largura × altura):"))
        lbl_model_dims_title.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        lbl_model_dims_title.setToolTip(tr("Definir o tamanho físico de cada item impresso"))
        ly_imp.addWidget(lbl_model_dims_title)
        self.spin_w_mm = QDoubleSpinBox()
        self.spin_w_mm.setRange(10, 2000)
        self.spin_w_mm.setSuffix(" mm")
        self.spin_w_mm.setDecimals(2)

        self.spin_h_mm = QDoubleSpinBox()
        self.spin_h_mm.setRange(10, 2000)
        self.spin_h_mm.setSuffix(" mm")
        self.spin_h_mm.setDecimals(2)

        self.spin_w_mm.setValue(initial_print["w"])
        self.spin_h_mm.setValue(initial_print["h"])

        self.spin_w_mm.valueChanged.connect(self._on_width_changed)
        self.spin_h_mm.valueChanged.connect(self._on_height_changed)

        ly_model_dims = QHBoxLayout()
        ly_model_dims.addWidget(self.spin_w_mm)
        ly_model_dims.addWidget(QLabel("x"))
        ly_model_dims.addWidget(self.spin_h_mm)
        ly_model_dims.addStretch()
        ly_imp.addLayout(ly_model_dims)

        self.lbl_capacity = QLabel(tr("Calculando capacidade…"))
        themed_style(self.lbl_capacity, "font-weight: bold; color: @success@;")
        ly_imp.addWidget(self.lbl_capacity)

        self.chk_crop_marks = QCheckBox(tr("Habilitar marcas de corte"))
        self.chk_crop_marks.setChecked(initial_print["crop"])
        self.chk_crop_marks.setToolTip(tr("Adicionar marcas para orientar o corte dos itens"))
        ly_imp.addWidget(self.chk_crop_marks)
        self.chk_bleed = QCheckBox(tr("Habilitar margem de sangria"))
        self.chk_bleed.setChecked(initial_print["bleed"])
        self.chk_bleed.setToolTip(tr("Reservar uma margem adicional ao redor dos itens"))
        ly_imp.addWidget(self.chk_bleed)
        
        # Carrega a UI com os dados em memória
        self._load_presets_ui()
        
        ly_print.addWidget(self.container_imposition)
        print_group = QGroupBox(tr("Impressão"))
        print_layout = QVBoxLayout(print_group)
        print_layout.setContentsMargins(8, 10, 8, 8)
        print_layout.addWidget(tab_print)
        content_layout.addWidget(print_group)
        content_layout.addStretch(1)

        # Conexões de Cálculo
        self.spin_sheet_w_mm.valueChanged.connect(self._update_capacity_preview)
        self.spin_sheet_h_mm.valueChanged.connect(self._update_capacity_preview)
        self.spin_w_mm.valueChanged.connect(self._update_capacity_preview)
        self.spin_h_mm.valueChanged.connect(self._update_capacity_preview)
        self.chk_crop_marks.toggled.connect(self._update_capacity_preview)
        self.chk_bleed.toggled.connect(self._update_capacity_preview)
        self.chk_imposition.toggled.connect(self._update_capacity_preview)

        # Botões
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self._on_accept)
        self.buttonBox.rejected.connect(self.reject)
        style_dialog_button_box(self.buttonBox)
        main_layout.addWidget(self.buttonBox)

        self._toggle_imposition_ui(self.chk_imposition.isChecked())
        self._update_capacity_preview()
    def get_pattern(self):
        return self.result_pattern
    
    def get_imposition_settings(self):
        return {
            "enabled": self.chk_imposition.isChecked(),
            "sheet_w_mm": self.spin_sheet_w_mm.value(),
            "sheet_h_mm": self.spin_sheet_h_mm.value(),
            "crop_marks": self.chk_crop_marks.isChecked(),
            "bleed_margin": self.chk_bleed.isChecked(),
            "target_w_mm": self.spin_w_mm.value(),
            "target_h_mm": self.spin_h_mm.value(),
            "presets": self.presets,
            "active_preset_name": self.active_preset_name
        }

    def _settings_for_active_preset(self):
        """Retorna os valores iniciais da UI sem contaminar a definição do modelo."""
        base = {
            "enabled": False,
            "sheet_w": 210.0,
            "sheet_h": 297.0,
            "w": self.model_print_w_mm,
            "h": self.model_print_h_mm,
            "crop": True,
            "bleed": True,
        }

        if self.active_preset_name == self.SYSTEM_PRESET_NAME:
            return base

        preset = self.presets.get(self.active_preset_name)
        if not preset:
            self.active_preset_name = self.SYSTEM_PRESET_NAME
            return base

        return {
            "enabled": preset.get("enabled", False),
            "sheet_w": preset.get("sheet_w", base["sheet_w"]),
            "sheet_h": preset.get("sheet_h", base["sheet_h"]),
            "w": preset.get("w", base["w"]) or base["w"],
            "h": preset.get("h", base["h"]) or base["h"],
            "crop": preset.get("crop", True),
            "bleed": preset.get("bleed", True),
        }

    def _set_model_print_size_controls(self):
        self.spin_w_mm.blockSignals(True)
        self.spin_h_mm.blockSignals(True)
        self.spin_w_mm.setValue(self.model_print_w_mm)
        self.spin_h_mm.setValue(self.model_print_h_mm)
        self.spin_w_mm.blockSignals(False)
        self.spin_h_mm.blockSignals(False)

    def _update_capacity_preview(self):
        """Calcula dinamicamente quantos itens cabem e valida se o modelo cabe na folha."""
        if not self.chk_imposition.isChecked():
            self.lbl_capacity.setText(tr("Imposição desativada (1 item por arquivo)"))
            themed_style(self.lbl_capacity, "color: gray;")
            self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            return

        sw = self.spin_sheet_w_mm.value()
        sh = self.spin_sheet_h_mm.value()
        tw = self.spin_w_mm.value()
        th = self.spin_h_mm.value()
        marks = self.chk_crop_marks.isChecked()
        bleed = self.chk_bleed.isChecked()

        # Instancia o assembler (o mesmo motor que gera as imagens)
        assembler = SheetAssembler(tw, th, sw, sh, marks, bleed)
        
        ok_button = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        if assembler.capacity > 0:
            self.lbl_capacity.setText(tr("✅ Capacidade: {capacidade} itens por página ({colunas}×{linhas})").format(
                capacidade=assembler.capacity, colunas=assembler.cols, linhas=assembler.rows
            ))
            themed_style(self.lbl_capacity, "font-weight: bold; color: @success@;")
            ok_button.setEnabled(True)
        else:
            self.lbl_capacity.setText(tr("❌ Modelo muito grande para a página!"))
            themed_style(self.lbl_capacity, "font-weight: bold; color: @danger@;")
            ok_button.setEnabled(False)

    def _on_accept(self):
        # Auto-save inteligente das configurações
        if self.active_preset_name == self.SYSTEM_PRESET_NAME:
            # Se ativou imposição no preset de sistema, assumimos que algo foi customizado
            if self.chk_imposition.isChecked():
                name, ok = dialog_get_text(
                    self, tr("Configurações personalizadas"),
                    tr("Você alterou as configurações padrão.\nDê um nome para salvar esta predefinição:"),
                    QLineEdit.EchoMode.Normal, tr("Personalizada")
                )
                
                # Se o usuário cancelar ou deixar em branco, aplica o nome padrão de fallback
                new_name = name.strip() if (ok and name.strip()) else "Personalizada"
                if new_name == self.SYSTEM_PRESET_NAME:
                    new_name = "Personalizada"
                
                # Previne colisão silenciosa caso a pessoa apenas feche a janela ou confirme o padrão
                final_name = new_name
                counter = 2
                while final_name in self.presets:
                    final_name = f"{new_name} {counter}"
                    counter += 1
                    
                self.presets[final_name] = self._get_current_settings()
                self.active_preset_name = final_name
        else:
            # Se já está em um preset do usuário, salva silenciosamente (auto-save fluido)
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
        if index < 0: return
        name = self._preset_name_at(index)

        if name == self.SYSTEM_PRESET_NAME:
            self.chk_imposition.setChecked(False)
            self.spin_sheet_w_mm.setValue(210.0)
            self.spin_sheet_h_mm.setValue(297.0)
            self._set_model_print_size_controls()
            self.chk_crop_marks.setChecked(True)
            self.chk_bleed.setChecked(True)
            self.active_preset_name = self.SYSTEM_PRESET_NAME
            self.btn_rename_preset.setEnabled(False)
            self.btn_del_preset.setEnabled(False)
        else:
            data = self.presets.get(name)
            if not data: return
            
            self.spin_sheet_w_mm.setValue(data.get("sheet_w", 210.0))
            self.spin_sheet_h_mm.setValue(data.get("sheet_h", 297.0))
            self.chk_imposition.setChecked(data.get("enabled", False))
            self.spin_w_mm.setValue(data.get("w", 0))
            self.spin_h_mm.setValue(data.get("h", 0))
            self.chk_crop_marks.setChecked(data.get("crop", True))
            self.chk_bleed.setChecked(data.get("bleed", True))
            
            self.active_preset_name = name
            self.btn_rename_preset.setEnabled(True)
            self.btn_del_preset.setEnabled(True)
        self._refresh_preset_combo_tooltip()

    def _get_current_settings(self):
        """Coleta as configurações atuais da tela."""
        settings = {
            "sheet_w": self.spin_sheet_w_mm.value(),
            "sheet_h": self.spin_sheet_h_mm.value(),
            "enabled": self.chk_imposition.isChecked(),
            "w": self.spin_w_mm.value(),
            "h": self.spin_h_mm.value(),
            "crop": self.chk_crop_marks.isChecked(),
            "bleed": self.chk_bleed.isChecked()
        }
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

    def _toggle_imposition_ui(self, enabled):
        self.container_imposition.setVisible(enabled)
        if enabled:
            if self.active_preset_name == self.SYSTEM_PRESET_NAME:
                self._set_model_print_size_controls()
            self.lbl_imposition_hint.setText(tr("⚙️ Configure a folha e as dimensões do modelo para um resultado preciso."))
            themed_style(self.lbl_imposition_hint, "color: @warning@; font-style: italic; padding-left: 4px;")
        else:
            self.lbl_imposition_hint.setText(tr("ℹ️ O arquivo gerado terá as dimensões exatas do modelo original (1 item por arquivo)."))
            themed_style(self.lbl_imposition_hint, "color: gray; font-style: italic; padding-left: 4px;")

    def _insert_variable(self, var_name):
        self.txt_pattern.insert(f"{{{var_name}}}")
        self.txt_pattern.setFocus()

    def _on_width_changed(self, new_w):
        self.spin_h_mm.blockSignals(True)
        self.spin_h_mm.setValue(new_w / self.ratio)
        self.spin_h_mm.blockSignals(False)

    def _on_height_changed(self, new_h):
        self.spin_w_mm.blockSignals(True)
        self.spin_w_mm.setValue(new_h * self.ratio)
        self.spin_w_mm.blockSignals(False)

    def set_link_warning_visible(self, visible):
        self.lbl_link_warning.setVisible(visible)
    
    
