"""Confere igualdade das 160 amostras e produz a tabela da etapa 09."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('folder',type=Path);args=p.parse_args()
before=json.loads((args.folder/'antes.json').read_text())['results']
after=json.loads((args.folder/'depois.json').read_text())['results']
assert len(before)==len(after)==8
results=[];failures=[];lines=['| Cenário (ida e volta) | Antes, mediana / p95 (ms) | Depois, mediana / p95 (ms) | Redução da mediana |','|---|---:|---:|---:|']
for first,last in zip(before,after):
    identity=first['scenario']['id'];assert first['scenario']==last['scenario']
    assert first['status']==last['status']=='ok'
    assert first['input_sha256']==last['input_sha256']
    assert first['font']==last['font'] and first['viewport']==last['viewport']
    assert len(first['states'])==len(last['states'])==20
    if first['scenario']['edit']:
        assert first['edit_start_x']==last['edit_start_x']
        assert len(first['edit_start_x'])==20 and len(set(first['edit_start_x']))==1
    differences=[{'sample':index,'keys':[key for key in one if one[key]!=two[key]]}
                 for index,(one,two) in enumerate(zip(first['states'],last['states'])) if one!=two]
    if first['final_all_pages']!=last['final_all_pages']:
        differences.append({'sample':'final_all_pages','keys':[key for key in first['final_all_pages'] if first['final_all_pages'][key]!=last['final_all_pages'][key]]})
    if differences:failures.append({'id':identity,'differences':differences})
    a,b=first['summary'],last['summary'];reduction=100*(1-b['median_ms']/a['median_ms'])
    lines.append(f"| {identity} | {a['median_ms']:.2f} / {a['p95_ms']:.2f} | {b['median_ms']:.2f} / {b['p95_ms']:.2f} | {reduction:.1f}% |")
    results.append({'id':identity,'reduction_percent':reduction,'equal_samples':not differences,'before_counts':first['profile_counts'],'after_counts':last['profile_counts'],'before_rss':first['rss_after_0_20_40_60_80_100_cycles'],'after_rss':last['rss_after_0_20_40_60_80_100_cycles']})
(args.folder/'tabela.md').write_text('\n'.join(lines)+'\n')
(args.folder/'verificacao-comparacao.json').write_text(json.dumps({'paired_samples':160,'failures':failures,'results':results},ensure_ascii=False,indent=2)+'\n')
print('\n'.join(lines));print('DIFERENÇAS',failures)
raise SystemExit(bool(failures))
