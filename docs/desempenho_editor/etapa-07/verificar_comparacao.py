"""Audita instrumentos, fontes, patch, contratos e todas as amostras da etapa 07."""
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CHANGED = {'features/editor/editor_window.py', 'core/history_manager.py'}
ADDED = {'features/editor/history_capture.py'}


def read(name):
    return json.loads((OUT/name).read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    a, b = read('ambiente-antes.json'), read('ambiente-depois.json')
    assert a['harness_sha256'] == b['harness_sha256']
    for name, value in b['harness_sha256'].items():
        assert digest(ROOT/'tests/performance'/name) == value, name
    for name in ('platform', 'python', 'cpu_model', 'pyside6', 'qt', 'qt_platform',
                 'theme', 'locale', 'window_requested', 'warm_samples', 'warmups',
                 'workers_concurrent', 'benchmark'):
        assert a[name] == b[name], name
    old_hashes, new_hashes = a['product_sha256'], b['product_sha256']
    assert old_hashes.keys() <= new_hashes.keys()
    assert new_hashes.keys() - old_hashes.keys() == ADDED
    changed = {name for name, value in old_hashes.items() if new_hashes[name] != value}
    assert changed == CHANGED, changed
    for name, value in new_hashes.items():
        assert digest(ROOT/name) == value, name
    for name, value in read('contratos-antes.json').items():
        assert digest(ROOT/name) == value, name
    with TemporaryDirectory(prefix='fornax-history-audit-') as temporary:
        restored = Path(temporary)
        for name in CHANGED | ADDED:
            path = restored/name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, path)
        subprocess.run(['patch', '-p1', '-R', '--batch', '--directory', temporary,
                        '--input', str(OUT/'alteracoes-etapa-07.patch')],
                       check=True, capture_output=True)
        recovered = {name: digest(restored/name) for name in sorted(CHANGED)}
        assert all(value == old_hashes[name] for name, value in recovered.items())
        assert not any((restored/name).exists() for name in ADDED)
    (OUT/'verificacao-patch.json').write_text(json.dumps({
        'all_recovered_hashes_match': True, 'recovered_sha256': recovered,
        'added_files_removed_by_reverse_patch': sorted(ADDED),
    }, indent=2)+'\n')
    old = {v['scenario']['id']: v for v in read('antes.json')['results']}
    new = {v['scenario']['id']: v for v in read('depois.json')['results']}
    assert old.keys() == new.keys() and len(old) == 12
    results = []
    for name, before in old.items():
        after = new[name]
        assert before['status'] == after['status'] == 'ok', name
        for field in ('scenario', 'input_sha256', 'font', 'viewport'):
            assert before[field] == after[field], (name, field)
        assert len(before['samples_ms']) == len(after['samples_ms']) == 20
        assert len(before['states']) == len(after['states']) == 20
        for index, (x, y) in enumerate(zip(before['states'], after['states'])):
            assert x.keys() == y.keys(), (name, index)
            differences = [field for field in x if field != 'rss_bytes' and x[field] != y[field]]
            assert not differences, (name, index, differences)
        results.append({'scenario': name, 'before': before['summary'], 'after': after['summary'],
                        'profile_before': before['profile_counts'], 'profile_after': after['profile_counts'],
                        'median_reduction_percent': (1-after['summary']['median_ms']/before['summary']['median_ms'])*100})
    evidence = {}
    for theme in ('dark', 'light'):
        before, after = read(f'evidencia-antes-{theme}.json'), read(f'evidencia-depois-{theme}.json')
        assert before == after, (theme, [k for k in before if before[k] != after.get(k)])
        assert len(before) == 4
        evidence[theme] = len(before)
    counts = {'regressoes': 209, 'selection': 18, 'layer': 19, 'board': 13,
              'text': 13, 'copy': 15, 'paint': 11}
    for label in ('antes', 'depois'):
        for name, expected in counts.items():
            log = (OUT/('regressoes-'+label+'.log' if name == 'regressoes' else name+'-'+label+'.runner.log')).read_text()
            assert sum(map(int, re.findall(r'Ran (\d+) tests?', log))) == expected, (name, label)
            assert 'FAILED' not in log and 'Traceback (most recent call last)' not in log, (name, label)
        for theme in ('dark', 'light'):
            log = (OUT/f'history-{theme}-{label}.runner.log').read_text()
            expected = 15 if label == 'antes' else 17
            assert sum(map(int, re.findall(r'Ran (\d+) tests?', log))) == expected
            assert 'FAILED' not in log and 'Traceback (most recent call last)' not in log
    limits_before, limits_after = read('limites-antes.json'), read('limites-depois.json')
    for label, limits, environment in (('antes', limits_before, a), ('depois', limits_after, b)):
        assert limits['passed'] and limits['tests'] == 4
        assert limits['probe_sha256'] == digest(OUT/'verificar_limites.py')
        assert limits['source_sha256'] == environment['product_sha256']['core/history_manager.py']
        log = (OUT/f'limites-{label}.runner.log').read_text()
        assert 'FAILED' not in log and 'Traceback (most recent call last)' not in log
    assert json.dumps(limits_before['records'], sort_keys=True) == json.dumps(limits_after['records'], sort_keys=True)
    result = {'all_states_match': True, 'scenarios': 12, 'samples_per_version': 240,
              'history_evidence': evidence, 'limits_tests': 4,
              'tests_before': 317, 'tests_after': 319,
              'sources_and_harness_verified': True, 'results': results}
    (OUT/'verificacao-comparacao.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('OK: 12 cenários, 240 amostras por versão, 8 registros exatos; patch e fontes conferidos.')


if __name__ == '__main__':
    main()
