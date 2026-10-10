"""Etapa 04: tabela sintética de 800 células; edição local e pintura retida.

Mede operações reais da sessão, com duas preparações e vinte amostras.
Não compara estes recursos novos com uma versão que ainda não os possuía.
"""
from copy import deepcopy
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_SCALE_FACTOR', '1')

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QImage, QPainter, QInputMethodEvent
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem
from core.ui_font import install_ui_font
from features.editor.editor_window import EditorWindow
from features.editor.table_item import TableItem
from table_fixtures import table_spec
from table_document_fixtures import document_from_spec
from run_table_prototype import distribution, rss


def measure(operation, prepare=lambda: None):
    times = []
    for index in range(22):
        prepare()
        start = time.perf_counter()
        operation()
        elapsed = (time.perf_counter()-start)*1000
        if index >= 2:
            times.append(elapsed)
    return distribution(times)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='fornax-table-canvas-bench-') as directory:
        for key, subdir in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
            os.environ[key] = directory+'/'+subdir
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        install_ui_font(app)
        errors = []
        def exception_hook(typ, value, tb):
            errors.append(str(value))
            sys.__excepthook__(typ, value, tb)
        sys.excepthook = exception_hook
        dense = table_spec('densa', 40, 20)
        dense.update(default_font='Inter 18pt', default_font_size_pt=7, padding_mm=.5)
        for cell in dense['cells']:
            cell['html'] = f'<p><b>{cell["row"]+1}</b>/{cell["column"]+1}</p>'
        source = document_from_spec({'id': 'densa', 'pages': [{'page': 'front', 'tables': [dense]}]})
        window = EditorWindow()
        try:
            window._load_document_into_scene(source)
            window.resize(1280, 800)
            window.show()
            app.processEvents()
            window._zoom_to_fit()
            app.processEvents()
            item = next(root for root in window.scene.items() if isinstance(root, TableItem))
            item.overlays_enabled = False
            baseline_data = deepcopy(item.data)
            retained = item.layout
            identities = [entry.document for entry in retained.cells]
            operations = {}
            image = QImage(620, 877, QImage.Format.Format_ARGB32)

            def paint_region(local=False):
                image.fill(Qt.GlobalColor.white)
                option = QStyleOptionGraphicsItem()
                option.exposedRect = retained.cells[0].rect if local else item.boundingRect()
                painter = QPainter(image)
                try:
                    painter.scale(.25, .25)
                    painter.setClipRect(option.exposedRect)
                    item.paint(painter, option)
                finally:
                    painter.end()

            operations['paint_all_cells'] = measure(paint_region)
            operations['paint_one_cell_region'] = measure(lambda: paint_region(True))

            def select_and_move():
                item.select_cell(10, 10)
                item.setPos(item.x()+1, item.y()+1)
                app.processEvents()
            operations['select_and_move_with_events'] = measure(select_and_move)
            assert item.layout is retained
            assert all(entry.document is document for entry, document in zip(retained.cells, identities))

            def start_edit():
                window.table_edit.finish()
                item.publish_cell_html((0, 0), baseline_data['cells'][0]['html'])
                window.table_edit.begin(item, (0, 0))
                app.processEvents()

            start_edit()
            identities = [entry.document for entry in retained.cells]
            history_before = len(window.history._undo_stack)
            def type_character():
                event = QInputMethodEvent()
                event.setCommitString('á')
                window.scene.sendEvent(window.table_edit.text, event)
                app.processEvents()
            operations['type_character_with_events'] = measure(type_character)
            assert len(window.history._undo_stack) == history_before
            assert item.layout is retained
            assert all(entry.document is document for entry, document in zip(retained.cells, identities))
            window.table_edit.finish()

            def prepare_checkpoint():
                start_edit()
                event = QInputMethodEvent()
                event.setCommitString(' Editado')
                window.scene.sendEvent(window.table_edit.text, event)
                app.processEvents()
            def checkpoint():
                window.table_edit.checkpoint()
                app.processEvents()
            operations['checkpoint_cell_with_history_and_events'] = measure(checkpoint, prepare_checkpoint)
            assert item.layout is retained
            assert all(entry.document is document for entry, document in zip(retained.cells[1:], identities[1:]))
            assert 'Editado' in item.layout.cells[0].document.toPlainText()
            paths = ['core/table_layout.py', 'core/table_paint.py', 'features/editor/table_item.py',
                     'features/editor/table_edit.py', 'features/editor/editor_window.py',
                     'tests/performance/benchmark_table_canvas.py']
            result = dict(python=sys.version, platform=platform.platform(),
                          qt_scale=os.environ['QT_SCALE_FACTOR'], cells=800, warmups=2, samples=20,
                          operations=operations, rss_process_bytes=rss(),
                          viewport=[window.view.viewport().width(), window.view.viewport().height()],
                          fixture_sha256=sha256(json.dumps(dense, sort_keys=True).encode()).hexdigest(),
                          source_hashes={path: sha256((ROOT/path).read_bytes()).hexdigest() for path in paths})
        finally:
            window._finish_page_interaction()
            window._last_saved_state = window.get_current_scene_state()
            window._last_saved_document_state = window._capture_document_history_state()
            window.close()
            window.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not errors, errors
        result['callback_errors'] = errors
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({name: {key: value[key] for key in ('median_ms', 'p95_ms')}
                          for name, value in operations.items()}, indent=2))


if __name__ == '__main__':
    main()
