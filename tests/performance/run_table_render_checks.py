"""Etapa 03: renderer em duas escalas, preferências temporárias e logs locais."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    failed=[]
    for scale in ('1','2'):
        with TemporaryDirectory(prefix='fornax-table-render-checks-') as directory:
            env={**os.environ,'PYTHONPATH':str(ROOT/'tests'),'QT_QPA_PLATFORM':'offscreen',
                 'QT_SCALE_FACTOR':scale,'XDG_CONFIG_HOME':directory+'/config',
                 'XDG_DATA_HOME':directory+'/data','XDG_CACHE_HOME':directory+'/cache'}
            result=subprocess.run([sys.executable,'-m','unittest','test_table_rendering','-v'],
                                  cwd=ROOT,env=env,text=True,capture_output=True,timeout=180)
            output=result.stdout+result.stderr
            (args.output/('renderer-escala-'+scale+'.log')).write_text(output,encoding='utf-8')
            if result.returncode or 'Traceback (most recent call last)' in output:failed.append(scale)
            print('Escala '+scale+': '+('FALHA' if scale in failed else 'OK'),flush=True)
    return int(bool(failed))


if __name__=='__main__':raise SystemExit(main())
