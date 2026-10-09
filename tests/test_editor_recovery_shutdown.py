"""A real Qt application exit cancels and drains native recovery threads."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]


class RecoveryShutdownTest(unittest.TestCase):
    def test_quit_while_protected_recovery_waits_for_publication(self):
        script=''' 
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from core.fornax_container import FULL_MODE, save_protected_fornax
from core.fornax_session import FornaxSessionManager
from core.model_document import normalize_model_document
from features.editor.recovery_worker import RecoveryTask,RecoveryWorker,_LIVE_WORKERS
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
reached=threading.Event();original=RecoveryWorker.dispatch_commit
def waiting(worker,action):
    reached.set()
    return original(worker,action)
RecoveryWorker.dispatch_commit=waiting
with TemporaryDirectory() as root:
    source=Path(root)/'protected.fornax';destination=Path(root)/'recovery.fornax'
    document=normalize_model_document({'name':'Teste','canvas_size':{'w':300,'h':300},'boxes':[]})
    save_protected_fornax(document,source,'senha-teste',mode=FULL_MODE)
    sessions=FornaxSessionManager();sessions.unlock(source,'senha-teste')
    document=sessions.document();document['name']='Nova revisão'
    task=RecoveryTask.capture(document,lambda ref: sessions.asset(ref),sessions.prepare_recovery(source),destination,0,None)
    worker=RecoveryWorker(task);worker.start()
    timer=QTimer();timer.setInterval(2);timer.timeout.connect(lambda: app.quit() if reached.is_set() else None);timer.start()
    QTimer.singleShot(8000,app.quit)
    app.exec()
    assert reached.is_set(), 'Não chegou à etapa de publicação'
    assert not _LIVE_WORKERS and worker.isFinished(), 'Thread ainda em execução no fim do aplicativo'
    assert not task.document and not task.assets and task.authorization._key is None
    assert not destination.exists()
    assert not list(Path(root).glob('*.pending-*'))
    sessions.close()
''' 
        with TemporaryDirectory(prefix='fornax-recovery-shutdown-') as root:
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','PYTHONPATH':str(ROOT/'tests'),
                 'XDG_CONFIG_HOME':root+'/config','XDG_DATA_HOME':root+'/data','XDG_CACHE_HOME':root+'/cache'}
            result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('Traceback',result.stderr)
        self.assertNotIn('Destroyed while thread',result.stderr)

if __name__=='__main__':unittest.main()
