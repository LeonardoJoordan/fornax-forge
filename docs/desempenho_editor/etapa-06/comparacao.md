# Etapa 06 — Pintar somente o necessário

**Concluída em 08/10/2026.** A etapa 07 aguarda autorização.

## Mudança aplicada

A view passou de `FullViewportUpdate` para `BoundingRectViewportUpdate`: redesenha o retângulo que contém as regiões alteradas, em vez de toda a área visível em cada alteração. Mantém antialiasing e as expansões de segurança do Qt. A opção pode redesenhar espaço entre alterações distantes; não promete o mínimo absoluto de pixels. Transformações, exposição de janela e mudanças que atinjam toda a view continuam permitindo pintura completa. O comportamento dos modos está documentado no [Qt — ViewportUpdateMode](https://doc.qt.io/qt-6/qgraphicsview.html#ViewportUpdateMode-enum).

Um conjunto do organograma continua sendo um único objeto. Na pintura do editor, calcula apenas as linhas/colunas de cartões que alcançam a região exposta, considerando contorno para fora e folga de três pixels físicos para antialiasing/traços cosméticos. Mantém a ordem e as mesmas rotinas de desenho. `ItemUsesExtendedStyleOption` permite ao Qt informar um `exposedRect` mais preciso, conforme [Qt — exposedRect](https://doc.qt.io/qt-6/qstyleoptiongraphicsitem.html#exposedRect-var). Pintura sem widget de view continua desenhando todos os cartões; o renderer da prévia/exportação permanece completo e não foi alterado.

As réguas verificam transformação, deslocamento, geometria do documento/viewport, posição dos widgets e DPI antes de pedir outra pintura. Alterar o conteúdo sem mudar essas entradas evita redesenhá-las. Mudanças de tema continuam solicitando sua atualização diretamente.

A validação inicial revelou um rastro ao mover um texto selecionado. As alças podem aumentar seu tamanho durante a pintura, e a área antiga automaticamente invalidada pelo pai não incluía toda a sua extensão. Antes de mover textos, imagens, formas ou assinaturas, a implementação agora invalida também os limites antigos das alças visíveis. A área nova continua sendo invalidada pelo Qt. Não foi necessário forçar uma repintura completa para corrigir esse caso. A checagem complementar revelou também pixels ausentes nas alças da seleção coletiva: elas ignoram o zoom, e a área suja arredondada pelo Qt deixava de fora uma faixa na sua extremidade. Ao posicioná-las ou exibi-las, invalidam-se seus limites antigos/novos em coordenadas da view, com folga para antialiasing. As duas correções preservam os pixels anteriores sem forçar atualização de toda a view. Tentativas e diagnósticos em pixels estão em `diagnostico-invalidação/`.

Mudaram somente `features/editor/controls.py`, `features/editor/rulers.py`, `features/editor/organogram_editor.py` e `features/editor/canvas_items.py`. O patch exclusivo e sua reversão exata estão em `alteracoes-etapa-06.patch` e `verificacao-patch.json`. Fontes, modelos prontos e demais arquivos de produto do manifesto permanecem iguais. As alterações locais das etapas anteriores foram preservadas.

## Método

- ThinkPad i5-8350U, Linux, Python 3.13.13, PySide6/Qt 6.11.0, fonte Inter e backend Qt `offscreen`. Janela solicitada de 1280 × 800; viewport, fonte e hashes das fixtures conferidos em cada cenário.
- **15 cenários, 20 amostras antes e depois**, duas preparações e uma execução adicional com profiler fora dos tempos medidos. São 300 amostras por versão. Processos em sequência, sem outros testes simultâneos durante as medições.
- Conjuntos de 40/400/2.500 cartões, vistos de perto e por inteiro; pequena invalidação local; seleção e arraste de conjuntos conectados; digitação; rolagem, pan real e zoom; invalidação local e rotação numa página com 60 objetos mistos.
- O cronômetro inclui a operação, pintura efetiva da view e seis turnos de processamento dos eventos. Captura do backing store e inspeção do documento ficam fora dele. Operações sem mutação reutilizam a cena aquecida, restaurando escala/posição entre amostras; operações com mutação restauram uma cópia idêntica do cenário fora do cronômetro.
- `QScreen.grabWindow` captura os pixels que já foram pintados. Não se usa `QWidget.grab` ou `scene.render` para verificar rastros: essas chamadas forçariam outra pintura e poderiam esconder uma invalidação incorreta. O instrumento também exige que a captura não provoque nova pintura.
- Cada amostra exige documento final, seleção, número de objetos, pixels, viewport, transformação e rolagem iguais à referência. Os drivers verificam que pan, zoom, arraste, rotação e digitação realmente ocorreram. Os testes de calibração que detectaram drivers sem efeito estão separados em `diagnostico-instrumentos/`.
- Instrumentos temporizados e contratos mantêm os mesmos hashes antes/depois. A checagem complementar de alças usa o mesmo script contra os seis módulos anteriores preservados e contra os módulos atuais, em processos separados; registra origens e hashes de cada módulo. Nenhum modelo pessoal ou configuração real foi usado.

## Tempos

Milissegundos; p95 interpolado. Dados completos, dispersão, memória e perfis estão em `antes.json`, `depois.json` e `raw/`.

| Operação | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|
| 40 cartões — visão aproximada | 32,57 | 16,43 | 35,92 → 17,41 |
| 40 cartões — quadro inteiro | 45,59 | 34,18 | 51,12 → 44,03 |
| 400 cartões — visão aproximada | 183,75 | 13,90 | 218,64 → 16,67 |
| 400 cartões — quadro inteiro | 208,05 | 163,22 | 235,36 → 195,58 |
| 2.500 cartões — visão aproximada | 1.117,71 | 13,26 | 1.208,15 → 14,87 |
| 2.500 cartões — quadro inteiro | 1.172,28 | 929,34 | 1.396,18 → 1.000,21 |
| 2.500 cartões — invalidação local | 1.075,97 | 1,98 | 1.277,92 → 2,85 |
| Selecionar conjunto — 40 conjuntos conectados | 40,38 | 28,28 | 48,55 → 36,87 |
| Arrastar conjunto — 40 conjuntos conectados | 140,70 | 62,56 | 151,70 → 74,73 |
| Digitar sete caracteres — quadro com 400 cartões | 203,63 | 20,57 | 248,15 → 25,54 |
| Rolagem — 2.500 cartões | 1.082,79 | 15,55 | 1.199,23 → 17,56 |
| Pan — 2.500 cartões | 1.049,94 | 16,07 | 1.130,82 → 18,22 |
| Zoom — 2.500 cartões | 894,40 | 14,39 | 1.109,16 → 16,73 |
| Invalidação local — página com 60 objetos | 13,75 | 1,64 | 15,23 → 2,62 |
| Rotação de texto — página com 60 objetos | 15,69 | 9,37 | 19,61 → 11,74 |

Na visão aproximada de 2.500 cartões, a mediana caiu **98,8%**, de 1.117,71 para 13,26 ms. A invalidação local caiu de 1.075,97 para 1,98 ms. Esses cenários deixam de percorrer/desenhar os cartões fora da tela e, na alteração local, também deixam de repintar a view inteira. A entrada é uma grade sintética; os valores não garantem a mesma latência em qualquer modelo real.

Na visão inteira continuam sendo desenhados todos os cartões. A mediana dos 2.500 cartões caiu de 1.172,28 para 929,34 ms nesta rodada, mas a pintura continua custosa. Essa queda menor não pode ser atribuída à eliminação de cartões: o número desenhado permaneceu 2.500. Evitar pinturas das réguas e diferenças no modo de atualização se somam à variação do ambiente. Não se promete que toda pintura completa seja igualmente acelerada. O custo do histórico, preparação de prévias e outros processos fora desta etapa permanece.

## Trabalho e memória

Contagens de uma execução adicional com profiler, fora dos tempos medidos. Nos quadros sintéticos, `QPainter.drawImage` conta o desenho dos cartões. Quantidades de conectores referem-se a chamadas de pintura, não a conexões removidas do documento.

| Operação | Cartões desenhados | Conectores pintados | Pinturas das réguas |
|---|---:|---:|---:|
| 40 cartões — visão aproximada | 40 → 6 | 0 → 0 | 2 → 0 |
| 400 cartões — visão aproximada | 400 → 6 | 0 → 0 | 2 → 0 |
| 2.500 cartões — visão aproximada | 2500 → 6 | 0 → 0 | 2 → 0 |
| 2.500 cartões — quadro inteiro | 2500 → 2500 | 0 → 0 | 2 → 0 |
| 2.500 cartões — invalidação local | 2500 → 1 | 0 → 0 | 2 → 0 |
| Selecionar conjunto — 40 conjuntos conectados | 6 → 1 | 11 → 6 | 2 → 1 |
| Arrastar conjunto — 40 conjuntos conectados | 40 → 8 | 39 → 18 | 3 → 1 |
| Digitar sete caracteres — quadro com 400 cartões | 400 → 2 | 0 → 0 | 3 → 1 |
| Rolagem — 2.500 cartões | 2500 → 6 | 0 → 0 | 4 → 2 |
| Pan — 2.500 cartões | 2500 → 6 | 0 → 0 | 4 → 2 |
| Zoom — 2.500 cartões | 2500 → 6 | 0 → 0 | 4 → 2 |

O viewport efetivo tem **664 × 604 = 401.056 pixels lógicos**. A tabela abaixo mostra a mediana da soma das áreas dos retângulos delimitadores dos eventos de pintura da view. É um limite superior da área da região suja, não uma contagem exata de pixels modificados; vários eventos podem contar a mesma área mais de uma vez. Nesta rodada houve um evento da view por amostra nos cenários apresentados.

| Operação | Área antes | Área depois |
|---|---:|---:|
| 2.500 cartões — invalidação local | 401.056 | 169 |
| Selecionar conjunto — 40 conjuntos conectados | 401.056 | 111.447 |
| Arrastar conjunto — 40 conjuntos conectados | 401.056 | 25.530 |
| Digitar sete caracteres — quadro com 400 cartões | 401.056 | 65.484 |
| Invalidação local — página com 60 objetos | 401.056 | 169 |
| Rotação de texto — página com 60 objetos | 401.056 | 74.354 |

Nas repinturas completas solicitadas pelo instrumento, e nos casos medidos de rolagem/pan/zoom, esse retângulo permanece abrangendo a view inteira. Ainda assim a visão aproximada desenha seis cartões, em vez de todos os 2.500. As réguas continuam sendo pintadas quando sua posição/escala muda ou quando um widget é exposto; a otimização elimina pedidos repetidos quando suas entradas permanecem iguais.

| Cenário | RSS antes (MiB) | RSS depois (MiB) |
|---|---:|---:|
| 2.500 cartões — visão aproximada | 127,41–127,43 | 127,32–127,33 |
| 2.500 cartões — quadro inteiro | 127,24–127,27 | 127,12–127,14 |
| Arrastar conjunto — 40 conjuntos conectados | 128,59–128,81 | 128,68–128,90 |
| Digitar sete caracteres — quadro com 400 cartões | 127,96–128,13 | 127,98–128,17 |
| Rotação de texto — página com 60 objetos | 233,17–233,27 | 232,98–233,05 |

RSS mede a memória residente corrente do processo, não o pico nem somente as alocações Python. As faixas permaneceram próximas; a principal melhoria desta etapa é de pintura/latência, sem alegar economia relevante de memória ou ausência de vazamentos em sessões prolongadas. Nenhuma amostra ultrapassou o limite de 2 GiB.

## Validação

**297 testes distintos passaram na referência e 302 na versão final.** As repetições por tema/DPI não multiplicam esse total.

- 209 regressões gerais, incluindo editor, organograma, histórico, prévia, assinaturas, fidelidade de texto, modelos prontos, frente/verso e exportação em ladrilhos.
- 18 contratos de seleção, 19 de camadas, 13 de organograma/conexões, 13 de texto e 15 de colagem/duplicação, antes e depois: 287 testes existentes.
- Seis contratos visuais novos, antes e depois, repetidos nos temas claro/escuro e em escala normal/200%. Cada combinação guarda 38 registros: 37 estados da tela e um registro com os hashes da prévia/PNG. São **152 registros exatamente iguais**, sem tolerância nos pixels ou no documento persistente.
- Cinco contratos de redução/proteção do trabalho passaram depois: desenho parcial de cartões, margens para contorno grosso, invalidação local menor que o viewport, atualização das réguas e desenho integral fora da view. Antes, quatro falharam como diagnóstico esperado de trabalho excessivo; o desenho integral sem widget já passou. Esse diagnóstico está em `diagnostico-trabalho-antes.log` e não integra o total de testes aprovados da referência.
- Quatro contratos complementares, executados contra os módulos anteriores e os atuais: alças de imagem/assinatura, seleção coletiva e guias/troca de tema. Os **14 estados adicionais**, em escala normal, mantêm pixels e documento idênticos. Origens, hashes e resultado dos módulos estão em `selecoes-antes.modules.json` e `selecoes-depois.modules.json`.

A captura da tela pintada parcialmente foi comparada a uma repintura completa forçada, e ambas foram comparadas à referência. Foram cobertos mover/redimensionar/girar/ocultar/excluir, undo/redo, transparência, contornos grossos e seu crescimento/redução, sombra sintética, máscaras, colagem, alças, seleção, textos atravessando conectores, zoom, pan, rolagem, redimensionamento de janela, guias e mudança de tema. Exceções de callbacks Qt também reprovam os testes.

O renderer mantém os 40 e os 2.500 slots completos, independentemente da área visível no editor. Prévia e PNG do cenário de 40 cartões foram efetivamente gerados, com hashes de pixels iguais antes/depois nos quatro pares tema/DPI. Não se gerou uma imagem gigante dos 2.500 cartões: nesse tamanho foi conferida a estrutura integral dos slots. Os testes gerais de PDF/ladrilhos também passaram.

A auditoria verificou os **15 cenários e as 300 amostras de cada versão**, incluindo documento, pixels, quantidade/seleção de itens, transformações e rolagem. Conferiu instrumentos, contratos, fontes/modelos, ambiente e reversão do patch aos hashes anteriores. O resultado está em `verificacao-comparacao.json`.

## Reproduzir e limites

Os comandos abaixo executam a versão atual com dados/preferências temporários. As medições devem rodar sozinhas. Para recriar a referência, recuperar os arquivos anteriores usando o patch exclusivo **numa cópia isolada do projeto**, sem desfazer a implementação da pasta de trabalho.

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-etapa06-regressoes.log
.venv/bin/python tests/performance/run_paint_checks.py --theme dark --scale 1 --evidence /tmp/fornax-etapa06-pixels.json
.venv/bin/python docs/desempenho_editor/etapa-06/verificar_selecoes.py --output /tmp/fornax-etapa06-selecoes.json
.venv/bin/python tests/performance/benchmark_paint.py --output /tmp/fornax-etapa06-medições --label depois
.venv/bin/python docs/desempenho_editor/etapa-06/verificar_comparacao.py
```

Para os quatro pares de tema/DPI, repetir a checagem de pintura com `--theme dark/light` e `--scale 1/2`, usando caminhos de evidência diferentes. `verificar_selecoes.py --reference-editor DIRETORIO` carrega os seis módulos anteriores preservados, verificando suas origens; os demais módulos e fixtures permanecem iguais.

A validação usa a view real, eventos de pintura e seu backing store no backend Qt `offscreen`; não substitui teste manual em uma sessão gráfica Linux ou Windows, com o driver e a escala reais. Uso prolongado, touchpad, múltiplos monitores, exposições de janela pelo sistema e renderização no backend nativo continuam como verificação complementar. Pintura completa de quadros grandes ainda pode ser lenta. A etapa 07 não foi iniciada.
