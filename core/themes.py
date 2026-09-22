"""Temas de interface. Cores do documento nunca passam por este módulo."""
import json
import re
import uuid
import weakref
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QSaveFile, QIODevice
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from core.paths import get_app_data_dir
from core.resources import PROJECT_ROOT, navigation_icon_path

TOKEN = re.compile(r"@([a-z][a-z0-9_]*)@")


def load_theme(path, fallback=None):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_theme(data, fallback)


def validate_theme(data, fallback=None):
    if not isinstance(data, dict):
        raise ValueError('Formato de tema inválido')
    if data.get('version') != 1 or not isinstance(data.get('colors'), dict):
        raise ValueError('Formato de tema inválido')
    result = dict(fallback or {})
    for key, value in data['colors'].items():
        if fallback is not None and key not in fallback:
            raise ValueError(f'Cor desconhecida: {key}')
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError(f'Cor inválida: {key}')
        result[key] = value.lower()
    return {'version': 1, 'name': str(data.get('name', 'Tema')), 'colors': result}


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.dark = load_theme(PROJECT_ROOT / 'assets/themes/dark.json')
        self.light = load_theme(PROJECT_ROOT / 'assets/themes/light.json', self.dark['colors'])
        self.builtins = {}
        for theme_id in ('carbon', 'dark', 'graphite', 'rose', 'light'):
            self.builtins[theme_id] = load_theme(
                PROJECT_ROOT / 'assets/themes' / (theme_id + '.json'), self.dark['colors'])
        self.current = self.dark
        self.theme_id = 'dark'
        self.styles = weakref.WeakKeyDictionary()
        self.settings = None
        self._icon_directory = tempfile.TemporaryDirectory(prefix='fornax-theme-icons-')
        self._icon_paths = {}
        self._prepare_icons()

    def _prepare_icons(self):
        # Setas preenchidas nos campos numéricos; chevron nas comboboxes.
        for name, icon_name in [('spin_up', 'arrow_drop_up'),
                                ('spin_down', 'arrow_drop_down'),
                                ('combo_arrow', 'chevron-down')]:
            color = self.color('icon')
            target = Path(self._icon_directory.name) / (name + color[1:] + '.svg')
            if not target.exists():
                svg = navigation_icon_path(icon_name).read_text(encoding='utf-8')
                svg = re.sub(r'#[0-9a-fA-F]{6}', color, svg)
                svg = svg.replace('currentColor', color)
                target.write_text(svg, encoding='utf-8')
            self._icon_paths[name] = target.as_posix()
        # Marcas explícitas: não dependem do contraste do estilo nativo do SO.
        for name, shape in [('check', '<path d="M3 7l3 3 5-6" fill="none" stroke-width="2"/>'),
                            ('partial', '<path d="M3 7h8" fill="none" stroke-width="2"/>'),
                            ('radio_dot', '<circle cx="7" cy="7" r="3" fill="none" stroke-width="3"/>')]:
            color = self.color('on_accent')
            target = Path(self._icon_directory.name) / (name + color[1:] + '.svg')
            if not target.exists():
                target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14"><g stroke="{color}" stroke-linecap="round" stroke-linejoin="round">{shape}</g></svg>', encoding='utf-8')
            self._icon_paths[name] = target.as_posix()

    def color(self, role):
        return self.current['colors'][role]

    def resolve(self, template):
        return TOKEN.sub(lambda match: self._icon_paths[match[1]] if match[1] in self._icon_paths else self.color(match[1]), template)

    def style(self, widget, template):
        self.styles[widget] = template
        widget.setStyleSheet(self.resolve(template))

    def select(self, theme_id, data=None):
        if data is None:
            if theme_id in self.builtins:
                data = self.builtins[theme_id]
            else:
                if not re.fullmatch(r'custom-[0-9a-f]{32}', theme_id):
                    raise ValueError('Identificador de tema inválido')
                data = load_theme(get_app_data_dir() / 'themes' / (theme_id + '.json'), self.dark['colors'])
        data = validate_theme(data, self.dark['colors'])
        self.current, self.theme_id = data, theme_id
        self._prepare_icons()
        app = QApplication.instance()
        if app:
            palette = QPalette()
            roles = {'Window': 'surface', 'WindowText': 'text', 'Base': 'field',
                     'AlternateBase': 'alternate', 'Text': 'text', 'Button': 'button',
                     'ButtonText': 'text', 'Highlight': 'selection', 'HighlightedText': 'text',
                     'ToolTipBase': 'button', 'ToolTipText': 'text', 'Link': 'accent',
                     'PlaceholderText': 'muted'}
            for role, color in roles.items():
                palette.setColor(getattr(QPalette.ColorRole, role), QColor(self.color(color)))
            for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
                palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(self.color('disabled')))
            app.setPalette(palette)
            app.setStyleSheet(self.resolve('''
                QDialog { background: @surface@; color: @text@; }
                QMenu { background: @button@; color: @text@; border: 1px solid @border@; }
                QMenu::item:selected { background: @selection@; }
                QToolTip { background: @button@; color: @text@; border: 1px solid @border@; }
                QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid @border_strong@;
                    border-radius: 3px; background: @field@; }
                QCheckBox::indicator:hover { border: 1px solid @accent@; background: @hover@; }
                QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate {
                    background: @accent@; border: 1px solid @accent@; }
                QCheckBox::indicator:checked { image: url(@check@); }
                QCheckBox::indicator:indeterminate { image: url(@partial@); }
                QCheckBox::indicator:disabled { background: @button@; border: 1px solid @disabled@; }
                QCheckBox::indicator:checked:disabled, QCheckBox::indicator:indeterminate:disabled {
                    background: @disabled@; }
                QRadioButton::indicator { width: 14px; height: 14px; border-radius: 8px;
                    border: 1px solid @border_strong@; background: @field@; }
                QRadioButton::indicator:hover { border: 1px solid @accent@; background: @hover@; }
                QRadioButton::indicator:checked { background: @accent@; border: 1px solid @accent@;
                    image: url(@radio_dot@); }
                QRadioButton::indicator:disabled { border: 1px solid @disabled@; background: @button@; }
                QRadioButton::indicator:checked:disabled { background: @disabled@; }
            '''))
        for widget, template in list(self.styles.items()):
            if isValid(widget):
                widget.setStyleSheet(self.resolve(template))
        self.changed.emit()
        if app:
            for widget in app.topLevelWidgets():
                widget.update()

    def initialize(self, settings):
        self.settings = settings
        default = 'dark' if settings.value('dark_mode', True, type=bool) else 'light'
        chosen = settings.value('theme/id', default)
        try:
            self.select(chosen)
        except (OSError, ValueError, TypeError):
            self.select(default)

    def save_custom(self, name, colors):
        theme_id = 'custom-' + uuid.uuid4().hex
        folder = get_app_data_dir() / 'themes'
        folder.mkdir(parents=True, exist_ok=True)
        data = validate_theme({'version': 1, 'name': name, 'colors': colors}, self.dark['colors'])
        target = QSaveFile(str(folder / (theme_id + '.json')))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        if target.write(encoded) != len(encoded) or not target.commit():
            raise OSError(target.errorString())
        self.select(theme_id)
        return theme_id

    def persist(self):
        if self.settings is not None:
            self.settings.setValue('theme/id', self.theme_id)
            self.settings.sync()


_manager = None


def theme_manager():
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def themed_style(widget, template):
    theme_manager().style(widget, template)


def theme_color(role):
    return theme_manager().color(role)
