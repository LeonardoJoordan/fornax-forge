import os,sys,json
from pathlib import Path
from tempfile import TemporaryDirectory
root=TemporaryDirectory();os.environ.update(QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=root.name+'/config',XDG_DATA_HOME=root.name+'/data',XDG_CACHE_HOME=root.name+'/cache')
repo=Path('/home/leonardo/Desenvolvimento/fornax-forge');sys.path[:0]=[str(repo),str(repo/'tests'),str(repo/'tests/performance')]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF,QEvent,QObject
from paint_cases import settle,screen_image,image_hash
from test_editor_paint_updates import PaintBehaviorTest
from core.themes import theme_manager
app=QApplication([]);app.setCursorFlashTime(0);theme_manager().select('dark')
out=repo/'docs/desempenho_editor/etapa-06/diagnostico-invalidação'
class Debug(PaintBehaviorTest):
 def record(self,w,key):
  settle(app);a=screen_image(w,workspace=True)
  w.view.viewport().update();w.ruler_workspace.top.update();w.ruler_workspace.left.update();settle(app);b=screen_image(w,workspace=True)
  av=memoryview(a.constBits()).cast('I');bv=memoryview(b.constBits()).cast('I');stride=a.bytesPerLine()//4
  points=[(i%stride,i//stride,av[i],bv[i]) for i in range(len(av)) if av[i]!=bv[i]]
  print(key,'diff',len(points), 'bounds',(min((x for x,y,a,b in points),default=0),min((y for x,y,a,b in points),default=0),max((x for x,y,a,b in points),default=0),max((y for x,y,a,b in points),default=0)), 'pixels',points[:10],flush=True)
  if points:
   a.save(str(out/(key+'-partial.png')));b.save(str(out/(key+'-full.png')))
  w._document_with_active_page()
Debug.setUpClass();test=Debug('test_page_movement_resize_rotation_visibility_delete_and_history');test.setUp()
try:test.test_page_movement_resize_rotation_visibility_delete_and_history()
finally:test.doCleanups()
