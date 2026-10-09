"""Galerias reais: abertura até pintura, amostras sem profiler e contagens separadas."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark_editor import distribution, environment, rss_bytes, write_json


def worker(kind, cold, output, reference=None):
    if reference:
        import features.editor
        features.editor.__path__=[str(reference/'features/editor'),*features.editor.__path__]
    from PySide6.QtCore import QEvent, Qt, QObject
    from PySide6.QtWidgets import QApplication, QMainWindow
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from features.editor import starter_dialog as module
    from paint_cases import settle
    errors=[]
    sys.excepthook=lambda typ,value,tb:errors.append(''.join(traceback.format_exception(typ,value,tb)))
    app = QApplication([]); app.setQuitOnLastWindowClosed(False); app.setCursorFlashTime(0)
    install_ui_font(app); theme_manager().select('dark')
    parent = QMainWindow(); parent.resize(1280,800); parent.show()
    sys.path.insert(0,str(ROOT/'tests'))
    from test_organogram import card_document
    card, provider = card_document(), None
    parent._fornax_asset_provider = provider
    settle(app)
    class PaintCounter(QObject):
        def __init__(self,target):
            super().__init__(target); self.paints=0; target.installEventFilter(self)
        def eventFilter(self,target,event):
            if event.type()==QEvent.Type.Paint: self.paints+=1
            return False
    def open_gallery():
        from itertools import count
        from uuid import UUID
        ids=count(1)
        with patch('core.organogram.uuid4',side_effect=lambda:UUID(int=next(ids))):
            dialog = module.StarterDialog(kind, parent, document=card if kind=='organogram' else None)
        dialog._benchmark_paint=PaintCounter(dialog.gallery.viewport())
        dialog.show(); settle(app)
        assert dialog._benchmark_paint.paints>0, 'A galeria ainda não foi pintada.'
        assert not errors, errors
        return dialog
    def capture(dialog):
        return [{'id':dialog.gallery.item(i).data(Qt.ItemDataRole.UserRole),
                 'title':dialog.gallery.item(i).text(),
                 'dimensions':dialog.gallery.item(i).data(module.TEMPLATE_DIMENSIONS_ROLE),
                 'pixels':sha256(bytes(dialog.gallery.item(i).icon().pixmap(320,232).toImage().constBits())).hexdigest()}
                for i in range(dialog.gallery.count())]
    def close(dialog):
        dialog.reject(); dialog.deleteLater(); settle(app)
    if not cold:
        for _ in range(2): close(open_gallery())
    samples=[]; states=[]; retained=[]
    for _ in range(1 if cold else 20):
        started=time.perf_counter(); dialog=open_gallery(); samples.append((time.perf_counter()-started)*1000)
        screen=dialog.screen().grabWindow(dialog.winId()).toImage()
        assert not screen.isNull()
        states.append({'items':capture(dialog), 'gallery_pixels':sha256(bytes(screen.constBits())).hexdigest()}); close(dialog)
        cache=getattr(parent,'_starter_preview_cache',None)
        retained.append(cache.pixels.retained_bytes if cache else 0)
        assert retained[-1]<=16*1024*1024
    with patch.object(module,'starter_thumbnail',wraps=module.starter_thumbnail) as render:
        dialog=open_gallery(); count=render.call_count; close(dialog)
    memory=[]
    for index in range(0 if cold else 20):
        close(open_gallery())
        if index in (0,9,19): memory.append({'cycle':index+1,'rss':rss_bytes()})
    cache=getattr(parent,'_starter_preview_cache',None)
    if cache: cache.clear()
    released=cache.pixels.retained_bytes if cache else 0
    parent.close(); parent.deleteLater(); settle(app)
    assert not errors, errors
    assert all(sample['rss'] is None or sample['rss']<2*1024**3 for sample in memory)
    metadata=environment()
    if reference:
        for name in ('starter_dialog.py','editor_window.py','organogram_editor.py'):
            metadata['product_sha256']['features/editor/'+name]=sha256((reference/'features/editor'/name).read_bytes()).hexdigest()
        metadata['product_sha256']['features/workspace/main_window.py']=sha256((reference/'features/workspace/main_window.py').read_bytes()).hexdigest()
    else:
        metadata['product_sha256']['features/workspace/main_window.py']=sha256((ROOT/'features/workspace/main_window.py').read_bytes()).hexdigest()
    metadata['reference']=str(reference) if reference else None
    result={'kind':kind,'cold':cold,'samples_ms':samples,'distribution':distribution(samples),
            'states':states,'generated_on_extra_warm_open':count,'retained_bytes':retained,
            'memory_cycles':memory,'bytes_after_clear':released,'environment':metadata}
    write_json(output,result)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',choices=['model','organogram']); parser.add_argument('--cold',action='store_true')
    parser.add_argument('--reference',type=Path)
    args=parser.parse_args()
    if args.worker: return worker(args.worker,args.cold,args.output,args.reference)
    args.output.mkdir(parents=True,exist_ok=True)
    for kind in ('model','organogram'):
        for mode in ['warm']+[f'cold-{i}' for i in range(5)]:
            target=args.output/f'{kind}-{mode}.json'; print(target.name,flush=True)
            with TemporaryDirectory(prefix='fornax-gallery10-') as temp:
                env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':temp+'/config',
                     'XDG_DATA_HOME':temp+'/data','XDG_CACHE_HOME':temp+'/cache'}
                command=[sys.executable,__file__,'--worker',kind,'--output',str(target)]+(['--cold'] if mode!='warm' else [])+(['--reference',str(args.reference)] if args.reference else [])
                with target.with_suffix('.log').open('w') as log:
                    subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)

if __name__=='__main__': main()
