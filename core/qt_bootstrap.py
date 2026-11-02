"""Configure platform defaults before importing Qt or constructing its application."""

import os
import sys


def configure_qt_environment() -> None:
    """Use FreeType on Windows unless the caller selected another Qt platform."""
    if sys.platform == 'win32':
        os.environ.setdefault('QT_QPA_PLATFORM', 'windows:fontengine=freetype')
