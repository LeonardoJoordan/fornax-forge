"""Entrada oficial do FORNAX Forge."""
import sys

from core.qt_bootstrap import configure_qt_environment

configure_qt_environment()

from features.workspace.main import main


if __name__ == "__main__":
    sys.exit(main())
