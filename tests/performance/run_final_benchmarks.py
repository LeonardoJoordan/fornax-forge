"""Repete os 43 cenários iniciais no produto final e recupera referências corrigidas."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from benchmark_editor import environment,write_json
from editor_scenarios import scenarios
from hashlib import sha256


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--diagnostic',action='store_true');args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    initial=json.loads((ROOT/'docs/desempenho_editor/etapa-00/antes.json').read_text())['results']
    ids={entry['scenario']['id'] for entry in initial}
    if args.reference:ids={'text_insert-60','text_insert-1200'}
    cases=[case for case in scenarios() if case.id in ids]
    if args.diagnostic:cases=[case for case in cases if case.id in ('text_insert-60','autosave-public-small','gallery-organogram-warm','page_cycles')]
    meta=environment()
    if args.reference:
        for name in list(meta['product_sha256']):
            file=args.reference/name
            if file.is_file():meta['product_sha256'][name]=sha256(file.read_bytes()).hexdigest()
        meta['baseline_source']=str(args.reference)
    write_json(args.output/'ambiente.json',meta)
    results=[]
    for case in cases:
        print('INICIANDO',case.id,flush=True)
        path=args.output/'raw'/(case.id+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='fornax-final-bench-') as temp:
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':temp+'/config','XDG_DATA_HOME':temp+'/data','XDG_CACHE_HOME':temp+'/cache'}
            if args.reference:
                overlay=Path(temp)/'sitecustomize.py'
                overlay.write_text('import sys\nsys.path.insert(0,'+repr(str(args.reference))+')\nimport core,features\ncore.__path__=['+repr(str(args.reference/'core'))+']\nfeatures.__path__=['+repr(str(args.reference/'features'))+']\n')
                env['PYTHONPATH']=temp
            command=[sys.executable,'tests/performance/benchmark_editor.py','--worker','--case',case.id,'--output',str(path)]+(['--samples','1'] if args.diagnostic else [])
            with path.with_suffix('.log').open('w') as stream:
                run=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=2400)
        result=json.loads(path.read_text()) if path.exists() else {'scenario':{'id':case.id},'status':'error'}
        result['returncode']=run.returncode;results.append(result)
        write_json(args.output/'resultados.json',{'diagnostic':args.diagnostic,'results':results})
        print(case.id,result['status'],result.get('summary',{}).get('median_ms'),flush=True)
        if run.returncode:raise SystemExit(run.returncode)

if __name__=='__main__':main()
