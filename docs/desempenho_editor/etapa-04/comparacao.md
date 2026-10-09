# Etapa 04 — Layout e métricas de texto

**Concluída em 08/10/2026.** A etapa 05 não foi iniciada.

## Mudança aplicada

A caixa consolida as solicitações de reposicionamento enquanto sua configuração é reconstruída. A geometria é medida uma vez ao final da operação síncrona, quando HTML, fonte, largura, entrelinhas, alinhamento e cor já estão aplicados. A criação da caixa e a formatação de uma seleção usam o mesmo mecanismo, com suporte a lotes aninhados e liberação segura diante de exceções. O ajuste de largura evita medições recursivas intermediárias. Não foi introduzido timer ou adiamento da sincronização do conteúdo.

Somente o cálculo de posição é consolidado. Os sinais do documento continuam ativos, e `CanvasEdit.changed` mantém o HTML da fonte da verdade atualizado em cada alteração. Cursor, seleção textual, foco, formatação e histórico continuam usando as APIs nativas do Qt. Cada tecla ainda produz sua atualização imediata; não se juntam várias teclas para obter um resultado aparentemente mais rápido.

A identificação das fontes nas linhas relevantes passa a ler trechos de formatação, em vez de consultar cada posição de caractere. Preserva a semântica existente de `QTextCursor.charFormat` nos limites dos trechos e os offsets UTF-16 do Qt. Um teste compara cada linha com a implementação anterior por caractere, em várias larguras, incluindo fontes/tamanhos mistos, linhas vazias, acentos, símbolos fora do BMP e fonte ausente com fallback.

As métricas dos mesmos objetos `QFont` são compartilhadas entre topo e base somente durante uma chamada a `text_geometry`. A chave usa o valor completo da fonte, com cópia própria. O cache é descartado ao retornar, sem guardar texto, HTML, documentos, posições ou snapshots. Não há cache global que possa manter conteúdo protegido ou exigir invalidação entre DPI, instalação de fontes, documentos e sessões. Esta etapa não cria um cache permanente de geometria textual.

Mudaram somente `core/text_layout.py`, `features/editor/canvas_items.py` e `features/editor/canvas_edit.py`. O patch exclusivo e a reconstituição exata dos três arquivos anteriores por SHA-256 estão em `alteracoes-etapa-04.patch` e `verificacao-patch.json`. Os demais hashes do produto coincidem; as etapas anteriores e alterações locais foram preservadas. Nenhum modelo pronto foi modificado.

## Método

- ThinkPad i5-8350U, Python 3.13.13, PySide6/Qt 6.11.0, Inter, Qt `offscreen`, tema escuro, janela solicitada de 1280 × 800. Fontes e viewport efetivo coincidem por cenário. As versões e hashes estão nos manifestos antes/depois.
- **14 cenários:** oito operações aquecidas, com duas preparações e vinte amostras medidas; seis carregamentos, com cinco janelas/sessões novas do editor. Aplicação Qt e processo do cenário permanecem vivos nesses carregamentos; os caches do editor são novos, mas caches de fontes do Qt e do sistema operacional podem estar aquecidos. Não se afirma abertura com todo o sistema frio.
- Processos de benchmark em sequência, sem outros testes simultâneos. Tempo sem profiler, incluindo pintura quando necessária e estabilização dos eventos; contagens em uma execução adicional fora das amostras.
- Textos curtos usam um parágrafo e longos usam trinta, com fontes, tamanhos e ênfases mistas. Os sufixos `60`/`1200` escolhem esses casos; não significam número exato de caracteres. Digitar envia sete teclas reais (` equipe`); colar envia Ctrl+V com um ou vinte trechos Unicode. A entrada é restaurada fora do cronômetro.
- O estado inicial é capturado antes de abrir a edição, pois a leitura pública do documento encerra a interação. O driver exige sessão ativa, texto completo e HTML sincronizado antes de concluir a operação. O redimensionamento coletivo usa a sessão real de quatro textos e verifica o fator 1,2 na largura; não mede uma chamada sem efeito.
- A calibração dos testes está identificada em `diagnostico-instrumentos/`: um auxiliar de pintura recebia atributos de contorno diferentes do renderer. O contrato final usa propriedades iguais e exige pixels iguais entre texto do editor, prévia e PNG. Os contornos presentes nos modelos aprovados são verificados nas comparações de saída. Rodadas exploratórias do driver ficaram fora da referência oficial.
- Instrumentos temporizados e todas as entradas mantêm os hashes antes/depois. O probe/comparador auxiliar e o hash do módulo de testes foram acrescentados ao completar a referência, após o manifesto inicial; ficam identificados separadamente em `instrumentos-adicionais-antes.json` e `verificacao-comparacao.json`. Os manifestos históricos não foram reescritos para esconder a diferença de catálogo.
- Todas as amostras dos 14 cenários preservam hash do documento final, seleção, quantidade e retenção dos itens gráficos, índice do histórico, linhas/widgets de camadas, entrada, viewport e fonte. Amostras, dispersão, RSS e perfis completos estão em `antes.json`, `depois.json` e `raw/`.

## Tempos

Milissegundos; p95 interpolado. Carregamentos com cinco amostras são mais sensíveis à variação do ambiente.

| Operação | Amostras | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|---:|
| Abrir cartão de aniversário | 5 | 458,59 | 428,35 | 483,49 → 488,27 |
| Abrir certificado de estágio | 5 | 662,38 | 449,50 | 788,62 → 467,73 |
| Abrir prisma de identificação | 5 | 401,97 | 321,06 | 408,87 → 341,76 |
| Abrir convite | 5 | 495,37 | 373,76 | 514,96 → 414,33 |
| Digitar sete teclas — texto curto | 20 | 53,88 | 38,90 | 62,52 → 52,12 |
| Colar um trecho Unicode | 20 | 34,15 | 27,45 | 45,58 → 36,46 |
| Digitar sete teclas — texto longo | 20 | 118,48 | 95,36 | 133,45 → 101,38 |
| Colar vinte trechos Unicode | 20 | 66,13 | 60,76 | 73,04 → 67,36 |
| Redimensionar um texto longo | 20 | 63,97 | 64,48 | 76,14 → 98,86 |
| Redimensionar quatro textos longos | 20 | 682,59 | 517,94 | 728,98 → 615,16 |
| Formatar a seleção em negrito | 20 | 58,20 | 47,19 | 69,66 → 67,02 |
| Reconstruir a configuração de uma caixa | 20 | 137,72 | 107,35 | 155,34 → 123,85 |
| Carregar 60 caixas de texto | 5 | 1.714,32 | 1.453,08 | 1.759,26 → 1.610,61 |
| Carregar 200 caixas de texto | 5 | 12.959,33 | 12.245,66 | 14.423,90 → 12.642,18 |

As medianas foram menores na digitação, colagem, formatação, reconstrução de configuração e redimensionamento coletivo nesta rodada. O carregamento dos modelos e das páginas densas também pode incluir custos de cena, camadas, imagens e histórico, além do texto; não se atribui todo seu tempo ao cálculo de fontes.

O carregamento de 200 caixas teve mediana 5,51% menor, mas a dispersão e as cinco amostras não demonstram ganho conclusivo nesse cenário. A redução de medições é comprovada pelas contagens; outros custos continuam dominando o carregamento.

**Redimensionar um texto individual não apresentou ganho relevante:** 63,97 → 64,48 ms. Seu número de medições já era um. A pintura, o processamento da interface e outros custos permanecem; a redução de consultas de fonte não garante queda proporcional no tempo total. A etapa não elimina a reconstrução completa da cena durante carregamento.

## Trabalho e memória

Contagens do profiler, fora dos tempos medidos. `text_geometry` conta medições efetivas; chamadas a `recalculate_text_position` podem agora apenas marcar trabalho pendente dentro do lote.

| Operação | Medições efetivas antes → depois | Configurações completas antes → depois |
|---|---:|---:|
| Reconstruir a configuração de uma caixa | 4 → 1 | 1 → 1 |
| Formatar a seleção em negrito | 2 → 1 | 0 → 0 |
| Digitar sete teclas — texto longo | 7 → 7 | 0 → 0 |
| Redimensionar quatro textos longos | 16 → 4 | 4 → 4 |
| Carregar 60 caixas de texto | 540 → 120 | 120 → 120 |
| Carregar 200 caixas de texto | 1800 → 400 | 400 → 400 |

Carregar ainda configura cada caixa duas vezes: uma para sua construção e outra para aplicar as propriedades importadas. Isso não foi transformado em um novo processo de construção nesta etapa. Cada configuração agora mede somente o estado final: as 540 medições das 60 caixas passaram para 120; as 1.800 das 200 passaram para 400. O redimensionamento coletivo passou de dezesseis medições para quatro; formatar passou de duas para uma.

O probe separado registra consultas nativas que o resumo de funções Python do profiler não conta individualmente:

| Entrada | Consultas ao cursor antes → depois | QFontMetrics antes → depois |
|---|---:|---:|
| Texto simples, várias linhas | 222 → 2 | 2 → 1 |
| Texto com fontes e ênfases mistas | 138 → 2 | 10 → 5 |
| Linha larga com 2.160 caracteres | 4.320 → 2 | 2 → 1 |

A geometria dos três probes é exatamente igual. O caso largo mede topo e base da mesma linha, por isso a referência consultava cada caractere duas vezes. O teste também exige consultas proporcionais às duas linhas relevantes, em vez do comprimento do texto, e confirma novas métricas na chamada seguinte: o cache não fica retido entre medições.

| Cenário | RSS antes (MiB) | RSS depois (MiB) |
|---|---:|---:|
| Digitar sete teclas — texto longo | 139,58–147,19 | 139,70–147,32 |
| Reconstruir a configuração de uma caixa | 138,99–146,65 | 139,12–146,77 |
| Carregar 60 caixas de texto | 160,60–172,70 | 160,57–172,82 |
| Carregar 200 caixas de texto | 194,84–218,85 | 194,90–218,50 |

RSS é memória corrente do processo, não pico nem apenas alocações Python. Os carregamentos incluem histórico, fontes, imagens e a interface, e usam sessões novas do editor. Essas faixas não demonstram redução permanente de memória nem ausência de vazamento em sessões longas. `visual_cache_bytes` continua contando os caches raster existentes, sem medir o pequeno dicionário temporário de métricas.

## Comportamento e fidelidade

- **Antes:** 209 regressões + 18 testes de seleção + 19 de camadas + 13 do quadro + 7 contratos de texto = **266 testes distintos**, aprovados.
- **Depois:** os mesmos 259 testes anteriores + 13 de texto = **272 testes distintos**, aprovados. Os treze testes de texto passaram também no tema claro; repetições entre temas não aumentam o total. Poppler estava disponível; nenhum contrato PDF foi pulado.
- Os novos contratos cobrem teclado, colagem Unicode e método de entrada, foco, cursor/seleção, undo/redo textual e do editor, negrito/itálico/sublinhado dos placeholders, fontes e tamanhos mistos, entrelinhas/recuo/alinhamentos, rotação, redimensionamento individual/coletivo, medições em lote, exceção em lote aninhado, métricas temporárias e conteúdo imediatamente sincronizado. As regressões existentes cobrem prévia, assinaturas, máscaras, conectores, cache, troca de cenas, recuperação e exportação em ladrilhos. Exceções de callbacks Qt também reprovam.
- **20 estados por tema**, com igualdade exata de dados, HTML, cursor, geometria e hashes dos pixels registrados, sem tolerância geométrica ou raster. Os casos sintéticos também exigem igualdade entre texto do editor, prévia e PNG na mesma escala.
- Os quatro modelos publicados — cartão de aniversário, certificado, prisma e convite — têm comparações antes/depois de cena do editor, prévia, saída PNG e PDF renderizado. Os PDFs são produzidos pelo caminho real de geração, renderizados pelo Poppler a 96 DPI e comparados pelos pixels; não se compara o arquivo PDF binário, cuja metadata pode variar.
- A igualdade é exigida **em cada canal contra sua própria referência**: a cena do editor possui molduras de edição, a prévia usa escala menor, o PNG usa resolução completa e o PDF outro dispositivo de pintura. Não se declara igualdade entre imagens de tamanhos ou dispositivos diferentes. A inspeção visual dos PDFs complementa os hashes; os exemplos e preferências pessoais não foram alterados.

## Limites e repetição

A verificação é da mesma máquina, fontes e backend. Não se validou o backend nativo do Windows nem uma sessão real prolongada de edição com mouse/touchpad. Fontes ausentes no sistema continuam usando o fallback existente, e esta etapa não reformula os layouts dos modelos publicados. O convite apresenta aproximação/sobreposição entre o e-mail e a instrução dos botões no PDF desta referência; o resultado foi preservado e não é uma regressão da otimização. Ajustar o modelo/fonte é trabalho separado.

A manutenção imediata do HTML e do histórico permanece, assim como a construção completa das cenas e suas configurações importadas. Os cenários específicos `typography_*` são a referência de edição desta etapa; a sequência de preparação dos antigos cenários `text_insert` deve ser revista antes de usá-los numa comparação de digitação nativa, pois a leitura pública encerra a edição. Não extrapolar os ganhos para plataformas ou fluxos não medidos.

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-regressoes.txt
.venv/bin/python tests/performance/run_text_checks.py --theme dark
.venv/bin/python tests/performance/run_text_checks.py --theme light
.venv/bin/python tests/performance/probe_text_metrics.py --output /tmp/fornax-metricas-texto.json
.venv/bin/python tests/performance/compare_text_evidence.py docs/desempenho_editor/etapa-04/estados-antes.json docs/desempenho_editor/etapa-04/estados-depois.json
.venv/bin/python tests/performance/compare_text_evidence.py docs/desempenho_editor/etapa-04/estados-antes-claro.json docs/desempenho_editor/etapa-04/estados-depois-claro.json
```

Os comandos com os 14 cenários estão em `tests/performance/README.md`. Use outra pasta de saída para preservar estas evidências. A etapa 05 aguarda autorização.
