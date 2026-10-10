# Tabelas — etapa 01: prova técnica do layout

09/10/2026. **Etapa concluída.** A abordagem escolhida é uma grade de medidas
próprias com texto rico Qt por célula e pintura compartilhada. O protótipo
está isolado nos testes; não acrescenta uma tabela ao menu do FORNAX nem
define seu formato persistente. A próxima etapa é a 02.

## O que foi construído

- Tabela sintética 4 × 4 de **160 × 80 mm**, título mesclado em quatro
  colunas e outra área mesclada 2 × 2. São dez células âncora.
- Texto rico, placeholder literal `{nome}`, quebras manuais/automáticas,
  preenchimentos, cores de texto, contornos, Unicode, alinhamentos horizontal
  e vertical e dois exemplos deliberados de excesso de conteúdo.
- Um item raiz `QGraphicsItem`, sem widgets ou itens gráficos filhos por
  célula. Seleção retangular por arraste, expandida para abranger mesclagens;
  hit testing em coordenadas locais, acompanhando zoom e rotação.
- Pintura comum no item da cena, em imagens e em um PDF vetorial de prova.
  O PDF não substitui nem modifica os caminhos de geração do aplicativo.
- Exercício das quatro especificações da etapa 00, incluindo frente/verso,
  apenas para layout. Não há substituição de campos ou persistência nova.

Arquivos que compõem a prova:

- `tests/performance/table_layout_prototype.py`: os dois motores candidatos,
  medidas, fronteiras, recorte, seleção e pintura.
- `tests/test_table_layout_prototype.py`: treze contratos funcionais.
- `tests/performance/run_table_prototype.py`: observações do candidato Qt,
  comparação de PDF/imagem, capturas e medições de 800 células.

Nenhum arquivo em `core/`, `features/`, `assets/`, requisitos ou `main.py`
foi alterado. Foram conferidos **428 hashes**, sem diferenças ou arquivos
novos de produção. A etapa também não instala dependências, modifica modelos
pessoais, muda a licença ou publica qualquer arquivo.

## Por que não usar QTextTable para a geometria

O candidato foi exercitado no **PySide6/Qt 6.11.0 instalado**, com fonte Inter
incorporada, documento sem margem, colunas de largura fixa, espaçamento entre
células zero e preenchimento/mesclagem pelas APIs próprias do Qt.

| Experimento | Observação |
|---|---|
| Altura automática: uma linha → quarenta linhas na mesma célula | Altura do documento aumentou de **986 para 2.924 unidades**. A altura depende do texto. |
| Altura total fixa | O bloco de quarenta linhas ocupou **2.040 unidades**; definir a altura do quadro não recortou seu conteúdo na altura contratada para a célula. |
| Ciclo HTML do candidato com altura fixa | Texto, título em negrito, cor branca, preenchimento e mesclagem sobreviveram; a altura do documento mudou de **940,875 para 986 unidades**. |
| Layout próprio com texto longo | Retângulos, largura e altura da tabela permaneceram iguais. Apenas o indicador de excesso mudou. |

Esses resultados não significam que o QTextTable seja inadequado para edição
de documentos corridos. Para esta tabela gráfica, porém, seriam necessários
controles adicionais de geometria e recorte por célula. Por isso a prova
adota layout próprio e reaproveita o motor seguro `TextOnlyDocument` e a
configuração de texto existente. Não altera a semântica das caixas de texto.

## Decisões para a implementação

### Medidas e texto

- Usar as unidades atuais do documento: **300 / 25,4 unidades por mm**.
  As listas de larguras/alturas determinam a geometria; o texto não aumenta
  linhas, colunas ou a tabela silenciosamente.
- No protótipo, o dispositivo de métricas tem **300 DPI fixos** e vive tanto
  quanto os documentos de texto. As fontes das especificações são pontos
  físicos; não dependem do DPI do monitor ou da resolução do destino.
- A integração ainda deve mapear o painel de fonte para essa política:
  as caixas existentes usam a convenção atual de métricas a 96 DPI.
  Não transportar uma mesma medida numérica entre essas convenções nem
  mudar globalmente as caixas para fazer a tabela funcionar.
- Espaçamento interno acrescido de metade da espessura do contorno define
  a área de texto. Margens verticais dos parágrafos são zeradas explicitamente
  neste experimento; alinhamento da célula prevalece sobre alinhamentos
  incidentais do HTML. Ênfases, cores individuais e quebras são preservadas.
- Alinhamento vertical usa a altura lógica completa do documento. Conteúdo
  que excede a área começa pelo topo, conservando o início da informação.
  A política não muda entre imagem, canvas e PDF.
- Quebra automática desligada mantém quebras manuais. Conteúdo excedente
  continua íntegro no documento e é recortado apenas na pintura. O protótipo
  registra `overflow_x`/`overflow_y`; o aviso na interface/geração é das
  etapas posteriores, sem exportar um indicador junto ao desenho.

### Fronteiras e mesclagens

- Uma identidade por segmento: horizontal `(h, linha, coluna)` ou vertical
  `(v, linha, coluna)`. A divisa entre vizinhos é desenhada uma vez.
- Guardar também segmentos ocultos por uma mesclagem, permitindo preservar
  seus estilos no futuro. Na grade 4 × 4 são **40 segmentos canônicos**;
  as mesclagens deixam **33 visíveis**.
- O contorno é centrado na divisa; não herda posições dentro/fora ou raio
  de canto das formas. Os fundos são desenhados primeiro, sem suavização
  das divisas entre retângulos, e os contornos são desenhados por último.
  Um teste compara pixels com a ordem das células invertida.
- A prova usa um estilo uniforme de contorno. Sobrescritas por segmento,
  operações atômicas de mesclar/dividir e sua serialização serão definidas
  na etapa 02; esta estrutura ainda não é um contrato de arquivo.

### Custo de edição

- Reutilizar documentos/layouts enquanto conteúdo e geometria não mudarem.
  Pintar, mover ou selecionar não reconstrói o texto; o teste verifica a
  contagem de construções e a ausência de alteração dos dados.
- O protótipo monta todas as células para medir o custo inicial. Isso não
  justifica recriar centenas de documentos a cada tecla ou movimento.
  Invalidar a célula/coluna afetada será parte do renderer e do canvas.
- Nenhum cache persistente de texto resolvido foi criado. Dados de registros,
  autorização, limites e ciclo de vida do editor ainda serão integrados.

## Fidelidade verificada

- Retângulos esperados conferidos em unidades independentes do desenho:
  **160 × 80 mm**, inclusive com cem linhas de texto inseridas numa célula.
- Pintura do item na cena e pintura direta de imagem deram **pixels iguais**
  no mesmo tamanho, com a seleção desativada.
- Imagens de prova em escalas **0,25; 0,5; 1 e 2**, mantendo as mesmas
  medidas e quebras. Uma captura adicional mostra rotação de 30°.
- Hit testing conferido em quatro escalas e rotações **0°, 30°, 90° e −45°**,
  com transformação calculada também pela fórmula de rotação. Arraste real
  via `QTest` em uma view rotacionada selecionou a região esperada e soltou
  a captura do mouse.
- Recorte verificado pixel a pixel: fora da área interna da célula editada,
  o texto excedente não alterou nenhum pixel de vizinhos ou da página.
- PDF rasterizado com **Poppler a 300 DPI**, conferindo dez posições de
  fronteiras, caixas de tinta de cada célula, tamanho da página e texto
  extraído com `pypdf`. A diferença máxima nas caixas de tinta foi de
  **dois pixels (0,17 mm)**, incluindo arredondamento e antialiasing.
- `QPageSize/QPdfWriter` arredondaram a página de prova para pontos inteiros:
  diferenças físicas de **−0,022 mm na largura e −0,103 mm na altura**.
  Isso foi registrado, não declarado como igualdade absoluta. As quebras
  do texto são determinadas antes da pintura pelo dispositivo fixo.
- PNG, PDF rasterizado e imagem rotacionada foram inspecionados visualmente.
  Os trechos longos recortados são casos deliberados de overflow.

## Desempenho inicial — 40 × 20 células

Referência de um recurso novo, sem percentual de ganho contra uma tabela
anterior inexistente. Linux, Qt offscreen, Inter, escala de tela 1, uma tabela
de **180 × 480 mm**, 800 documentos de texto, fonte 7 pt, dados sintéticos.
Imagem pintada em escala 0,25. Duas preparações e vinte amostras por operação,
em sequência, sem profiler.

| Operação | Mediana | p95 |
|---|---:|---:|
| Construir layout e terminar a primeira pintura | **398,69 ms** | 488,33 ms |
| Pintar layout já construído | **37,91 ms** | 45,46 ms |
| Calcular seleção de intervalo | **0,31 ms** | 0,32 ms |

O cálculo de seleção não inclui o gesto ou sua repintura. As pinturas usam
QImage síncrona; não medem latência de mouse ou composição da janela nativa.
O cenário contém textos curtos, sem excessos; texto rico extenso pode custar
mais. Não define um limite de linhas/células para o produto.

O RSS observado passou de **107,30 para 117,70 MiB** ao montar e pintar o
layout inicial. Ao final das rodadas ficou em **143,25 MiB**, incluindo o
alocador e construções repetidas. São observações do processo, não memória
exclusiva das células nem pico, e não certificam ausência de vazamento em
uso prolongado. A integração deverá limitar retenção de layouts e medir
edição incremental, várias tabelas e cenários com conteúdo maior.

## Testes e reprodução

- **13 testes do protótipo**, todos aprovados com escala de tela 1.
- Os mesmos **13 testes** aprovados novamente com escala de tela 2;
  são repetições, não treze testes diferentes adicionais.
- **13 testes existentes** aprovados: seis de proteção contra falhas de
  texto, quatro de fidelidade e três de formatação de placeholders.
- Exceções em callbacks do protótipo são capturadas por `sys.excepthook`;
  os testes processam eventos e `DeferredDelete` antes de concluir.
- Os hashes do produto coincidem com o início da etapa. Não foi necessária
  nova rodada dos quinze benchmarks antigos, pois o produto não mudou.

```bash
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 PYTHONPATH=tests .venv/bin/python -m unittest test_table_layout_prototype -v
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 PYTHONPATH=tests .venv/bin/python -m unittest test_table_layout_prototype -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=tests .venv/bin/python -m unittest test_text_layout_crash test_text_fidelity test_placeholder_formatting -v
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 .venv/bin/python tests/performance/run_table_prototype.py --output docs/implementacao_tabelas/etapa-01
```

Os testes foram executados com pastas temporárias de preferências/dados/cache.
O runner precisa de Poppler e `pypdf`, já disponíveis neste ambiente; não são
novas dependências de execução do FORNAX.

Logs, PNG/PDF, amostras, métricas e hashes ficam **locais, ignorados pelo Git**,
conforme a regra aprovada. Neste diretório estão `testes-resumo.json`,
`candidato-qtexttable.json`, `medidas-layout-proprio.json`, `verificacao-pdf.json`,
`medicoes-800-celulas.json`, `ambiente.json` e `verificacao-producao.json`.
O relatório e os instrumentos permanecem disponíveis para versionamento.

## Próximo passo e limites

A prova sustenta a etapa 02: contrato de dados puros, validação, limites,
operações estruturais e persistência/compatibilidade. Não é necessário retirar
nenhuma das funções solicitadas com base nos resultados desta etapa.

Ainda não foram implementados digitação dentro da célula, painel Tabela,
placeholders resolvidos, undo/redo, proteção/recuperação da tabela, alteração
individual de linha/coluna ou integração no renderer do aplicativo. Não foi
certificado comportamento nativo de touchpad/foco, Windows ou geração de mil
cartões contendo tabelas. Esses critérios continuam nas etapas seguintes.
