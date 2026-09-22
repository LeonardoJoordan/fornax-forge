from core.themes import themed_style, theme_color, theme_manager
"""Identidade visual do workspace, compartilhando o padrão do editor."""
import os
import re
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QSize, QProcess
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QToolButton, QHBoxLayout, QVBoxLayout,
    QMessageBox, QMenu, QGridLayout, QSizePolicy, QListView, QApplication,
)
from core.paths import get_models_dir
from core.resources import action_icon_path, navigation_icon_path
from core.theme_icons import themed_svg_icon
from core.i18n import SUPPORTED_LANGUAGES, current_locale, set_preferred_locale, tr
from core.dialog_buttons import style_message_box
from features.tutorial.first_steps import start_first_steps_tutorial


def _restart_application(window):
    """Reinicia depois de encerrar trabalhos e liberar a instância única."""
    app = QApplication.instance()
    app._restart_requested = True
    if not window.close():
        app._restart_requested = False


def _launch_restarted_application():
    if os.environ.get("APPIMAGE"):
        program = os.environ["APPIMAGE"]
        arguments = []
    elif getattr(sys, "frozen", False) or "__compiled__" in globals():
        program = sys.executable
        arguments = []
    else:
        program = sys.executable
        arguments = [str(Path(sys.argv[0]).resolve())]

    result = QProcess.startDetached(program, arguments, os.getcwd())
    started = result[0] if isinstance(result, tuple) else bool(result)
    if started:
        return True

    QMessageBox.critical(
        None,
        tr('Não foi possível reiniciar'),
        tr('Feche e abra o FORNAX Forge para aplicar o novo idioma.'),
    )
    return False


STYLE = """
QMainWindow, QWidget { background: @surface@; color: @text@; font-size: 12px; }
QMainWindow { background: @window@; }
QWidget#workspaceRoot { background: @window@; }
QWidget#workspaceLeft, QWidget#previewPanel, QWidget#dataPanel,
QWidget#modelActions {
    background: @panel@; border: none; border-radius: 0;
}
QWidget#previewWorkspace { background: @panel@; }
QWidget#outputPanel {
    background: @panel@; border: none; border-top: 1px solid @grid@;
    border-radius: 0;
}
QWidget#logPanel {
    background: @panel@; border: none; border-top: 1px solid @grid@;
}
QFrame#dataRail {
    background: @panel@; border: none; border-radius: 0;
}
QToolButton#dataRailToggle {
    background: @alternate@; color: @muted@; border: none;
    border-right: 1px solid @grid@; border-radius: 0; padding: 0; font-size: 15px;
}
QToolButton#dataRailToggle:hover { background: @selection@; color: @on_accent@; border-right-color: @accent@; }
QFrame#modelBar, QFrame#logHeader { background: @panel@; border-bottom: 1px solid @grid@; }
QWidget#outputControls { background: transparent; }
QLabel#contextLabel { color: @muted@; font-size: 10px; font-weight: 600; }
QToolButton#moreActions { background: @button@; border: 1px solid @border@; border-radius: 6px; padding: 7px 10px; }
QToolButton#moreActions::menu-indicator { image: none; }
QMenuBar { background: @window@; color: @text@; padding: 3px 8px; border-bottom: 1px solid @grid@; }
QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: @hover@; }
QMenu { background: @button@; color: @text@; border: 1px solid @border_strong@; padding: 6px; }
QMenu::item { padding: 8px 28px; border-radius: 4px; }
QMenu::item:selected { background: @selection@; }
QMenu::separator { height: 1px; background: @border_strong@; margin: 8px 8px; }
QWidget#previewPanel, QWidget#dataPanel { padding: 10px; }
QLabel { background: transparent; }
QPushButton {
    background: @button@; color: @text@; border: 1px solid @border@;
    border-radius: 6px; padding: 7px 10px; min-height: 20px;
}
QPushButton:hover { background: @hover@; border-color: @border_strong@; }
QPushButton:pressed, QPushButton:checked { background: @selection@; border-color: @accent@; }
QPushButton:disabled { color: @disabled@; background: @surface@; }
QPushButton#primary { background: @accent@; border-color: @accent@; color: @on_accent@; font-weight: 600; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#danger { color: @danger@; }
QPushButton#outputFolderBrowse {
    padding: 0; min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px;
}
QLineEdit#dynamicImageDirectory { min-height: 22px; max-height: 22px; }
QPushButton#previewPrevious, QPushButton#previewNext {
    min-height: 20px; max-height: 20px; padding: 0; border-radius: 5px; font-size: 15px;
}
QPushButton#previewPageButton {
    min-height: 20px; max-height: 20px; padding: 0 8px; border-radius: 5px;
}
QPushButton#previewPageButton:checked {
    background: @selection@; border-color: @accent@;
}
QPushButton#unlockModel {
    background: transparent; border: 1px solid @border@; border-radius: 5px;
    padding: 4px 10px;
}
QPushButton#unlockModel:hover {
    background: @hover@; border-color: @border_strong@;
}
QPushButton#unlockModel:disabled {
    background: transparent; border-color: @grid@; color: @disabled@;
}
QWidget#modelLockBalance, QWidget#modelLockActionSlot {
    background: transparent; border: none;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background: @field@; color: @text@; border: 1px solid @border@;
    border-radius: 5px; padding: 5px; min-height: 20px;
    selection-background-color: @selection@;
}
QSpinBox#previewNavigationIndex, QComboBox#previewMode {
    min-height: 0; padding-top: 0; padding-bottom: 0;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border-color: @accent@;
}
QComboBox:hover { border-color: @border_strong@; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(@combo_arrow@); width: 10px; height: 6px; }
QComboBox[dropArrow="true"]::down-arrow { image: url(@spin_down@); width: 10px; height: 6px; }
QListView#workspaceComboOptions {
    background: @button@; color: @text@; border: 1px solid @border_strong@;
    border-radius: 8px; padding: 6px; outline: none;
    selection-background-color: transparent;
}
QListView#workspaceComboOptions::item {
    min-height: 18px; padding: 2px 12px; border: 1px solid transparent;
    border-radius: 5px; background: transparent;
}
QListView#workspaceComboOptions::item:selected,
QListView#workspaceComboOptions::item:hover {
    background: @selection@; border-color: @accent@; color: @text@;
}
QTableWidget {
    background: @field@; alternate-background-color: @alternate@; color: @text@;
    border: 1px solid @border@; border-radius: 6px; gridline-color: @grid@;
    selection-background-color: @selection@; selection-color: @on_accent@;
}
QHeaderView::section {
    background: @button@; color: @text@; border: none;
    border-right: 1px solid @border@; border-bottom: 1px solid @border@;
    padding: 7px; font-weight: 600;
}
QProgressBar { background: @button@; border: none; border-radius: 4px; }
QProgressBar::chunk { background: @accent@; border-radius: 4px; }
QSplitter::handle { background: @grid@; width: 1px; }
QScrollBar:vertical { background: @scroll_track@; width: 8px; margin: 0; }
QScrollBar:horizontal { background: @scroll_track@; height: 8px; margin: 0; }
QScrollBar::handle:vertical { background: @scroll_handle@; min-height: 24px; border-radius: 2px; }
QScrollBar::handle:horizontal { background: @scroll_handle@; min-width: 24px; border-radius: 2px; }
QScrollBar::handle:hover { background: @scroll_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: @button@; color: @text@; border: 1px solid @border_strong@; padding: 6px; }
"""

def install_frontend(window):
    window.resize(1440, 860)
    central = window.centralWidget()
    central.setObjectName('workspaceRoot')
    layout = central.layout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    window.preview_panel.setObjectName('previewPanel')
    window.table_panel.setObjectName('dataPanel')
    window.splitter.setHandleWidth(1)

    window.btn_generate_cards.setObjectName('primary')
    themed_style(window.progress_bar, '')

    window.table_panel.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    for combo in (window.preview_panel.cbo_models,
                  window.cbo_presets_main, window.cbo_export_format):
        combo.setProperty('dropArrow', True)

    # Popups consistentes com o menu de Formas do editor.
    workspace_combos = (
        window.preview_panel.cbo_models,
        window.preview_panel.cbo_preview_mode,
        window.cbo_export_format,
        window.cbo_presets_main,
    )
    for combo in workspace_combos:
        popup = QListView(combo)
        popup.setObjectName('workspaceComboOptions')
        popup.setMouseTracking(True)
        popup.setUniformItemSizes(True)
        combo.setMaxVisibleItems(12)
        combo.setView(popup)

    # Barra permanente do modelo.
    model_bar = QFrame()
    model_bar.setObjectName('modelBar')
    model_bar.setFixedHeight(58)
    model_row = QHBoxLayout(model_bar)
    model_row.setContentsMargins(14, 10, 14, 10)
    model_row.setSpacing(8)
    context = QLabel(tr('MODELO'))
    context.setObjectName('contextLabel')
    model_row.addWidget(context)
    window.preview_panel.cbo_models.setMinimumWidth(100)
    window.preview_panel.cbo_models.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    model_row.addWidget(window.preview_panel.cbo_models, 1)
    window.btn_config_model = QPushButton(tr('Editar modelo'))
    window.btn_config_model.setToolTip(tr('Abrir o modelo selecionado no editor'))
    window.btn_config_model.clicked.connect(window._open_model_dialog)
    model_row.addWidget(window.btn_config_model)
    more = QToolButton()
    more.setObjectName('moreActions')
    more.setText('')
    more.setIcon(themed_svg_icon(action_icon_path('more-vertical')))
    more.setIconSize(QSize(18, 18))
    more.setFixedWidth(38)
    more.setToolTip(tr('Mais ações do modelo'))
    more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    model_actions = QMenu(more)
    pin_action = model_actions.addAction(
        tr('Fixar modelo no topo'), window._toggle_current_model_pinned
    )
    model_actions.addSeparator()
    protect_action = model_actions.addAction(
        tr('Proteger modelo…'), window._protect_current_model
    )
    model_actions.addSeparator()
    delete_action = None
    for action_id, label, callback in (
        ('duplicate', tr('Duplicar modelo'), window._on_duplicate_model),
        ('rename', tr('Renomear modelo'), window._on_rename_model),
        ('delete', tr('Excluir modelo'), window._on_remove_model),
    ):
        if action_id == 'delete':
            model_actions.addAction(
                tr('Informações do modelo…'), window._open_model_info_dialog
            )
            model_actions.addSeparator()
        action = model_actions.addAction(label)
        action.triggered.connect(callback)
        if action_id == 'delete':
            delete_action = action
    def style_model_action_hover(action):
        if action is delete_action:
            themed_style(model_actions, 'QMenu::item:selected { background: @danger_background@; color: @on_danger@; }')
        else:
            themed_style(model_actions, '')
    model_actions.hovered.connect(style_model_action_hover)
    def refresh_model_actions():
        entry = window._current_library_entry()
        pinned = set(window._model_library_list_setting(
            'workspace/model_library_pinned'
        ))
        pin_action.setEnabled(bool(entry and not entry.key.startswith('external:')))
        pin_action.setText(
            tr('Remover modelo do topo')
            if entry is not None and entry.key in pinned else
            tr('Fixar modelo no topo')
        )
        protect_action.setEnabled(bool(
            entry is not None and entry.is_fornax
            and entry.descriptor.mode == 'none'
        ))
    model_actions.aboutToShow.connect(refresh_model_actions)
    more.setMenu(model_actions)
    model_row.addWidget(more)
    for control in (window.preview_panel.cbo_models, window.btn_config_model, more):
        control.setFixedHeight(38)

    # As ações de saída ficam próximas, mesmo em uma tela ultrawide.
    # Reparentar os controles conserva suas conexões e os valores selecionados.
    output_controls = QWidget()
    output_controls.setObjectName('outputControls')
    output_grid = QGridLayout(output_controls)
    output_grid.setContentsMargins(0, 0, 0, 0)
    output_grid.setHorizontalSpacing(8)
    output_grid.setVerticalSpacing(8)
    destination = QHBoxLayout()
    destination.setSpacing(8)
    destination_label = QLabel(tr('Salvar em'))
    destination_label.setObjectName('outputDestinationLabel')
    output_grid.addWidget(destination_label, 0, 0)
    destination.addWidget(window.txt_output_path, 1)
    window.txt_output_path.setPlaceholderText(tr('Escolha a pasta de destino dos arquivos'))
    window.btn_sel_out.setText('')
    window.btn_sel_out.setObjectName('outputFolderBrowse')
    window.btn_sel_out.setIcon(themed_svg_icon(action_icon_path('more')))
    window.btn_sel_out.setIconSize(QSize(18, 18))
    window.btn_sel_out.setFixedSize(34, 34)
    window.btn_sel_out.setToolTip(tr('Escolher a pasta de destino'))
    destination.addWidget(window.btn_sel_out)
    output_grid.addLayout(destination, 0, 1, 1, 4)
    format_label = QLabel(tr('Formato'))
    format_label.setObjectName('outputFormatLabel')
    output_label_width = max(
        destination_label.sizeHint().width(), format_label.sizeHint().width()
    )
    destination_label.setFixedWidth(output_label_width)
    format_label.setFixedWidth(output_label_width)
    output_grid.addWidget(format_label, 1, 0)
    window.cbo_export_format.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    output_grid.addWidget(window.cbo_export_format, 1, 1)
    export_tooltips = {
        'png': tr('Uma imagem PNG para cada item.'),
        'pdf_item': tr('Um arquivo PDF separado para cada item.'),
        'pdf_grouped': tr('Todos os itens reunidos em um único arquivo PDF.'),
    }
    for index in range(window.cbo_export_format.count()):
        mode = window.cbo_export_format.itemData(index)
        window.cbo_export_format.setItemData(index, export_tooltips[mode], Qt.ItemDataRole.ToolTipRole)
    window.cbo_export_format.setToolTip(tr('Selecionar o formato dos arquivos gerados'))
    window.cbo_presets_main.setMinimumWidth(100)
    window.cbo_presets_main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    window.cbo_presets_main.setToolTip(tr('Selecionar uma predefinição de impressão'))
    preset_label = QLabel(tr('Predefinição'))
    preset_label.setObjectName('outputPresetLabel')
    output_grid.addWidget(preset_label, 1, 2)
    output_grid.addWidget(window.cbo_presets_main, 1, 3)
    output_grid.setColumnStretch(1, 1)
    output_grid.setColumnStretch(3, 2)
    window.btn_generate_cards.setFixedWidth(140)
    window.btn_generate_cards.setFixedHeight(34)
    window.btn_generate_cards.setToolTip(tr('Gerar os arquivos usando os dados da tabela'))
    output_grid.addWidget(window.btn_generate_cards, 1, 4, 1, 1, Qt.AlignmentFlag.AlignVCenter)
    for control in (window.txt_output_path, window.cbo_export_format,
                    window.cbo_presets_main):
        control.setFixedHeight(34)

    window.footer_container = QWidget()
    window.footer_container.setObjectName('outputPanel')
    window.footer_container.setFixedHeight(100)
    footer_layout = QHBoxLayout(window.footer_container)
    footer_layout.setContentsMargins(14, 12, 14, 12)
    footer_layout.setSpacing(0)
    footer_layout.addWidget(output_controls, 1)

    # O log fica oculto durante o trabalho normal e é acessado pelo menu Exibir.
    window.log_panel.setMaximumHeight(180)
    window.log_panel.setObjectName('logPanel')
    window.log_panel.hide()
    def toggle_log(opened):
        window.log_panel.setVisible(opened)

    # A seleção, a prévia e a saída formam uma única área de trabalho.
    preview_workspace = QWidget()
    preview_workspace.setObjectName('previewWorkspace')
    preview_workspace.setMinimumWidth(500)
    preview_workspace_layout = QVBoxLayout(preview_workspace)
    preview_workspace_layout.setContentsMargins(0, 0, 0, 0)
    preview_workspace_layout.setSpacing(0)
    preview_workspace_layout.addWidget(model_bar)
    preview_workspace_layout.addWidget(window.preview_panel, 1)
    preview_workspace_layout.addWidget(window.log_panel)
    preview_workspace_layout.addWidget(window.footer_container)
    preview_workspace_layout.addWidget(window.progress_bar)

    # A tabela vive em um painel lateral que pode virar apenas uma barra estreita.
    data_rail = QFrame()
    data_rail.setObjectName('dataRail')
    data_rail_layout = QHBoxLayout(data_rail)
    data_rail_layout.setContentsMargins(0, 0, 0, 0)
    data_rail_layout.setSpacing(0)
    data_toggle = QToolButton()
    data_toggle.setObjectName('dataRailToggle')
    data_toggle.setFixedWidth(38)
    data_toggle.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    data_toggle.setToolTip(tr('Recolher tabela de dados'))
    data_rail_layout.addWidget(data_toggle)
    data_rail_layout.addWidget(window.table_panel, 1)

    window.splitter.addWidget(preview_workspace)
    window.splitter.addWidget(data_rail)
    window.splitter.setCollapsible(0, False)
    window.splitter.setCollapsible(1, False)
    window.splitter.setSizes([700, 700])

    panel_state = {'expanded_width': 700, 'collapsed': False, 'fixed': False}

    def refresh_data_toggle_icon():
        asset_name = (
            'double-chevron-left' if panel_state['collapsed']
            else 'double-chevron-right'
        )
        data_toggle.setText('')
        data_toggle.setIcon(themed_svg_icon(navigation_icon_path(asset_name)))
        data_toggle.setIconSize(QSize(20, 20))

    def set_data_panel_collapsed(collapsed):
        collapsed = bool(collapsed)
        if collapsed and panel_state['fixed']:
            return
        if collapsed == panel_state['collapsed']:
            return
        if collapsed:
            sizes = window.splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 60:
                panel_state['expanded_width'] = sizes[1]
            window.table_panel.hide()
            data_toggle.setToolTip(tr('Expandir tabela de dados'))
            data_rail.setMinimumWidth(38)
            data_rail.setMaximumWidth(38)
            window.splitter.setSizes([max(500, sum(sizes) - 38), 38])
        else:
            data_rail.setMinimumWidth(420)
            data_rail.setMaximumWidth(16777215)
            window.table_panel.show()
            data_toggle.setToolTip(tr('Recolher tabela de dados'))
            total = max(1000, sum(window.splitter.sizes()))
            right = min(max(420, panel_state['expanded_width']), total - 500)
            window.splitter.setSizes([total - right, right])
        panel_state['collapsed'] = collapsed
        refresh_data_toggle_icon()
        window.settings.setValue('workspaceDataPanelCollapsed', collapsed)

    data_toggle.clicked.connect(lambda: set_data_panel_collapsed(not panel_state['collapsed']))
    refresh_data_toggle_icon()
    manager = theme_manager()
    manager.changed.connect(refresh_data_toggle_icon)

    def disconnect_data_toggle_theme(*_):
        try:
            manager.changed.disconnect(refresh_data_toggle_icon)
        except (RuntimeError, TypeError):
            # The application/theme manager may already be shutting down.
            pass

    data_toggle.destroyed.connect(disconnect_data_toggle_theme)

    # Menus conhecidos de aplicativos de criação, reutilizando as ações existentes.
    menu = window.menuBar()
    menu.clear()
    arquivo = menu.addMenu(tr('Arquivo'))
    new_model_action = arquivo.addAction(tr('Novo modelo'), window._on_add_model)
    arquivo.addAction(tr('Importar modelos…'), window._on_import_models)
    arquivo.addAction(tr('Exportar modelos…'), window._on_export_models)
    arquivo.addSeparator()
    arquivo.addAction(tr('Configurações de geração…'), window._open_config_dialog)
    arquivo.addSeparator()
    arquivo.addAction(
        tr('Abrir biblioteca de modelos'),
        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_models_dir())))
    )
    arquivo.addAction(tr('Sair'), window.close)

    exibir = menu.addMenu(tr('Exibir'))
    fixed_data = exibir.addAction(tr('Fixar tabela de dados'))
    fixed_data.setCheckable(True)
    show_log = exibir.addAction(tr('Mostrar log de processamento'))
    show_log.setCheckable(True)
    show_log.toggled.connect(toggle_log)
    exibir.addSeparator()
    sort_menu = exibir.addMenu(tr('Ordenar modelos por'))
    sort_group = QActionGroup(sort_menu)
    sort_group.setExclusive(True)
    selected_sort = str(
        window.settings.value('workspace/model_library_sort', 'name') or 'name'
    )
    sort_actions = []
    for mode, label in (
        ('name', tr('Nome')),
        ('recent', tr('Usados recentemente')),
    ):
        action = sort_menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(selected_sort == mode)
        action.triggered.connect(
            lambda checked=False, selected=mode:
            window._set_model_library_sort_mode(selected) if checked else None
        )
        sort_group.addAction(action)
        sort_actions.append(action)

    configuracoes = menu.addMenu(tr('Configurações'))
    configuracoes.addAction(tr('Tema da interface…'), window._open_theme_dialog)
    idioma = configuracoes.addMenu(tr('Idioma'))
    language_group = QActionGroup(idioma)
    language_group.setExclusive(True)
    for locale, native_name in SUPPORTED_LANGUAGES:
        language_action = idioma.addAction(native_name)
        language_action.setCheckable(True)
        language_action.setChecked(locale == current_locale())
        language_group.addAction(language_action)
        def choose_language(_checked=False, selected=locale):
            set_preferred_locale(window.settings, selected)
            if selected == current_locale():
                return
            prompt = QMessageBox(window)
            prompt.setIcon(QMessageBox.Icon.Question)
            prompt.setWindowTitle(tr('Reiniciar o programa'))
            prompt.setText(tr('Reinicie o programa para aplicar o novo idioma.'))
            restart_now = prompt.addButton(
                tr('Reiniciar agora'), QMessageBox.ButtonRole.AcceptRole
            )
            prompt.addButton(
                tr('Reiniciar depois'), QMessageBox.ButtonRole.RejectRole
            )
            prompt.setDefaultButton(restart_now)
            style_message_box(prompt)
            prompt.exec()
            if prompt.clickedButton() is restart_now:
                _restart_application(window)
        language_action.triggered.connect(choose_language)
    def set_data_panel_fixed(fixed):
        panel_state['fixed'] = bool(fixed)
        if fixed:
            set_data_panel_collapsed(False)
        data_toggle.setVisible(not fixed)
        if not fixed:
            data_toggle.setToolTip(
                tr('Expandir tabela de dados') if panel_state['collapsed'] else tr('Recolher tabela de dados')
            )
        window.settings.setValue('workspaceDataPanelFixed', bool(fixed))
    fixed_data.toggled.connect(set_data_panel_fixed)
    ajuda = menu.addMenu(tr('Ajuda'))
    first_steps_tutorial_action = ajuda.addAction(tr('Tutorial interativo…'))
    first_steps_tutorial_action.triggered.connect(
        lambda: start_first_steps_tutorial(window)
    )
    ajuda.addSeparator()
    ajuda.addAction(tr('Sobre o FORNAX Forge'), lambda: QMessageBox.about(
        window, tr('Sobre o FORNAX Forge'),
        tr('<b>FORNAX Forge</b><br>Geração de material personalizado em lote.<br><br>'
           'Desenvolvido por Leonardo Joordan Belisário Lima da Silva.<br>'
           'Licenciado sob a GNU GPL v3 exclusivamente.<br><br>'
           'Interface desenvolvida com <a href="https://www.qt.io/qt-for-python">Qt for Python (PySide6)</a>.')
    ))
    ajuda.addAction(tr('Licenças de terceiros'), lambda: QMessageBox.information(
        window, tr('Licenças de terceiros'),
        tr('Este programa utiliza Qt for Python (PySide6), disponibilizado sob opções de licença LGPLv3/GPLv3 ou comercial. '
           'Os componentes de terceiros permanecem sob suas próprias licenças. Consulte os avisos incluídos no pacote de distribuição.')
    ))
    # Mantém wrappers Python vivos durante toda a janela (necessário no PySide).
    window._workspace_menus = (
        arquivo, idioma, language_group, exibir, sort_menu, sort_group,
        configuracoes, ajuda,
        model_actions,
    )
    window._tutorial_menu = ajuda
    window._tutorial_actions = (first_steps_tutorial_action,)
    window._first_steps_tutorial_action = first_steps_tutorial_action
    window._model_menu = arquivo
    window._new_model_action = new_model_action
    window._view_menu = exibir
    window._workspace_log_toggle = show_log
    window._workspace_data_toggle = data_toggle
    window._workspace_data_fixed_action = fixed_data
    window._workspace_data_rail = data_rail
    window._model_pin_action = pin_action
    window._model_sort_menu = sort_menu
    window._model_sort_actions = tuple(sort_actions)
    data_panel_fixed = window.settings.value('workspaceDataPanelFixed', False, type=bool)
    if data_panel_fixed:
        fixed_data.setChecked(True)
    elif window.settings.value('workspaceDataPanelCollapsed', False, type=bool):
        set_data_panel_collapsed(True)
    themed_style(window, STYLE)
    # Reaplica as dimensões depois do QSS: no Qt, padding e borda podem alterar
    # as restrições calculadas durante o polimento do estilo.
    window.txt_output_path.setFixedHeight(34)
    window.btn_sel_out.setFixedSize(34, 34)
    window.cbo_export_format.setFixedHeight(34)
    window.cbo_presets_main.setFixedHeight(34)
    window.btn_generate_cards.setFixedHeight(34)
