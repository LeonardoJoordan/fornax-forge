"""Execute: .venv/bin/python features/workspace/main.py"""
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault('QT_IM_MODULE', 'ibus')
os.environ.setdefault('GTK_IM_MODULE', 'ibus')
os.environ.setdefault('XMODIFIERS', '@im=ibus')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from core.app_instance import ApplicationInstance
from core.custom_tooltip import CustomTooltipManager
from core.paths import APP_ID, get_logs_dir
from core.settings import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from core.resources import app_icon_path
from core.ui_font import install_ui_font
from core.wheel_focus import install_wheel_focus_guard
from core.i18n import initialize_i18n, tr
from core.dialog_buttons import install_dialog_button_style
from core.diagnostic_logs import append_diagnostic_log, crash_summary
from core.temp_storage import cleanup_stale_workspaces
from features.workspace.main_window import MainWindow


class FornaxApplication(QApplication):
    fileOpenRequested = Signal(str)

    def __init__(self, arguments):
        super().__init__(arguments)
        self.pending_file_opens = []

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen and event.file():
            path = str(Path(event.file()).expanduser())
            self.pending_file_opens.append(path)
            self.fileOpenRequested.emit(path)
            return True
        return super().event(event)


def _external_arguments(arguments):
    result = []
    for argument in arguments[1:]:
        path = Path(argument).expanduser()
        if path.suffix.lower() in {".fornax", ".zip"}:
            result.append(str(path.resolve()))
    return result


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    log_file = get_logs_dir() / 'crash_log.txt'
    try:
        append_diagnostic_log(
            "crash_log.txt", crash_summary(exc_type, exc_traceback), sanitize=False,
        )
    except OSError:
        pass
    message = QMessageBox()
    message.setIcon(QMessageBox.Icon.Critical)
    message.setWindowTitle(tr('Erro fatal'))
    message.setText(tr('Ocorreu um erro inesperado e o sistema precisa ser encerrado.'))
    message.setInformativeText(tr('Os detalhes técnicos foram salvos em:\n{arquivo}').format(arquivo=log_file))
    message.setDetailedText(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    message.exec()


def main():
    app = FornaxApplication(sys.argv)
    app.setOrganizationName(SETTINGS_ORGANIZATION)
    app.setApplicationName(SETTINGS_APPLICATION)
    app.setApplicationDisplayName('FORNAX Forge')
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(app_icon_path())))
    app.setStyle('Fusion')
    install_ui_font(app)
    install_wheel_focus_guard(app)
    from core.themes import theme_manager
    from core.settings import get_app_settings
    settings = get_app_settings()
    initialize_i18n(app, settings)
    theme_manager().initialize(settings)
    install_dialog_button_style(app)
    sys.excepthook = global_exception_handler
    CustomTooltipManager.install(delay_ms=1500)
    external_paths = _external_arguments(sys.argv)
    instance = ApplicationInstance(app)
    if ApplicationInstance.forward_to_running(external_paths):
        return 0
    if not instance.listen():
        # Outro processo pode ter vencido a eleição depois da primeira tentativa.
        if ApplicationInstance.forward_to_running(external_paths):
            return 0
        QMessageBox.critical(None, tr('Erro fatal'), tr('Não foi possível iniciar uma instância exclusiva do programa. Tente novamente.'))
        return 1
    cleanup_stale_workspaces()
    queued_files = []
    instance.filesReceived.connect(queued_files.extend)
    window = MainWindow()
    instance.filesReceived.disconnect(queued_files.extend)
    instance.filesReceived.connect(window.handle_external_files)
    app.fileOpenRequested.connect(window.handle_external_file)
    window.show()
    initial_paths = list(dict.fromkeys([*external_paths, *app.pending_file_opens, *queued_files]))
    if initial_paths:
        QTimer.singleShot(0, lambda: window.handle_external_files(initial_paths))
    result = app.exec()
    instance.close()
    if getattr(app, "_restart_requested", False):
        from features.workspace.frontend import _launch_restarted_application
        if not _launch_restarted_application():
            return 1
    return result


if __name__ == '__main__':
    sys.exit(main())
