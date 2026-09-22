"""Carregamento centralizado das traduções da interface do FORNAX."""

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from core.resources import translation_path


LANGUAGE_SETTING = "language/locale"
DEFAULT_LOCALE = "pt_BR"
SUPPORTED_LANGUAGES = (
    ("pt_BR", "Português (Brasil)"),
    ("en_US", "English"),
    ("es_ES", "Español"),
)

_app_translator = None
_qt_translator = None
_current_locale = DEFAULT_LOCALE


def tr(source: str, disambiguation=None, n: int = -1) -> str:
    # Funções globais `tr()` são catalogadas pelo lupdate no contexto vazio.
    return QCoreApplication.translate("", source, disambiguation, n)


def current_locale() -> str:
    return _current_locale


def set_preferred_locale(settings, locale: str) -> None:
    supported = {code for code, _name in SUPPORTED_LANGUAGES}
    if locale not in supported:
        raise ValueError(f"Idioma não suportado: {locale}")
    settings.setValue(LANGUAGE_SETTING, locale)
    settings.sync()


def initialize_i18n(app, settings) -> str:
    """Instala os tradutores antes da construção de qualquer janela."""
    global _app_translator, _qt_translator, _current_locale

    locale = str(settings.value(LANGUAGE_SETTING, DEFAULT_LOCALE) or DEFAULT_LOCALE)
    if locale not in {code for code, _name in SUPPORTED_LANGUAGES}:
        locale = DEFAULT_LOCALE
    _current_locale = locale

    if _app_translator is not None:
        app.removeTranslator(_app_translator)
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
    _app_translator = QTranslator(app)
    _qt_translator = QTranslator(app)

    if locale != DEFAULT_LOCALE:
        catalog = translation_path(locale)
        if catalog.is_file() and _app_translator.load(str(catalog)):
            app.installTranslator(_app_translator)

    qt_catalog = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if _qt_translator.load(QLocale(locale), "qtbase", "_", qt_catalog):
        app.installTranslator(_qt_translator)
    return locale
