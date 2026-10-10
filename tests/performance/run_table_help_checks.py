"""Etapa 08: catálogo, artigos e traduções, em processos Qt isolados."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('test_help', 'test_table_help', 'test_table_i18n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    failures = []
    for scale in ('1', '2'):
        for module in MODULES:
            label = module + '-escala-' + scale
            with TemporaryDirectory(prefix='fornax-table-help-') as directory:
                env = {**os.environ, 'PYTHONPATH': str(ROOT / 'tests'),
                       'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale,
                       'XDG_CONFIG_HOME': directory + '/config',
                       'XDG_DATA_HOME': directory + '/data',
                       'XDG_CACHE_HOME': directory + '/cache',
                       'APPDATA': directory + '/config'}
                result = subprocess.run(
                    [sys.executable, '-X', 'faulthandler', '-m', 'unittest', module, '-v'],
                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=180)
                output = result.stdout + result.stderr
                (args.output / (label + '.log')).write_text(output, encoding='utf-8')
                count = re.search(r'Ran (\d+) tests?', output)
                failed = (result.returncode != 0 or not count
                          or 'Traceback (most recent call last)' in output)
                if failed:
                    failures.append(label)
                print(label + ': ' + ('FALHA' if failed else 'OK')
                      + (' (' + count[1] + ' testes)' if count else ''), flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
