"""Custo das novas operações em 800 células; não havia painel anterior equivalente."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_SCALE_FACTOR','1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='fornax-table-controls-bench-') as directory:
        for key,subdir in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')):
            os.environ[key]=directory+'/'+subdir
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
        from core.ui_font import install_ui_font
        from features.editor.editor_window import EditorWindow
        from features.editor.table_item import TableItem
        from table_fixtures import table_spec
        from table_document_fixtures import document_from_spec
        from run_table_prototype import distribution,rss
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors=[]
        def hook(typ,value,tb):
            errors.append(str(value));sys.__excepthook__(typ,value,tb)
        sys.excepthook=hook
        spec=table_spec('densa',40,20)
        spec.update(default_font='Inter 18pt',default_font_size_pt=7,padding_mm=.5)
        for cell in spec['cells']:cell['html']=f'<p><b>{cell["row"]+1}</b>/{cell["column"]+1}</p>'
        source=document_from_spec({'id':'densa','pages':[{'page':'front','tables':[spec]}]})
        window=EditorWindow()
        try:
            window._load_document_into_scene(source);window.resize(1280,800);window.show()
            app.processEvents();window._zoom_to_fit();app.processEvents()
            item=next(i for i in window.scene.items() if isinstance(i,TableItem))
            controller=window.table_controller
            item.select_cell(10,10);item.select_cell(13,13,extend=True)
            docs=[entry.document for entry in item.layout.cells]
            results={}
            def measure(name,operation):
                values=[]
                for index in range(22):
                    start=time.perf_counter();accepted=operation(index);app.processEvents()
                    assert accepted is True,window.table_panel.message.text()
                    assert not window.table_panel.message.text(),window.table_panel.message.text()
                    if index>=2:values.append((time.perf_counter()-start)*1000)
                results[name]=distribution(values)
            measure('fill_16_cells_with_history',lambda n: controller.cell_style(
                {'fill_color':'#ddeeff' if n%2 else '#ffffff'}))
            assert all(e.document is doc for e,doc in zip(item.layout.cells,docs))
            measure('copy_16_cells_mime_and_tsv',lambda n: controller.copy_selection())
            measure('paste_16_cells_internal_with_history',lambda n: controller.paste_selection())
            measure('edge_color_16_cells_with_history',lambda n: controller.edge_style(
                {'color':'#112233' if n%2 else '#203746'}))
            measure('width_4_columns_with_history',lambda n: controller.track('column',10 if n%2 else 11))
            paths=['features/editor/table_controller.py','features/editor/table_panel.py',
                   'features/editor/table_item.py','core/table_model.py','core/table_html.py',
                   'core/table_layout.py','core/table_clipboard.py','tests/performance/benchmark_table_controls.py']
            result=dict(cells=800,range=[10,10,13,13],samples=20,warmups=2,
                        qt_scale=os.environ['QT_SCALE_FACTOR'],operations=results,
                        viewport=[window.view.viewport().width(),window.view.viewport().height()],
                        rss_process_bytes=rss(),fixture_sha256=sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),
                        source_hashes={path:sha256((ROOT/path).read_bytes()).hexdigest() for path in paths})
        finally:
            app.clipboard().clear();window._finish_page_interaction();window._recovered_unsaved=False
            window._last_saved_state=window.get_current_scene_state()
            window._last_saved_document_state=window._capture_document_history_state()
            window.close();window.deleteLater();app.processEvents()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        if errors:raise AssertionError(errors)
        result['callback_errors']=errors
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({name:{key:value[key] for key in ('median_ms','p95_ms')}
                          for name,value in results.items()},indent=2))


if __name__ == '__main__':main()
