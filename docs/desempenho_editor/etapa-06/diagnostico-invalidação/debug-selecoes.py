import os,sys,runpy
from pathlib import Path
repo=Path('/home/leonardo/Desenvolvimento/fornax-forge');sys.path[:0]=[str(repo),str(repo/'tests'),str(repo/'tests/performance')]
from PySide6.QtCore import QEvent,QObject
from paint_cases import settle,screen_image
from test_editor_paint_updates import PaintBehaviorTest
out=repo/'docs/desempenho_editor/etapa-06/diagnostico-invalidação'
original=PaintBehaviorTest.record
class Watch(QObject):
 def eventFilter(self,source,event):
  if event.type()==QEvent.Type.Paint:print('PAINT',event.region().boundingRect(),flush=True)
  return False
def record(self,w,key):
 if not hasattr(w,'paint_watch'):
  w.paint_watch=Watch(w.view.viewport());w.view.viewport().installEventFilter(w.paint_watch)
 settle(self.app);a=screen_image(w,workspace=True)
 w.view.viewport().update();w.ruler_workspace.top.update();w.ruler_workspace.left.update();settle(self.app);b=screen_image(w,workspace=True)
 av=memoryview(a.constBits()).cast('I');bv=memoryview(b.constBits()).cast('I');stride=a.bytesPerLine()//4
 points=[(i%stride,i//stride,av[i],bv[i]) for i in range(len(av)) if av[i]!=bv[i]]
 print(key,'diff',len(points),'bbox',(min((p[0] for p in points),default=0),min((p[1] for p in points),default=0),max((p[0] for p in points),default=0),max((p[1] for p in points),default=0)),'pixels',points[:10],flush=True)
 if key.startswith('multi'):
  frame=w._selection_frame
  print('FRAME',frame.rect(),frame.isVisible(),flush=True)
  for h in frame.handles:print('HANDLE',h.pos(),h.isVisible(),h.deviceTransform(w.view.viewportTransform()).mapRect(h.boundingRect()),flush=True)
 if points:a.save(str(out/(key+'-partial.png')));b.save(str(out/(key+'-full.png')))
 return original(self,w,key)
PaintBehaviorTest.record=record
sys.argv=[str(out.parent/'verificar_selecoes.py'),'--output','/tmp/selecoes-debug.json']
runpy.run_path(sys.argv[0],run_name='__main__')
