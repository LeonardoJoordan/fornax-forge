"""Etapa 06: checkpoints sem edição e undo/redo completo em 800 células."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_SCALE_FACTOR','1')
import argparse,json,sys,time
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from core.ui_font import install_ui_font
from core.table_model import new_table,format_cells
from core.model_document import normalize_model_document,add_model_table
from features.editor.editor_window import EditorWindow
from features.editor.table_item import TableItem
from run_table_prototype import distribution,rss


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='fornax-table-integration-') as temp:
        for key,sub in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:os.environ[key]=temp+'/'+sub
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors=[];sys.excepthook=lambda typ,value,tb:errors.append(str(value))
        table=new_table(40,20,width=1200,height=1600)
        for c in table['cells']:c['html']=f'<p><b>{c["row"]+1}</b>/{c["column"]+1}</p>'
        w=EditorWindow()
        try:
            w._load_document_into_scene(add_model_table(normalize_model_document({'canvas_size':{'w':1400,'h':1800}}),table))
            w.resize(1280,800);w.show();app.processEvents();w._zoom_to_fit();app.processEvents()
            w.history.clear();w.save_snapshot();initial=w._capture_document_history_state()['document']
            def measure(operation):
                samples=[]
                for n in range(22):
                    start=time.perf_counter();operation();app.processEvents();elapsed=(time.perf_counter()-start)*1000
                    if n>=2:samples.append(elapsed)
                return distribution(samples)
            results={'unchanged_checkpoint_with_events':measure(w.save_snapshot)}
            assert len(w.history._undo_stack)==1
            item=next(i for i in w.scene.items() if isinstance(i,TableItem))
            item.publish_table_data(format_cells(item.to_data(),0,0,0,0,{'fill_color':'#bbddff'}));w.save_snapshot()
            changed=w._capture_document_history_state()['document']
            def cycle():w.undo();w.redo()
            results['undo_redo_one_fill_in_dense_table']=measure(cycle)
            assert w._capture_document_history_state()['document']==changed
            w.undo();assert w._capture_document_history_state()['document']==initial;w.redo()
            paths=['features/editor/editor_window.py','features/editor/history_capture.py','features/editor/table_item.py',
                   'features/editor/document_session.py','features/editor/page_scenes.py','core/table_model.py',
                   'tests/performance/benchmark_table_integration.py']
            result=dict(cells=800,samples=20,warmups=2,qt_scale=os.environ['QT_SCALE_FACTOR'],operations=results,
                rss_process_bytes=rss(),source_hashes={s:sha256((ROOT/s).read_bytes()).hexdigest() for s in paths})
        finally:
            w._finish_page_interaction();w._last_saved_state=w.get_current_scene_state();w._last_saved_document_state=w._capture_document_history_state()
            w.close();w.deleteLater();app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not errors,errors
        result['callback_errors']=errors;args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(results,indent=2))
if __name__=='__main__':main()
