"""Audita as entradas e consolida resultados preservados; não executa benchmarks."""
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def index(data):
    return {r['scenario']['id']: r for r in data['results']}


def rss(result):
    return max((r.get('rss_bytes', 0) for r in result.get('memory_and_structure', result.get('states', []))), default=0)


def main():
    original = index(read(HERE.parent / 'etapa-00/antes.json'))
    corrected = index(read(HERE / 'referencia-corrigida/resultados.json'))
    final = index(read(HERE / 'final/resultados.json'))
    assert len(original) == len(final) == 43 and original.keys() == final.keys()
    initial = {**original, **corrected}
    rows = []
    for name, a in initial.items():
        b = final[name]
        assert a['status'] == b['status'] == 'ok'
        assert all(a[k] == b[k] for k in ('input_sha256', 'viewport', 'ui_font')), name
        assert a['summary']['sample_count'] == b['summary']['sample_count'], name
        med = (b['summary']['median_ms'] / a['summary']['median_ms'] - 1) * 100
        p95 = (b['summary']['p95_ms'] / a['summary']['p95_ms'] - 1) * 100
        rows.append({'id': name, 'baseline_source': 'referencia-corrigida' if name in corrected else 'etapa-00',
                     'before': a['summary'], 'after': b['summary'], 'median_change_percent': med,
                     'p95_change_percent': p95, 'rss_before_bytes': rss(a), 'rss_after_bytes': rss(b),
                     'input_sha256': a['input_sha256'], 'viewport': a['viewport'], 'font': a['ui_font']})
    write('comparacao-acumulada.json', {'cases': rows, 'median_worse': [r['id'] for r in rows if r['median_change_percent'] > 0],
                                      'p95_worse': [r['id'] for r in rows if r['p95_change_percent'] > 0]})
    lines = ['# Comparação acumulada — 43 cenários', '',
             'Valores em ms. Variação positiva significa mais lento; negativa, mais rápido.', '',
             '| Cenário | Mediana antes | Mediana final | Variação | P95 antes | P95 final | RSS máximo observado antes → final (MiB) |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['id']} | {r['before']['median_ms']:.2f} | {r['after']['median_ms']:.2f} | {r['median_change_percent']:+.1f}% | {r['before']['p95_ms']:.2f} | {r['after']['p95_ms']:.2f} | {r['rss_before_bytes']/2**20:.2f} → {r['rss_after_bytes']/2**20:.2f} |")
    lines += ['', 'RSS é memória corrente após cada operação, não pico. Diferenças de processos isolados',
              'também incluem alocador, bibliotecas e caches. Não se mede somente memória Python.',
              'Os dois casos `text_insert` usam a referência inicial recalibrada; os outros usam',
              'a referência preservada da etapa 00. `page_cycles` executa vinte idas e voltas',
              'por amostra. `drag_*` usa deslocamentos sequenciais, não um gesto coletivo nativo.',
              'As cinco recuperações são comparadas até a conclusão, não só até liberar a UI.', '']
    (HERE / 'COMPARACAO_ACUMULADA.md').write_text('\n'.join(lines))

    intermediate = []
    for stage in range(1, 10):
        folder = HERE.parent / f'etapa-{stage:02}'
        a, b = index(read(folder / 'antes.json')), index(read(folder / 'depois.json'))
        for name in sorted(a.keys() & b.keys()):
            changes = {key: (b[name]['summary'][key] / a[name]['summary'][key] - 1) * 100 for key in ('median_ms', 'p95_ms')}
            if any(v > 0 for v in changes.values()):
                intermediate.append({'stage': stage, 'id': name, 'before': a[name]['summary'], 'after': b[name]['summary'], 'changes_percent': changes})
    for r in read(HERE.parent / 'etapa-10/comparacao.json')['comparisons']:
        for temperature in ('warm', 'cold'):
            a, b = r[temperature + '_before'], r[temperature + '_after']
            changes = {key: (b[key] / a[key] - 1) * 100 for key in ('median_ms', 'p95_ms')}
            if any(v > 0 for v in changes.values()):
                intermediate.append({'stage': 10, 'id': r['kind'] + '-' + temperature, 'before': a, 'after': b, 'changes_percent': changes})
    write('pioras-intermediarias.json', intermediate)

    repeat_rows=[]
    for file in sorted((HERE/'repeticao-pioras/antes').glob('*.json')):
        a=read(file);b=read(HERE/'repeticao-pioras/depois'/file.name)
        assert a['status']==b['status']=='ok'
        assert all(a[k]==b[k] for k in ('scenario','input_sha256','viewport','ui_font'))
        assert a['summary']['sample_count']==b['summary']['sample_count']
        repeat_rows.append({'id':a['scenario']['id'],'before':a['summary'],'after':b['summary'],
                            'median_change_percent':(b['summary']['median_ms']/a['summary']['median_ms']-1)*100,
                            'p95_change_percent':(b['summary']['p95_ms']/a['summary']['p95_ms']-1)*100})
    assert len(repeat_rows)==4
    write('comparacao-repeticao-pioras.json',repeat_rows)

    recovery_before = index(read(HERE.parent / 'etapa-08/antes.json'))
    recovery_after = index(read(HERE / 'recuperacao/depois.json'))
    recovery = []
    for name, a in recovery_before.items():
        b = recovery_after[name]
        assert a['status'] == b['status'] == 'ok'
        assert all(a[k] == b[k] for k in ('input_sha256', 'font', 'viewport')), name
        # RSS é medição, não estado de documento.
        assert [{k:v for k,v in s.items() if k != 'rss_bytes'} for s in a['states']] == [{k:v for k,v in s.items() if k != 'rss_bytes'} for s in b['states']], name
        recovery.append({'id':name,'before_total':a['summary'],'after_total':b['summary'],
                         'before_ui_gap':a['ui_gap_summary'],'after_ui_gap':b['ui_gap_summary'],
                         'before_call':a['call_summary'],'after_call':b['call_summary'],
                         'writes_before':a['writes'],'writes_after':b['writes'],
                         'rss_before_bytes':rss(a),'rss_after_bytes':rss(b)})
    write('comparacao-recuperacao.json', recovery)

    a = read(HERE / 'fluxos-antes.json'); b = read(HERE / 'fluxos-depois.json')
    flow_rows = []
    assert len(a['journeys']) == len(b['journeys']) == 5
    for x, y in zip(a['journeys'], b['journeys']):
        assert (x['fixture'],x['mode']) == (y['fixture'],y['mode'])
        assert len(x['states']) == len(y['states'])
        for s, t in zip(x['states'], y['states']):
            assert all(s[k] == t[k] for k in ('label','document','render_pixels','history_index')), (x['fixture'],x['mode'],s['label'])
            flow_rows.append({'fixture':x['fixture'],'mode':x['mode'],'label':s['label'],
                              'document_equal':True,'render_pixels_equal':True,'history_index_equal':True,
                              'canvas_pixels_equal':s['canvas_pixels']==t['canvas_pixels']})
    assert not a['callback_errors'] and not b['callback_errors']
    write('comparacao-fluxos.json', flow_rows)

    meta = read(HERE / 'final/ambiente.json')
    old_meta = read(HERE.parent / 'etapa-00/ambiente.json')
    conditions = ('platform','python','cpu_model','pyside6','qt','qt_platform','theme','locale','window_requested','workers_concurrent')
    assert all(meta[k] == old_meta[k] for k in conditions)
    product = {name:sha256((ROOT/name).read_bytes()).hexdigest() for name in meta['product_sha256']}
    mismatches = [name for name in product if product[name] != meta['product_sha256'][name]]
    harness_mismatches = [name for name,digest in meta['harness_sha256'].items() if sha256((ROOT/'tests/performance'/name).read_bytes()).hexdigest()!=digest]
    assert not mismatches and not harness_mismatches, (mismatches,harness_mismatches)
    stage10 = read(HERE.parent / 'etapa-10/depois/model-warm.json')['environment']['product_sha256']
    stage10_mismatches = [name for name,digest in stage10.items() if sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    assert not stage10_mismatches, stage10_mismatches
    # O inventário amplo do driver legado não incluía a janela principal.
    product['features/workspace/main_window.py'] = sha256((ROOT/'features/workspace/main_window.py').read_bytes()).hexdigest()
    checks = read(HERE / 'checks/checks-depois.json')
    assert all(r['returncode']==0 for r in checks)
    write('verificacao-final.json', {'conditions_equal':list(conditions),'inputs_fonts_viewports_equal':43,
                                   'product_hash_mismatches':mismatches,'harness_hash_mismatches':harness_mismatches,
                                   'stage10_product_hash_mismatches':stage10_mismatches,
                                   'product_sha256':product,'regression_tests':sum(r['tests'] for r in checks),
                                   'gallery_tests':18,'flow_states':len(flow_rows),
                                   'final_samples':sum(r['after']['sample_count'] for r in rows),
                                   'recovery_samples':sum(len(r['writes_after']) for r in recovery),
                                   'repeat_samples_per_version':sum(r['after']['sample_count'] for r in repeat_rows),
                                   'native_validation':'pending'})
    print('43 cenários, 160 recuperações e fluxos auditados; identidades conferidas.')


if __name__ == '__main__':
    main()
