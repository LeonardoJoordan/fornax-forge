import json,os,subprocess,sys
from pathlib import Path
from tempfile import TemporaryDirectory
root=Path(__file__).resolve().parents[3];out=root/'docs/desempenho_editor/etapa-11';reference=Path(json.loads((out/'reconstrucao-referencia.json').read_text())['reference'])
sys.path[:0]=[str(root),str(root/'tests/performance')]
from benchmark_editor import environment,write_json
from hashlib import sha256
meta=environment();before=json.loads(json.dumps(meta))
for name in before['product_sha256']:
 file=reference/name
 if file.is_file():before['product_sha256'][name]=sha256(file.read_bytes()).hexdigest()
write_json(out/'repeticao-pioras'/'ambiente-antes.json',before)
write_json(out/'repeticao-pioras'/'ambiente-depois.json',meta)
for case in ['drag_one-100' ,'paint_far-400','paint_far-2500','gallery-model-cold']:
 for version in ['antes','depois']:
  target=out/'repeticao-pioras'/version/(case+'.json');target.parent.mkdir(parents=True,exist_ok=True)
  with TemporaryDirectory(prefix='fornax-repeat-') as temp:
   env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':'1','XDG_CONFIG_HOME':temp+'/config','XDG_DATA_HOME':temp+'/data','XDG_CACHE_HOME':temp+'/cache'}
   if version=='antes':
    (Path(temp)/'sitecustomize.py').write_text('import sys\nsys.path.insert(0,'+repr(str(reference))+')\nimport core,features\ncore.__path__=['+repr(str(reference/'core'))+']\nfeatures.__path__=['+repr(str(reference/'features'))+']\n')
    env['PYTHONPATH']=temp
   command=[sys.executable,'tests/performance/benchmark_editor.py','--worker','--case',case,'--output',str(target)]
   print(case,version,flush=True)
   with target.with_suffix('.log').open('w') as stream:run=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
   if run.returncode:raise SystemExit(run.returncode)
   data=json.loads(target.read_text());print(data['status'],data['summary']['median_ms'],flush=True)
