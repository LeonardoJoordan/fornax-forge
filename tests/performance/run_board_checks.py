"""Contratos de conectores e evidências visuais, com preferências isoladas."""
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme', choices=('dark', 'light'), default='dark')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--behavior-only', action='store_true')
    parser.add_argument('--reference-editor', type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='fornax-board-') as root:
        os.environ.update(QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=root+'/config',
                          XDG_DATA_HOME=root+'/data', XDG_CACHE_HOME=root+'/cache')
        if args.evidence:
            os.environ['FORNAX_BOARD_EVIDENCE'] = str(args.evidence)
        if args.reference_editor:
            import features.editor
            features.editor.__path__ = [str(args.reference_editor), *features.editor.__path__]
        from PySide6.QtWidgets import QApplication
        from core.ui_font import install_ui_font
        from core.themes import theme_manager
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        install_ui_font(app)
        theme_manager().select(args.theme)
        target = 'test_editor_board_updates' + ('.BoardUpdateBehaviorTest' if args.behavior_only else '')
        suite = unittest.defaultTestLoader.loadTestsFromName(target)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
