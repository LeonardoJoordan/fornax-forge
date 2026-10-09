"""Regressões isoladas por módulo; exceções de callbacks Qt também reprovam."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    'test_organogram', 'test_board_border_independence', 'test_board_connectors',
    'test_block_assignment', 'test_organogram_layers', 'test_organogram_preview',
    'test_organogram_history', 'test_scene_loading', 'test_editor_visual_cache',
    'test_editor_autosave', 'test_editor_pointer', 'test_placeholder_formatting',
    'test_text_fidelity', 'test_text_layout_crash', 'test_window_handoff',
    'test_signature_preview', 'test_starter_templates', 'test_tiled_export',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-contracts', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failures, total = [], 0
    modules = MODULES + (('test_editor_performance_contracts',) if args.include_contracts else ())
    with args.output.open('w', encoding='utf-8') as log:
        log.write('Qt offscreen; preferências e dados isolados; um processo por módulo.\n')
        for module in modules:
            command = [sys.executable, '-m', 'unittest', module, '-q']
            with TemporaryDirectory(prefix='fornax-regression-') as root:
                env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONPATH': str(ROOT/'tests'),
                       'XDG_CONFIG_HOME': root+'/config', 'XDG_DATA_HOME': root+'/data',
                       'XDG_CACHE_HOME': root+'/cache', 'APPDATA': root+'/config'}
                try:
                    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                    output = result.stdout + result.stderr
                    failed = result.returncode != 0 or 'Traceback (most recent call last)' in output
                    match = re.search(r'Ran (\d+) tests?', output)
                    total += int(match[1]) if match else 0
                    if not match:
                        failed = True
                except subprocess.TimeoutExpired:
                    output, failed = 'TIMEOUT: 180 segundos\n', True
            log.write('\nCOMANDO: '+' '.join(command)+'\n'+output+'RESULTADO: '+('FALHA' if failed else 'OK')+'\n')
            log.flush()
            print(module+': '+('FALHA' if failed else 'OK'), flush=True)
            if failed:
                failures.append(module)
        log.write(f'\nTOTAL: {total} testes; módulos com falha: {failures}\n')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
