"""Referência de processos existentes antes da implementação das tabelas.

Não mede o recurso futuro: reaproveita instrumentos sem alterar seu critério
de conclusão, com processos isolados e execução sequencial para evitar disputa
de CPU. Repetir com --label depois para verificar as operações antigas.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='antes')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    editor_cases = ('typography_type-60', 'typography_paste-60', 'copy_paste-10-60',
                    'copy_duplicate_group', 'page_cycles')
    commands = [
        ('pareto', ['tests/performance/benchmark_pareto.py', '--output',
                    str(args.output / 'pareto-medicoes'), '--label', args.label, '--samples', '5']),
        ('editor', ['tests/performance/benchmark_editor.py', '--output',
                    str(args.output / 'editor-medicoes'), '--label', args.label,
                    *(argument for case in editor_cases for argument in ('--case', case))]),
    ]
    commands.extend((case, ['tests/performance/benchmark_history.py', '--output',
                           str(args.output / 'historico' / case), '--label', args.label,
                           '--case', case, '--samples', '20'])
                    for case in ('snapshot-60', 'snapshot-after-undo', 'snapshot-move'))
    instruments = [Path(__file__).resolve(), *(ROOT / command[0] for _, command in commands),
                   ROOT / 'tests/performance/editor_scenarios.py',
                   ROOT / 'tests/performance/history_cases.py',
                   ROOT / 'tests/performance/table_fixtures.py']
    (args.output / f'instrumentos-{args.label}.json').write_text(json.dumps(
        {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
         for path in sorted(set(instruments))}, indent=2) + '\n')
    executions = []
    for name, arguments in commands:
        command = [sys.executable, *arguments]
        print('EXECUTANDO', name, flush=True)
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True,
                                     text=True, timeout=2400,
                                     env={**os.environ, 'QT_SCALE_FACTOR': '1',
                                          'PYTHONDONTWRITEBYTECODE': '1'})
            output, returncode = process.stdout + process.stderr, process.returncode
        except subprocess.TimeoutExpired:
            output, returncode = 'Timeout do conjunto de medições: 2400 segundos.\n', 124
        (args.output / f'{name}-{args.label}.runner.log').write_text(output)
        executions.append(dict(name=name, command=command, returncode=returncode))
        (args.output / f'execucoes-{args.label}.json').write_text(
            json.dumps(executions, ensure_ascii=False, indent=2) + '\n')
        print(output, end='' if output.endswith('\n') else '\n', flush=True)
        if returncode:
            return returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
