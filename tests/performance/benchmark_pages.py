"""Cenas: processos isolados, 2 aquecimentos e 20 amostras; perfil separado."""
import argparse, cProfile, json, os, subprocess, sys, time, traceback
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from benchmark_editor import distribution, environment, rss_bytes, write_json
from page_cases import cases


def worker(case, samples, reference=None, progress_path=None):
    if reference:
        import features.editor
        features.editor.__path__ = [str(reference), *features.editor.__path__]
    from PySide6.QtWidgets import QApplication
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from features.editor.editor_window import EditorWindow
    from page_cases import PageSession, close_window
    from editor_scenarios import fingerprint
    app = QApplication([]); app.setQuitOnLastWindowClosed(False); app.setCursorFlashTime(0)
    install_ui_font(app); theme_manager().select('dark')
    errors = []; sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ,value,tb)))
    w = EditorWindow(); session = PageSession(w, case, app)
    timings, states, counts, edit_starts = [], [], [], []
    try:
        for index in range(samples + 3):
            session.prepare()
            if case.edit and 2 <= index < samples + 2:
                start_x = session.edit_box().x()
                assert start_x == session.initial_x
                edit_starts.append(start_x)
            profiler = cProfile.Profile() if index == samples + 2 else None
            if profiler: profiler.enable()
            started = time.perf_counter_ns(); session.perform(); elapsed = (time.perf_counter_ns()-started)/1e6
            if profiler:
                profiler.disable()
                for entry in profiler.getstats():
                    code = entry.code
                    if not isinstance(code,str) and (code.co_name in ('apply_scene_state','_insert_scene_items','_load_board_items','render_preview_image','_load_proxy_pixmap_bytes','_load_proxy_pixmap','_refresh_layer_rows') or code.co_qualname in ('DesignerBox.__init__','RectangleItem.__init__','ImageItem.__init__','SignatureItem.__init__','BoardGroupItem.__init__','BoardConnectorItem.__init__')):
                        counts.append({'function':code.co_qualname,'calls':entry.callcount})
            else:
                result = session.verify(); assert not errors, errors
                if index >= 2: timings.append(elapsed); states.append(result)
            if progress_path:
                write_json(progress_path,{'case':case.id,'sample':index,'elapsed_ms':elapsed,'phase':'samples'})
        memory = [rss_bytes()]
        pages = session.verify(all_pages=True)
        # 100 ciclos simples; 5 no maior caso; 20 nos demais, além das 46 trocas
        # de aquecimento/medição/verificação. Não há pausas artificiais.
        cycles=100 if case.id in ('duplex-20','board-5') else 5 if case.id=='duplex-200' else 20
        positions=[0]
        for done in range(0,cycles,20):
            batch=min(20,cycles-done)
            for _ in range(batch): session.prepare(); session.perform()
            memory.append(rss_bytes())
            positions.append(done+batch)
            if progress_path: write_json(progress_path,{'case':case.id,'phase':'memory','cycles':done+batch})
        assert not errors, errors
        assert all(value is None or value < 2 * 1024**3 for value in memory), memory
        cached = getattr(w, '_inactive_page_scene', None)
        return {'scenario':asdict(case),'status':'ok', 'input_sha256':fingerprint(session.document,session.provider),
                'summary':distribution(timings),'samples_ms':timings,'states':states,'final_all_pages':pages,'profile_counts':counts,
                'edit_start_x':edit_starts,
                'rss_after_0_20_40_60_80_100_cycles':memory,
                'rss_cycle_positions':positions,
                'retained_scenes':int(cached is not None),
                'retained_estimated_bytes':cached.estimated_bytes if cached is not None else 0,
                'font':app.font().key(),'viewport':[w.view.viewport().width(),w.view.viewport().height()]}
    finally: close_window(w, app)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--label',default='antes'); p.add_argument('--case'); p.add_argument('--worker',action='store_true'); p.add_argument('--samples',type=int,default=20)
    p.add_argument('--reference',type=Path)
    args=p.parse_args(); chosen=[c for c in cases() if not args.case or c.id==args.case]; assert chosen
    if args.worker:
        try: result=worker(chosen[0],args.samples,args.reference,args.output.with_suffix('.progress.json'))
        except Exception: result={'status':'error','error':traceback.format_exc()}
        write_json(args.output,result); return int(result['status']!='ok')
    args.output.mkdir(parents=True,exist_ok=True); metadata=environment(); metadata.update(benchmark='benchmark_pages.py',warm_samples=args.samples,cold_samples=0)
    write_json(args.output/f'ambiente-{args.label}.json',metadata); results=[]
    if args.reference:
        from hashlib import sha256
        for file in args.reference.glob('*.py'):
            metadata['product_sha256']['features/editor/'+file.name]=sha256(file.read_bytes()).hexdigest()
        metadata['reference_editor']=str(args.reference)
        write_json(args.output/f'ambiente-{args.label}.json',metadata)
    for case in chosen:
        print('INICIANDO '+case.id,flush=True); path=args.output/'raw'/args.label/(case.id+'.json')
        with TemporaryDirectory(prefix='fornax-pages-bench-') as root:
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':root+'/config','XDG_DATA_HOME':root+'/data','XDG_CACHE_HOME':root+'/cache','APPDATA':root+'/config'}
            command=[sys.executable,__file__,'--worker','--case',case.id,'--samples',str(args.samples),'--output',str(path)]
            if args.reference: command += ['--reference',str(args.reference)]
            run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
        path.parent.mkdir(parents=True,exist_ok=True); path.with_suffix('.log').write_text(run.stdout+run.stderr)
        result=json.loads(path.read_text()); results.append(result); write_json(args.output/(args.label+'.json'),{'results':results})
        print(case.id+' '+result['status']+' '+str(result.get('summary',{})),flush=True)
        if run.returncode: return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
