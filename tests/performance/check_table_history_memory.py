"""Diagnóstico auxiliar: lote offscreen versus descarte tardio do Qt."""
import argparse,gc,json,os,sys,weakref
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from core.ui_font import install_ui_font
from core.table_model import new_table,format_cells
from core.model_document import normalize_model_document,add_model_table
from features.editor.editor_window import EditorWindow
from features.editor.table_item import TableItem
from run_table_prototype import rss

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='fornax-table-memory-') as temp:
        for key,sub in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:os.environ[key]=temp+'/'+sub
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors=[];sys.excepthook=lambda typ,value,tb:errors.append(str(value))
        w=EditorWindow();refs=[];layouts=[];result={}
        def current():return next(i for i in w.scene.items() if isinstance(i,TableItem))
        def observe():return dict(rss_bytes=rss(),old_roots_alive=sum(ref() is not None for ref in refs),
            old_layouts_alive=sum(ref() is not None for ref in layouts))
        def settle():
            app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);gc.collect();app.processEvents()
        try:
            table=new_table(40,20,width=1200,height=1600)
            for c in table['cells']:c['html']=f'<p><b>{c["row"]+1}</b>/{c["column"]+1}</p>'
            w._load_document_into_scene(add_model_table(normalize_model_document({'canvas_size':{'w':1400,'h':1800}}),table))
            w.resize(1280,800);w.show();settle();w.history.clear();w.save_snapshot()
            item=current();item.publish_table_data(format_cells(item.to_data(),0,0,0,0,{'fill_color':'#bbddff'}));w.save_snapshot();del item
            settle();result['initial']=observe()
            for _ in range(10):
                for operation in (w.undo,w.redo):
                    refs.append(weakref.ref(current()));layouts.append(weakref.ref(current().layout))
                    operation();app.processEvents()
            result['burst_without_deferred_delete']=observe();settle();result['after_deferred_delete_and_gc']=observe()
            for _ in range(10):
                for operation in (w.undo,w.redo):
                    refs.append(weakref.ref(current()));layouts.append(weakref.ref(current().layout))
                    operation();settle()
            result['cycles_with_deferred_delete']=observe()
            assert all(isValid(i) for i in w.scene.items())
        finally:
            w._finish_page_interaction();w._last_saved_state=w.get_current_scene_state();w._last_saved_document_state=w._capture_document_history_state()
            w.close();w.deleteLater();settle()
        assert not errors,errors
        result['callback_errors']=errors;args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
