"""Contratos da rodada Pareto, com um processo e preferências temporárias por módulo."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('test_editor_visual_cache', 'test_scene_loading', 'test_editor_page_scenes',
           'test_board_connectors', 'test_editor_board_updates', 'test_recovery_package_publication',
           'test_editor_recovery_concurrency', 'test_editor_recovery_updates', 'test_editor_recovery_shutdown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--module', action='append')
    args = parser.parse_args()
    modules = args.module or (MODULES if args.baseline else (*MODULES, 'test_pareto_optimizations'))
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for module in modules:
        with TemporaryDirectory(prefix='fornax-pareto-check-') as temporary:
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTHONPATH': os.pathsep.join((str(ROOT/'tests'), str(ROOT/'tests/performance'))),
                   'XDG_CONFIG_HOME': temporary+'/config', 'XDG_DATA_HOME': temporary+'/data',
                   'XDG_CACHE_HOME': temporary+'/cache'}
            try:
                process = subprocess.run([sys.executable, '-m', 'unittest', module, '-q'],
                                         cwd=ROOT, env=env, text=True, capture_output=True, timeout=300)
                output = process.stdout + process.stderr
                match = re.search(r'Ran (\d+) tests?', output)
                passed = process.returncode == 0 and match is not None and 'Traceback (most recent call last)' not in output
                count = int(match[1]) if match else 0
            except subprocess.TimeoutExpired:
                output, passed, count = 'TIMEOUT: 300 segundos\n', False, 0
        (args.output/(module+'.log')).write_text(output)
        results.append({'module': module, 'tests': count, 'passed': passed})
        (args.output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
        print(module, results[-1], flush=True)
        if not passed: return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
