# Tabelas — etapa 03: layout, variáveis e saída

09/10/2026. **Etapa concluída.** As tabelas do contrato v6 agora são
desenhadas na prévia e na geração. O editor ainda recusa sua abertura para
edição, até receber item de cena, sessão de texto e histórico na etapa 04.
Nenhum botão público de inserção de tabela foi habilitado nesta etapa.

## O que foi implementado

- `core/table_layout.py`: medidas derivadas das linhas/colunas, células
  mescladas, área interna descontando cada contorno e espaçamento, quebras,
  alinhamentos e identificação de excesso. Texto não aumenta a tabela.
  O dispositivo de métricas usa 300 DPI fixos e fontes em pontos físicos,
  preservando casas decimais; a convenção das caixas antigas não mudou.
- `core/table_paint.py`: fundos, texto recortado e fronteiras canônicas
  desenhadas uma única vez. A pintura preserva estado do painter, ordem de
  interseções, posição, rotação e opacidade. Não desenha seleção ou avisos
  dentro da imagem/PDF. O futuro item do canvas pode usar a mesma pintura
  local; uma prova com `QGraphicsItem` conferiu essa equivalência.
- `core/table_text.py`: resolução específica de células, reaproveitando a
  inserção segura de texto rico existente. Valor ausente esvazia somente o
  campo; texto fixo, preenchimento e grade permanecem. A prévia sem dados
  mostra placeholders literais. Blocos opcionais, Unicode/offsets UTF-16 e
  placeholders divididos entre trechos são tratados. Negrito, itálico e
  sublinhado do modelo são preservados, somando ênfases da planilha.
- `NativeRenderer`: dispatch de tabelas, classificação estática/dinâmica e
  preservação da ordem de camadas. Tabela com variável não é congelada no
  cache estático. Valores e documentos resolvidos não passam de um registro
  para outro. Layouts/documentos Qt são criados na thread que pinta; o fork
  conserva apenas dados, cache de imagem existente e avisos em dados puros.
- `OrganogramRenderer`: tabelas da Página 1 nos cartões e tabelas do quadro
  nos planos anterior/posterior à camada do organograma. Tabela transparente
  à frente também interrompe conectores; atrás não interrompe. Campos só de
  células contam para reconhecer um cartão preenchido.
- Coleta de fontes e informações do modelo inclui células, verso e quadro.
  O workspace avisa sobre fontes ausentes. Nas tabelas, o alias `Inter` é
  resolvido para a família embutida `Inter 18pt`, inclusive no HTML, sem
  instalar uma substituição global que altere as caixas existentes.
- `core/table_warnings.py` e workers: avisos de excesso no log de geração,
  identificando tabela, célula, face e registro original ou bloco/cartão.
  O cálculo ocorre durante a pintura, sem uma segunda renderização para
  conferir o conteúdo. Os avisos não incluem o valor dos registros.

O workspace abre prévias de pacotes públicos e protegidos v6, configura
campos de células na planilha e permite sua geração. As barreiras temporárias
dos renderizadores foram removidas. As barreiras do editor continuam, para
evitar um salvamento que descarte tabelas enquanto a cena não as suporta.
As regras de cópias e assinaturas da planilha permanecem as existentes.

## Validação

| Bateria | Resultado |
|---|---|
| Regressão existente antes da integração | 209 testes, 19 módulos, aprovados |
| Regressão existente após a integração | Os mesmos 209 aprovados |
| Dados, persistência, protótipo e publicação | 62 testes aprovados |
| Layout/renderer/workspace/workers da etapa 03 | 27 testes novos aprovados |
| Repetição dos 27 testes com escala Qt 2 | Aprovados novamente |

São **298 testes distintos** nas baterias citadas; repetir a escala ou uma
rodada não aumenta essa contagem. Falhas de callbacks Qt também reprovam;
preferências e dados usados pelos instrumentos são temporários.

Entre os contratos verificados estão:

- Geometria conferida por medidas conhecidas, hit testing de mesclagens,
  espaçamento assimétrico, contornos externos/internos e transparência de
  uma divisa sem pintura duplicada.
- Alinhamentos, quebras manuais com quebra automática desligada, fonte
  decimal, texto fixo com variável ausente e ausência de invasão da célula
  vizinha por texto longo.
- Unicode fora do BMP antes de placeholders, ênfase do placeholder mais a
  da planilha e preservação da fonte/tamanho/cor do modelo. Recursos locais
  e remotos inseridos via texto rico não são carregados ou pintados.
- Alternância de registros preenchidos/vazios, independência do documento
  de entrada, cache com tabela estática/dinâmica e avisos sem acumulação no
  fork. A política de ocultar caixas de texto antigas continua igual.
- As quatro especificações sintéticas da etapa 00, frente/verso,
  documentos públicos/protegidos só com tabelas e avisos de fontes ausentes.
- Workers reais de PNG, folha PDF e PDF agrupado protegido, com e sem
  imposição. Os avisos identificam a linha original da planilha.
- Planos do organograma, recorte de conectores por tabela transparente,
  tabela como único conteúdo variável do cartão e saídas PNG/PDF do quadro.

## Fidelidade PNG/PDF

O espécime possui 4 × 4 posições, dez células âncora, duas mesclagens,
conteúdo variável e dois excessos deliberados. Sua página mede
**127 × 72,8133 mm**; a grade ocupa 1440 × 800 unidades lógicas.

Foram gerados PNG a 300 DPI e PDF vetorial por `NativeRenderer.paint_card`.
O Poppler rasterizou o PDF independentemente. As caixas de tinta das dez
células apresentaram diferença máxima de **2 pixels a 300 DPI**, cerca de
0,17 mm, sem alteração das quebras ou posicionamentos de referência. Cores,
mesclagens, recortes e contornos foram conferidos também visualmente nas duas
imagens. Os exemplos sem quebra/com muitas linhas cortam o texto por projeto;
seu conteúdo integral continua nos dados e produz aviso.

O PDF de prova contém texto/fontes reais e nenhuma imagem raster. Seu
MediaBox é **360 × 206 pt**, contra 360 × 206,4 pt esperados: o Qt quantiza a
página em pontos inteiros, uma diferença de 0,141 mm na altura. A escala do
desenho é física (`resolução / 300`), como no PDF do organograma, sem
comprimir a tabela para compensar a quantização da página. A inspeção de
texto confirma palavras e conteúdo, mas não garante extração perfeita de
todos os símbolos especiais por leitores de PDF.

Isso não muda todo o pipeline de exportação do FORNAX: **PDF por item,
folhas e agrupados continuam usando imagens**, como antes. O PDF do
organograma e a prova do painter permitem desenho vetorial. Não prometer
saída vetorial para os outros modos nem igualdade pixel a pixel entre
rasterizadores ou sistemas operacionais diferentes.

## Desempenho e custos

Linux, Python 3.13.13, PySide6/Qt instalado na `.venv`, escala 1, sem suítes
pesadas concorrentes. Tabela sintética de **40 × 20 / 800 células**, fonte
Inter 18pt, 7 pt, pintura em escala 0,25. Duas preparações e vinte amostras
por operação. O protótipo é executado novamente no mesmo processo e ambiente
como referência técnica; não representa tabelas antigas do aplicativo,
que ainda não existiam.

| Operação | Protótipo: mediana / p95 | Produção: mediana / p95 |
|---|---:|---:|
| Construir e pintar pela primeira vez | 399,088 / 455,667 ms | 379,795 / 439,357 ms |
| Pintar um layout já retido | 38,379 / 43,531 ms | 39,650 / 42,562 ms |

A construção ficou próxima da referência. A mediana de repintura ficou
**1,27 ms / 3,3% acima** do protótipo, com p95 menor; essa diferença pequena
não demonstra uma regressão relevante da interface, que ainda não existe.
A produção confere o contrato, copia dados e suporta estilos por fronteira,
resolução de variáveis e avisos, recursos ausentes no protótipo. Não retirar
essas garantias para igualar um número de benchmark.

Na primeira versão desta etapa, a repintura levava **55,585 ms** de mediana,
contra 37,924 ms do protótipo daquela rodada. Havia reconstrução de pontos,
cores e canetas a cada segmento. A versão final prepara os pontos no layout
e reaplica caneta/opacidade somente ao mudar o estilo, mantendo a sequência
das divisas. A mediana caiu para 39,650 ms, cerca de **29%**. Três cenários
com contornos mistos, rotação e transparência mantiveram pixels idênticos
à pintura anterior; o espécime também manteve sua imagem idêntica.

O processo terminou a rodada com aproximadamente **147,5 MiB RSS**, incluindo
Qt, fontes e caches acumulados; isso não mede memória exclusiva da tabela.
Não deduzir daí uma capacidade de dezenas de tabelas ou milhares de cartões.

O renderer monta o layout por tabela/registro ao pintar; uma tabela estática
no prefixo pode usar o cache raster existente. A pintura de um layout retido
serve de referência para o futuro canvas: mover/selecionar não deve reconstruir
800 documentos. Não há cache global de documentos Qt nem valores resolvidos
entre registros. A etapa 04 deve manter dispositivo/layout vivos na cena,
recalcular só o necessário e liberar as referências na thread correta.
Os limites da etapa 02 e as medições gerais anteriores continuam válidos;
a comparação completa de desempenho do editor fica para a etapa 08.

## Reproduzir e continuar

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/tabelas-regressoes.log
.venv/bin/python tests/performance/run_table_data_checks.py --output /tmp/tabelas-dados.log
.venv/bin/python tests/performance/run_table_render_checks.py --output /tmp/tabelas-render
.venv/bin/python tests/performance/run_table_render_evidence.py --output /tmp/tabelas-evidencias
```

Evidências locais desta execução: `referencia.json`, `regressoes-antes.log`,
`regressoes-depois.log`, `dados-persistencia.log`, `renderer-escala-1.log`,
`renderer-escala-2.log`, `evidencias.json`, `custo-inicial.json`, imagens e PDF.
Elas são ignoradas pelo Git. Relatório, plano e instrumentos são versionáveis.

A auditoria conferiu os **331 assets** da referência, todos inalterados, e
nenhum arquivo de produção desapareceu. Oito fontes existentes mudaram na
integração, além dos quatro módulos novos de layout/texto/pintura/avisos.
Não houve mudança de dependências, licença, modelos pessoais/prontos ou
publicação. As alterações locais das etapas anteriores foram preservadas.

Próxima etapa: **04 — canvas e sessão de edição**, com foco, atalhos,
serialização e histórico básico antes de habilitar a inserção na interface.
