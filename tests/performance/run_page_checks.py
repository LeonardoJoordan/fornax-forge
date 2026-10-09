"""Contratos de cena em processo com preferências isoladas."""
import argparse,os,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]; sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]
def main():
    p=argparse.ArgumentParser(); p.add_argument('--reuse',action='store_true'); p.add_argument('--theme',default='dark'); p.add_argument('--case'); args=p.parse_args()
    with TemporaryDirectory(prefix='fornax-page-checks-') as root:
        os.environ.update(QT_QPA_PLATFORM='offscreen',QT_SCALE_FACTOR='1',XDG_CONFIG_HOME=root+'/config',XDG_DATA_HOME=root+'/data',XDG_CACHE_HOME=root+'/cache')
        from PySide6.QtWidgets import QApplication
        from core.themes import theme_manager
        app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setCursorFlashTime(0); theme_manager().select(args.theme)
        errors=[]; sys.excepthook=lambda typ,value,tb: errors.append(str(value))
        import test_editor_page_scenes as module
        suite=unittest.defaultTestLoader.loadTestsFromName('test_editor_page_scenes.'+args.case) if args.case else unittest.defaultTestLoader.loadTestsFromTestCase(module.PageBehaviorTest)
        if args.reuse:
            suite.addTests(module.PageReuseTest(name) for name in module.PageReuseTest.__dict__ if name.startswith('test_'))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if errors: print('CALLBACKS',errors)
        return int(not result.wasSuccessful() or bool(errors))
if __name__=='__main__':raise SystemExit(main())
