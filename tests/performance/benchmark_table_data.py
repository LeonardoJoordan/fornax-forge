"""Etapa 02: custo dos dados; não mede pintura, interface ou geração em lote."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import resource
import statistics
import sys
from time import perf_counter
import tracemalloc
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def legacy_document():
    """Mesma entrada v4 com sessenta textos, inclusive na referência antiga."""
    boxes = [dict(object_id=f'text-{i}', x=(i % 6)*100, y=(i // 6)*30,
                  w=90, h=25, html=f'<p><b>Texto {i}</b>: {{nome}}</p>') for i in range(60)]
    return dict(schema_version=4, canvas_size={'w':800, 'h':600},
                target_w_mm=68, target_h_mm=51, placeholders=['nome'], pages=[dict(
                    page_id='front', field_ids=['nome'], boxes=boxes, images=[],
                    shapes=[], signatures=[], guidelines=[], background_path=None,
                    layer_order=[box['object_id'] for box in boxes])])


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def measure(operation, source):
    original = deepcopy(source)
    for _ in range(2):
        operation()
    samples = []
    for _ in range(20):
        started = perf_counter()
        operation()
        samples.append((perf_counter()-started)*1000)
    assert source == original, 'Medição alterou sua entrada'
    # Memória em rodada separada: tracemalloc não distorce as amostras de tempo.
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(samples_ms=samples, median_ms=statistics.median(samples),
                p95_ms=sorted(samples)[math.ceil(.95*len(samples))-1],
                peak_python_bytes=peak, input_sha256=fingerprint(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-source', type=Path)
    args = parser.parse_args()
    if args.reference_source:
        module = types.ModuleType('core.model_document')
        sys.modules[module.__name__] = module
        source = args.reference_source.read_text(encoding='utf-8')
        exec(compile(source, str(args.reference_source), 'exec'), module.__dict__)
    from core.model_document import normalize_model_document
    document = legacy_document()
    cases = {'normalizar-v4-60-textos': measure(lambda: normalize_model_document(document), document)}
    if not args.reference_source:
        from core.model_document import add_model_table
        from core.table_model import (new_table, validate_table, set_cell_html,
                                      insert_rows, merge_cells, split_cell)
        table = new_table(40,20,width=2400,height=4000)
        table['object_id'] = 'benchmark-table'
        for index, cell in enumerate(table['cells']):
            cell.update(id=f'benchmark-cell-{index}', html=f'<p><b>{{nome}}</b> — célula {index}</p>')
        validate_table(table)
        merged = merge_cells(table,0,0,1,1)
        v6 = add_model_table(document,table)
        tasks = (
            ('validar-800-celulas', lambda:validate_table(table),table),
            ('editar-uma-celula-em-800', lambda:set_cell_html(table,10,10,'<p>Novo {nome}</p>'),table),
            ('inserir-linha-em-800', lambda:insert_rows(table,20),table),
            ('mesclar-2x2-em-800', lambda:merge_cells(table,0,0,1,1),table),
            ('dividir-2x2-em-800', lambda:split_cell(merged,0,0),merged),
            ('normalizar-v6-800-celulas', lambda:normalize_model_document(v6),v6),
        )
        cases.update({name:measure(operation,source) for name,operation,source in tasks})
    sources = ['core/model_document.py','core/table_model.py','core/json_limits.py',
               'core/text_safety.py','tests/performance/benchmark_table_data.py']
    hashes = {name:sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    if args.reference_source:
        hashes['core/model_document.py'] = sha256(args.reference_source.read_bytes()).hexdigest()
    result = dict(python=sys.version,platform=platform.platform(),cases=cases,source_hashes=hashes,
                  reference_source=str(args.reference_source) if args.reference_source else None,
                  max_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  warmups=2,samples=20,note='Tempo síncrono de dados; sem Qt/pintura na rodada atual.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,values in cases.items():
        print(f'{name}: {values["median_ms"]:.3f} ms; p95 {values["p95_ms"]:.3f} ms')


if __name__ == '__main__':
    main()
