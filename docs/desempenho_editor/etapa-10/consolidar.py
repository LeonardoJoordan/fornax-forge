"""Compara as evidências gravadas; não altera fontes nem resultados brutos."""
from pathlib import Path
from hashlib import sha256
import difflib
import json
import statistics
import subprocess
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(ROOT/'tests/performance'))
from benchmark_editor import distribution


def consolidate():
    comparisons=[]; failures=[]
    for kind in ('model','organogram'):
        before=json.loads((HERE/'antes'/f'{kind}-warm.json').read_text())
        after=json.loads((HERE/'depois'/f'{kind}-warm.json').read_text())
        for index,(b,a) in enumerate(zip(before['states'],after['states'])):
            if b!=a: failures.append({'kind':kind,'sample':index,'mismatch':'state_or_pixels'})
        cold_before=[];cold_after=[]
        for index in range(5):
            b=json.loads((HERE/'antes'/f'{kind}-cold-{index}.json').read_text())
            a=json.loads((HERE/'depois'/f'{kind}-cold-{index}.json').read_text())
            cold_before+=b['samples_ms'];cold_after+=a['samples_ms']
            if b['states']!=a['states']: failures.append({'kind':kind,'cold':index,'mismatch':'state_or_pixels'})
        gain=100*(1-after['distribution']['median_ms']/before['distribution']['median_ms'])
        comparisons.append({'kind':kind,'warm_before':before['distribution'],'warm_after':after['distribution'],
                            'warm_gain_percent':gain,'cold_before':distribution(cold_before),'cold_after':distribution(cold_after),
                            'render_before':before['generated_on_extra_warm_open'],'render_after':after['generated_on_extra_warm_open'],
                            'retained_bytes':after['retained_bytes'][-1], 'memory_before':before['memory_cycles'],
                            'memory_after':after['memory_cycles'],'released_bytes':after['bytes_after_clear']})
    result={'warm_pairs':40,'cold_pairs':10,'comparisons':comparisons,'failures':failures}
    (HERE/'comparacao.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    assert not failures,failures
    lines=['# Etapa 10 — Miniaturas da galeria','',
           'Concluída em 09/10/2026. As reaberturas reutilizam miniaturas pela composição, bytes do exemplo e das imagens, cartão da Página 1, grade, fonte, idioma e autorização. O cache LRU retém até 16 MiB por janela; mudanças de documento, fontes, autorização e fechamento liberam as entradas. A interface conserva a arte e continua criando cópias editáveis independentes.', '',
           'As cinco estruturas compartilham os bytes do cartão durante a abertura, sem trocar o caminho de renderização nem converter o desenho vetorial da exportação em bitmap. Os diálogos são liberados após a transferência do resultado; cancelamentos descartam imagens e providers. Uma sessão protegida é conferida antes/depois do acesso e antes da aceitação, com limpeza pelo timer de 250 ms quando a autorização termina. Nada deste cache é gravado em disco.', '',
           '## Medições', '',
           'Qt offscreen, Linux, Inter, tema escuro, escala 1, configurações e dados temporários. Dois aquecimentos e 20 amostras por galeria; cinco primeiras aberturas em processos independentes. O cronômetro inclui montagem, eventos e pintura confirmada do viewport. Estados/capturas e instrumentação ficam fora do intervalo. Os modelos são os cinco exemplos públicos distribuídos; os organogramas usam as cinco estruturas reais com um cartão sintético fixo. UUIDs são fixados no driver porque a ordem de roteamento pode variar com identidades aleatórias, inclusive antes desta etapa. O produto continua atribuindo identidades novas às cópias.', '',
           '| Galeria | Reabertura antes: mediana / p95 | Depois: mediana / p95 | Redução da mediana | Miniaturas renderizadas ao reabrir |',
           '|---|---:|---:|---:|---:|']
    for c in comparisons:
        b,a=c['warm_before'],c['warm_after']
        lines.append(f"| {c['kind']} | {b['median_ms']:.2f} / {b['p95_ms']:.2f} ms | {a['median_ms']:.2f} / {a['p95_ms']:.2f} ms | {c['warm_gain_percent']:.1f}% | {c['render_before']} → {c['render_after']} |")
    lines+=['','| Galeria | Primeira abertura antes: mediana / p95 | Depois: mediana / p95 | Cache retido |','|---|---:|---:|---:|']
    for c in comparisons:
        b,a=c['cold_before'],c['cold_after']
        lines.append(f"| {c['kind']} | {b['median_ms']:.2f} / {b['p95_ms']:.2f} ms | {a['median_ms']:.2f} / {a['p95_ms']:.2f} ms | {c['retained_bytes']/1024**2:.2f} MiB |")
    cold_models=next(c for c in comparisons if c['kind']=='model')
    cold_increase=100*(cold_models['cold_after']['median_ms']/cold_models['cold_before']['median_ms']-1)
    lines+=['',f'Nesta medição, a primeira abertura da galeria de modelos ficou {cold_increase:.1f}% mais lenta ({cold_models["cold_before"]["median_ms"]:.2f} → {cold_models["cold_after"]["median_ms"]:.2f} ms). É um custo observado desta versão e precisa ser considerado junto com o ganho nas reaberturas.', '', 'A primeira abertura continua renderizando os exemplos e passa a conferir os bytes das dependências. O benefício principal é a reabertura; os números de primeira abertura têm somente cinco amostras e não sustentam uma promessa de aceleração. Cada JSON conserva todas as amostras e a dispersão. Os recursos comuns são compartilhados durante o diálogo; não há cache permanente de documentos, providers ou imagens decodificadas.', '',
            '## Memória e fidelidade','']
    for c in comparisons:
        b=c['memory_before'];a=c['memory_after']
        lines.append(f"- {c['kind']}: RSS após 1/10/20 reaberturas adicionais: antes {', '.join(f'{x["rss"]/1024**2:.2f}' for x in b)} MiB; depois {', '.join(f'{x["rss"]/1024**2:.2f}' for x in a)} MiB. Cache após limpeza: {c['released_bytes']} bytes.")
    lines+=['','40 pares de reaberturas e 10 pares de primeiras aberturas apresentaram igualdade exata dos pixels das miniaturas e do backing store do painel, além de ordem, títulos e dimensões. O cache ficou dentro do limite e o RSS abaixo de 2 GiB. Estas execuções curtas não substituem testes prolongados.', '',
            '## Verificações','',
            '- Antes: 26 testes existentes de modelos/cache visual e seis contratos novos da galeria passaram.',
            '- Depois: 44 testes de modelos/cache/galeria passaram (26 existentes e 18 da galeria). Os 209 testes gerais incluem esses 26 existentes; 26 testes de cenas por página também passaram. São 253 verificações distintas, sem contar repetições.',
            '- Cobertura específica: cópias independentes, começar em branco, grade e retorno aos valores anteriores, conteúdos/presets alterados, mudança de cartão/documento/fonte, imagens substituídas com mesmos bytes de tamanho e timestamp, snapshots comuns, limite/evicção/cópias dos pixels, sessão protegida real expirada e reautorizada, aceitação bloqueada sem autorização, transferência/liberação do diálogo e troca de arquivo durante o carregamento.',
            '- Tema claro e escuro verificados por testes; a troca de tema conserva os pixels da arte. Não houve teste manual no backend nativo Linux/Windows nem com touchpad nesta etapa.', '',
            '## Reproduzir','',
            '```bash',
            '.venv/bin/python tests/performance/benchmark_gallery.py --output /tmp/fornax-gallery-after',
            'PYTHONPATH=tests FORNAX_GALLERY_CACHE_CHECKS=1 QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/fornax-check/config XDG_DATA_HOME=/tmp/fornax-check/data .venv/bin/python -m unittest test_starter_gallery_cache test_starter_templates test_editor_visual_cache -q',
            '```','',
            'O antes usa um overlay com os quatro módulos copiados da árvore local ao iniciar esta etapa, incluindo todas as otimizações anteriores; não usa o HEAD. Para reconstruí-lo, copie os quatro arquivos indicados em `identidade-patch.json` e `starter_cache.py` para uma árvore temporária, aplique `git apply --reverse patch-etapa-10.diff` nessa árvore e confira os hashes. Use `--reference <árvore-temporária>` no benchmark. O módulo novo pode aparecer no inventário amplo de hashes do antes, mas não é importado pelo diálogo de referência.', '',
            'Resultados brutos, logs e hashes de ambiente/harness estão em `antes/` e `depois/`; a igualdade está em `comparacao.json`. A etapa 11 permanece pendente.']
    (HERE/'comparacao.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':consolidate()
