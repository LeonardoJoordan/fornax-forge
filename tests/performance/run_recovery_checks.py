"""Recuperação: contratos isolados, inclusive exceções de callbacks Qt."""
import argparse,os,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--behavior-only',action='store_true');p.add_argument('--work-only',action='store_true');p.add_argument('--concurrency',action='store_true');p.add_argument('--theme',choices=('dark','light'),default='dark');args=p.parse_args()
    with TemporaryDirectory(prefix='fornax-recovery-checks-') as root:
        os.environ.update(QT_QPA_PLATFORM='offscreen',QT_SCALE_FACTOR='1',XDG_CONFIG_HOME=root+'/config',XDG_DATA_HOME=root+'/data',XDG_CACHE_HOME=root+'/cache',APPDATA=root+'/config')
        from PySide6.QtWidgets import QApplication
        from core.ui_font import install_ui_font
        from core.themes import theme_manager
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setCursorFlashTime(0);install_ui_font(app);theme_manager().select(args.theme)
        errors=[];sys.excepthook=lambda typ,value,tb:errors.append(str(value))
        target='test_editor_recovery_concurrency.RecoveryConcurrencyTest' if args.concurrency else 'test_editor_recovery_updates'+('.RecoveryBehaviorTest' if args.behavior_only else '.RecoveryWorkTest' if args.work_only else '')
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(target))
        if errors:print('EXCEÇÕES DE CALLBACK',errors)
        return int(not result.wasSuccessful() or bool(errors))
if __name__=='__main__':raise SystemExit(main())
