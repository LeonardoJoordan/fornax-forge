"""Contratos de cópia e evidências visuais, com preferências isoladas."""
import argparse, os, sys, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme',choices=('dark','light'),default='dark')
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--behavior-only',action='store_true')
    parser.add_argument('--work-only',action='store_true')
    args=parser.parse_args()
    with TemporaryDirectory(prefix='fornax-copy-checks-') as root:
        os.environ.update(QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=root+'/config',XDG_DATA_HOME=root+'/data',XDG_CACHE_HOME=root+'/cache')
        if args.evidence:os.environ['FORNAX_COPY_EVIDENCE']=str(args.evidence)
        from PySide6.QtWidgets import QApplication
        from core.ui_font import install_ui_font
        from core.themes import theme_manager
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app);theme_manager().select(args.theme)
        target='test_editor_copy_insertion'+('.CopyWorkTest' if args.work_only else '.CopyBehaviorTest' if args.behavior_only else '')
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(target))
        return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
