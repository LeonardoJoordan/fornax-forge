# Etapa 01 — Seleção e painéis em lote

**Concluída em 08/10/2026.** Escopo: seleção, levantamento dos objetos agrupáveis e sincronização dos painéis. A etapa 02 não foi iniciada.

## Mudança aplicada

Selecionar tudo, selecionar um grupo, desagrupar e escolher elementos pelas camadas ou pela estrutura do quadro concluem a seleção antes de publicar uma notificação. Um bloqueio com escopo, que aceita operações aninhadas, preserva também bloqueios externos e libera os sinais mesmo em caso de erro.

A expansão automática dos grupos e a remoção das guias de uma seleção mista acontecem sem carregar propriedades para cada estado intermediário. O levantamento dos objetos agrupáveis é reutilizado pelas alças da mesma operação; a busca de raízes usa conjuntos para evitar percorrer repetidamente a cena. Não há cache persistente de objetos.

Os painéis e o inspetor são sincronizados juntos, inclusive no organograma. Selecionar pelas camadas continua permitindo selecionar parte de um grupo; selecionar pelo canvas continua completando o grupo. Máscaras mantêm a seleção e a movimentação aprovadas, incluindo a regra existente para uma máscara dentro de um grupo. A ordem das camadas, o magnetismo, o documento e o histórico não foram modificados por estas seleções.

## Método e origem da referência

- ThinkPad com Linux, Python/PySide6/Qt e fonte Inter registrados em `ambiente-antes.json` e `ambiente-depois.json`. Backend Qt `offscreen`, tema escuro e janela solicitada de 1280 × 800.
- Oito cenários, cada um com duas preparações e **20 amostras medidas até a pintura e estabilização dos eventos**. O profiler roda separadamente e não entra nos tempos.
- A referência de **200 objetos** foi reutilizada da etapa 00, após verificar a igualdade de todos os hashes do produto. Entrada, assets, fonte, viewport, seleção e protocolo coincidem. Isso evita repetir mais de vinte operações que demoravam aproximadamente 53 segundos cada. Origem explícita em `referencia-reutilizada.json`; o resultado bruto foi copiado para esta pasta.
- Os outros sete cenários foram repetidos com os três módulos anteriores isolados e identificados por hash. Os demais arquivos coincidem com a referência inicial. O parâmetro `--reference-editor` muda somente a origem desses módulos no processo do teste, sem restaurar ou editar o projeto de trabalho.
- O cenário da árvore seleciona **20 blocos, inclusive nós filhos**. Foi corrigido no instrumento antes da comparação final: selecionar apenas um intervalo de linhas de nível superior não exercitava vários blocos de uma árvore hierárquica.
- `benchmark_editor.py` e `editor_scenarios.py` têm hashes iguais nas rodadas finais antes/depois. Os resultados oficiais não usam `--samples` de diagnóstico.
- Foi feita uma segunda rodada, de 20 amostras antes/depois, para as duas operações do organograma que apresentaram dispersão. Esses resultados estão separados em `repeticao-organograma/`; não foram misturados nem usados para substituir a primeira rodada.

## Tempo medido

Todos os valores da tabela são em milissegundos. P95 é o percentil 95 interpolado.

| Operação | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|
| Selecionar tudo — 20 objetos | 104,61 | 31,31 | 125,96 → 33,49 |
| Selecionar tudo — 60 objetos | 1.194,38 | 43,53 | 1.314,15 → 51,39 |
| Selecionar tudo — 200 objetos | 52.819,69 | 115,31 | 57.106,59 → 131,81 |
| Selecionar grupo na página de 60 objetos | 84,40 | 27,85 | 100,18 → 33,39 |
| Selecionar 20 linhas nas camadas | 48,03 | 37,67 | 54,45 → 45,62 |
| Selecionar por área — 60 objetos | 149,31 | 46,77 | 164,68 → 51,28 |
| Selecionar 20 blocos pela árvore — 40 blocos | 38,70 | 44,40 | 49,90 → 68,01 |
| Selecionar conjuntos e conectores por área — 40 blocos | 52,87 | 52,77 | 60,33 → 69,22 |

No cenário de 200 objetos, a mediana caiu de **52,82 s para 0,115 s**, redução de **99,78%**. Com 60 objetos, caiu de **1,194 s para 43,53 ms**; com 20, de **104,61 ms para 31,31 ms**. A seleção por grupo e a seleção por área de objetos mistos também tiveram redução acima da dispersão registrada.

A seleção pela árvore teve mediana maior na primeira rodada (38,70 → 44,40 ms), mas o sentido se inverteu na repetição (43,35 → 40,77 ms). A seleção de conjuntos/conectores por área ficou próxima da referência nas duas rodadas (52,87 → 52,77 ms e 49,17 → 48,83 ms). **Não há ganho de desempenho demonstrado nessas duas operações**, que já consolidavam a seleção. As contagens de pintura/roteamento e atualização da estrutura foram preservadas. A otimização de conectores/pintura pertence às próximas etapas.

## Trabalho contado

Uma execução adicional com profiler, após aquecimento:

| Operação | Manipulador de seleção antes → depois | Levantamentos de objetos agrupáveis antes → depois |
|---|---:|---:|
| Selecionar tudo — 20 objetos | 19 → 1 | 189 → 1 |
| Selecionar tudo — 60 objetos | 59 → 1 | 1632 → 1 |
| Selecionar tudo — 200 objetos | 199 → 1 | 17998 → 1 |
| Selecionar grupo na página de 60 objetos | 10 → 1 | 56 → 2 |
| Selecionar 20 linhas nas camadas | 1 → 1 | 18 → 1 |
| Selecionar por área — 60 objetos | 3 → 1 | 162 → 1 |
| Selecionar 20 blocos pela árvore — 40 blocos | 1 → 1 | 0 → 0 |
| Selecionar conjuntos e conectores por área — 40 blocos | 1 → 1 | 0 → 0 |

Em todos os oito cenários, a versão final executou **uma sincronização dos painéis e uma do inspetor**. Selecionar um grupo faz dois levantamentos: um para localizar seus membros e outro para tratar a seleção final. Nas seleções exclusivamente de conjuntos/conectores, não há levantamento de objetos agrupáveis.

Não foram reconstruídas as camadas ou a cena nas operações medidas. Todos os objetos originais foram preservados, sem acréscimo de passos de histórico. A quantidade final de itens selecionados coincidiu com a referência em todas as 20 amostras de cada cenário. O RSS ficou estável durante as repetições: por exemplo, no cenário de 200 objetos, 328,6 MiB no início e no final. Não se atribui a esta etapa uma redução de memória de abertura.

## Comportamento e fidelidade

- **Antes:** 209 regressões + 13 contratos de seleção = **222 testes**. Os 13 contratos também passaram no tema claro.
- **Depois:** 209 regressões + 18 contratos de seleção = **227 testes**. Os 18 contratos também passaram no tema claro. São 227 testes distintos; repetições entre temas não aumentam esse total.
- Os cinco contratos novos de trabalho verificam uma publicação final, uma carga de propriedades/inspetor, expansão de grupo sem recursão e restauração dos sinais em lotes aninhados, bloqueios externos e exceções.
- As regressões cobrem organogramas, conectores, contornos, camadas, máscaras, histórico, carregamento, cache visual, recuperação automática, ponteiro, texto, assinaturas, modelos prontos e exportação em ladrilhos. Cada módulo foi executado em processo isolado.
- Seleção por Ctrl+clique, Ctrl+A durante edição, conclusão da edição sem perder texto, atalhos e finalização de máscaras foram exercitados. Foram capturadas também exceções de callbacks Qt.
- **Nove cenários visuais em cada tema**, com igualdade exata dos documentos, seleção, habilitação dos painéis, alças e hashes dos pixels: selecionar tudo, grupo, grupo a partir de um membro, máscara, máscara dentro de grupo, fim da edição da máscara, seleção parcial pelas camadas, blocos pela árvore e blocos/conectores por área. Registros em `estados-*.json`, `fidelidade.txt` e `fidelidade-claro.txt`. Não foi aplicada tolerância visual.

Os testes usam dados sintéticos e preferências temporárias. Nenhum modelo pessoal foi alterado. Os testes de mouse/teclado são automatizados com QTest; ainda cabe experimentar no aplicativo aberto com mouse e touchpad reais. Estes resultados não são validação no backend nativo do Windows ou do Linux.

## Repetir as verificações

Da raiz do projeto:

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-regressoes.txt
.venv/bin/python tests/performance/run_selection_checks.py --theme dark
.venv/bin/python tests/performance/run_selection_checks.py --theme light
.venv/bin/python tests/performance/compare_selection_evidence.py docs/desempenho_editor/etapa-01/estados-antes.json docs/desempenho_editor/etapa-01/estados-depois.json
.venv/bin/python tests/performance/compare_selection_evidence.py docs/desempenho_editor/etapa-01/estados-antes-claro.json docs/desempenho_editor/etapa-01/estados-depois-claro.json
```

O benchmark aceita várias opções `--case` na mesma rodada. Repetir os oito cenários com `--label depois`, usando o comando registrado no plano/README dos instrumentos e uma pasta de saída separada para preservar estas evidências.

`alteracoes-etapa-01.patch` guarda exclusivamente as mudanças desta etapa nos três módulos. Ele reconstitui os módulos anteriores aplicando o patch inverso a cópias dos módulos finais em uma pasta temporária (`patch -R -p3 -d <pasta>`). Essa reconstrução foi verificada contra os hashes anteriores; não depende das cópias temporárias usadas durante o desenvolvimento. Os outros arquivos do produto precisam corresponder aos hashes da referência para que essa execução represente o mesmo código.

## Encerramento

A etapa 01 está concluída com ganho comprovado na seleção de páginas densas e comportamento/pixels preservados nos cenários verificados. A próxima etapa autorizável é **02 — atualização incremental das camadas**.
