"""Etapa 07: geometria leve do editor e prévia real de 1.000 cartões."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_SCALE_FACTOR','1')
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
import time
from tempfile import TemporaryDirectory
from uuid import uuid5,NAMESPACE_URL
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]
from PySide6 import __version__ as qt_version
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from core.ui_font import install_ui_font
from core.table_model import new_table
from core.model_document import add_model_table
from core.organogram import board_bounds
from features.editor.editor_window import EditorWindow
from features.editor.table_item import TableItem
from features.generator.organogram import OrganogramRenderer
from test_table_product import specimen
from run_table_prototype import distribution,rss


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='fornax-product-bench-') as temp:
        os.environ.update(XDG_CONFIG_HOME=temp+'/config',XDG_DATA_HOME=temp+'/data',XDG_CACHE_HOME=temp+'/cache',APPDATA=temp+'/config')
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors=[];sys.excepthook=lambda typ,value,tb:errors.append(typ.__name__)
        window=EditorWindow()
        inputs={};results={}
        def measure(operation,count):
            samples=[]
            for n in range(count+2):
                started=time.perf_counter();operation();elapsed=(time.perf_counter()-started)*1000
                if n>=2:samples.append(elapsed)
            return distribution(samples)
        def digest(data):return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        try:
            source=specimen();inputs['without_artwork']=digest(source)
            window._load_document_into_scene(source);window.switch_model_page('organogram')
            app.processEvents()
            results['geometry_without_table']=measure(window._board_geometry,20)
            table=new_table(40,20,width=1200,height=1600);table.update(x=-1400,y=-1700)
            table['object_id']=str(uuid5(NAMESPACE_URL,'fornax/product/dense'))
            for i,cell in enumerate(table['cells']):
                cell['id']=str(uuid5(NAMESPACE_URL,f'fornax/product/dense/{i}'));cell['html']='<p>Referência</p>'
            source=add_model_table(source,table,'organogram');inputs['dense_artwork']=digest(source)
            window._load_document_into_scene(source);window.switch_model_page('organogram');app.processEvents()
            expected=board_bounds(source['organogram'])
            before=window._board_geometry()[3]
            results['geometry_with_800_cells']=measure(window._board_geometry,20)
            extent_correct=window._board_geometry()[3]==expected
            paths=window._board_geometry()[1]
            item=next(i for i in window.scene.items() if isinstance(i,TableItem))
            def move():
                item.setX(-1401 if item.x()==-1400 else -1400)
                window._board_geometry()
            results['geometry_after_table_move']=measure(move,20)
            assert window._board_geometry()[1] is paths
            source=specimen(groups=20,columns=10,rows=5);inputs['thousand_cards']=digest(source)
            rows=[{'nome':str(i)} for i in range(1000)]
            def preview():
                renderer=OrganogramRenderer(source,rows)
                image=renderer.preview(1200)
                assert len(renderer.slots)==1000 and max(image.width(),image.height())==1200
            results['construct_and_preview_1000_cards']=measure(preview,5)
            payload={'operations':results,'table_bounds_correct':extent_correct,'groups':20,'cards':1000,
                     'table_slots_per_card':1,'artwork_table_slots':800,'qt_scale':os.environ['QT_SCALE_FACTOR'],
                     'qt':qt_version,'python':platform.python_version(),'font':app.font().key(),
                     'warmups':2,'cheap_samples':20,'expensive_samples':5,'rss_bytes':rss(),
                     'input_hashes':inputs,'source_hashes':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in
                         ['features/editor/organogram_editor.py','core/organogram.py','features/editor/table_item.py',
                          'features/generator/organogram.py','features/generator/renderer.py','tests/test_table_product.py',
                          'tests/performance/benchmark_table_product.py']}}
        finally:
            window._finish_page_interaction();window._last_saved_state=window.get_current_scene_state()
            window._last_saved_document_state=window._capture_document_history_state();window.close()
            app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not errors,errors
        payload['callback_errors']=errors
        args.output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:round(v['median_ms'],3) for k,v in results.items()}))


if __name__=='__main__':main()
