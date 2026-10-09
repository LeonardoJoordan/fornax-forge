"""Validação complementar das alças, seleção coletiva, guias e troca de tema.

A referência usa os seis módulos anteriores preservados no diretório informado;
os demais módulos, instrumentos e fixtures permanecem os mesmos.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'tests/performance')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-editor', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='fornax-selection-paint-') as directory:
        os.environ.update(QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR='1',
                          XDG_CONFIG_HOME=directory+'/config', XDG_DATA_HOME=directory+'/data',
                          XDG_CACHE_HOME=directory+'/cache', APPDATA=directory+'/config',
                          FORNAX_PAINT_EVIDENCE=str(args.output))
        if args.reference_editor:
            import features.editor
            features.editor.__path__ = [str(args.reference_editor), *features.editor.__path__]
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        from core.themes import theme_manager
        from core.ui_font import install_ui_font
        from features.editor.canvas_items import DesignerBox, ImageItem, SignatureItem, Guideline
        from paint_cases import PaintCase, PaintSession
        from test_editor_paint_updates import PaintBehaviorTest
        import test_editor_performance_contracts as contracts

        class SelectionPaintTest(unittest.TestCase):
            setUpClass = classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
            setUp = contracts.PerformanceContractsTest.setUp
            editor = contracts.PerformanceContractsTest.editor
            record = PaintBehaviorTest.record

            def page(self):
                w = self.editor('simple', 1)
                return PaintSession(w, PaintCase('selection', 'local', 'mixed', 60), self.app).window

            def move_item(self, item_type, prefix):
                w = self.page()
                item = next(i for i in w.scene.items() if type(i) is item_type)
                w.view.centerOn(item.sceneBoundingRect().center())
                item.setSelected(True)
                self.record(w, prefix+'-selected')
                item.moveBy(90, 45)
                self.record(w, prefix+'-moved')
                item.setVisible(False)
                self.record(w, prefix+'-hidden')

            def test_image_handles(self):
                self.move_item(ImageItem, 'image')

            def test_signature_handles(self):
                self.move_item(SignatureItem, 'signature')

            def test_multi_selection_handles(self):
                w = self.page()
                items = sorted((i for i in w.scene.items() if type(i) is DesignerBox),
                               key=lambda i: (i.sceneBoundingRect().center()-QPointF(300, 240)).manhattanLength())[:2]
                with w._selection_batch():
                    for item in items:
                        item.setSelected(True)
                self.record(w, 'multi-selected')
                self.assertTrue(w._selection_frame.isVisible())
                for item in items:
                    item.moveBy(90, 45)
                self.record(w, 'multi-moved')
                w.scene.clearSelection()
                self.record(w, 'multi-deselected')

            def test_guides_and_live_theme_change(self):
                w = self.page()
                guide = next(i for i in w.scene.items() if isinstance(i, Guideline))
                self.record(w, 'guide-original')
                guide.moveBy(60 if guide.is_vertical else 0, 0 if guide.is_vertical else 60)
                self.record(w, 'guide-moved')
                guide.hide()
                self.record(w, 'guide-hidden')
                theme_manager().select('light')
                self.record(w, 'theme-light')
                theme_manager().select('dark')
                self.record(w, 'theme-dark')

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        app.setCursorFlashTime(0)
        install_ui_font(app)
        theme_manager().select('dark')
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SelectionPaintTest))
        modules = ('controls', 'canvas_items', 'rulers', 'organogram_editor', 'frontend', 'editor_window')
        origins = {}
        for name in modules:
            path = Path(sys.modules['features.editor.'+name].__file__)
            if args.reference_editor:
                assert path.parent == args.reference_editor.resolve(), path
            origins[name] = {'source': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
        provenance = {'probe_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                      'modules': origins, 'tests': result.testsRun, 'passed': result.wasSuccessful()}
        args.output.with_suffix('.modules.json').write_text(json.dumps(provenance, indent=2)+'\n')
        return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
