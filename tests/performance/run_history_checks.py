"""Contratos de histórico em ambiente isolado."""
import argparse,os,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--theme',choices=('dark','light'),default='dark');p.add_argument('--evidence',type=Path);p.add_argument('--behavior-only',action='store_true');p.add_argument('--work-only',action='store_true');args=p.parse_args()
    with TemporaryDirectory(prefix='fornax-history-checks-') as temporary:
        os.environ.update(QT_QPA_PLATFORM='offscreen',QT_SCALE_FACTOR='1',XDG_CONFIG_HOME=temporary+'/config',XDG_DATA_HOME=temporary+'/data',XDG_CACHE_HOME=temporary+'/cache',APPDATA=temporary+'/config')
        if args.evidence:os.environ['FORNAX_HISTORY_EVIDENCE']=str(args.evidence)
        from PySide6.QtWidgets import QApplication
        from core.ui_font import install_ui_font
        from core.themes import theme_manager
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setCursorFlashTime(0);install_ui_font(app);theme_manager().select(args.theme)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_editor_history_capture'+('.HistoryBehaviorTest' if args.behavior_only else '.HistoryWorkTest' if args.work_only else '')))
        return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
