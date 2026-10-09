# Etapa 10 — Miniaturas da galeria

Concluída em 09/10/2026. As reaberturas reutilizam miniaturas pela composição, bytes do exemplo e das imagens, cartão da Página 1, grade, fonte, idioma e autorização. O cache LRU retém até 16 MiB por janela; mudanças de documento, fontes, autorização e fechamento liberam as entradas. A interface conserva a arte e continua criando cópias editáveis independentes.

As cinco estruturas compartilham os bytes do cartão durante a abertura, sem trocar o caminho de renderização nem converter o desenho vetorial da exportação em bitmap. Os diálogos são liberados após a transferência do resultado; cancelamentos descartam imagens e providers. Uma sessão protegida é conferida antes/depois do acesso e antes da aceitação, com limpeza pelo timer de 250 ms quando a autorização termina. Nada deste cache é gravado em disco.

## Medições

Qt offscreen, Linux, Inter, tema escuro, escala 1, configurações e dados temporários. Dois aquecimentos e 20 amostras por galeria; cinco primeiras aberturas em processos independentes. O cronômetro inclui montagem, eventos e pintura confirmada do viewport. Estados/capturas e instrumentação ficam fora do intervalo. Os modelos são os cinco exemplos públicos distribuídos; os organogramas usam as cinco estruturas reais com um cartão sintético fixo. UUIDs são fixados no driver porque a ordem de roteamento pode variar com identidades aleatórias, inclusive antes desta etapa. O produto continua atribuindo identidades novas às cópias.

| Galeria | Reabertura antes: mediana / p95 | Depois: mediana / p95 | Redução da mediana | Miniaturas renderizadas ao reabrir |
|---|---:|---:|---:|---:|
| model | 913.37 / 936.10 ms | 484.01 / 616.44 ms | 47.0% | 5 → 0 |
| organogram | 502.11 / 636.54 ms | 45.37 / 63.75 ms | 91.0% | 5 → 0 |

| Galeria | Primeira abertura antes: mediana / p95 | Depois: mediana / p95 | Cache retido |
|---|---:|---:|---:|
| model | 1405.85 / 1549.16 ms | 1621.80 / 1701.23 ms | 1.40 MiB |
| organogram | 568.71 / 735.20 ms | 561.13 / 627.60 ms | 1.44 MiB |

Nesta medição, a primeira abertura da galeria de modelos ficou 15.4% mais lenta (1405.85 → 1621.80 ms). É um custo observado desta versão e precisa ser considerado junto com o ganho nas reaberturas.

A primeira abertura continua renderizando os exemplos e passa a conferir os bytes das dependências. O benefício principal é a reabertura; os números de primeira abertura têm somente cinco amostras e não sustentam uma promessa de aceleração. Cada JSON conserva todas as amostras e a dispersão. Os recursos comuns são compartilhados durante o diálogo; não há cache permanente de documentos, providers ou imagens decodificadas.

## Memória e fidelidade

- model: RSS após 1/10/20 reaberturas adicionais: antes 161.41, 161.46, 167.54 MiB; depois 150.41, 150.44, 150.21 MiB. Cache após limpeza: 0 bytes.
- organogram: RSS após 1/10/20 reaberturas adicionais: antes 128.90, 128.92, 128.93 MiB; depois 129.62, 129.70, 129.70 MiB. Cache após limpeza: 0 bytes.

40 pares de reaberturas e 10 pares de primeiras aberturas apresentaram igualdade exata dos pixels das miniaturas e do backing store do painel, além de ordem, títulos e dimensões. O cache ficou dentro do limite e o RSS abaixo de 2 GiB. Estas execuções curtas não substituem testes prolongados.

## Verificações

- Antes: 26 testes existentes de modelos/cache visual e seis contratos novos da galeria passaram.
- Depois: 44 testes de modelos/cache/galeria passaram (26 existentes e 18 da galeria). Os 209 testes gerais incluem esses 26 existentes; 26 testes de cenas por página também passaram. São 253 verificações distintas, sem contar repetições.
- Cobertura específica: cópias independentes, começar em branco, grade e retorno aos valores anteriores, conteúdos/presets alterados, mudança de cartão/documento/fonte, imagens substituídas com mesmos bytes de tamanho e timestamp, snapshots comuns, limite/evicção/cópias dos pixels, sessão protegida real expirada e reautorizada, aceitação bloqueada sem autorização, transferência/liberação do diálogo e troca de arquivo durante o carregamento.
- Tema claro e escuro verificados por testes; a troca de tema conserva os pixels da arte. Não houve teste manual no backend nativo Linux/Windows nem com touchpad nesta etapa.

## Reproduzir

```bash
.venv/bin/python tests/performance/benchmark_gallery.py --output /tmp/fornax-gallery-after
PYTHONPATH=tests FORNAX_GALLERY_CACHE_CHECKS=1 QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/fornax-check/config XDG_DATA_HOME=/tmp/fornax-check/data .venv/bin/python -m unittest test_starter_gallery_cache test_starter_templates test_editor_visual_cache -q
```

O antes usa um overlay com os quatro módulos copiados da árvore local ao iniciar esta etapa, incluindo todas as otimizações anteriores; não usa o HEAD. Para reconstruí-lo, copie os quatro arquivos indicados em `identidade-patch.json` e `starter_cache.py` para uma árvore temporária, aplique `git apply --reverse patch-etapa-10.diff` nessa árvore e confira os hashes. Use `--reference <árvore-temporária>` no benchmark. O módulo novo pode aparecer no inventário amplo de hashes do antes, mas não é importado pelo diálogo de referência.

Resultados brutos, logs e hashes de ambiente/harness estão em `antes/` e `depois/`; a igualdade está em `comparacao.json`. A etapa 11 permanece pendente.
