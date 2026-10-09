"""Histórico: 20 amostras aquecidas, processos isolados e perfil separado."""
import argparse,cProfile,json,os,subprocess,sys,time,traceback
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from benchmark_editor import distribution,environment,rss_bytes,write_json
from history_cases import cases

def worker(case,samples):
    from PySide6.QtWidgets import QApplication
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from features.editor.editor_window import EditorWindow
    from history_cases import HistorySession,settle,close_window
    from editor_scenarios import fingerprint
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setCursorFlashTime(0)
    install_ui_font(app);theme_manager().select('dark')
    errors=[];sys.excepthook=lambda typ,value,tb:errors.append(''.join(traceback.format_exception(typ,value,tb)))
    w=EditorWindow();session=HistorySession(w,case,app)
    timings=[];states=[];counts=[]
    try:
        for index in range(samples+3):
            if index:session.restore()
            profiler=cProfile.Profile() if index==samples+2 else None
            if profiler:profiler.enable()
            started=time.perf_counter_ns();session.perform();settle(app);elapsed=(time.perf_counter_ns()-started)/1e6
            if profiler:profiler.disable()
            result=session.verify();assert not errors,errors
            result={k:(sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest() if k in ('document','history') else v) for k,v in result.items()}
            result['rss_bytes']=rss_bytes()
            assert result['rss_bytes']<2*1024**3
            if profiler:
                for entry in profiler.getstats():
                    code=entry.code
                    if not isinstance(code,str) and (code.co_name in ('get_current_scene_state','_capture_document_history_state','_normalize_state_for_compare','deepcopy','dumps','push','history_inputs','_history_snapshot_is_current')):
                        counts.append({'function':code.co_qualname,'calls':entry.callcount})
            elif index>=2:timings.append(elapsed);states.append(result)
        return {'scenario':asdict(case),'status':'ok','input_sha256':fingerprint(session.document,session.provider),
                'summary':distribution(timings),'samples_ms':timings,'states':states,'profile_counts':counts,
                'font':app.font().key(),'viewport':[w.view.viewport().width(),w.view.viewport().height()]}
    finally:close_window(w,app)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--label',default='antes');p.add_argument('--case');p.add_argument('--worker',action='store_true');p.add_argument('--samples',type=int,default=20);args=p.parse_args()
    chosen=[c for c in cases() if not args.case or c.id==args.case];assert chosen
    if args.worker:
        try:result=worker(chosen[0],args.samples)
        except Exception:result={'scenario':asdict(chosen[0]),'status':'error','error':traceback.format_exc()}
        write_json(args.output,result);return int(result['status']!='ok')
    args.output.mkdir(parents=True,exist_ok=True);metadata=environment();metadata.update(benchmark='benchmark_history.py',warm_samples=args.samples);write_json(args.output/'ambiente.json',metadata)
    results=[]
    for case in chosen:
        print('INICIANDO '+case.id,flush=True);path=args.output/'raw'/args.label/(case.id+'.json')
        with TemporaryDirectory(prefix='fornax-history-bench-') as temporary:
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':temporary+'/config','XDG_DATA_HOME':temporary+'/data','XDG_CACHE_HOME':temporary+'/cache','APPDATA':temporary+'/config'}
            run=subprocess.run([sys.executable,__file__,'--worker','--case',case.id,'--samples',str(args.samples),'--output',str(path)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=240)
        path.parent.mkdir(parents=True,exist_ok=True);path.with_suffix('.log').write_text(run.stdout+run.stderr)
        result=json.loads(path.read_text());results.append(result);write_json(args.output/(args.label+'.json'),{'results':results})
        print(case.id+' '+result['status']+' '+str(result.get('summary',{})),flush=True)
        if run.returncode:return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
