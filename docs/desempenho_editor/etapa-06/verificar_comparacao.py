"""Auditoria dos 15 cenários e das quatro referências visuais da etapa 06."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CHANGED = {'features/editor/controls.py', 'features/editor/rulers.py',
           'features/editor/organogram_editor.py', 'features/editor/canvas_items.py'}


def read(name):
    return json.loads((OUT/name).read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    a, b = read('ambiente-antes.json'), read('ambiente-depois.json')
    assert a['harness_sha256'] == b['harness_sha256']
    for name, expected in b['harness_sha256'].items():
        assert digest(ROOT/'tests/performance'/name) == expected, name
    for name in ('platform', 'python', 'cpu_model', 'pyside6', 'qt', 'qt_platform',
                 'theme', 'locale', 'window_requested', 'warm_samples', 'warmups',
                 'workers_concurrent', 'scale_factor', 'benchmark'):
        assert a[name] == b[name], name
    changed = {name for name, value in a['product_sha256'].items() if b['product_sha256'][name] != value}
    assert changed == CHANGED, changed
    for name, value in b['product_sha256'].items():
        assert digest(ROOT/name) == value, name
    for name, value in read('contratos-antes.json').items():
        assert digest(ROOT/name) == value, name
    with TemporaryDirectory(prefix='fornax-paint-audit-') as temporary:
        restored = Path(temporary)
        for name in changed:
            path = restored/name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, path)
        subprocess.run(['patch', '-p1', '-R', '--batch', '--directory', temporary,
                        '--input', str(OUT/'alteracoes-etapa-06.patch')],
                       check=True, capture_output=True)
        recovered = {name: digest(restored/name) for name in sorted(changed)}
        assert all(value == a['product_sha256'][name] for name, value in recovered.items())
    (OUT/'verificacao-patch.json').write_text(json.dumps({'all_recovered_hashes_match': True,
                                                       'recovered_sha256': recovered}, indent=2)+'\n')
    old = {v['scenario']['id']: v for v in read('antes.json')['results']}
    new = {v['scenario']['id']: v for v in read('depois.json')['results']}
    assert old.keys() == new.keys() and len(old) == 15
    fields = ('pixels_sha256', 'image_size', 'scene_items', 'selected_items',
              'scroll', 'transform', 'document_sha256', 'viewport_area')
    results = []
    for name, before in old.items():
        after = new[name]
        assert before['status'] == after['status'] == 'ok', name
        for field in ('scenario', 'input_sha256', 'ui_font', 'viewport', 'completion'):
            assert before[field] == after[field], (name, field)
        assert len(before['samples_ms']) == len(after['samples_ms']) == 20
        assert len(before['states']) == len(after['states']) == 20
        for index, (x, y) in enumerate(zip(before['states'], after['states'])):
            differences = [f for f in fields if x[f] != y[f]]
            assert not differences, (name, index, differences)
        results.append({'scenario': name, 'before': before['summary'], 'after': after['summary'],
                        'paint_before': before['paint_summary'], 'paint_after': after['paint_summary'],
                        'median_reduction_percent': (1 - after['summary']['median_ms']/before['summary']['median_ms'])*100})
    states = {}
    for theme in ('dark', 'light'):
        for scale in ('1', '2'):
            before, after = read(f'evidencia-antes-{theme}-{scale}.json'), read(f'evidencia-depois-{theme}-{scale}.json')
            assert before == after, (theme, scale, [k for k in before if before[k] != after.get(k)])
            assert len(before) == 38
            states[theme+'-'+scale] = len(before)
    extra_before, extra_after = read('selecoes-antes.json'), read('selecoes-depois.json')
    assert extra_before == extra_after and len(extra_before) == 14
    old_modules, new_modules = read('selecoes-antes.modules.json'), read('selecoes-depois.modules.json')
    assert old_modules['probe_sha256'] == new_modules['probe_sha256'] == digest(OUT/'verificar_selecoes.py')
    for provenance, environment in ((old_modules, a), (new_modules, b)):
        assert provenance['passed'] and provenance['tests'] == 4
        for name, module in provenance['modules'].items():
            assert module['sha256'] == environment['product_sha256']['features/editor/'+name+'.py']
    import re
    expected = {'regressoes': 209, 'selection': 18, 'layer': 19, 'board': 13, 'text': 13, 'copy': 15}
    for label in ('antes', 'depois'):
        for name, count in expected.items():
            log = (OUT/('regressoes-'+label+'.log' if name == 'regressoes' else name+'-'+label+'.runner.log')).read_text()
            total = sum(map(int, re.findall(r'Ran (\d+) tests?', log)))
            assert total == count and 'FAILED' not in log and 'Traceback' not in log, (name, label)
        for theme in ('dark', 'light'):
            for scale in ('1', '2'):
                log = (OUT/f'paint-{theme}-{scale}-{label}.runner.log').read_text()
                assert re.findall(r'Ran (\d+) tests?', log) == ['6' if label == 'antes' else '11']
                assert 'FAILED' not in log and 'Traceback' not in log
    value = {'all_checks_passed': True, 'scenarios': 15, 'samples_per_version': 300,
             'state_fields_identical': list(fields), 'states_per_theme_scale': states,
             'additional_selection_states': 14, 'additional_probe_hash_identical': True,
             'distinct_tests_before': 297, 'distinct_tests_after': 302,
             'harness_hashes_identical': True, 'product_changed': sorted(changed),
             'results': results}
    (OUT/'verificacao-comparacao.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    print('15 cenários, 300 amostras por versão, 166 registros visuais, 302 testes finais e hashes conferidos.')


if __name__ == '__main__':
    main()
