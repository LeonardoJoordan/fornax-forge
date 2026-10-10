"""Etapa 06: integração em temas claro/escuro, escalas 1/2, Qt isolado."""
import argparse,os,re,subprocess,sys
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);failures=[]
    for theme in ('dark','light'):
        for scale in ('1','2'):
            label=theme+'-escala-'+scale
            with TemporaryDirectory(prefix='fornax-integration-') as directory:
                env={**os.environ,'PYTHONPATH':str(ROOT/'tests'),'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale,
                     'FORNAX_TEST_THEME':theme,'XDG_CONFIG_HOME':directory+'/config','XDG_DATA_HOME':directory+'/data',
                     'XDG_CACHE_HOME':directory+'/cache','APPDATA':directory+'/config'}
                result=subprocess.run([sys.executable,'-X','faulthandler','-m','unittest','test_table_integration','-v'],
                    cwd=ROOT,env=env,text=True,capture_output=True,timeout=180)
                output=result.stdout+result.stderr;(args.output/(label+'.log')).write_text(output,encoding='utf-8')
                count=re.search(r'Ran (\d+) tests?',output)
                failed=result.returncode or not count or 'Traceback (most recent call last)' in output
                if failed:failures.append(label)
                print(label+': '+('FALHA' if failed else 'OK')+(' ('+count[1]+' testes)' if count else ''),flush=True)
    return int(bool(failures))
if __name__=='__main__':raise SystemExit(main())
