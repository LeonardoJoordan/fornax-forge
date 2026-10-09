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
from features.editor.canvas_items import SelectionTransformFrame
original_update = SelectionTransformFrame.update_bounds
def traced(frame,bounds):
 if frame.scene() and frame.scene().views():
  view=frame.scene().views()[0]
  print('FRAME', frame.rect(), '->', bounds, 'LEFT', frame.handles[-1].deviceTransform(view.viewportTransform()).mapRect(frame.handles[-1].boundingRect()),flush=True)
 original_update(frame,bounds)
 if frame.scene() and frame.scene().views():
  view=frame.scene().views()[0]
  print('LEFT AFTER',frame.handles[-1].deviceTransform(view.viewportTransform()).mapRect(frame.handles[-1].boundingRect()),flush=True)
SelectionTransformFrame.update_bounds=traced
class Watch(QObject):
 def eventFilter(self,source,event):
  if event.type()==QEvent.Type.Paint:print('PAINT',event.region().boundingRect(),'pieces',event.region().rectCount(),flush=True)
  return False
class Debug(PaintBehaviorTest):
 def record(self,w,key):
  if not hasattr(w,'watch'):
   w.watch=Watch(w.view.viewport());w.view.viewport().installEventFilter(w.watch)
  settle(app);a=screen_image(w,workspace=True)
  if key in ('page-select','page-move'):
   for item in w.scene.selectedItems():
    print('SELECTED',type(item).__name__,item.pos(),item.sceneBoundingRect(),flush=True)
    if hasattr(item,'resize_handles'):
     for name,h in item.resize_handles.items():print('HANDLE',name,h.isVisible(),h.rect(),h.sceneBoundingRect(),h.deviceTransform(w.view.viewportTransform()).mapRect(h.boundingRect()),flush=True)
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
