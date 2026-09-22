from PySide6.QtCore import QSettings


SETTINGS_ORGANIZATION = "FORNAX Forge"
SETTINGS_APPLICATION = "MainApp"
LEGACY_SETTINGS_ORGANIZATION = "Projeto ComSoc"
LEGACY_SETTINGS_APPLICATION = "MainApp"
MIGRATION_MARKER = "migration/comsocSettingsCopied"


def get_app_settings() -> QSettings:
    """Abre preferências FORNAX e copia chaves COMSOC que ainda não existem."""
    settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
    if settings.value(MIGRATION_MARKER, False, type=bool):
        return settings

    legacy = QSettings(LEGACY_SETTINGS_ORGANIZATION, LEGACY_SETTINGS_APPLICATION)
    existing = set(settings.allKeys())
    for key in legacy.allKeys():
        if key not in existing:
            settings.setValue(key, legacy.value(key))
    settings.setValue(MIGRATION_MARKER, True)
    settings.sync()
    return settings
