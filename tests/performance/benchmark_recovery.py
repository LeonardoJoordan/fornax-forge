"""Oito cenários aquecidos de recuperação, vinte amostras e latência da UI."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json,os,subprocess,sys,time,traceback
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from benchmark_editor import environment,distribution,write_json,rss_bytes
from recovery_cases import cases


def worker(case,samples):
    from PySide6.QtWidgets import QApplication
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from features.editor.editor_window import EditorWindow
    from recovery_cases import RecoverySession
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setCursorFlashTime(0);install_ui_font(app);theme_manager().select('dark')
    errors=[];sys.excepthook=lambda typ,value,tb:errors.append(''.join(traceback.format_exception(typ,value,tb)))
    times=[];states=[]
    with TemporaryDirectory(prefix='fornax-recovery-case-') as root:
        session=RecoverySession(EditorWindow(),case,app,root)
        try:
            for index in range(samples+2):
                if index:session.restore()
                timing=session.perform();state=session.verify();assert not errors,errors
                state={k:(sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest() if k in ('document','saved','history') else v) for k,v in state.items()}
                state['rss_bytes']=rss_bytes();assert state['rss_bytes']<2*1024**3
                if index>=2:times.append(timing);states.append(state)
            return {'scenario':asdict(case),'status':'ok','input_sha256':session.input_sha256,
                    'font':app.font().key(),'viewport':[session.window.view.viewport().width(),session.window.view.viewport().height()],
                    'samples':times,'states':states,'summary':distribution([t['total_ms'] for t in times]),
                    'call_summary':distribution([sum(t['call_ms']) for t in times]),
                    'ui_gap_summary':distribution([t['max_ui_gap_ms'] for t in times]),
                    'writes':[t['effective_writes'] for t in times]}
        finally:session.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--label',default='antes');parser.add_argument('--case');parser.add_argument('--samples',type=int,default=20);parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    chosen=[c for c in cases() if not args.case or c.id==args.case];assert chosen
    if args.worker:
        try:result=worker(chosen[0],args.samples)
        except Exception:result={'scenario':asdict(chosen[0]),'status':'error','error':traceback.format_exc()}
        write_json(args.output,result);return int(result['status']!='ok')
    args.output.mkdir(parents=True,exist_ok=True);meta=environment();meta.update(benchmark='benchmark_recovery.py',warm_samples=args.samples,cold_samples=0,ui_wait='QEventLoop',memory_measurement='current RSS after each recovery, not peak',asset_comparison='SHA-256 references and multiset');write_json(args.output/'ambiente.json',meta)
    results=[]
    for case in chosen:
        print('INICIANDO '+case.id,flush=True);path=args.output/'raw'/args.label/(case.id+'.json')
        with TemporaryDirectory(prefix='fornax-recovery-bench-') as root:
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':root+'/config','XDG_DATA_HOME':root+'/data','XDG_CACHE_HOME':root+'/cache','APPDATA':root+'/config'}
            result=subprocess.run([sys.executable,__file__,'--worker','--case',case.id,'--samples',str(args.samples),'--output',str(path)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=300)
        path.with_suffix('.log').write_text(result.stdout+result.stderr)
        data=json.loads(path.read_text());results.append(data);write_json(args.output/(args.label+'.json'),{'results':results})
        print(case.id+' '+data['status']+' '+str(data.get('summary')),flush=True)
        if result.returncode:return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
