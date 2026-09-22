"""Execute: .venv/bin/python features/editor/main.py [--model arquivo.json]."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from core.paths import APP_ID
from core.resources import app_icon_path
from core.ui_font import install_ui_font
from core.wheel_focus import install_wheel_focus_guard
from core.i18n import initialize_i18n
from core.settings import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from core.dialog_buttons import install_dialog_button_style
from features.editor.editor_window import EditorWindow


def main():
    parser = argparse.ArgumentParser(description='Editor visual independente do FORNAX Forge')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--screenshot', type=Path)
    args = parser.parse_args()
    if args.model and not args.model.exists():
        parser.error('Modelo não encontrado.')
    app = QApplication(sys.argv)
    app.setOrganizationName(SETTINGS_ORGANIZATION)
    app.setApplicationName(SETTINGS_APPLICATION)
    app.setApplicationDisplayName('FORNAX Forge — Editor')
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
    window = EditorWindow()
    if args.model:
        window.load_from_json(args.model)
    window.show()
    if args.check or args.screenshot:
        def finish():
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot)):
                    app.exit(1)
                    return
            app.quit()
        QTimer.singleShot(500, finish)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
