# Tabelas — etapa 04: canvas e sessão de edição

09/10/2026. **Etapa concluída.** O editor agora carrega tabelas v6 como
objetos editáveis, preservando conteúdo e identidades nos snapshots e no
salvamento. O botão de inserção e o painel completo pertencem à etapa 05.
Nenhum modelo ou asset da biblioteca foi alterado.

## O que foi implementado

- `TableItem`: um item raiz por tabela, com layout retido e coordenadas
  locais. Mesclagens entram no hit testing e na seleção por intervalo.
  Seleção, cursor e gesto de arraste são estados transitórios, fora do JSON.
  A moldura permite mover o objeto; clicar/arrastar dentro seleciona células.
- `TableEdit`: somente a célula ativa recebe um `QGraphicsTextItem`
  temporário. A sessão usa o mesmo construtor de texto e dispositivo lógico
  de 300 DPI da pintura, preservando fonte, alinhamento, cor e recorte.
  Enquanto se edita, o painter da tabela não desenha esse texto em duplicata.
  O HTML original de placeholders e delimitadores opcionais permanece editável.
- Teclado por contexto: digitar ou compor texto inicia a célula selecionada;
  Enter/F2 também iniciam edição. Tab/Shift+Tab visitam as âncoras das células,
  sem criar linhas automaticamente. Fora da edição textual, setas navegam
  pela grade e Shift estende/reduz o intervalo, sem mover o objeto.
  Dentro do texto, as setas continuam sendo do cursor nativo.
- Esc conclui a edição; outro Esc abandona a seleção interna. Delete atua
  no texto, no conteúdo das células selecionadas ou no objeto inteiro,
  conforme o contexto. Ctrl+A seleciona texto durante edição e a grade
  inteira durante seleção interna. Negrito/itálico/sublinhado e undo/redo
  textual usam o cursor/documento Qt. Colagem na célula é texto literal,
  incluindo quebras de linha; não interpreta HTML externo como estrutura.
- Mudar o foco para um controle lateral conserva célula, cursor e rascunho.
  Clique fora, troca de página, substituição válida do documento, salvar e
  fechar concluem a sessão. Perda de grab/desativação da janela libera o
  gesto de seleção. Um documento inválido é recusado antes de destruir a
  cena ou o texto ativo.
- Snapshots incluem o rascunho válido da célula ativa; a recuperação pode
  salvá-lo sem encerrar a sessão nem modificar o pacote original. Salvamento
  manual e histórico básico preservam tabelas, células e suas identidades.
  A sessão antiga termina antes de trocar contexto/provedor de assets.
- O cache de cenas contabiliza também documentos de células e HTML retido.
  Tabelas do organograma são reconhecidas como arte do quadro; seus planos
  e recortes de conectores usam os mesmos critérios já existentes.
- Os limites de HTML por célula, tabela e documento continuam ativos.
  O orçamento considera outras tabelas já editadas na cena e páginas
  inativas. Uma entrada excessiva restaura o último texto aceito e informa
  o limite; não publica parcialmente o conteúdo.

Não existe `scene.clear()` por caractere. Ao publicar uma célula, somente seu
documento e métricas são reconstruídos, preservando os demais documentos e
o layout da tabela. Limpar um intervalo valida/publica o lote inteiro e
registra uma única ação de histórico.

## Verificação antes e depois

Antes de alterar a produção, foram registrados hashes de 432 arquivos em
`referencia.json` e executados os **209 testes anteriores**, todos aprovados.
Depois, a mesma regressão passou novamente. A auditoria encontrou os **331
assets de referência inalterados**, inclusive fontes, ícones e modelos.
Alterações anteriores das etapas 01–03 foram preservadas.

| Verificação final | Testes distintos | Resultado |
|---|---:|---|
| Regressão do editor e contratos existentes | 209 | Passaram antes e depois |
| Dados, persistência, protótipo e publicação de recuperação | 62 | Passaram |
| Renderer, variáveis e saída | 27 | Passaram nas escalas Qt 1 e 2 |
| Canvas, sessão, eventos e recuperação ativa | 25 | Passaram nas escalas Qt 1 e 2 |

São **323 testes distintos**; repetir as escalas não aumenta essa contagem.
Os testes novos exercitam eventos nativos de mouse/teclado e composição
Unicode, foco no painel, zoom/rotação, mesclagens, Esc/Delete/Tab/setas,
Ctrl+S, gesto interrompido, limite de conteúdo, histórico, verso e quadro.
Recuperação/salvamento com texto inacabado foram testados em pacotes públicos
e totalmente protegidos, exigindo original intacto antes do salvamento manual.

Também há comparações exatas de pixels entre canvas e renderer sem overlays,
entre pintura parcial/completa e entre célula ativa/inativa com fonte/cor e
alinhamento próprios, retirando apenas o cursor da comparação. Exceções de
callbacks Qt e descarte tardio de objetos fazem o teste falhar.

Os testes rodaram em Linux, Qt offscreen. Não substituem teste manual de
touchpad/IME real nem demonstram identidade de pixels no Windows.

## Desempenho: 800 células

O recurso não existia antes desta etapa. A comparação abaixo é entre a
implementação inicial da etapa 04 e sua pintura por região, **não** uma
comparação de tabelas em duas versões públicas. O mesmo instrumento/fixture
foi usado sequencialmente, com duas preparações e vinte amostras por caso.
Escala Qt 1, janela solicitada 1280 × 800, viewport efetivo 664 × 604.
Nenhuma suíte pesada foi executada em paralelo às medições válidas.

| Operação | Mediana inicial (ms) | Mediana final (ms) | p95 inicial → final (ms) |
|---|---:|---:|---:|
| Pintar a tabela inteira retida | 47,39 | 46,30 | 62,88 → 52,23 |
| Pintar a região de uma célula | 38,87 | 3,54 | 43,34 → 4,55 |
| Selecionar/mover com eventos da janela | 23,50 | 24,21 | 47,31 → 47,46 |
| Digitar um caractere com eventos da janela | 24,09 | 23,69 | 77,18 → 50,74 |
| Checkpoint de célula, histórico e eventos | 190,94 | 193,58 | 223,43 → 217,76 |

A pintura parcial ficou aproximadamente **11 vezes mais rápida** (redução
de 90,9%). O item solicita a região exposta detalhada ao Qt e deixa de pintar
textos/fundos das células fora dela. Ao expor a tabela inteira, usa o caminho
integral sem consultar a interseção de cada célula. A pintura de exportação
continua integral, com o mesmo comportamento padrão do renderer.

A digitação completa ficou praticamente igual. Esse ganho local de pintura
não deve ser apresentado como ganho de 11 vezes na digitação ou na janela
inteira: os eventos, layout textual nativo e atualização da view continuam
fazendo parte dessas operações. O benchmark exige que digitar não crie
snapshots por tecla e que documentos não afetados conservem suas identidades.

### Resultados piores e custo que permanece

Selecionar/mover ficou 0,71 ms acima da mediana inicial (+3,0%); checkpoint
ficou 2,63 ms acima (+1,4%). O p95 do movimento praticamente não mudou e o
do checkpoint caiu. Essas pequenas diferenças não comprovam uma regressão
causal; não foi identificada uma nova etapa específica que as explique.

O custo absoluto do checkpoint, perto de 194 ms nesta tabela de 800 células,
permanece relevante: inclui validação, coleta de campos e captura completa
do documento/histórico. Essa captura já existia na primeira implementação
medida. Não foi removida para obter um número menor. Otimizar sua captura e
restauração com equivalência comprovada pertence à etapa 06; por enquanto,
o fallback completo preserva conteúdo e identidades. Undo/redo global pode
reconstruir a cena; o undo textual local não precisa fazê-lo.

Uma tentativa intermediária de evitar `prepareGeometryChange()` quando o
deslocamento vertical não mudasse apresentou digitação com mediana de
52,57 ms. A tentativa foi retirada e os 25 testes repetidos nas duas escalas.
A rodada final voltou a 23,69 ms. Não há diagnóstico suficiente para
atribuir a diferença a um detalhe interno específico do Qt; o tratamento
anterior, validado, foi mantido. As evidências desse experimento ficam locais.

## Continuidade e limites desta entrega

- Etapa 05: botão Elementos → Tabela, inserção pública, painel lateral,
  medidas, tipografia, estilos e operações estruturais/clipboard de intervalos.
- Etapa 06: cópia/duplicação com identidades novas, agrupamento e integração
  completa das camadas, geometria e caminhos de histórico. Nesta etapa 04,
  copiar/duplicar objetos que contenham tabela é recusado, preservando o
  comportamento dos demais objetos e impedindo que a tabela seja descartada.
- Etapas 07/08: matriz completa de organograma/exportações/proteção,
  regressão final de desempenho, ajuda e revisão visual.

Não foi renomeado o menu Formas nem adicionado um painel incompleto. A
edição básica está disponível ao abrir documentos v6 contendo tabelas;
modelos existentes sem tabelas continuam no seu fluxo anterior.

## Instrumentos e evidências locais

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output docs/implementacao_tabelas/etapa-04/regressoes-depois.log
.venv/bin/python tests/performance/run_table_data_checks.py --output docs/implementacao_tabelas/etapa-04/dados-persistencia.log
.venv/bin/python tests/performance/run_table_render_checks.py --output docs/implementacao_tabelas/etapa-04
.venv/bin/python tests/performance/run_table_canvas_checks.py --output docs/implementacao_tabelas/etapa-04
.venv/bin/python tests/performance/benchmark_table_canvas.py --output docs/implementacao_tabelas/etapa-04/desempenho-depois-recorte.json
```

Logs, referência, amostras e experimento em JSON ficam nesta pasta,
ignorados pelo Git. O benchmark registra hashes dos fontes/instrumento e
da especificação da fixture, tempos brutos e RSS do processo inteiro.
Os arquivos MD/PY são versionáveis. Não houve commit, publicação ou
alteração de pacotes/assets distribuídos.
