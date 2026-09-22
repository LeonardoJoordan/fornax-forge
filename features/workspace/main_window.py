import zipfile
import os
import shutil
import json
import tempfile
import copy
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4
from shiboken6 import isValid
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                                QSplitter, QPushButton, QApplication, QMessageBox,
                                  QLineEdit, QLabel, QFileDialog, QProgressBar,
                                  QComboBox, QTableWidgetItem, QInputDialog)
from PySide6.QtCore import Qt, QSignalBlocker, QTimer, QThread
from PySide6.QtGui import QPainter, QImage, QPixmap, QIcon, QPageLayout, QPalette, QColor, QBrush

from features.preview.preview_panel import PreviewPanel
from features.preview.sheet_preview_worker import SheetPreviewWorker
from shared.log_panel import LogPanel
from features.spreadsheet.table_panel import TablePanel
from features.generator.renderer import NativeRenderer, renderers_for_document
from features.editor.editor_window import EditorWindow
from features.generator.manager import RenderManager
from features.generator.production_plan import build_imposition_plan
from features.workspace.settings_dialogs import ExportConfigDialog, ThemeDialog
from features.generator.preset_warnings import warning_display_name, warning_tooltip
from features.workspace.import_models_dialog import ImportModelsDialog
from features.workspace.export_models_dialog import ExportModelsDialog
from core.template_manager import slugify_model_name
from core.paths import get_models_dir
from core.settings import get_app_settings
from core.render_cache import ensure_background_proxy, get_thumbnail_cache_path
from core.theme_icons import themed_svg_icon
from core.resources import object_icon_path
from core.output_folders import create_forge_output_dir
from core.model_library import LibraryModel, scan_model_library
from core.fornax_container import (
    FULL_MODE, PUBLIC_MODE,
    SIGNATURES_MODE,
    FornaxError,
    inspect_fornax,
    open_public_fornax,
    password_bytes,
    save_public_fornax,
    save_protected_fornax,
    unlock_fornax,
)
from core.fornax_session import AccessState, FornaxSessionManager
from core.legacy_migration import migrate_legacy_model
from core.fornax_export import ExportRequest, export_models
from core.fornax_import import import_candidate, import_legacy_document, open_import_package
from core.file_transactions import file_sha256
from core.dynamic_images import dynamic_image_fields, resolve_dynamic_image
from core.themes import themed_style, theme_color
from core.i18n import tr
from core.dialog_buttons import get_text as dialog_get_text, style_message_box
from core.model_document import (
    V3_FILENAME,
    V4_FILENAME,
    adapt_model_page,
    document_signatures,
    iter_page_link_items,
    load_model_document,
    normalize_model_document,
    resolve_model_file,
    save_model_document,
)
from core.model_info import build_model_snapshot, current_model_snapshot, ensure_origin_info
from features.workspace.model_info_dialog import ModelInfoDialog
from features.spreadsheet.headers import (
    SIGNATURE_ID_ROLE,
    is_quantity_header,
    is_signature_header,
    quantity_header_label,
    signature_id_from_header,
    table_column_key,
)




class MainWindow(QMainWindow):
    SYSTEM_IMPOSITION_PRESET = "Definição do Modelo"

    def _apply_tooltip(self, widget, text):
            """Aplica tooltip e garante que labels estáticos capturem o evento no motor customizado."""
            if isinstance(widget, QLabel):
                widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
            widget.setToolTip(text)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("FORNAX Forge — Geração de material personalizado em lote"))
        self.setMinimumSize(1024, 680)
        self.resize(1440, 860)

        central = QWidget()
        central.setObjectName("workspaceRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        root.addWidget(self.splitter, 1)

        self.current_filename_suffix = ""
        self.manager = None
        self.preview_panel = PreviewPanel()
        self.log_panel = LogPanel()
        self.table_panel = TablePanel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Estes controles já nascem para o layout aprovado. Nenhuma interface
        # intermediária é criada e posteriormente ocultada.
        self.txt_output_path = QLineEdit()
        self.btn_sel_out = QPushButton()
        self.btn_sel_out.clicked.connect(self._select_output_folder)
        self.cbo_export_format = QComboBox()
        self.cbo_export_format.addItem("PNG", "png")
        self.cbo_export_format.addItem(tr("PDF por item"), "pdf_item")
        self.cbo_export_format.addItem(tr("PDF agrupado"), "pdf_grouped")
        self._export_mode_tooltips = {
            "png": tr("Uma imagem PNG para cada item."),
            "pdf_item": tr("Um arquivo PDF separado para cada item."),
            "pdf_grouped": tr("Todos os itens reunidos em um único arquivo PDF."),
        }
        self.cbo_presets_main = QComboBox()
        self.cbo_presets_main.currentIndexChanged.connect(self._on_main_preset_changed)
        self._presets_main_base_tooltip = tr("Selecionar uma predefinição de impressão")
        self.btn_generate_cards = QPushButton(tr("Gerar material"))
        self.btn_generate_cards.clicked.connect(self._generate_cards_async)

        self._preview_mode = "item"
        self._preview_item_index = 0
        self._preview_page_index = 0
        self._selecting_preview_item = False
        self._preview_sheet_index = 0
        self._sheet_preview_revision = 0
        self._sheet_preview_worker = None
        self._sheet_preview_workers = set()
        self._preview_workers = set()
        self._sheet_preview_dir = None
        self._sheet_preview_paths = {}
        self._stale_sheet_preview_dirs = set()
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(100)
        self._preview_refresh_timer.timeout.connect(self._refresh_preview_after_data_change)
        self.preview_panel.modeChanged.connect(self._on_preview_mode_changed)
        self.preview_panel.indexRequested.connect(self._on_preview_index_requested)
        self.preview_panel.pageChanged.connect(self._on_preview_page_changed)
        self.preview_panel.btn_unlock_model.clicked.connect(self._toggle_selected_model_lock)

        self.cached_model_data = None
        self.cached_model_document = None
        self.preview_renderer = None
        self._preview_renderers = []
        self.settings = get_app_settings()
        self._fornax_sessions = FornaxSessionManager()
        self._session_maintenance_timer = QTimer(self)
        self._session_maintenance_timer.setInterval(1000)
        self._session_clock_sample = (time.monotonic(), time.time())
        self._session_maintenance_timer.timeout.connect(self._maintain_fornax_sessions)
        self._session_maintenance_timer.start()
        self._library_models_by_key = {}
        self._active_library_model = None
        self._fornax_asset_provider = None
        self._protected_preview_memory_only = False
        self._active_fornax_status = None
        self._external_models_dir = tempfile.TemporaryDirectory(prefix="fornax_external_")
        self._pending_external_files = []

        self._initialize_theme()
        from .frontend import install_frontend
        install_frontend(self)

        self._ensure_starter_pack()
        self._reload_models_from_disk()
        self.preview_panel.cbo_models.currentTextChanged.connect(self._on_model_changed)
        self.cbo_export_format.currentIndexChanged.connect(self._on_export_mode_changed)
        self.table_panel.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table_panel.table.itemChanged.connect(self._on_preview_data_changed)
        self.table_panel.table.signatureColumnToggled.connect(
            lambda *_: self._on_preview_data_changed()
        )
        self.table_panel.table.model().rowsInserted.connect(self._on_preview_rows_changed)
        self.table_panel.table.model().rowsRemoved.connect(self._on_preview_rows_changed)
        self.table_panel.btn_dynamic_image_dir.clicked.connect(
            self._select_dynamic_image_directory
        )

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("splitterState")
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        last_output = self.settings.value("last_output_dir", "")
        if last_output:
            self.txt_output_path.setText(str(last_output))

    def _ensure_starter_pack(self):
        models_dir = get_models_dir()
        
        # Se a pasta já contém algo, o usuário não é novo. Interrompe a criação.
        if any(models_dir.iterdir()):
            return
            
        self.log_panel.append(tr("🌱 Primeiro uso detectado. Preparando modelo de exemplo…"))
        slug = "modelo_exemplo"
        example_dir = models_dir / slug
        example_dir.mkdir(parents=True, exist_ok=True)
        
        example_data = {
            "name": "Modelo Exemplo",
            "canvas_size": {"w": 1000, "h": 1000},
            "target_w_mm": 100.0,
            "target_h_mm": 100.0,
            "placeholders": ["Nome", "Cargo"],
            "boxes": [
                {
                    "id": "Nome",
                    "html": "<b>{Nome}</b>",
                    "x": 350, "y": 400, "w": 300, "h": 60,
                    "font_family": "Arial", "font_size": 36,
                    "align": "center", "visible": True
                },
                {
                    "id": "Cargo",
                    "html": "<i>{Cargo}</i>",
                    "x": 350, "y": 480, "w": 300, "h": 60,
                    "font_family": "Arial", "font_size": 24,
                    "align": "center", "visible": True
                }
            ]
        }
        example_document = normalize_model_document(example_data)
        example_page = example_document["pages"][0]
        example_page["layer_order"] = [
            item["object_id"]
            for collection in ("shapes", "images", "signatures", "boxes")
            for item in example_page[collection]
        ]
        save_model_document(example_document, example_dir)

    def _initialize_theme(self):
        from core.themes import theme_manager
        theme_manager().initialize(self.settings)

    def _maintain_fornax_sessions(self):
        now = (time.monotonic(), time.time())
        previous = self._session_clock_sample
        self._session_clock_sample = now
        # Relógios divergentes indicam suspensão ou ajuste do relógio do SO.
        # Em ambos os casos descarte apenas sessões fora do modelo ativo.
        if abs((now[1] - previous[1]) - (now[0] - previous[0])) > 5:
            self._fornax_sessions.suspend()
        self._fornax_sessions.expire_due()

    def closeEvent(self, event):
        """Salva a posição, tamanho e estado do splitter ao fechar o programa."""
        self._session_maintenance_timer.stop()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitterState", self.splitter.saveState())
        self._stop_sheet_preview_worker(wait=True)
        for worker in tuple(self._sheet_preview_workers):
            worker.stop()
            worker.requestInterruption()
            worker.wait()
        for worker in tuple(self._preview_workers):
            worker.requestInterruption()
            worker.wait()
        for directory in ({self._sheet_preview_dir} | self._stale_sheet_preview_dirs):
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
        if self.manager is not None and self.manager._is_running:
            self.manager.stop()
        self._sheet_preview_revision += 1
        self._sheet_preview_paths.clear()
        self.preview_panel.set_preview_text("")
        self._preview_renderers = []
        self.preview_renderer = None
        self.cached_model_document = None
        self.cached_model_data = None
        self._fornax_asset_provider = None
        self._pending_external_files.clear()
        self._fornax_sessions.close()
        self._external_models_dir.cleanup()
        super().closeEvent(event)

    def handle_external_files(self, paths):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        for path in paths:
            self.handle_external_file(path)

    def handle_external_file(self, path):
        try:
            source = Path(path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            QMessageBox.warning(self, tr("Arquivo inválido"), tr("O arquivo solicitado não existe."))
            return
        if source.suffix.lower() not in {".fornax", ".zip"} or not source.is_file():
            QMessageBox.warning(
                self, tr("Arquivo inválido"),
                tr("Selecione um arquivo .fornax ou um lote .zip."),
            )
            return
        editor = getattr(self, "editor_window", None)
        if editor is not None and isValid(editor) and editor.isVisible():
            value = str(source)
            if value not in self._pending_external_files:
                self._pending_external_files.append(value)
            QMessageBox.information(
                editor, tr("Arquivo aguardando"),
                tr("O arquivo será aberto quando a edição atual for encerrada. Suas alterações não foram afetadas."),
            )
            return
        if source.suffix.lower() == ".zip":
            self._dispatch_import_path(str(source))
            return

        library_model = self._matching_library_model(source)
        if library_model is not None:
            index = self.preview_panel.cbo_models.findData(library_model.key)
            if index >= 0:
                if index == self.preview_panel.cbo_models.currentIndex():
                    # O arquivo já está aberto; não refazer desbloqueio/render.
                    self.log_panel.append(
                        tr("Modelo já presente na biblioteca: {nome}").format(
                            nome=library_model.display_name,
                        )
                    )
                else:
                    self.preview_panel.cbo_models.setCurrentIndex(index)
                return

        prompt = QMessageBox(self)
        prompt.setWindowTitle(tr("Abrir modelo FORNAX"))
        prompt.setText(tr("Deseja adicionar este modelo à sua biblioteca?"))
        add_button = prompt.addButton(
            tr("Adicionar à biblioteca"), QMessageBox.ButtonRole.AcceptRole,
        )
        temporary_button = prompt.addButton(
            tr("Abrir sem adicionar"), QMessageBox.ButtonRole.ActionRole,
        )
        prompt.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        prompt.exec()
        if prompt.clickedButton() is add_button:
            self._on_import_fornax(str(source))
        elif prompt.clickedButton() is temporary_button:
            self._open_temporary_fornax(source)

    def _matching_library_model(self, source: Path) -> LibraryModel | None:
        """Reconhece o próprio arquivo ou uma cópia da mesma revisão."""
        source = source.resolve()
        for model in self._library_models_by_key.values():
            if not model.is_fornax:
                continue
            try:
                if source.samefile(model.path):
                    return model
            except OSError:
                if source == model.path.resolve():
                    return model
        try:
            descriptor = inspect_fornax(source)
        except Exception:
            return None
        for model in self._library_models_by_key.values():
            current = model.descriptor
            if (model.is_fornax and current is not None
                    and current.model_id == descriptor.model_id
                    and current.revision_id == descriptor.revision_id):
                return model
        return None

    def _open_temporary_fornax(self, source: Path):
        destination = Path(self._external_models_dir.name) / f"{uuid4().hex}.fornax"
        shutil.copyfile(source, destination)
        descriptor = inspect_fornax(destination)
        if descriptor.mode == FULL_MODE:
            name = source.stem
        else:
            name = str(open_public_fornax(descriptor).document().get("name") or source.stem)
        display_name = tr("{nome} (temporário)").format(nome=name)
        key = f"external:{uuid4()}"
        model = LibraryModel(key, display_name, destination, "fornax", descriptor)
        self._library_models_by_key[key] = model
        self.preview_panel.cbo_models.addItem(display_name, key)
        self.preview_panel.cbo_models.setCurrentIndex(
            self.preview_panel.cbo_models.findData(key)
        )
        self.log_panel.append(tr("Modelo aberto temporariamente: {nome}").format(nome=name))

    def _connect_editor_lifecycle(self):
        editor = getattr(self, "editor_window", None)
        if editor is not None:
            editor.closed.connect(self._process_pending_external_files)

    def _process_pending_external_files(self):
        if not self._pending_external_files:
            return
        pending = self._pending_external_files[:]
        self._pending_external_files.clear()
        QTimer.singleShot(0, lambda: self.handle_external_files(pending))

    def _model_library_list_setting(self, key: str) -> list[str]:
        raw = str(self.settings.value(key, "") or "")
        try:
            value = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            return []
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item) for item in value if isinstance(item, str)))

    def _set_model_library_list_setting(self, key: str, values):
        self.settings.setValue(
            key, json.dumps(list(dict.fromkeys(values)), ensure_ascii=False),
        )
        self.settings.sync()

    def _remember_recent_model(self, model_key: str):
        if not model_key or model_key.startswith("external:"):
            return
        key = "workspace/model_library_recent"
        recent = self._model_library_list_setting(key)
        recent = [model_key] + [item for item in recent if item != model_key]
        self._set_model_library_list_setting(key, recent[:100])

    def _set_model_library_sort_mode(self, mode: str):
        mode = mode if mode in {"name", "recent"} else "name"
        current_name = self.preview_panel.cbo_models.currentText()
        self.settings.setValue("workspace/model_library_sort", mode)
        self.settings.sync()
        self._reload_models_from_disk(select_name=current_name)

    def _toggle_current_model_pinned(self):
        model = self._current_library_entry()
        if model is None or model.key.startswith("external:"):
            return
        key = "workspace/model_library_pinned"
        pinned = self._model_library_list_setting(key)
        if model.key in pinned:
            pinned.remove(model.key)
        else:
            pinned.append(model.key)
        self._set_model_library_list_setting(key, pinned)
        self._reload_models_from_disk(select_name=model.display_name)

    def _forget_model_library_order(self, model_key: str):
        for key in (
            "workspace/model_library_pinned",
            "workspace/model_library_recent",
        ):
            values = self._model_library_list_setting(key)
            if model_key in values:
                self._set_model_library_list_setting(
                    key, [value for value in values if value != model_key]
                )

    def _reload_models_from_disk(self, select_name: str | None = None):
        self.preview_panel.cbo_models.blockSignals(True)
        self.preview_panel.cbo_models.clear()

        models_dir = get_models_dir()
        models_dir.mkdir(parents=True, exist_ok=True)

        found = scan_model_library(models_dir, legacy_loader=load_model_document)
        protected_names = self._protected_model_names()
        found = tuple((
            LibraryModel(
                model.key,
                protected_names.get(model.descriptor.model_id, model.display_name)
                if model.is_fornax and model.descriptor.mode == FULL_MODE else model.display_name,
                model.path, model.kind, model.descriptor,
            )
            for model in found
        ))
        pinned_keys = set(self._model_library_list_setting(
            "workspace/model_library_pinned"
        ))
        pinned = sorted(
            (model for model in found if model.key in pinned_keys),
            key=lambda model: (model.display_name.casefold(), model.key),
        )
        remaining = [model for model in found if model.key not in pinned_keys]
        sort_mode = str(
            self.settings.value("workspace/model_library_sort", "name") or "name"
        )
        if sort_mode == "recent":
            recent = self._model_library_list_setting("workspace/model_library_recent")
            recent_rank = {key: index for index, key in enumerate(recent)}
            remaining.sort(key=lambda model: (
                recent_rank.get(model.key, len(recent_rank)),
                model.display_name.casefold(), model.key,
            ))
        else:
            remaining.sort(key=lambda model: (model.display_name.casefold(), model.key))
        found = tuple(pinned + remaining)
        self._library_models_by_key = {model.key: model for model in found}
        for index, model in enumerate(found):
            if index == len(pinned) and pinned and remaining:
                self.preview_panel.cbo_models.insertSeparator(
                    self.preview_panel.cbo_models.count()
                )
            self.preview_panel.cbo_models.addItem(model.display_name, model.key)

        self.preview_panel.cbo_models.blockSignals(False)

        target_index = 0
        if select_name:
            idx = self.preview_panel.cbo_models.findText(select_name)
            if idx >= 0:
                target_index = idx
        else:
            last_model_id = str(
                self.settings.value("workspace/last_model_id", "") or ""
            )
            if last_model_id:
                idx = self.preview_panel.cbo_models.findData(last_model_id)
                if idx >= 0:
                    target_index = idx

        if self.preview_panel.cbo_models.count() > 0:
            self.preview_panel.cbo_models.setCurrentIndex(target_index)
            current_text = self.preview_panel.cbo_models.itemText(target_index)
            self._on_model_changed(current_text)
        else:
            self._on_model_changed("")

    def _current_library_entry(self) -> LibraryModel | None:
        key = self.preview_panel.cbo_models.currentData()
        return self._library_models_by_key.get(str(key)) if key is not None else None

    def _protected_model_names(self) -> dict[str, str]:
        """Nomes locais dos modelos integrais, cujo documento fica criptografado."""
        raw = str(self.settings.value("workspace/protected_model_names", "") or "")
        try:
            value = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            str(model_id): str(name)
            for model_id, name in value.items()
            if isinstance(model_id, str) and isinstance(name, str) and name.strip()
        }

    def _remember_protected_model_name(self, model_id: str, name: str):
        name = str(name or "").strip()
        if not model_id or not name:
            return
        names = self._protected_model_names()
        if names.get(model_id) == name:
            return
        names[model_id] = name
        self.settings.setValue(
            "workspace/protected_model_names",
            json.dumps(names, ensure_ascii=False, sort_keys=True),
        )
        self.settings.sync()

    def _forget_protected_model_name(self, model_id: str):
        names = self._protected_model_names()
        if model_id not in names:
            return
        names.pop(model_id, None)
        self.settings.setValue(
            "workspace/protected_model_names",
            json.dumps(names, ensure_ascii=False, sort_keys=True),
        )
        self.settings.sync()

    def _request_fornax_password(self, title: str) -> str | None:
        password, accepted = QInputDialog.getText(
            self, title, tr("Senha do modelo:"), QLineEdit.EchoMode.Password,
        )
        return password if accepted else None

    def _request_new_fornax_password(self) -> str | None:
        while True:
            password, accepted = QInputDialog.getText(
                self, tr("Criar senha"),
                tr("Digite uma senha de 8 a 64 caracteres:"),
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return None
            confirmation, accepted = QInputDialog.getText(
                self, tr("Confirmar senha"), tr("Digite novamente a senha:"),
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return None
            try:
                normalized_password = password_bytes(password)
                normalized_confirmation = password_bytes(confirmation)
            except FornaxError as error:
                QMessageBox.warning(self, tr("Senha inválida"), str(error))
                continue
            if normalized_password != normalized_confirmation:
                QMessageBox.warning(
                    self, tr("Senha inválida"),
                    tr("As senhas informadas não coincidem."),
                )
                continue
            return password

    def _legacy_migration_credentials(self, document):
        if not document_signatures(document):
            document.pop("protection_preferences", None)
            return PUBLIC_MODE, None
        prompt = QMessageBox(self)
        prompt.setWindowTitle(tr("Proteção do modelo"))
        prompt.setText(tr(
            "Este modelo possui assinaturas. Recomendamos protegê-las com senha para "
            "evitar o uso não autorizado. Você também pode continuar sem senha; nesse "
            "caso, as assinaturas ficarão acessíveis dentro do arquivo do modelo."
        ))
        signatures_button = prompt.addButton(
            tr("Proteger assinaturas"), QMessageBox.ButtonRole.AcceptRole,
        )
        full_button = prompt.addButton(
            tr("Proteger modelo inteiro"), QMessageBox.ButtonRole.ActionRole,
        )
        public_button = prompt.addButton(
            tr("Salvar sem senha"), QMessageBox.ButtonRole.ActionRole,
        )
        prompt.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        style_message_box(prompt)
        prompt.exec()
        clicked = prompt.clickedButton()
        if clicked is signatures_button:
            mode = SIGNATURES_MODE
        elif clicked is full_button:
            mode = FULL_MODE
        elif clicked is public_button:
            document["protection_preferences"] = {
                "public_signatures_acknowledged": True,
            }
            return PUBLIC_MODE, None
        else:
            return None
        document.pop("protection_preferences", None)
        password = self._request_new_fornax_password()
        return (mode, password) if password is not None else None

    def _migrate_selected_legacy(self, model: LibraryModel) -> bool:
        try:
            document = load_model_document(model.path)
            credentials = self._legacy_migration_credentials(document)
            if credentials is None:
                return False
            mode, password = credentials
            result = migrate_legacy_model(
                model.path, get_models_dir(), mode=mode, password=password,
                public_signatures_acknowledged=(
                    mode == PUBLIC_MODE and bool(document_signatures(document))
                ),
            )
        except Exception as error:
            QMessageBox.critical(
                self, tr("Falha na conversão"),
                tr("O modelo antigo foi preservado e não pôde ser convertido:\n{erro}").format(
                    erro=error,
                ),
            )
            return False
        try:
            if mode == PUBLIC_MODE:
                self._fornax_sessions.select(result.destination)
            else:
                self._fornax_sessions.unlock(result.destination, password)
        except Exception as error:
            self.log_panel.append(
                tr("O modelo foi convertido, mas precisará ser aberto novamente: {erro}").format(
                    erro=error,
                )
            )
        self.log_panel.append(
            tr("Modelo convertido para .fornax: {nome}").format(nome=model.display_name)
        )
        if not result.cleanup_complete:
            QMessageBox.warning(
                self, tr("Conversão concluída com pendência"),
                tr("O arquivo .fornax foi criado e validado, mas alguns arquivos antigos mudaram ou não puderam ser removidos. O programa manterá somente o novo modelo na biblioteca."),
            )
        self._reload_models_from_disk(select_name=model.display_name)
        return True

    def _open_selected_fornax(self, model: LibraryModel):
        """Abre o conteúdo disponível sem interromper a seleção com diálogos."""
        status = self._fornax_sessions.select(model.path)
        if status.state in {
            AccessState.PUBLIC_ACTIVE,
            AccessState.AUTHORIZED_ACTIVE,
            AccessState.SIGNATURE_FREE_COPY,
        }:
            return self._fornax_sessions.document(), self._fornax_sessions.asset, status

        if status.descriptor.mode == SIGNATURES_MODE:
            status = self._fornax_sessions.open_without_signatures(model.path)
            return self._fornax_sessions.document(), self._fornax_sessions.asset, status
        return None

    def _unlock_selected_model(self):
        """Solicita a senha somente quando o usuário pede acesso ao conteúdo protegido."""
        model = self._current_library_entry()
        if model is None or not model.is_fornax or model.descriptor.mode == PUBLIC_MODE:
            return

        password = self._request_fornax_password(tr("Desbloquear modelo"))
        if password is None:
            return
        try:
            status = self._fornax_sessions.unlock(model.path, password)
        except FornaxError as error:
            QMessageBox.warning(self, tr("Não foi possível desbloquear"), str(error))
            return
        if status.public_changed:
            answer = QMessageBox.warning(
                self, tr("Possível alteração externa"),
                tr("Foi identificada uma possível alteração no conteúdo deste modelo desde o último salvamento protegido. Confira os textos, imagens e configurações antes de gerar materiais."),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                self._fornax_sessions.forget(model.path)
                self._on_model_changed(self.preview_panel.cbo_models.currentText())
                return
        document = self._fornax_sessions.document()
        display_name = str(document.get("name") or model.display_name)
        self._remember_protected_model_name(status.descriptor.model_id, display_name)
        self._reload_models_from_disk(select_name=display_name)

    def _toggle_selected_model_lock(self):
        model = self._current_library_entry()
        if model is None or not model.is_fornax or model.descriptor.mode == PUBLIC_MODE:
            return
        try:
            status = self._fornax_sessions.status(model.path)
        except FornaxError:
            status = None
        if status is not None and status.state == AccessState.AUTHORIZED_ACTIVE:
            if self.manager is not None and self.manager._is_running:
                QMessageBox.information(
                    self, tr("Processamento em andamento"),
                    tr("Aguarde o término da geração antes de bloquear o modelo."),
                )
                return
            self._fornax_sessions.forget(model.path)
            self.log_panel.append(
                tr("Modelo bloqueado: {nome}").format(nome=model.display_name)
            )
            self._on_model_changed(model.display_name)
            return
        self._unlock_selected_model()

    def _protect_current_model(self):
        """Eleva explicitamente um modelo público sem deixar backup aberto."""
        model = self._current_library_entry()
        if model is None or not model.is_fornax:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo FORNAX."))
            return
        if model.key.startswith("external:"):
            QMessageBox.information(
                self, tr("Modelo temporário"),
                tr("Para preservar o arquivo recebido, duplique o modelo ou abra o editor e salve-o como um novo modelo da biblioteca."),
            )
            return
        recovery = EditorWindow.fornax_recovery_path(model.path)
        if recovery.exists() or recovery.with_name(recovery.name + ".bak").exists():
            QMessageBox.warning(
                self, tr("Proteção do modelo"),
                tr("Há uma recuperação pendente deste modelo. Abra o editor e salve ou descarte a recuperação antes de ativar a proteção."),
            )
            return
        if model.descriptor.mode != PUBLIC_MODE:
            QMessageBox.information(self, tr("Modelo protegido"), tr("Este modelo já está protegido."))
            return
        try:
            opened = self._open_selected_fornax(model)
            if opened is None:
                return
            document, asset_provider, _status = opened
            has_signatures = bool(document_signatures(document))
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("Proteger modelo"))
            dialog.setText(tr("Escolha o alcance da proteção por senha."))
            signature_button = None
            if has_signatures:
                signature_button = dialog.addButton(
                    tr("Proteger assinaturas"), QMessageBox.ButtonRole.AcceptRole,
                )
            full_button = dialog.addButton(
                tr("Proteger modelo inteiro"), QMessageBox.ButtonRole.ActionRole,
            )
            dialog.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            style_message_box(dialog)
            dialog.exec()
            clicked = dialog.clickedButton()
            if signature_button is not None and clicked is signature_button:
                mode = SIGNATURES_MODE
            elif clicked is full_button:
                mode = FULL_MODE
            else:
                return
            password = self._request_new_fornax_password()
            if password is None:
                return
            save_protected_fornax(
                document, model.path, password, mode=mode,
                asset_provider=asset_provider, model_id=model.descriptor.model_id,
            )
            if mode == FULL_MODE:
                self._remember_protected_model_name(
                    model.descriptor.model_id, model.display_name,
                )
            self._fornax_sessions.forget(model.path)
            self._fornax_sessions.unlock(model.path, password)
            self.log_panel.append(
                tr("Proteção ativada para '{nome}'.").format(nome=model.display_name)
            )
            self._reload_models_from_disk(select_name=model.display_name)
        except Exception as error:
            QMessageBox.critical(
                self, tr("Erro"),
                tr("Falha ao proteger modelo:\n{erro}").format(erro=error),
            )

    def _approve_shared_model(self, opened):
        """Não redefine a referência autenticada sem revisão explícita."""
        if not opened.public_changed:
            return True
        return QMessageBox.warning(
            self, tr("Possível alteração externa"),
            tr("Foi identificada uma possível alteração no conteúdo deste modelo desde o último salvamento protegido. Confira os textos, imagens e configurações antes de gerar materiais."),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Ok

    def _on_add_model(self):
        self.editor_window = EditorWindow(self)
        self.editor_window.modelSaved.connect(self._on_editor_saved)
        self._connect_editor_lifecycle()
        self.editor_window.show()

    def _on_duplicate_model(self):
        original_name = self.preview_panel.cbo_models.currentText()
        
        if not original_name:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo para duplicar."))
            return

        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            counter = 1
            while True:
                suffix = " (Cópia)" if counter == 1 else f" (Cópia {counter})"
                new_name = f"{original_name}{suffix}"
                new_path = get_models_dir() / f"{slugify_model_name(new_name)}.fornax"
                if not new_path.exists() and not new_path.with_suffix("").exists():
                    break
                counter += 1
            try:
                descriptor = library_model.descriptor
                if descriptor.mode == "none":
                    opened = open_public_fornax(descriptor)
                    document = opened.document()
                    document["name"] = new_name
                    document.pop("protection_preferences", None)
                    credentials = self._legacy_migration_credentials(document)
                    if credentials is None:
                        return
                    mode, password = credentials
                    if mode == PUBLIC_MODE:
                        save_public_fornax(document, new_path, asset_provider=opened.asset)
                    else:
                        saved = save_protected_fornax(
                            document, new_path, password, mode=mode,
                            asset_provider=opened.asset,
                        )
                        if mode == FULL_MODE:
                            self._remember_protected_model_name(saved.model_id, new_name)
                else:
                    password = self._request_fornax_password(tr("Duplicar modelo protegido"))
                    if password is None:
                        return
                    opened = unlock_fornax(descriptor, password)
                    if not self._approve_shared_model(opened):
                        return
                    document = opened.document()
                    document["name"] = new_name
                    saved = save_protected_fornax(
                        document, new_path, password, mode=descriptor.mode,
                        asset_provider=opened.asset,
                    )
                    if descriptor.mode == FULL_MODE:
                        self._remember_protected_model_name(saved.model_id, new_name)
                self.log_panel.append(tr("Modelo duplicado: '{nome}'").format(nome=new_name))
                self._reload_models_from_disk(select_name=new_name)
            except Exception as error:
                QMessageBox.critical(
                    self, tr("Erro"),
                    tr("Falha ao duplicar modelo:\n{erro}").format(erro=error),
                )
            return

        original_slug = slugify_model_name(original_name)
        original_dir = get_models_dir() / original_slug

        if not original_dir.exists():
            self.log_panel.append(tr("ERRO: Pasta do modelo original não encontrada."))
            return

        counter = 1
        while True:
            suffix = " (Cópia)" if counter == 1 else f" (Cópia {counter})"
            new_name = f"{original_name}{suffix}"
            new_slug = slugify_model_name(new_name)
            new_dir = get_models_dir() / new_slug
            
            if not new_dir.exists():
                break
            counter += 1

        try:
            shutil.copytree(original_dir, new_dir)
            
            data = load_model_document(new_dir)
            data["name"] = new_name
            save_model_document(data, new_dir)

            self.log_panel.append(tr("Modelo duplicado: '{nome}'").format(nome=new_name))
            self._reload_models_from_disk(select_name=new_name)

        except Exception as e:
            QMessageBox.critical(self, tr("Erro"), tr("Falha ao duplicar modelo:\n{erro}").format(erro=e))
            if new_dir.exists():
                shutil.rmtree(new_dir, ignore_errors=True)

    def _on_rename_model(self):
        old_name = self.preview_panel.cbo_models.currentText()
        
        if not old_name:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo para renomear."))
            return

        current = self._current_library_entry()
        if current is not None and current.key.startswith("external:"):
            QMessageBox.information(
                self, tr("Modelo temporário"),
                tr("Para preservar o arquivo recebido, duplique o modelo ou abra o editor e salve-o como um novo modelo da biblioteca."),
            )
            return

        new_name, ok = dialog_get_text(
            self, tr("Renomear modelo"), tr("Novo nome:"), text=old_name
        )
        if not ok or not new_name.strip():
            return
        
        new_name = new_name.strip()
        if new_name == old_name:
            return

        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            new_path = get_models_dir() / f"{slugify_model_name(new_name)}.fornax"
            if new_path != library_model.path and new_path.exists():
                QMessageBox.warning(self, tr("Erro"), tr("Já existe um modelo com esse nome."))
                return
            try:
                descriptor = library_model.descriptor
                password = None
                if descriptor.mode == "none":
                    opened = open_public_fornax(descriptor)
                else:
                    password = self._request_fornax_password(tr("Renomear modelo protegido"))
                    if password is None:
                        return
                    opened = unlock_fornax(descriptor, password)
                    if not self._approve_shared_model(opened):
                        return
                document = opened.document()
                document["name"] = new_name
                if descriptor.mode == "none":
                    save_public_fornax(
                        document, new_path, asset_provider=opened.asset,
                        model_id=descriptor.model_id,
                    )
                else:
                    save_protected_fornax(
                        document, new_path, password, mode=descriptor.mode,
                        asset_provider=opened.asset, model_id=descriptor.model_id,
                    )
                    if descriptor.mode == FULL_MODE:
                        self._remember_protected_model_name(descriptor.model_id, new_name)
                if new_path != library_model.path:
                    library_model.path.unlink()
                    self._fornax_sessions.forget(library_model.path)
                self.log_panel.append(
                    tr("Modelo renomeado: '{anterior}' → '{novo}'").format(
                        anterior=old_name, novo=new_name,
                    )
                )
                self._reload_models_from_disk(select_name=new_name)
            except Exception as error:
                if new_path != library_model.path:
                    new_path.unlink(missing_ok=True)
                QMessageBox.critical(
                    self, tr("Erro"), tr("Falha ao renomear: {erro}").format(erro=error),
                )
            return

        old_slug = slugify_model_name(old_name)
        new_slug = slugify_model_name(new_name)
        
        old_dir = get_models_dir() / old_slug
        new_dir = get_models_dir() / new_slug

        # Se os slugs forem diferentes e o destino já existe, há um conflito real.
        if new_slug != old_slug and new_dir.exists():
            QMessageBox.warning(self, tr("Erro"), tr("Já existe um modelo com o identificador '{slug}'.").format(slug=new_slug))
            return

        folder_renamed = False
        try:
            # 1. Renomeia a pasta apenas se o slug mudou
            if new_slug != old_slug:
                old_dir.rename(new_dir)
                folder_renamed = True
            
            # 2. Define o caminho correto do JSON para atualizar o nome visual
            actual_dir = new_dir if new_slug != old_slug else old_dir
            data = load_model_document(actual_dir)
            data["name"] = new_name
            save_model_document(data, actual_dir)
            old_key = f"workspace/dynamic_images/{old_slug}"
            new_key = f"workspace/dynamic_images/{new_slug}"
            remembered = self.settings.value(old_key, "")
            if remembered and not self.settings.value(new_key, ""):
                self.settings.setValue(new_key, remembered)
            if old_key != new_key:
                self.settings.remove(old_key)
            self.settings.sync()
            
            self.log_panel.append(tr("Modelo renomeado: '{anterior}' → '{novo}'").format(anterior=old_name, novo=new_name))
            self._reload_models_from_disk(select_name=new_name)

        except Exception as e:
            if folder_renamed and new_dir.exists() and not old_dir.exists():
                try:
                    new_dir.rename(old_dir)
                except OSError:
                    pass
            QMessageBox.critical(self, tr("Erro"), tr("Falha ao renomear: {erro}").format(erro=e))

    def _on_remove_model(self):
        model_name = (self.preview_panel.cbo_models.currentText() or "").strip()
        if not model_name: return

        library_model = self._current_library_entry()
        slug = slugify_model_name(model_name)
        model_dir = library_model.path if library_model is not None else get_models_dir() / slug

        if not model_dir.exists(): return

        resp = QMessageBox.question(self, tr("Confirmar exclusão"), tr("Excluir '{nome}'?").format(nome=model_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes: return

        try:
            if model_dir.is_dir():
                shutil.rmtree(model_dir)
            else:
                model_dir.unlink()
                self._fornax_sessions.forget(model_dir)
                if library_model is not None and library_model.descriptor is not None:
                    self._forget_protected_model_name(library_model.descriptor.model_id)
        except Exception as e:
            QMessageBox.critical(self, tr("Erro"), tr("Falha ao excluir: {erro}").format(erro=e))
            return

        self.settings.remove(self._dynamic_image_settings_key())
        if library_model is not None:
            self._forget_model_library_order(library_model.key)
        self.settings.sync()
        self.log_panel.append(tr("Modelo excluído: {nome}").format(nome=model_name))
        self._reload_models_from_disk()

    def _on_import_models(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Importar modelos"), "",
            tr("Modelos FORNAX (*.fornax *.zip)"),
        )
        if not file_path: return

        self._dispatch_import_path(file_path)

    def _dispatch_import_path(self, file_path):

        path = Path(file_path)
        modern = path.suffix.lower() == ".fornax"
        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    names = [info.filename for info in archive.infolist()]
                modern = bool(names) and all(
                    "/" not in name and "\\" not in name
                    and Path(name).suffix.lower() == ".fornax"
                    for name in names
                )
            except (OSError, zipfile.BadZipFile):
                modern = True
        if modern:
            self._on_import_fornax(file_path)
        else:
            self._on_import_legacy_zip(file_path)

    def _on_import_fornax(self, file_path):
        try:
            models_dir = get_models_dir()
            with open_import_package(file_path) as candidates:
                existing_slugs = {
                    slugify_model_name(model.display_name)
                    for model in self._library_models_by_key.values()
                }
                modes = {
                    PUBLIC_MODE: tr("Sem proteção"),
                    SIGNATURES_MODE: tr("Assinaturas protegidas"),
                    FULL_MODE: tr("Modelo integralmente protegido"),
                }
                dialog_models = [
                    (candidate.entry_name, candidate.display_name, modes[candidate.descriptor.mode])
                    for candidate in candidates
                ]
                dlg = ImportModelsDialog(self, dialog_models, existing_slugs)
                if not dlg.exec():
                    return
                decisions = dlg.get_decisions()
                selected = [
                    candidate for candidate in candidates
                    if decisions.get(candidate.entry_name, {}).get("import")
                    and decisions[candidate.entry_name]["action"] != "ignore"
                ]
                if not selected:
                    return

                protected = [
                    candidate for candidate in selected
                    if candidate.descriptor.mode != PUBLIC_MODE
                ]
                candidates_with_signatures = [
                    candidate for candidate in selected
                    if candidate.descriptor.mode != PUBLIC_MODE
                    or candidate.descriptor.version == 2
                ]
                include_signatures = False
                if candidates_with_signatures:
                    prompt = QMessageBox(self)
                    prompt.setWindowTitle(tr("Importar assinaturas"))
                    prompt.setText(tr("Deseja incorporar as assinaturas dos modelos selecionados?"))
                    include_button = prompt.addButton(
                        tr("Importar com assinaturas"), QMessageBox.ButtonRole.AcceptRole,
                    )
                    remove_button = prompt.addButton(
                        tr("Importar sem assinaturas"), QMessageBox.ButtonRole.ActionRole,
                    )
                    prompt.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
                    prompt.exec()
                    if prompt.clickedButton() is include_button:
                        include_signatures = True
                    elif prompt.clickedButton() is not remove_button:
                        return

                must_unlock = [
                    candidate for candidate in protected
                    if include_signatures or candidate.descriptor.mode == FULL_MODE
                ]
                common_transport = None
                if must_unlock:
                    common_transport = self._request_fornax_password(
                        tr("Senha recebida com a exportação")
                    )
                    if common_transport is None:
                        return

                authorized = {}
                skipped = []
                signature_choice = {
                    candidate.entry_name: (
                        include_signatures
                        if candidate in candidates_with_signatures else False
                    )
                    for candidate in selected
                }
                for candidate in must_unlock:
                    password = common_transport
                    while True:
                        try:
                            approved_hash = file_sha256(candidate.path)
                            opened = unlock_fornax(candidate.descriptor, password)
                            if not self._approve_shared_model(opened):
                                skipped.append(candidate.entry_name)
                                break
                            # Não reter documentos/assets de todo o lote decifrados.
                            authorized[candidate.entry_name] = (password, approved_hash)
                            opened = None
                            break
                        except FornaxError:
                            retry = QMessageBox(self)
                            retry.setWindowTitle(tr("Senha inválida"))
                            retry.setText(tr("Não foi possível desbloquear '{nome}'.").format(
                                nome=candidate.display_name,
                            ))
                            retry_button = retry.addButton(
                                tr("Tentar outra senha"), QMessageBox.ButtonRole.AcceptRole,
                            )
                            without_button = None
                            if candidate.descriptor.mode == SIGNATURES_MODE:
                                without_button = retry.addButton(
                                    tr("Importar sem assinaturas"), QMessageBox.ButtonRole.ActionRole,
                                )
                            skip_button = retry.addButton(
                                tr("Ignorar modelo"), QMessageBox.ButtonRole.DestructiveRole,
                            )
                            retry.addButton(tr("Cancelar importação"), QMessageBox.ButtonRole.RejectRole)
                            retry.exec()
                            clicked = retry.clickedButton()
                            if clicked is retry_button:
                                password = self._request_fornax_password(
                                    tr("Senha recebida com a exportação")
                                )
                                if password is None:
                                    return
                                continue
                            if without_button is not None and clicked is without_button:
                                signature_choice[candidate.entry_name] = False
                                break
                            if clicked is skip_button:
                                skipped.append(candidate.entry_name)
                                break
                            return

                selected = [
                    candidate for candidate in selected
                    if candidate.entry_name not in skipped
                ]
                target_modes = {
                    candidate.entry_name: (
                        candidate.descriptor.mode
                        if candidate.descriptor.mode != PUBLIC_MODE
                        and signature_choice[candidate.entry_name]
                        else PUBLIC_MODE
                    )
                    for candidate in selected
                }
                public_signed = [
                    candidate for candidate in selected
                    if candidate.descriptor.mode == PUBLIC_MODE
                    and candidate.descriptor.version == 2
                    and signature_choice[candidate.entry_name]
                ]
                if public_signed:
                    protection_prompt = QMessageBox(self)
                    protection_prompt.setWindowTitle(tr("Proteção local"))
                    protection_prompt.setText(tr(
                        "Os modelos públicos selecionados possuem assinaturas. "
                        "Recomendamos protegê-las com senha."
                    ))
                    signatures_button = protection_prompt.addButton(
                        tr("Proteger assinaturas"), QMessageBox.ButtonRole.AcceptRole,
                    )
                    full_button = protection_prompt.addButton(
                        tr("Proteger modelo inteiro"), QMessageBox.ButtonRole.ActionRole,
                    )
                    public_button = protection_prompt.addButton(
                        tr("Manter sem senha"), QMessageBox.ButtonRole.ActionRole,
                    )
                    protection_prompt.addButton(
                        tr("Cancelar"), QMessageBox.ButtonRole.RejectRole,
                    )
                    style_message_box(protection_prompt)
                    protection_prompt.exec()
                    clicked = protection_prompt.clickedButton()
                    if clicked is signatures_button:
                        public_target_mode = SIGNATURES_MODE
                    elif clicked is full_button:
                        public_target_mode = FULL_MODE
                    elif clicked is public_button:
                        public_target_mode = PUBLIC_MODE
                    else:
                        return
                    for candidate in public_signed:
                        target_modes[candidate.entry_name] = public_target_mode

                protected_local = [
                    candidate for candidate in selected
                    if target_modes[candidate.entry_name] != PUBLIC_MODE
                ]
                local_passwords = {}
                if protected_local:
                    password_prompt = QMessageBox(self)
                    password_prompt.setWindowTitle(tr("Nova proteção local"))
                    password_prompt.setText(tr("Como deseja definir as novas senhas locais?"))
                    common_button = password_prompt.addButton(
                        tr("Usar a mesma senha"), QMessageBox.ButtonRole.AcceptRole,
                    )
                    individual_button = password_prompt.addButton(
                        tr("Definir individualmente"), QMessageBox.ButtonRole.ActionRole,
                    )
                    password_prompt.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
                    password_prompt.exec()
                    clicked = password_prompt.clickedButton()
                    if clicked is common_button:
                        password = self._request_new_fornax_password()
                        if password is None:
                            return
                        local_passwords = {
                            candidate.entry_name: password for candidate in protected_local
                        }
                    elif clicked is individual_button:
                        for candidate in protected_local:
                            QMessageBox.information(
                                self, tr("Nova senha local"),
                                tr("Defina a senha local de '{nome}'.").format(
                                    nome=candidate.display_name,
                                ),
                            )
                            password = self._request_new_fornax_password()
                            if password is None:
                                skipped.append(candidate.entry_name)
                                continue
                            local_passwords[candidate.entry_name] = password
                    else:
                        return

                imported = []
                failures = []
                for candidate in selected:
                    if candidate.entry_name in skipped:
                        continue
                    decision = decisions[candidate.entry_name]
                    target_name = candidate.display_name
                    target_slug = slugify_model_name(target_name) or "modelo"
                    conflict = (
                        (models_dir / target_slug).exists()
                        or (models_dir / f"{target_slug}.fornax").exists()
                    )
                    if decision["action"] == "rename" and conflict:
                        base_name = tr("{nome} (Nova importação)").format(nome=target_name)
                        target_name = base_name
                        target_slug = slugify_model_name(target_name)
                        counter = 2
                        while (
                            (models_dir / target_slug).exists()
                            or (models_dir / f"{target_slug}.fornax").exists()
                        ):
                            target_name = f"{base_name} {counter}"
                            target_slug = slugify_model_name(target_name)
                            counter += 1
                    destination = models_dir / f"{target_slug}.fornax"
                    legacy_path = models_dir / target_slug
                    try:
                        import_candidate(
                            candidate, destination,
                            include_signatures=signature_choice[candidate.entry_name],
                            target_mode=target_modes[candidate.entry_name],
                            public_signatures_acknowledged=(
                                target_modes[candidate.entry_name] == PUBLIC_MODE
                                and signature_choice[candidate.entry_name]
                            ),
                            transport_password=authorized.get(candidate.entry_name, (None, None))[0],
                            approved_sha256=authorized.get(candidate.entry_name, (None, None))[1],
                            local_password=local_passwords.get(candidate.entry_name),
                            model_name=target_name,
                            replace_existing=decision["action"] == "replace",
                            legacy_source=(legacy_path if decision["action"] == "replace" and legacy_path.is_dir() else None),
                        )
                        if decision["action"] == "replace" and legacy_path.is_dir():
                            failures.append(f"{target_name}: " + tr("Limpeza da pasta antiga pendente; os arquivos restantes foram preservados."))
                        imported.append(target_name)
                    except Exception as error:
                        failures.append(f"{candidate.display_name}: {error}")

            if imported:
                self._reload_models_from_disk(select_name=imported[-1])
                self.log_panel.append(
                    tr("📥 {quantidade} modelo(s) incorporado(s) de: {arquivo}").format(
                        quantidade=len(imported), arquivo=Path(file_path).name,
                    )
                )
            report = []
            if imported:
                report.append(tr("Importados: {quantidade}").format(quantidade=len(imported)))
            if skipped:
                report.append(tr("Ignorados: {quantidade}").format(quantidade=len(skipped)))
            if failures:
                report.append(tr("Falhas:\n{falhas}").format(falhas="\n".join(failures)))
            QMessageBox.information(
                self, tr("Importação concluída"), "\n\n".join(report),
            )
        except Exception as error:
            QMessageBox.critical(
                self, tr("Falha na importação"),
                tr("Não foi possível importar o pacote:\n{erro}").format(erro=error),
            )

    def _on_import_legacy_zip(self, file_path):

        try:
            models_dir = get_models_dir()
            
            # Etapa 1: Espionagem do ZIP (Leitura ultrarrápida de cabeçalhos sem extrair)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                infos = zip_ref.infolist()
                if len(infos) > 10000 or sum(info.file_size for info in infos) > 4 * 1024**3:
                    raise ValueError(tr("O pacote legado excede os limites de segurança."))
                seen_names = set()
                for info in infos:
                    member = PurePosixPath(info.filename)
                    folded = info.filename.casefold()
                    unix_mode = (info.external_attr >> 16) & 0o170000
                    if (
                        not info.filename or "\\" in info.filename or ":" in info.filename
                        or any(ord(c) < 32 for c in info.filename)
                        or member.as_posix() != info.filename.rstrip("/")
                        or member.is_absolute() or ".." in member.parts
                        or folded in seen_names or info.flag_bits & 0x1
                        or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                        or unix_mode == 0o120000
                    ):
                        raise ValueError(tr("O pacote legado contém uma entrada insegura."))
                    seen_names.add(folded)
                # Descobre as pastas de modelo dentro do zip
                top_level_folders = set(info.filename.split('/')[0] for info in infos if '/' in info.filename)
                names = set(zip_ref.namelist())
                
                models_in_zip = {} # Mapeamento (Nome Legível do JSON -> Nome da Pasta no Zip)
                for zip_slug in sorted(top_level_folders):
                    json_path = next((f"{zip_slug}/{filename}" for filename in (V4_FILENAME, V3_FILENAME)
                                      if f"{zip_slug}/{filename}" in names), None)
                    if json_path is None:
                        continue
                    try:
                        with zip_ref.open(json_path) as f:
                            document = normalize_model_document(json.loads(f.read().decode('utf-8')))
                            name = document.get("name", zip_slug)
                            models_in_zip[name] = zip_slug
                    except (KeyError, ValueError, UnicodeError, json.JSONDecodeError):
                        continue
                        
                if not models_in_zip:
                    QMessageBox.warning(self, tr("Arquivo inválido"), tr("Este arquivo ZIP não contém modelos compatíveis com o FORNAX Forge."))
                    return
                
                # Etapa 2: Checagem de Conflitos e Abertura da Janela de Decisão
                existing_slugs = {d.name if d.is_dir() else d.stem for d in models_dir.iterdir()
                                  if d.is_dir() or d.suffix.lower() == ".fornax"}
                
                dlg = ImportModelsDialog(self, list(models_in_zip.keys()), existing_slugs)
                if not dlg.exec():
                    return # O usuário clicou em Cancelar
                    
                decisions = dlg.get_decisions()
                
                # Etapa 3: Extração Cirúrgica via Cache Temporário
                imported_count = 0
                failures = []
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_ref.extractall(temp_dir)
                    
                    for model_name, decision in decisions.items():
                        if not decision["import"] or decision["action"] == "ignore":
                            continue # Pula modelos desmarcados ou ignorados
                            
                        zip_slug = models_in_zip[model_name]
                        source_dir = Path(temp_dir) / zip_slug
                        if not source_dir.exists():
                            continue

                        # Valida e publica o documento completo antes de tocar na
                        # biblioteca. Isso também promove pacotes v3 para v4 sem
                        # descartar uma eventual página de verso.
                        try:
                            imported_document = load_model_document(source_dir)
                        except Exception:
                            continue
                            
                        target_slug = slugify_model_name(model_name)
                        target_name = model_name
                        
                        # Tratamento da Rota Escolhida
                        if decision["action"] == "rename":
                            # Validação dupla: Se por acaso o usuário marcou "Novo Nome" mas o arquivo 
                            # não era conflito, ele mantém o original. Se for conflito, roda a lógica.
                            if (models_dir / target_slug).exists() or (models_dir / f"{target_slug}.fornax").exists():
                                counter = 1
                                base_name = f"{model_name} (Nova Importação)"
                                target_name = base_name
                                target_slug = slugify_model_name(target_name)
                                
                                # Garante um nome livre na pasta de modelos (Ex: Nova Importação 2)
                                while (models_dir / target_slug).exists() or (models_dir / f"{target_slug}.fornax").exists():
                                    counter += 1
                                    target_name = f"{base_name} {counter}"
                                    target_slug = slugify_model_name(target_name)
                            
                            # Entra no modelo temporário e atualiza o JSON dele silenciosamente
                            imported_document['name'] = target_name

                        imported_document["origin_info"] = build_model_snapshot(
                            imported_document, source="imported"
                        )
                        try:
                            credentials = self._legacy_migration_credentials(imported_document)
                            if credentials is None:
                                continue
                            mode, password = credentials
                            legacy_target = models_dir / target_slug
                            import_legacy_document(
                                imported_document, source_dir, models_dir / f"{target_slug}.fornax",
                                mode=mode,
                                include_signatures=bool(document_signatures(imported_document)),
                                public_signatures_acknowledged=(
                                    mode == PUBLIC_MODE
                                    and bool(document_signatures(imported_document))
                                ),
                                password=password,
                                replace_existing=decision["action"] == "replace",
                                legacy_source=(legacy_target if decision["action"] == "replace" and legacy_target.is_dir() else None),
                            )
                            if decision["action"] == "replace" and legacy_target.is_dir():
                                self.log_panel.append(tr("Limpeza da pasta antiga pendente; os arquivos restantes foram preservados."))
                            imported_count += 1
                        except Exception as error:
                            failures.append(f"{model_name}: {error}")
            
            # Etapa 4: Finalização e Limpeza Automática do TempDir
            if imported_count > 0:
                imported_log = (
                    tr("📥 1 modelo processado e importado de: {arquivo}")
                    if imported_count == 1 else
                    tr("📥 {quantidade} modelos processados e importados de: {arquivo}")
                )
                self.log_panel.append(imported_log.format(
                    quantidade=imported_count, arquivo=Path(file_path).name,
                ))
                self._reload_models_from_disk()
                imported_message = (
                    tr("1 modelo adicionado à sua biblioteca!") if imported_count == 1 else
                    tr("{quantidade} modelos adicionados à sua biblioteca!").format(quantidade=imported_count)
                )
                QMessageBox.information(self, tr("Importação concluída"), imported_message)
            else:
                self.log_panel.append(tr("⚠️ Processo finalizado: nenhum modelo novo foi adicionado."))
            if failures:
                QMessageBox.warning(self, tr("Falha na importação"), "\n".join(failures))
                
        except Exception as e:
            QMessageBox.critical(self, tr("Falha crítica"), tr("Falha ao processar o arquivo ZIP:\n{erro}").format(erro=e))

    def _on_export_models(self):
        all_models = [
            (
                self.preview_panel.cbo_models.itemData(i),
                self.preview_panel.cbo_models.itemText(i),
            )
            for i in range(self.preview_panel.cbo_models.count())
        ]
        
        if not all_models:
            QMessageBox.warning(self, tr("Atenção"), tr("Nenhum modelo disponível para exportar."))
            return
            
        dlg = ExportModelsDialog(self, all_models)
        if not dlg.exec():
            return
            
        selected_keys = dlg.get_selected_models()
        if not selected_keys:
            QMessageBox.warning(self, tr("Atenção"), tr("Nenhum modelo foi selecionado para exportação."))
            return
        selected = [
            self._library_models_by_key[str(key)]
            for key in selected_keys
            if str(key) in self._library_models_by_key
        ]
        legacy = [model.display_name for model in selected if not model.is_fornax]
        selected = [model for model in selected if model.is_fornax]
        if legacy:
            QMessageBox.warning(
                self, tr("Modelos antigos não exportados"),
                tr("Abra estes modelos uma vez para convertê-los antes da exportação:\n{modelos}").format(
                    modelos="\n".join(legacy),
                ),
            )
        if not selected:
            return

        protected = [model for model in selected if model.descriptor.mode != PUBLIC_MODE]
        signature_bearing = [
            model for model in selected
            if model.descriptor.mode != PUBLIC_MODE or model.descriptor.version == 2
        ]
        include_signatures = False
        if signature_bearing:
            prompt = QMessageBox(self)
            prompt.setWindowTitle(tr("Exportar assinaturas"))
            prompt.setText(tr("Deseja incluir as assinaturas dos modelos selecionados?"))
            include_button = prompt.addButton(
                tr("Enviar com assinaturas"), QMessageBox.ButtonRole.AcceptRole,
            )
            remove_button = prompt.addButton(
                tr("Enviar sem assinaturas"), QMessageBox.ButtonRole.ActionRole,
            )
            prompt.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            prompt.exec()
            if prompt.clickedButton() is include_button:
                include_signatures = True
            elif prompt.clickedButton() is not remove_button:
                return

        common_password = None
        if protected and (include_signatures or any(
            model.descriptor.mode == FULL_MODE for model in protected
        )):
            common_password = self._request_fornax_password(
                tr("Desbloquear modelos para exportação")
            )
            if common_password is None:
                return

        requests = []
        skipped = []
        for model in selected:
            descriptor = model.descriptor
            if descriptor.mode == PUBLIC_MODE:
                requests.append(ExportRequest(model.path, model.display_name))
                continue
            include_for_model = include_signatures
            needs_unlock = include_signatures or descriptor.mode == FULL_MODE
            password = common_password if needs_unlock else None
            opened = None
            approved_hash = None
            if needs_unlock:
                while True:
                    try:
                        approved_hash = file_sha256(model.path)
                        opened = unlock_fornax(descriptor, password)
                        if not self._approve_shared_model(opened):
                            skipped.append(model.display_name)
                        break
                    except FornaxError:
                        retry = QMessageBox(self)
                        retry.setWindowTitle(tr("Senha inválida"))
                        retry.setText(tr("Não foi possível desbloquear '{nome}'.").format(
                            nome=model.display_name,
                        ))
                        retry_button = retry.addButton(
                            tr("Tentar outra senha"), QMessageBox.ButtonRole.AcceptRole,
                        )
                        without_button = None
                        if descriptor.mode == SIGNATURES_MODE:
                            without_button = retry.addButton(
                                tr("Enviar sem assinaturas"), QMessageBox.ButtonRole.ActionRole,
                            )
                        skip_button = retry.addButton(
                            tr("Ignorar modelo"), QMessageBox.ButtonRole.DestructiveRole,
                        )
                        retry.addButton(tr("Cancelar exportação"), QMessageBox.ButtonRole.RejectRole)
                        retry.exec()
                        clicked = retry.clickedButton()
                        if clicked is retry_button:
                            password = self._request_fornax_password(
                                tr("Desbloquear modelo")
                            )
                            if password is None:
                                return
                            continue
                        if without_button is not None and clicked is without_button:
                            password = None
                            include_for_model = False
                            break
                        if clicked is skip_button:
                            skipped.append(model.display_name)
                            break
                        return
                if model.display_name in skipped:
                    continue
            requests.append(ExportRequest(
                model.path, model.display_name, local_password=password,
                include_signatures=include_for_model, approved_sha256=approved_hash,
            ))
            opened = None
        if not requests:
            return

        needs_transport_password = any(
            request.include_signatures
            and inspect_fornax(request.source).mode != PUBLIC_MODE
            for request in requests
        )
        transport_password = None
        if needs_transport_password:
            QMessageBox.information(
                self, tr("Senha de exportação"),
                tr("Crie uma senha exclusiva para este envio. O destinatário usará essa senha apenas para importar os modelos."),
            )
            transport_password = self._request_new_fornax_password()
            if transport_password is None:
                return

        single = len(requests) == 1
        if single:
            default_name = f"{slugify_model_name(requests[0].display_name)}.fornax"
            file_filter = tr("Modelo FORNAX (*.fornax)")
        else:
            default_name = "Modelos_FORNAX_Forge.zip"
            file_filter = tr("Arquivos ZIP (*.zip)")
        save_path, _ = QFileDialog.getSaveFileName(
            self, tr("Exportar modelos"), default_name, file_filter,
        )
        if not save_path:
            return

        try:
            exported = export_models(
                requests, save_path, include_signatures=include_signatures,
                transport_password=transport_password,
            )
            exported_count = len(exported)
            exported_log = (
                tr("📤 1 modelo exportado para: {arquivo}") if exported_count == 1 else
                tr("📤 {quantidade} modelos exportados para: {arquivo}")
            )
            self.log_panel.append(exported_log.format(
                quantidade=exported_count, arquivo=Path(save_path).name,
            ))
            exported_message = (
                tr("1 modelo exportado com sucesso!") if exported_count == 1 else
                tr("{quantidade} modelos exportados com sucesso!").format(quantidade=exported_count)
            )
            QMessageBox.information(self, tr("Sucesso"), exported_message)
            if skipped:
                QMessageBox.warning(
                    self, tr("Modelos não exportados"),
                    tr("Os seguintes modelos foram ignorados:\n{modelos}").format(
                        modelos="\n".join(skipped),
                    ),
                )
        except Exception as e:
            QMessageBox.critical(
                self, tr("Erro na exportação"),
                tr("Falha ao exportar os modelos:\n{erro}").format(erro=e),
            )

    def _on_model_changed(self, name: str):
        self._preview_generation = getattr(self, "_preview_generation", 0) + 1
        generation = self._preview_generation
        self.preview_renderer = None
        self._preview_renderers = []
        self._fornax_asset_provider = None
        self._protected_preview_memory_only = False
        self._active_fornax_status = None
        self.cached_model_data = None
        self.cached_model_document = None
        self._preview_mode = "item"
        self._preview_item_index = 0
        self._preview_page_index = 0
        self._preview_sheet_index = 0
        self._invalidate_sheet_previews()
        self.preview_panel.set_page_navigation(1, 0)
        self.preview_panel.set_model_lock_state(False)
        self.preview_panel.set_preview_text(tr("Prévia do modelo selecionado:\n{nome}").format(nome=name))
        self.log_panel.append(tr("Modelo ativo: {nome}").format(nome=name))
        self.active_model_name = name
        self.current_filename_suffix = ""

        if not name:
            self._fornax_sessions.leave_active()
            self._active_library_model = None
            self._update_table_columns([])
            return

        model_id = self.preview_panel.cbo_models.currentData()
        if model_id:
            self.settings.setValue("workspace/last_model_id", str(model_id))
            self._remember_recent_model(str(model_id))
            self.settings.sync()

        library_model = self._current_library_entry()
        self._active_library_model = library_model
        if library_model is not None and not library_model.is_fornax:
            if self._migrate_selected_legacy(library_model):
                return
            self._fornax_sessions.leave_active()
            self.cached_model_data = None
            self.cached_model_document = None
            self._update_table_columns([])
            self.preview_panel.set_preview_text(tr("Conversão do modelo cancelada"))
            if hasattr(self, "btn_config_model"):
                self.btn_config_model.setEnabled(False)
            return
        if library_model is not None and library_model.is_fornax:
            opened = self._open_selected_fornax(library_model)
            if opened is None:
                self.preview_panel.set_preview_text(tr("Modelo protegido"))
                self.preview_panel.set_model_lock_state(True)
                self._update_table_columns([])
                if hasattr(self, "btn_config_model"):
                    self.btn_config_model.setEnabled(False)
                return
            document, asset_provider, status = opened
            self._load_fornax_document(document, asset_provider, status)
            return
        self._fornax_sessions.leave_active()
        if hasattr(self, "btn_config_model"):
            self.btn_config_model.setEnabled(True)

        slug = slugify_model_name(name)
        model_dir = get_models_dir() / slug
        try:
            json_path = resolve_model_file(model_dir)
        except FileNotFoundError:
            self.log_panel.append(tr("ERRO: modelo '{nome}' não encontrado.").format(nome=name))
            return

        if json_path.exists():
            try:
                    document = load_model_document(model_dir)
                    data = adapt_model_page(document, "front")
                    
                    self.current_filename_suffix = data.get("output_suffix", "")

                    # Recupera o modo novo e também entende as preferências legadas.
                    last_fmt = data.get("last_export_format", "PNG")
                    last_single = data.get("last_single_pdf", False)
                    last_mode = data.get("last_export_mode")
                    if last_mode not in {"png", "pdf_item", "pdf_grouped"}:
                        last_mode = (
                            "png" if last_fmt == "PNG" else
                            ("pdf_grouped" if last_single else "pdf_item")
                        )

                    self.cbo_export_format.blockSignals(True)
                    idx = self.cbo_export_format.findData(last_mode)
                    if idx >= 0:
                        self.cbo_export_format.setCurrentIndex(idx)
                    self.cbo_export_format.blockSignals(False)
                    self._refresh_export_mode_tooltip()

                    model_dir = json_path.parent
                    if data.get("background_path") and not Path(data["background_path"]).is_absolute():
                        data["background_path"] = str(model_dir / data["background_path"])
                    for sig in data.get("signatures", []):
                        if not Path(sig["path"]).is_absolute():
                            sig["path"] = str(model_dir / sig["path"])
                    data["__model_dir"] = str(model_dir)
                    ensure_background_proxy(model_dir, data)

                    placeholders = document.get("placeholders", [])
                    signatures = document_signatures(document)
                    self._update_table_columns(placeholders, signatures)
                    
                    self.cached_model_data = data
                    self.cached_model_document = document
                    self._configure_dynamic_images_for_model(document)
                    self.preview_panel.set_page_navigation(len(document["pages"]), 0)
                    self._refresh_imposition_presets()
                    self._refresh_preview_navigation()

                    try:
                        # Cria o "Chef" na memória (operação ultraleve, sem desenho)
                        self._preview_renderers = renderers_for_document(document)
                        self.preview_renderer = self._preview_renderers[0]
                        
                        # Carregamento Instantâneo da Thumbnail de Performance ---
                        thumb_path = get_thumbnail_cache_path(model_dir, json_path, "front")
                        
                        if thumb_path is not None:
                            self.preview_panel.set_preview_image(str(thumb_path))
                        else:
                            # --- LEGO: Worker de Preview Assíncrono ---
                            self.preview_panel.set_preview_text(
                                tr("Gerando prévia, aguarde um instante…")
                            )
                            
                            from features.generator.workers import PreviewRenderWorker
                            
                            worker = PreviewRenderWorker(name, data, model_dir)
                            # Anexa à janela para o Garbage Collector não matar a Thread no meio do processo
                            worker.setParent(self)
                            self._preview_workers.add(worker)
                            
                            worker.preview_ready.connect(lambda model, path, revision=generation: self._on_preview_ready(model, path) if revision == self._preview_generation else None)
                            worker.error_occurred.connect(lambda msg: self.log_panel.append(tr("Erro ao gerar a prévia em segundo plano: {erro}").format(erro=msg)))
                            worker.finished.connect(
                                lambda current=worker: self._preview_workers.discard(current)
                            )
                            worker.finished.connect(worker.deleteLater)
                        
                            worker.start()
                            # --- FIM DO LEGO ---

                    except Exception as e:
                        self.log_panel.append(tr("Erro ao gerar a prévia: {erro}").format(erro=e))
                        self.preview_panel.set_preview_text(tr("Erro ao gerar a prévia do modelo"))
                    self._start_sheet_preview_preload()
            except Exception as e:
                self.log_panel.append(tr("Erro ao ler as colunas do modelo: {erro}").format(erro=e))

    def _load_fornax_document(self, document, asset_provider, status):
        """Apresenta um snapshot autorizado sem criar arquivos de cache abertos."""
        data = adapt_model_page(document, "front")
        self.current_filename_suffix = data.get("output_suffix", "")
        last_fmt = data.get("last_export_format", "PNG")
        last_single = data.get("last_single_pdf", False)
        last_mode = data.get("last_export_mode")
        if last_mode not in {"png", "pdf_item", "pdf_grouped"}:
            last_mode = "png" if last_fmt == "PNG" else (
                "pdf_grouped" if last_single else "pdf_item"
            )
        self.cbo_export_format.blockSignals(True)
        index = self.cbo_export_format.findData(last_mode)
        if index >= 0:
            self.cbo_export_format.setCurrentIndex(index)
        self.cbo_export_format.blockSignals(False)
        self._refresh_export_mode_tooltip()

        self._fornax_asset_provider = asset_provider
        self._active_fornax_status = status
        self.preview_panel.set_model_lock_state(
            status.descriptor.mode != PUBLIC_MODE,
            unlocked=status.state == AccessState.AUTHORIZED_ACTIVE,
        )
        self._protected_preview_memory_only = (
            status.descriptor.mode != "none"
            and status.state == AccessState.AUTHORIZED_ACTIVE
        )
        self.cached_model_document = document
        self.cached_model_data = data
        self._update_table_columns(
            document.get("placeholders", []), document_signatures(document)
        )
        self._configure_dynamic_images_for_model(document)
        self.preview_panel.set_page_navigation(len(document["pages"]), 0)
        self._refresh_imposition_presets()
        self._preview_renderers = renderers_for_document(
            document, asset_provider=asset_provider,
        )
        self.preview_renderer = self._preview_renderers[0]
        self.preview_panel.set_preview_pixmap(
            self.preview_renderer.render_to_pixmap(row_rich=None, max_side=1600)
        )
        self._refresh_preview_navigation()
        if status.notice:
            self.log_panel.append(status.notice)
        if hasattr(self, "btn_config_model"):
            self.btn_config_model.setEnabled(True)

    # --- LEGO: Recebimento do Preview e Descarte Inteligente ---
    def _on_preview_ready(self, worker_model_name: str, thumb_path: str):
        """Atualiza a UI apenas se o usuário ainda estiver aguardando este modelo específico."""
        if (self.active_model_name == worker_model_name
                and self._preview_page_index == 0
                and self.table_panel.table.currentRow() < 0):
            self.preview_panel.set_preview_image(thumb_path)
        # Nota: Se os nomes forem diferentes, significa que o usuário já trocou de modelo. 
        # A UI ignora, mas a imagem já ficou salva no disco em background para a próxima vez.
    # --- FIM DO LEGO ---

    def _update_table_columns(self, placeholders, signatures=None):
        self.table_panel.table.clearContents()
        self.table_panel.table.setRowCount(0)
        self.table_panel.table.setColumnCount(0)
        
        signatures = list(signatures or [])
        column_count = 1 + len(signatures) + len(placeholders)
        self.table_panel.table.setColumnCount(column_count)
        self.table_panel.table.setHorizontalHeaderItem(0, QTableWidgetItem(quantity_header_label()))
        for offset, signature in enumerate(signatures, start=1):
            label = str(signature.get("custom_name") or "").strip() or tr("Assinatura {numero}").format(numero=offset)
            header = QTableWidgetItem(label)
            header.setData(SIGNATURE_ID_ROLE, signature["signature_id"])
            header.setIcon(themed_svg_icon(object_icon_path("signature")))
            header.setToolTip(
                tr("{nome}\nClique no ícone para marcar ou desmarcar toda a coluna.").format(
                    nome=label
                )
            )
            self.table_panel.table.setHorizontalHeaderItem(offset, header)
        for offset, placeholder in enumerate(placeholders, start=1 + len(signatures)):
            self.table_panel.table.setHorizontalHeaderItem(offset, QTableWidgetItem(placeholder))
        
        # Ajuste de larguras iniciais
        self.table_panel.table.setColumnWidth(0, 70) # Cópias
        for column in range(1, 1 + len(signatures)):
            self.table_panel.table.setColumnWidth(column, 110)

        self.table_panel.table.setRowCount(1)
        
        # 1. Configura a célula de Quantidade (Index 0)
        qty_item = QTableWidgetItem("1")
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_panel.table.setItem(0, 0, qty_item)
        
        for column, signature in enumerate(signatures, start=1):
            state = Qt.CheckState.Checked if signature.get("visible", True) else Qt.CheckState.Unchecked
            self.table_panel.table.setItem(
                0, column, self.table_panel.table._signature_item(state)
            )

    def _on_table_selection(self):
        if not self.cached_model_data: return
        if self._preview_mode == "sheet":
            table_row = self.table_panel.table.currentRow()
            rows_plain, rows_rich, source_rows = self._scrape_table_data(include_sources=True)
            if table_row >= 0 and source_rows:
                self._preview_item_index = next(
                    (index for index, source in enumerate(source_rows) if source == table_row),
                    self._preview_item_index,
                )
                plan = build_imposition_plan(
                    list(zip(rows_plain, rows_rich)), self._preview_imposition_settings()
                )
                if plan.capacity and plan.sheets:
                    self._preview_sheet_index = min(
                        self._preview_item_index // plan.capacity, len(plan.sheets) - 1
                    )
            self._render_current_sheet_preview()
            return
        row = self.table_panel.table.currentRow()
        
        # --- LEGO: Fallback para a Thumbnail Estática se não houver linha selecionada ---
        if row < 0:
            if self._active_library_model is not None and self._active_library_model.is_fornax:
                if self._preview_renderers:
                    renderer = self._preview_renderers[
                        min(self._preview_page_index, len(self._preview_renderers) - 1)
                    ]
                    self.preview_panel.set_preview_pixmap(
                        renderer.render_to_pixmap(row_rich=None, max_side=1600)
                    )
                return
            slug = slugify_model_name(self.active_model_name)
            model_dir = get_models_dir() / slug
            try:
                source_path = resolve_model_file(model_dir)
            except FileNotFoundError:
                source_path = model_dir / V4_FILENAME
            pages = (self.cached_model_document or {}).get("pages", [])
            page_id = (
                pages[min(self._preview_page_index, len(pages) - 1)]["page_id"]
                if pages else "front"
            )
            thumb_path = get_thumbnail_cache_path(model_dir, source_path, page_id)
            if thumb_path is not None:
                self.preview_panel.set_preview_image(str(thumb_path))
            elif self._preview_renderers:
                renderer = self._preview_renderers[
                    min(self._preview_page_index, len(self._preview_renderers) - 1)
                ]
                self.preview_panel.set_preview_pixmap(
                    renderer.render_to_pixmap(row_rich=None, max_side=1600)
                )
            return
        # --- FIM DO LEGO ---

        try:
            row_rich = self._get_row_data_rich(row)
            if not self._preview_renderers:
                source = self.cached_model_document or self.cached_model_data
                self._preview_renderers = (
                    renderers_for_document(source, asset_provider=self._fornax_asset_provider)
                    if source.get("schema_version") == 4 else [NativeRenderer(source)]
                )
            self._preview_page_index = min(self._preview_page_index, len(self._preview_renderers) - 1)
            self.preview_renderer = self._preview_renderers[self._preview_page_index]
            pix = self.preview_renderer.render_to_pixmap(row_rich=row_rich, max_side=1600)
            self.preview_panel.set_preview_pixmap(pix)
            _, _, source_rows = self._scrape_table_data(include_sources=True)
            if not self._selecting_preview_item:
                self._preview_item_index = next(
                    (index for index, source in enumerate(source_rows) if source == row), 0
                )
            self._preview_item_index = min(
                max(0, self._preview_item_index), max(0, len(source_rows) - 1)
            )
            self.preview_panel.set_navigation(
                "item", self._preview_item_index, len(source_rows),
                sheet_available=self._sheet_preview_available(),
            )
        except Exception as e:
            print(f"Erro no Live Preview: {e}")

    def _visible_preview_rows(self):
        table = self.table_panel.table
        return [row for row in range(table.rowCount()) if not table.isRowHidden(row)]

    def _sheet_preview_available(self):
        return bool(
            self.cached_model_data
            and self._resolve_imposition_settings().get("enabled")
        )

    def _preview_imposition_settings(self):
        settings = dict(self._resolve_imposition_settings())
        settings["duplex"] = bool(
            self.cached_model_document and len(self.cached_model_document.get("pages", [])) > 1
        )
        return settings

    def _on_preview_page_changed(self, page_index):
        page_count = len(self._preview_renderers) or 1
        self._preview_page_index = min(max(0, page_index), page_count - 1)
        self.preview_panel.set_page_navigation(page_count, self._preview_page_index)
        if self._preview_mode == "sheet":
            self._render_current_sheet_preview()
        else:
            self._on_table_selection()

    def _on_preview_mode_changed(self, mode):
        previous_mode = self._preview_mode
        self._preview_mode = mode if mode == "sheet" and self._sheet_preview_available() else "item"
        if self._preview_mode == "sheet":
            if previous_mode == "item":
                rows_plain, rows_rich = self._scrape_table_data()
                plan = build_imposition_plan(
                    list(zip(rows_plain, rows_rich)), self._preview_imposition_settings()
                )
                if plan.capacity:
                    self._preview_sheet_index = min(
                        self._preview_item_index // plan.capacity,
                        max(0, len(plan.sheets) - 1),
                    )
            self._render_current_sheet_preview()
        else:
            if previous_mode == "sheet":
                self._select_first_item_from_sheet(self._preview_sheet_index)
            self._refresh_preview_navigation()
            self._on_table_selection()

    def _sheet_index_for_table_row(self, table_row):
        rows_plain, rows_rich, source_rows = self._scrape_table_data(include_sources=True)
        plan = build_imposition_plan(list(zip(rows_plain, rows_rich)), self._preview_imposition_settings())
        if not plan.sheets or table_row < 0:
            return 0
        try:
            production_index = source_rows.index(table_row)
        except ValueError:
            # Uma linha com quantidade zero não está na produção. Usa a ocorrência
            # válida mais próxima para manter a navegação previsível.
            production_index = next(
                (index for index, source in enumerate(source_rows) if source > table_row),
                max(0, len(source_rows) - 1),
            )
        return min(production_index // plan.capacity, len(plan.sheets) - 1)

    def _select_first_item_from_sheet(self, sheet_index):
        rows_plain, rows_rich, source_rows = self._scrape_table_data(include_sources=True)
        plan = build_imposition_plan(list(zip(rows_plain, rows_rich)), self._preview_imposition_settings())
        if not plan.sheets or not source_rows:
            return
        sheet_index = min(max(0, sheet_index), len(plan.sheets) - 1)
        production_index = sheet_index * plan.capacity
        self._preview_item_index = min(production_index, len(source_rows) - 1)
        table_row = source_rows[min(production_index, len(source_rows) - 1)]
        table = self.table_panel.table
        column = table.currentColumn()
        if column < 0 or column >= table.columnCount():
            column = 0
        self._selecting_preview_item = True
        try:
            table.setCurrentCell(table_row, column)
        finally:
            self._selecting_preview_item = False

    def _on_preview_index_requested(self, index):
        if self._preview_mode == "sheet":
            rows_plain, rows_rich = self._scrape_table_data()
            plan = build_imposition_plan(list(zip(rows_plain, rows_rich)), self._preview_imposition_settings())
            if not plan.sheets:
                self._render_current_sheet_preview()
                return
            self._preview_sheet_index = min(max(0, index), len(plan.sheets) - 1)
            self._render_current_sheet_preview(plan)
            return

        _, _, source_rows = self._scrape_table_data(include_sources=True)
        if not source_rows:
            self._refresh_preview_navigation()
            return
        index = min(max(0, index), len(source_rows) - 1)
        self._preview_item_index = index
        table = self.table_panel.table
        column = table.currentColumn()
        if column < 0 or column >= table.columnCount():
            column = 0
        self._selecting_preview_item = True
        try:
            table.setCurrentCell(source_rows[index], column)
        finally:
            self._selecting_preview_item = False
        self._on_table_selection()

    def _refresh_preview_navigation(self):
        sheet_available = self._sheet_preview_available()
        if self._preview_mode == "sheet" and sheet_available:
            rows_plain, rows_rich = self._scrape_table_data()
            plan = build_imposition_plan(list(zip(rows_plain, rows_rich)), self._preview_imposition_settings())
            total = len(plan.sheets)
            self._preview_sheet_index = min(self._preview_sheet_index, max(0, total - 1))
            self.preview_panel.set_navigation(
                "sheet", self._preview_sheet_index, total, sheet_available=True
            )
            return

        if not sheet_available:
            self._preview_mode = "item"
        _, _, source_rows = self._scrape_table_data(include_sources=True)
        self._preview_item_index = min(
            max(0, self._preview_item_index), max(0, len(source_rows) - 1)
        )
        self.preview_panel.set_navigation(
            "item", self._preview_item_index, len(source_rows), sheet_available=sheet_available
        )

    def _on_preview_data_changed(self, _item=None):
        self._invalidate_sheet_previews()
        self._preview_refresh_timer.start()

    def _on_preview_rows_changed(self, *_args):
        self._invalidate_sheet_previews()
        self._preview_refresh_timer.start()

    def _refresh_preview_after_data_change(self):
        self._refresh_dynamic_image_status()
        self._refresh_preview_navigation()
        if self._preview_mode == "sheet":
            self._render_current_sheet_preview()
        else:
            self._on_table_selection()
            self._start_sheet_preview_preload()

    def _invalidate_sheet_previews(self):
        self._sheet_preview_revision += 1
        self._sheet_preview_paths.clear()
        self._stop_sheet_preview_worker()
        if self._sheet_preview_dir:
            self._stale_sheet_preview_dirs.add(self._sheet_preview_dir)
            self._sheet_preview_dir = None

    def _stop_sheet_preview_worker(self, *, wait=False):
        worker = self._sheet_preview_worker
        if worker and worker.isRunning():
            worker.stop()
            worker.requestInterruption()
            if wait:
                worker.wait()
        self._sheet_preview_worker = None

    def _start_sheet_preview_preload(self, plan=None, first_page=None):
        if not self._sheet_preview_available():
            return
        if self._sheet_preview_worker and self._sheet_preview_worker.isRunning():
            requested_page = self._preview_sheet_index if first_page is None else first_page
            requested_key = (requested_page, self._preview_page_index)
            if requested_key in self._sheet_preview_paths:
                return
            old_dir = self._sheet_preview_dir
            self._stop_sheet_preview_worker()
            if old_dir:
                self._stale_sheet_preview_dirs.add(old_dir)

        if plan is None:
            rows_plain, rows_rich = self._scrape_table_data()
            rows = list(zip(rows_plain, rows_rich))
            plan = build_imposition_plan(rows, self._preview_imposition_settings())
        else:
            rows = [entry for page in plan.pages for entry in page]
        if not plan.sheets:
            return

        first_page = self._preview_sheet_index if first_page is None else first_page
        memory_only = self._protected_preview_memory_only
        authorized_snapshot = None
        template = copy.deepcopy(self.cached_model_document or self.cached_model_data)
        asset_provider = None
        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            try:
                authorized_snapshot = self._fornax_sessions.borrow_job(library_model.path)
                template = authorized_snapshot.document()
                asset_provider = authorized_snapshot.asset
            except FornaxError as error:
                self.log_panel.append(
                    tr("Erro na prévia da folha: {erro}").format(erro=error)
                )
                return
        output_dir = None if memory_only else tempfile.mkdtemp(prefix="fornax_sheet_preview_")
        self._sheet_preview_dir = output_dir
        generation = self._sheet_preview_revision
        worker = SheetPreviewWorker(
            template, rows,
            self._preview_imposition_settings(), output_dir,
            generation, first_page=first_page,
            first_face=self._preview_page_index, cache_limit=12, parent=self,
            asset_provider=asset_provider, memory_only=memory_only,
            authorized_snapshot=authorized_snapshot,
        )
        self._sheet_preview_worker = worker
        self._sheet_preview_workers.add(worker)
        worker.pageReady.connect(self._on_sheet_preview_ready)
        worker.pageFailed.connect(self._on_sheet_preview_failed)
        worker.finished.connect(lambda directory=output_dir, current=worker: self._on_sheet_preview_finished(current, directory))
        worker.finished.connect(worker.deleteLater)
        worker.start(QThread.Priority.LowPriority)

    def _on_sheet_preview_ready(self, page_index, face_index, preview, generation):
        if generation != self._sheet_preview_revision:
            return
        key = (page_index, face_index)
        self._sheet_preview_paths[key] = preview
        while len(self._sheet_preview_paths) > 12:
            old_key = next(iter(self._sheet_preview_paths))
            old_preview = self._sheet_preview_paths.pop(old_key)
            if isinstance(old_preview, (str, os.PathLike)):
                Path(old_preview).unlink(missing_ok=True)
        if (self._preview_mode == "sheet"
                and page_index == self._preview_sheet_index
                and face_index == self._preview_page_index):
            if isinstance(preview, QImage):
                self.preview_panel.set_preview_pixmap(QPixmap.fromImage(preview))
            else:
                self.preview_panel.set_preview_image(preview)

    def _on_sheet_preview_failed(self, _page_index, _face_index, message, generation):
        if generation == self._sheet_preview_revision:
            self.log_panel.append(tr("Erro na prévia da folha: {erro}").format(erro=message))

    def _on_sheet_preview_finished(self, worker, directory):
        self._sheet_preview_workers.discard(worker)
        if self._sheet_preview_worker is worker:
            self._sheet_preview_worker = None
        if directory in self._stale_sheet_preview_dirs:
            shutil.rmtree(directory, ignore_errors=True)
            self._stale_sheet_preview_dirs.discard(directory)

    def _render_current_sheet_preview(self, plan=None):
        if not self._sheet_preview_available():
            self._preview_mode = "item"
            self._on_table_selection()
            return

        if plan is None:
            rows_plain, rows_rich = self._scrape_table_data()
            plan = build_imposition_plan(list(zip(rows_plain, rows_rich)), self._preview_imposition_settings())
        total = len(plan.sheets)
        if not total:
            self.preview_panel.set_preview_text(tr("Não há itens para montar a folha"))
            self.preview_panel.set_navigation("sheet", 0, 0, sheet_available=True)
            return

        self._preview_sheet_index = min(max(0, self._preview_sheet_index), total - 1)
        self.preview_panel.set_navigation(
            "sheet", self._preview_sheet_index, total, sheet_available=True
        )
        preview = self._sheet_preview_paths.get(
            (self._preview_sheet_index, self._preview_page_index)
        )
        if isinstance(preview, QImage) and not preview.isNull():
            self.preview_panel.set_preview_pixmap(QPixmap.fromImage(preview))
            return
        if preview and Path(preview).exists():
            self.preview_panel.set_preview_image(preview)
            return
        self.preview_panel.set_preview_text(tr("Carregando prévia"))
        self._start_sheet_preview_preload(plan, first_page=self._preview_sheet_index)

    def _open_model_dialog(self):
        current_model_name = self.preview_panel.cbo_models.currentText()
        if not current_model_name:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo na lista antes de configurar."))
            return
        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            try:
                document = self._fornax_sessions.document(library_model.path)
                status = self._fornax_sessions.status(library_model.path)
            except FornaxError as error:
                QMessageBox.warning(self, tr("Modelo protegido"), str(error))
                return
            asset_provider = lambda reference, p=library_model.path: self._fornax_sessions.asset(reference, p)
            recovered = False
            recovery_path = EditorWindow.fornax_recovery_path(library_model.path)
            if recovery_path.is_file() and recovery_path.stat().st_mtime > library_model.path.stat().st_mtime:
                answer = QMessageBox.question(
                    self, tr("Recuperar edição"),
                    tr("Foi encontrada uma edição não salva deste modelo. Deseja recuperá-la?"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    try:
                        recovery = self._fornax_sessions.read_recovery(
                            recovery_path, path=library_model.path,
                        )
                        document = recovery.document()
                        asset_provider = recovery.asset
                        recovered = True
                    except FornaxError as error:
                        QMessageBox.warning(self, tr("Recuperação indisponível"), str(error))
                        recovery_path.unlink(missing_ok=True)
                        recovery_path.with_name(recovery_path.name + ".bak").unlink(missing_ok=True)
                else:
                    recovery_path.unlink(missing_ok=True)
                    recovery_path.with_name(recovery_path.name + ".bak").unlink(missing_ok=True)
            self.editor_window = EditorWindow(self)
            self.editor_window.modelSaved.connect(self._on_editor_saved)
            self._connect_editor_lifecycle()
            self.editor_window.load_from_fornax(
                document,
                path=library_model.path,
                mode=status.descriptor.mode,
                model_id=status.descriptor.model_id,
                asset_provider=asset_provider,
                session_manager=self._fornax_sessions,
                save_as_required=(
                    status.save_as_required or library_model.key.startswith("external:")
                ),
                recovered=recovered,
            )
            self.editor_window.show()
            return
            
        self.active_model_name = current_model_name

        slug = slugify_model_name(current_model_name)
        model_dir = get_models_dir() / slug
        try:
            json_path = resolve_model_file(model_dir)
        except Exception:
            json_path = None

        self.editor_window = EditorWindow(self)
        self.editor_window.modelSaved.connect(self._on_editor_saved)
        self._connect_editor_lifecycle()

        if json_path is not None:
            self.editor_window.load_from_json(str(model_dir))
        
        self.editor_window.show()

    def _open_model_info_dialog(self):
        model_name = self.preview_panel.cbo_models.currentText()
        if not model_name:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo primeiro."))
            return
        model_id = self.preview_panel.cbo_models.currentData()
        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            try:
                document = self._fornax_sessions.document(library_model.path)
                saved_at = datetime.fromtimestamp(
                    library_model.path.stat().st_mtime
                ).astimezone().isoformat(timespec="seconds")
                origin = document.get("origin_info")
                if not isinstance(origin, dict):
                    origin = build_model_snapshot(
                        document, source="fornax", captured_at=saved_at,
                    )
                current = current_model_snapshot(document, captured_at=saved_at)
                ModelInfoDialog(origin, current, self).exec()
            except Exception as error:
                QMessageBox.warning(
                    self, tr("Modelo protegido"),
                    tr("Desbloqueie o modelo antes de consultar suas informações.\n{erro}").format(
                        erro=error
                    ),
                )
            return
        model_dir = get_models_dir() / str(model_id or slugify_model_name(model_name))
        try:
            document = load_model_document(model_dir)
            if not isinstance(document.get("origin_info"), dict):
                document = ensure_origin_info(document, source="legacy")
                save_model_document(document, model_dir)
            model_file = resolve_model_file(model_dir)
            saved_at = datetime.fromtimestamp(model_file.stat().st_mtime).astimezone().isoformat(timespec="seconds")
            current = current_model_snapshot(document, captured_at=saved_at)
            ModelInfoDialog(document["origin_info"], current, self).exec()
        except Exception as error:
            QMessageBox.critical(
                self, tr("Erro"),
                tr("Não foi possível ler as informações do modelo:\n{erro}").format(erro=error),
            )

    def _on_editor_saved(self, model_name, placeholders, file_path, *, previous_name=None):
        # O nome fica criptografado no modo integral. Preserve o nome autorizado
        # antes de reexaminar a biblioteca, para não selecionar outro modelo e
        # retirar a sessão ativa do editor que acabou de salvar.
        saved_path = Path(file_path)
        if saved_path.suffix.lower() == '.fornax':
            descriptor = inspect_fornax(saved_path)
            if descriptor.mode == FULL_MODE:
                self._remember_protected_model_name(descriptor.model_id, model_name)
        table = self.table_panel.table
        old_name = self.preview_panel.cbo_models.currentText()
        target_name = old_name if previous_name and old_name not in (previous_name, model_name) else model_name
        current_row = table.currentRow()
        saved_rows = []
        if old_name == target_name or old_name == previous_name:
            for row in range(table.rowCount()):
                saved_rows.append({table_column_key(table.horizontalHeaderItem(col)): table.item(row, col).clone()
                                   for col in range(table.columnCount()) if table.item(row, col)})
        blocker = QSignalBlocker(table)
        # Formata o log conforme o seu novo padrão
        self.log_panel.append(tr("<b>Modelo '{nome}' salvo com sucesso em:</b> {arquivo}").format(nome=model_name, arquivo=file_path))
        self.log_panel.append(tr("Atualizando lista…"))
        self._reload_models_from_disk(select_name=target_name)
        if saved_rows and self.preview_panel.cbo_models.currentText() == target_name:
            defaults = [table.item(0, col).clone() if table.item(0, col) else None for col in range(table.columnCount())]
            table.setRowCount(len(saved_rows))
            for row, values in enumerate(saved_rows):
                for col in range(table.columnCount()):
                    name = table_column_key(table.horizontalHeaderItem(col))
                    item = values.get(name, defaults[col])
                    if item:
                        table.setItem(row, col, item.clone())
            if current_row >= 0:
                table.setCurrentCell(min(current_row, table.rowCount()-1), 0)
        del blocker
        self._on_table_selection()

    def _open_config_dialog(self):
        current_model_name = self.preview_panel.cbo_models.currentText()
        if not current_model_name:
            QMessageBox.warning(self, tr("Atenção"), tr("Selecione um modelo primeiro."))
            return
            
        self.active_model_name = current_model_name
        cols = self.table_panel.table.columnCount()
        # Adiciona 'modelo' explicitamente como uma variável disponível no diálogo
        vars_available = ["modelo"] + [
            self.table_panel.table.horizontalHeaderItem(c).text()
            for c in range(cols)
            if not is_signature_header(self.table_panel.table.horizontalHeaderItem(c))
        ]
        slug = slugify_model_name(self.active_model_name)
        
        current_imposition = None
        model_size = (1000, 1000) 
        model_print_size_mm = (100.0, 100.0)
        has_any_link = False

        if self.cached_model_data:
            sz = self.cached_model_data.get("canvas_size", {})
            model_size = (sz.get("w", 1000), sz.get("h", 1000))
            model_print_size_mm = self._get_model_base_print_size_mm()
            current_imposition = self.cached_model_data.get("imposition_settings") 
            has_any_link = any(box.get("has_link") for box in (self.cached_model_data.get("boxes", []) + self.cached_model_data.get("images", []) + self.cached_model_data.get("shapes", [])))

        dlg = ExportConfigDialog(self, slug, vars_available, self.current_filename_suffix,
                           model_size_px=model_size, 
                           model_print_size_mm=model_print_size_mm,
                           current_imposition=current_imposition)
        
        dlg.set_link_warning_visible(has_any_link)
        
        if dlg.exec():
            new_suffix = dlg.get_pattern()
            new_imposition = dlg.get_imposition_settings() 
            self.current_filename_suffix = new_suffix
            
            self._update_template_json({
                "output_suffix": new_suffix,
                "imposition_settings": new_imposition,
            })

            msg_imp = tr(" [Imposição ativada]") if new_imposition["enabled"] else ""
            if self.current_filename_suffix:
                self.log_panel.append(tr("Configuração salva: {nome}{estado}").format(nome=f"{slug}_{self.current_filename_suffix}.png", estado=msg_imp))
            else:
                self.log_panel.append(tr("Configuração salva: sequência automática{estado}").format(estado=msg_imp))

            self._refresh_imposition_presets()
            self._invalidate_sheet_previews()
            self._refresh_preview_navigation()
            if self._preview_mode == "sheet":
                self._render_current_sheet_preview()
            else:
                self._start_sheet_preview_preload()

    def _open_theme_dialog(self):
        dlg = ThemeDialog(self)
        dlg.exec()

    def _select_output_folder(self):
        start_dir = self.txt_output_path.text() or ""
        folder = QFileDialog.getExistingDirectory(self, tr("Selecionar pasta de saída"), start_dir)
        if folder:
            self.txt_output_path.setText(folder)
            self.settings.setValue("last_output_dir", folder)

    def _update_template_json(self, new_data: dict):
        """Atualiza metadados comuns e publica o documento v4 atomicamente."""
        if not self.active_model_name:
            return
        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            try:
                document = copy.deepcopy(self.cached_model_document)
                document.update(copy.deepcopy(new_data))
                status = self._fornax_sessions.status(library_model.path)
                if status.save_as_required:
                    self.cached_model_document = document
                    if self.cached_model_data:
                        self.cached_model_data.update(copy.deepcopy(new_data))
                    return
                status = self._fornax_sessions.save(
                    document, path=library_model.path,
                    asset_provider=self._fornax_asset_provider,
                )
                updated = LibraryModel(
                    key=library_model.key, display_name=library_model.display_name,
                    path=library_model.path, kind=library_model.kind,
                    descriptor=status.descriptor,
                )
                self._active_library_model = updated
                self._library_models_by_key[updated.key] = updated
                self.cached_model_document = self._fornax_sessions.document(library_model.path)
                self.cached_model_data = adapt_model_page(
                    self.cached_model_document, self._active_page_id if hasattr(self, "_active_page_id") else "front"
                )
            except Exception as error:
                QMessageBox.warning(
                    self, tr("Erro"),
                    tr("Falha ao salvar modelo:\n{erro}").format(erro=error),
                )
            return
        slug = slugify_model_name(self.active_model_name)
        model_dir = get_models_dir() / slug
        try:
            document = self.cached_model_document or load_model_document(model_dir)
            document.update(copy.deepcopy(new_data))
            saved_path = save_model_document(document, model_dir)
            document["__model_dir"] = str(model_dir.resolve())
            document["__model_file"] = str(saved_path.resolve())
            self.cached_model_document = document
            if self.cached_model_data:
                self.cached_model_data.update(copy.deepcopy(new_data))
        except Exception as e:
            print(f"Erro ao atualizar JSON do modelo: {e}")

    def _current_export_mode(self):
        mode = self.cbo_export_format.currentData()
        export_format = "PNG" if mode == "png" else "PDF"
        return mode, export_format, mode == "pdf_grouped"

    def _refresh_export_mode_tooltip(self):
        mode = self.cbo_export_format.currentData()
        self.cbo_export_format.setToolTip(self._export_mode_tooltips.get(mode, ""))

    def _on_export_mode_changed(self, _index):
        self._refresh_export_mode_tooltip()
        mode, export_format, single_pdf = self._current_export_mode()
        self._update_template_json({
            "last_export_mode": mode,
            "last_export_format": export_format,
            "last_single_pdf": single_pdf,
        })

    def _scrape_table_data(self, *, include_sources=False):
        table = self.table_panel.table
        rows = table.rowCount()
        cols = table.columnCount()
        data_plain, data_rich, source_rows = [], [], []

        for r in range(rows):
            row_p, row_r = {}, {}
            # Injeta o slug do modelo atual para permitir substituição dinâmica {modelo}
            current_slug = slugify_model_name(self.active_model_name)
            row_p["modelo"] = current_slug
            row_r["modelo"] = current_slug
            multiplier = 1
            has_content = False
            
            for c in range(cols):
                header = table.horizontalHeaderItem(c)
                key = header.text()
                item = table.item(r, c)

                # 1. Trata a nova coluna de Quantidade
                if is_quantity_header(key):
                    try:
                        val = int(item.text().strip()) if item else 1
                        multiplier = max(0, val) # Impede números negativos
                    except ValueError:
                        multiplier = 1
                    continue

                # 2. Trata a coluna de Assinatura
                if is_signature_header(header):
                    use_sig = (item.checkState() == Qt.CheckState.Checked) if item else True
                    signature_id = signature_id_from_header(header)
                    if signature_id:
                        row_p.setdefault("__signature_visibility__", {})[signature_id] = use_sig
                        row_r.setdefault("__signature_visibility__", {})[signature_id] = use_sig
                    else:
                        row_p["__use_signature__"] = use_sig
                        row_r["__use_signature__"] = use_sig
                    continue

                # 3. Trata placeholders comuns
                val_plain = item.text().strip() if item else ""
                val_rich = item.data(Qt.ItemDataRole.UserRole) if item else ""
                if not val_rich: val_rich = val_plain
                
                if val_plain: 
                    has_content = True
                
                row_p[key] = val_plain
                row_r[key] = val_rich

            # Validação: Se a linha tiver conteúdo OU o multiplicador for > 0, 
            # nós geramos (isso permite gerar cartões sem placeholders).
            if multiplier > 0:
                for _ in range(multiplier):
                    data_plain.append(row_p.copy())
                    data_rich.append(row_r.copy())
                    source_rows.append(r)
                    
        if include_sources:
            return data_plain, data_rich, source_rows
        return data_plain, data_rich
    
    def _get_row_data_rich(self, row_idx):
        table = self.table_panel.table
        cols = table.columnCount()
        row_data = {}
        for c in range(cols):
            header = table.horizontalHeaderItem(c)
            key = header.text()
            item = table.item(row_idx, c)

            # Ignora a coluna de quantidade no preview técnico do cartão
            if is_quantity_header(key):
                continue
                
            if is_signature_header(header):
                use_sig = (item.checkState() == Qt.CheckState.Checked) if item else True
                signature_id = signature_id_from_header(header)
                if signature_id:
                    row_data.setdefault("__signature_visibility__", {})[signature_id] = use_sig
                else:
                    row_data["__use_signature__"] = use_sig
                continue
                
            val = ""
            if item:
                val = item.data(Qt.ItemDataRole.UserRole)
                if not val: val = item.text()
            row_data[key] = val
        return row_data

    def _get_model_base_print_size_mm(self, model_data: dict = None):
        """Retorna o tamanho físico próprio do modelo, sem presets de impressão."""
        data = model_data or self.cached_model_data or {}

        w = data.get("target_w_mm", 0) or 0
        h = data.get("target_h_mm", 0) or 0
        if w > 0 and h > 0:
            return float(w), float(h)

        canvas = data.get("canvas_size", {})
        canvas_w = canvas.get("w", 1000)
        canvas_h = canvas.get("h", 1000)
        return (canvas_w / 300.0) * 25.4, (canvas_h / 300.0) * 25.4

    def _resolve_imposition_settings(self):
        """Resolve a configuração efetiva sem deixar presets contaminarem o modelo base."""
        base_w, base_h = self._get_model_base_print_size_mm()
        imp = (self.cached_model_data or {}).get("imposition_settings", {}) or {}
        presets = imp.get("presets", {}) or {}
        active_name = imp.get("active_preset_name") or self.SYSTEM_IMPOSITION_PRESET

        if active_name == self.SYSTEM_IMPOSITION_PRESET or active_name not in presets:
            return {
                "enabled": False,
                "target_w_mm": base_w,
                "target_h_mm": base_h,
                "active_preset_name": self.SYSTEM_IMPOSITION_PRESET,
            }

        preset = presets[active_name]
        return {
            "enabled": preset.get("enabled", False),
            "sheet_w_mm": preset.get("sheet_w", 210.0),
            "sheet_h_mm": preset.get("sheet_h", 297.0),
            "crop_marks": preset.get("crop", True),
            "bleed_margin": preset.get("bleed", True),
            "target_w_mm": preset.get("w", base_w),
            "target_h_mm": preset.get("h", base_h),
            "active_preset_name": active_name,
        }

    def _dynamic_image_settings_key(self):
        model_id = self.preview_panel.cbo_models.currentData()
        if not model_id:
            model_id = slugify_model_name(self.preview_panel.cbo_models.currentText())
        return f"workspace/dynamic_images/{model_id}"

    def _configure_dynamic_images_for_model(self, document):
        fields = dynamic_image_fields(document)
        footer = self.table_panel.dynamic_image_footer
        footer.setVisible(bool(fields))
        if not fields:
            self.table_panel.txt_dynamic_image_dir.clear()
            self.table_panel.lbl_dynamic_image_status.clear()
            document.pop("__dynamic_image_dir", None)
            return
        directory = str(self.settings.value(self._dynamic_image_settings_key(), "") or "")
        self.table_panel.txt_dynamic_image_dir.setText(directory)
        self.table_panel.txt_dynamic_image_dir.setToolTip(directory or tr(
            "Pasta usada para localizar os arquivos indicados na tabela"
        ))
        document["__dynamic_image_dir"] = directory
        self._refresh_dynamic_image_status()

    def _select_dynamic_image_directory(self):
        current = self.table_panel.txt_dynamic_image_dir.text().strip()
        directory = QFileDialog.getExistingDirectory(
            self, tr("Selecionar pasta de imagens"), current
        )
        if not directory:
            return
        self.settings.setValue(self._dynamic_image_settings_key(), directory)
        self.settings.sync()
        self.table_panel.txt_dynamic_image_dir.setText(directory)
        self.table_panel.txt_dynamic_image_dir.setToolTip(directory)
        if self.cached_model_document is not None:
            self.cached_model_document["__dynamic_image_dir"] = directory
        for renderer in self._preview_renderers:
            renderer.set_dynamic_image_directory(directory)
        self._invalidate_sheet_previews()
        self._refresh_dynamic_image_status()
        self._refresh_preview_after_data_change()

    def _refresh_dynamic_image_status(self):
        document = self.cached_model_document or {}
        fields = dynamic_image_fields(document)
        footer = getattr(self.table_panel, "dynamic_image_footer", None)
        if footer is None:
            return
        footer.setVisible(bool(fields))
        if not fields:
            return
        directory = self.table_panel.txt_dynamic_image_dir.text().strip()
        status_label = self.table_panel.lbl_dynamic_image_status
        if not directory or not Path(directory).is_dir():
            status_label.setText(tr("Selecione uma pasta de imagens válida."))
            themed_style(status_label, "color: @danger@; font-size: 11px;")
        else:
            status_label.setText(tr("Pasta pronta para {quantidade} campo(s) de imagem.").format(
                quantidade=len(fields)
            ))
            themed_style(status_label, "color: @success@; font-size: 11px;")

        table = self.table_panel.table
        headers = {
            table.horizontalHeaderItem(column).text(): column
            for column in range(table.columnCount())
            if table.horizontalHeaderItem(column)
            and not is_signature_header(table.horizontalHeaderItem(column))
        }
        counts = {"not_found": 0, "ambiguous": 0, "invalid": 0}
        old_blocked = table.blockSignals(True)
        try:
            for field in fields:
                column = headers.get(field)
                if column is None:
                    continue
                for row in range(table.rowCount()):
                    item = table.item(row, column)
                    if item is None:
                        continue
                    result = resolve_dynamic_image(directory, item.text())
                    if result.status in counts:
                        counts[result.status] += 1
                        item.setForeground(QBrush(QColor(theme_color("danger"))))
                        item.setToolTip(
                            tr("Arquivo ambíguo; informe também a extensão.")
                            if result.status == "ambiguous" else
                            tr("Imagem não encontrada na pasta configurada.")
                        )
                    else:
                        item.setForeground(QBrush(QColor(theme_color("text"))))
                        item.setToolTip(str(result.path) if result.path else "")
        finally:
            table.blockSignals(old_blocked)
        problems = sum(counts.values())
        if problems:
            status_label.setText(tr("{quantidade} referência(s) de imagem precisam de atenção.").format(
                quantidade=problems
            ))
            themed_style(status_label, "color: @danger@; font-size: 11px;")

    def _generate_cards_async(self):
        rows_plain, rows_rich, source_rows = self._scrape_table_data(include_sources=True)
        if not rows_plain:
            self.log_panel.append(tr("AVISO: a tabela está vazia. Nada a gerar."))
            return

        current_name = self.preview_panel.cbo_models.currentText()
        if not current_name:
            self.log_panel.append(tr("ERRO: nenhum modelo selecionado."))
            return

        dynamic_fields = dynamic_image_fields(self.cached_model_document or {})
        dynamic_directory = self.table_panel.txt_dynamic_image_dir.text().strip()
        if dynamic_fields and not Path(dynamic_directory).is_dir():
            QMessageBox.warning(
                self, tr("Pasta de imagens necessária"),
                tr("Selecione uma pasta de imagens válida antes de gerar o material."),
            )
            return
        unresolved = []
        for production_index, row_data in enumerate(rows_plain):
            row_number = source_rows[production_index] + 1
            for field_name in dynamic_fields:
                value = row_data.get(field_name, "")
                result = resolve_dynamic_image(dynamic_directory, value)
                if value and result.status != "ok":
                    unresolved.append((row_number, field_name, value, result.status))
        if unresolved:
            first = unresolved[0]
            reason = (
                tr("há mais de um arquivo com esse nome")
                if first[3] == "ambiguous" else tr("o arquivo não foi encontrado")
            )
            QMessageBox.warning(
                self, tr("Imagens não resolvidas"),
                tr("{quantidade} referência(s) de imagem precisam ser corrigidas. "
                   "A primeira está na linha {linha}, campo '{campo}': '{valor}' ({motivo}).").format(
                    quantidade=len(unresolved), linha=first[0], campo=first[1],
                    valor=first[2], motivo=reason,
                ),
            )
            return
        
        _, export_format, _ = self._current_export_mode()
        has_any_link = bool(
            self.cached_model_document
            and next(iter_page_link_items(self.cached_model_document), None)
        )

        if export_format == "PNG" and has_any_link:
            resp = QMessageBox.question(
                self, 
                tr("Aviso: links desativados em PNG"),
                tr("Este modelo possui links ativos, mas o formato de saída atual é PNG.\n\nOs links funcionam somente em PDF. Deseja continuar e gerar as imagens sem links?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.No:
                self.log_panel.append(tr("🛑 Geração cancelada para alteração de formato."))
                return
            
        custom_path = self.txt_output_path.text().strip()
        if not custom_path:
            QMessageBox.warning(
                self, tr("Atenção"),
                tr("Por favor, selecione uma pasta de saída antes de gerar o material.")
            )
            self.log_panel.append(tr("🛑 Geração cancelada: pasta de saída não definida."))
            return

        authorized_snapshot = None
        protected_content = False
        library_model = self._current_library_entry()
        if library_model is not None and library_model.is_fornax:
            try:
                authorized_snapshot = self._fornax_sessions.borrow_job(library_model.path)
                document = authorized_snapshot.document()
                asset_provider = authorized_snapshot.asset
                status = self._fornax_sessions.status(library_model.path)
                protected_content = (
                    status.descriptor.mode != PUBLIC_MODE
                    and status.state == AccessState.AUTHORIZED_ACTIVE
                )
            except FornaxError as error:
                if authorized_snapshot is not None:
                    authorized_snapshot.close()
                self.log_panel.append(
                    tr("ERRO: não foi possível autorizar a geração: {erro}").format(erro=error)
                )
                return
            model_dir = None
        else:
            slug = slugify_model_name(current_name)
            model_dir = get_models_dir() / slug
            try:
                document = load_model_document(model_dir)
            except (FileNotFoundError, ValueError):
                self.log_panel.append(tr("ERRO: modelo '{nome}' não encontrado.").format(nome=self.active_model_name))
                return
            asset_provider = None

        if dynamic_image_fields(document):
            document["__dynamic_image_dir"] = dynamic_directory

        imposition_cfg = self._resolve_imposition_settings()
        if model_dir is not None:
            for page in document["pages"]:
                page_data = adapt_model_page(document, page["page_id"])
                ensure_background_proxy(model_dir, page_data)

        renderers = renderers_for_document(
            document, dynamic_directory, asset_provider=asset_provider,
        )

        base_dir = Path(custom_path)
        self.settings.setValue("last_output_dir", custom_path)

        output_dir, _forge_number = create_forge_output_dir(base_dir, self.settings)
        self._last_forge_output_dir = output_dir
        folder_name = output_dir.name
        
        self.log_panel.append(tr("📂 Salvando em: {pasta}").format(pasta=folder_name))

        self.btn_generate_cards.setEnabled(False)
        self.btn_generate_cards.setText(tr("Gerando… Aguarde"))
        self.progress_bar.setValue(0)
        self.log_panel.append(
            tr("--- Iniciando lote de {count} itens ---").format(count=len(rows_plain))
        )

        # O padrão agora é 100% o que o usuário definiu. 
        # Se estiver vazio, usamos {modelo} como fallback padrão.
        full_pattern = self.current_filename_suffix if self.current_filename_suffix else "{modelo}"

        model_w_mm, model_h_mm = self._get_model_base_print_size_mm()
        _, export_format, is_single_pdf = self._current_export_mode()

        self.manager = RenderManager(
            renderers,
            rows_plain, 
            rows_rich, 
            output_dir, 
            full_pattern,
            imposition_settings=imposition_cfg,
            export_format=export_format,
            single_pdf=is_single_pdf,
            target_w_mm=model_w_mm,
            target_h_mm=model_h_mm,
            source_rows=source_rows,
            authorized_snapshot=authorized_snapshot,
            protected_content=protected_content,
        )
        self._generation_failed = False
        self.manager.progress_updated.connect(self.progress_bar.setValue)
        self.manager.log_updated.connect(self.log_panel.append)
        self.manager.error_occurred.connect(self._on_generation_error)
        self.manager.finished_process.connect(self._on_generation_finished)
        
        self.start_time = time.time()
        self.manager.start()

    def _on_generation_error(self, message):
        self._generation_failed = True
        self.log_panel.append(tr("[ERRO] {erro}").format(erro=message))

    def _on_generation_finished(self):
        self.btn_generate_cards.setEnabled(True)
        self.btn_generate_cards.setText(tr("Gerar material"))
        end_time = time.time()
        duration = end_time - getattr(self, 'start_time', end_time)
        self._last_generation_duration = duration
        
        if duration < 60:
            time_str = tr("{tempo:.1f} segundos").format(tempo=duration)
        else:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            time_str = tr("{minutos} min {segundos}s").format(minutos=minutes, segundos=seconds)

        if getattr(self, "_generation_failed", False):
            self.log_panel.append(tr("=== Processo interrompido por erro ==="))
            self.log_panel.append(tr("⏱️ Tempo total: {tempo}").format(tempo=time_str))
            return
        self.log_panel.append(tr("=== Processo finalizado ==="))
        self.log_panel.append(tr("⏱️ Tempo total: {tempo}").format(tempo=time_str))
        
    def _refresh_imposition_presets(self):
        """Atualiza a lista de presets rápidos na tela principal baseada no modelo atual."""
        SYSTEM_PRESET = self.SYSTEM_IMPOSITION_PRESET
        
        self.cbo_presets_main.blockSignals(True)
        self.cbo_presets_main.clear()

        # O preset de sistema sempre existe, mesmo sem modelo carregado
        self.cbo_presets_main.addItem(tr("Definição do Modelo"), SYSTEM_PRESET)
        self.cbo_presets_main.setEnabled(True)

        if self.cached_model_data:
            imp_settings = self.cached_model_data.setdefault("imposition_settings", {})
            presets = imp_settings.get("presets", {}) or {}
            active_name = imp_settings.get("active_preset_name", "")
            model_w, model_h = self._get_model_base_print_size_mm()

            user_presets = sorted(k for k in presets.keys() if k != SYSTEM_PRESET)
            for name in user_presets:
                preset = presets.get(name, {}) or {}
                label = warning_display_name(name, preset, model_w, model_h)
                self.cbo_presets_main.addItem(label, name)
                idx = self.cbo_presets_main.count() - 1
                tooltip = warning_tooltip(name, preset, model_w, model_h)
                if tooltip:
                    self.cbo_presets_main.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)

            # Sincroniza a seleção com o preset ativo salvo
            if active_name and active_name != SYSTEM_PRESET:
                idx = self.cbo_presets_main.findData(active_name, Qt.ItemDataRole.UserRole)
                if idx >= 0:
                    self.cbo_presets_main.setCurrentIndex(idx)
                else:
                    self.cbo_presets_main.setCurrentIndex(0)
                    imp_settings["active_preset_name"] = SYSTEM_PRESET
                    imp_settings["enabled"] = False
                    self._update_template_json({"imposition_settings": imp_settings})
            else:
                self.cbo_presets_main.setCurrentIndex(0)
                if active_name != SYSTEM_PRESET:
                    imp_settings["active_preset_name"] = SYSTEM_PRESET
                    imp_settings["enabled"] = False
                    self._update_template_json({"imposition_settings": imp_settings})

        self.cbo_presets_main.blockSignals(False)
        self._refresh_main_preset_tooltip()

    def _on_main_preset_changed(self, index):
        """Atualiza qual predefinição será usada, sem sobrescrever o modelo base."""
        SYSTEM_PRESET = self.SYSTEM_IMPOSITION_PRESET
        if not self.cached_model_data or index < 0: return
        
        name = self._main_preset_name_at(index)
        
        imp = self.cached_model_data.setdefault("imposition_settings", {})

        if name == SYSTEM_PRESET:
            imp["enabled"] = False
            imp["active_preset_name"] = SYSTEM_PRESET
            self._update_template_json({"imposition_settings": imp})
            self.log_panel.append(tr("⚡ Layout aplicado: <b>{nome}</b>").format(nome=tr(SYSTEM_PRESET)))
            self._refresh_main_preset_tooltip()
            self._invalidate_sheet_previews()
            self._refresh_preview_navigation()
            if self._preview_mode == "item":
                self._on_table_selection()
            return

        presets = imp.get("presets", {}) or {}
        if name in presets:
            imp["active_preset_name"] = name
            self._update_template_json({"imposition_settings": imp})
            self.log_panel.append(tr("⚡ Layout aplicado: <b>{nome}</b>").format(nome=name))
        self._refresh_main_preset_tooltip()
        self._invalidate_sheet_previews()
        self._refresh_preview_navigation()
        if self._preview_mode == "sheet":
            self._render_current_sheet_preview()
        else:
            self._start_sheet_preview_preload()

    def _main_preset_name_at(self, index):
        name = self.cbo_presets_main.itemData(index, Qt.ItemDataRole.UserRole)
        return name if name else self.cbo_presets_main.itemText(index)

    def _refresh_main_preset_tooltip(self):
        if not self.cached_model_data:
            self.cbo_presets_main.setToolTip(self._presets_main_base_tooltip)
            return

        name = self._main_preset_name_at(self.cbo_presets_main.currentIndex())
        imp_settings = self.cached_model_data.get("imposition_settings", {}) or {}
        preset = (imp_settings.get("presets", {}) or {}).get(name, {})
        model_w, model_h = self._get_model_base_print_size_mm()
        tooltip = warning_tooltip(name, preset, model_w, model_h)
        self.cbo_presets_main.setToolTip(tooltip or self._presets_main_base_tooltip)
    

   
