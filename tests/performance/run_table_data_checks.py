"""Etapa 02: dados/persistência e regressões complementares, em processos isolados."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('test_table_model', 'test_table_persistence', 'test_table_layout_prototype',
           'test_recovery_package_publication')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total, failures = 0, []
    with args.output.open('w', encoding='utf-8') as log:
        for module in MODULES:
            with TemporaryDirectory(prefix='fornax-table-checks-') as directory:
                env = {**os.environ, 'PYTHONPATH':str(ROOT/'tests'),
                       'QT_QPA_PLATFORM':'offscreen', 'QT_SCALE_FACTOR':'1',
                       'XDG_DATA_HOME':directory+'/data', 'XDG_CONFIG_HOME':directory+'/config',
                       'XDG_CACHE_HOME':directory+'/cache', 'APPDATA':directory+'/config'}
                command = [sys.executable, '-m', 'unittest', module, '-v']
                result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                output = result.stdout+result.stderr
                match = re.search(r'Ran (\d+) tests?', output)
                total += int(match[1]) if match else 0
                failed = result.returncode != 0 or 'Traceback (most recent call last)' in output or not match
                if failed:
                    failures.append(module)
                log.write('COMANDO: '+' '.join(command)+'\n'+output+'\n')
                log.flush()
                print(module+': '+('FALHA' if failed else 'OK'), flush=True)
        log.write(f'TOTAL: {total} testes; módulos com falha: {failures}\n')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
