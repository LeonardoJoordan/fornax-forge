import subprocess,sys,json,os,re
from pathlib import Path
import argparse
p=argparse.ArgumentParser(description='Regressões das etapas 00 a 09; referência opcional por overlay de módulos.')
p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--label',default='depois');args=p.parse_args()
root=Path(__file__).resolve().parents[2];out=args.output;out.mkdir(parents=True,exist_ok=True);label=args.label;py=sys.executable;reference=str(args.reference) if args.reference else None
commands=[('regressoes',[py,'tests/performance/run_regressions.py','--include-contracts','--output',str(out/f'regressoes-{label}.log')])]
commands += [(kind,[py,f'tests/performance/run_{kind}_checks.py']) for kind in ('selection','layer','board','text','copy','paint','history')]
commands += [('limites',[py,'docs/desempenho_editor/etapa-07/verificar_limites.py','--output',str(out/f'limites-{label}.json')])]
commands += [('recovery',[py,'tests/performance/run_recovery_checks.py']),('recovery-concurrency',[py,'tests/performance/run_recovery_checks.py','--concurrency'])]
commands += [('publication',[py,'-m','unittest','test_recovery_package_publication','-q']),('shutdown',[py,'-m','unittest','test_editor_recovery_shutdown','-q'])]
commands += [('pages',[py,'tests/performance/run_page_checks.py']+(['--reuse'] if label=='depois' else []))]
results=[]
# sitecustomize opera antes dos imports também nos subprocessos de regressão.
if reference:
 overlay=Path(__import__('tempfile').mkdtemp(prefix='fornax-page-overlay-'))
 (overlay/'sitecustomize.py').write_text("import sys\nsys.path.insert(0,"+repr(str(root))+")\nimport features.editor\nfeatures.editor.__path__ = ["+repr(reference)+", *features.editor.__path__]\n")
else:overlay=None
for name,command in commands:
 print(name,flush=True)
 env={**os.environ,'QT_QPA_PLATFORM':'offscreen','PYTHONPATH':os.pathsep.join([str(root/'tests'),str(root/'tests/performance')]+([str(overlay)] if overlay else [])),'XDG_CONFIG_HOME':f'/tmp/fornax-etapa09-{label}/config','XDG_DATA_HOME':f'/tmp/fornax-etapa09-{label}/data','XDG_CACHE_HOME':f'/tmp/fornax-etapa09-{label}/cache'}
 with (out/f'{name}-{label}.runner.log').open('w') as stream:
  result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
 output=(out/f'{name}-{label}.runner.log').read_text()
 count=sum(map(int,re.findall(r'Ran (\d+) tests?',output)))
 if name=='regressoes':count=int(re.search(r'TOTAL: (\d+)',(out/f'regressoes-{label}.log').read_text()).group(1))
 if name=='limites':count=4
 results.append({'name':name,'returncode':result.returncode,'tests':count,'command':command});(out/f'checks-{label}.json').write_text(json.dumps(results,indent=2))
 if result.returncode or 'Error in sitecustomize' in output:raise SystemExit(result.returncode or 1)
