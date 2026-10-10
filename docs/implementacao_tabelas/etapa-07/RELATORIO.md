# Tabelas — etapa 07: integração de produto

09/10/2026. Testes com modelos e credenciais sintéticos, em Linux/offscreen,
Python 3.13 e PySide6 6.11. Modelos pessoais e os 332 assets já existentes
foram preservados.

## Correção aplicada

O cálculo leve do editor de organograma ignorava tabelas complementares.
Uma tabela posicionada fora dos cartões aparecia no desenho/exportação, mas
não entrava no tamanho sugerido do quadro nem nos limites do fundo do editor.
Dois testes novos reproduziram o problema antes da alteração.

`_board_geometry_state` agora inclui posição, rotação, visibilidade, medidas
das linhas/colunas e maior espessura de contorno das tabelas. A expansão do
contorno acontece antes da rotação, seguindo `artwork_bounds`, usado na saída.
O cache de limites inclui esses dados em valores independentes e imutáveis;
movimento, redimensionamento, ocultação e alteração do traço invalidam o
resultado. A geometria da tabela não lê HTML, não chama `to_data` e não
encerra uma célula em edição. As rotas dos conectores continuam sendo
reutilizadas quando só o desenho complementar muda.

A mudança de produção desta etapa está limitada a
`features/editor/organogram_editor.py`. O motor de geração e os mecanismos
de autorização, criptografia e publicação atômica foram mantidos.

## Verificação funcional

| Conjunto | Testes distintos | Evidência |
|---|---:|---|
| Regressões anteriores e contratos do editor | 209 | Referência e resultado após a correção |
| Dados, persistência, protótipo e publicação de recuperação | 62 | Antes/depois |
| Renderer de tabelas | 27 | Antes/depois, escalas 1/2 |
| Canvas e edição de células | 25 | Antes/depois, escalas 1/2 |
| Operações de intervalos | 11 | Antes/depois |
| Controles Texto/Tabela | 16 | Antes/depois, temas claro/escuro, escalas 1/2 |
| Objetos, camadas, histórico e páginas | 20 | Antes/depois, temas claro/escuro, escalas 1/2 |
| Integração de produto desta etapa | 10 | Duas falhas geométricas reproduzidas antes; suíte final nas escalas 1/2 |
| Recuperação e transporte protegido com tabelas | 9 | Suíte final nas escalas 1/2 |

**389 testes distintos**, sem somar repetições de escala/tema. Os runners
verificam retorno, erros de callbacks Qt e descarte dos objetos. As tentativas
iniciais de ajuste das fixtures não entram na contagem final.

### Organograma e fidelidade

- Campo apenas dentro da tabela da Página 1 alimenta os cartões. Registros
  sem informação válida não criam cartões; a prévia sem dados mostra o layout.
- Cenário de **1.000 cartões em 20 conjuntos de 10 × 5**. No editor há
  20 itens de conjunto, compartilhando uma única imagem do cartão; não há
  1.000 tabelas editáveis na cena. Alterar a tabela da Página 1 e retornar
  ao quadro atualiza essa imagem. A prévia real preenche os 1.000 cartões.
- Tabela complementar rotacionada em coordenadas negativas, contorno largo,
  movimento, medidas, rotação e visibilidade: limites do editor iguais aos
  do documento destinado à saída, sem recapturar conteúdo ou refazer rotas.
- As suítes mantêm as verificações de tabelas atrás/à frente do quadro,
  recorte de conectores, campos em negrito e igualdade canvas/renderer.
- A remontagem de ladrilhos contendo cartões e tabela complementar coincide
  **pixel a pixel** com a pintura contínua, com escala e recortes equivalentes.

### Geração e biblioteca

- Formatos existentes **PNG e PDF**, em workers reais: lote de cartões,
  frente/verso, múltiplos por folha e PDF único. Verificados conteúdo de cor,
  dimensões raster e tamanho/número de páginas PDF.
- Organograma inteiro e ladrilhado: PNG, PDF único com várias páginas e
  PDFs separados com coordenadas de planilha no nome. Margens, marcas de
  corte e sobreposição seguem as escolhas e testes existentes de ladrilhos.
- A suíte de renderer mantém o teste de PDF vetorial com texto real, tamanho
  físico, ausência de raster e comparação de posições com rasterização
  Poppler. Antialiasing de outro motor não é tratado como igualdade literal.
- Importar/exportar `.fornax` v6, duplicar e renomear pelos fluxos da janela
  principal, reabrir e desenhar a prévia. O modelo público permanece público;
  as tabelas e o original são preservados pela duplicação/renomeação.
- Miniatura de modelo JSON v6 usa o worker/cache existente; uma revisão
  antiga não publica a miniatura depois que o arquivo muda. A prévia de
  `.fornax` continua usando o caminho existente, sem introduzir cache público
  em disco para conteúdo protegido.

### Proteção e recuperação

- Recuperação da célula ainda em edição nos modos público, proteção de
  assinaturas e proteção total, sem mudar original, histórico ou estado salvo.
- Fechamento/cancelamento com publicação pendente e salvamento manual:
  snapshot antigo descartado, arquivos temporários limpos e texto preservado.
- Alteração externa do original e expiração de autorização antes da
  publicação impedem gravação. O original alterado é conservado; chave e
  snapshot de recuperação são limpos. Pacotes de proteção total não contêm
  documento público no ZIP.
- Uma nova versão da célula substitui o snapshot antigo sem encerrar a
  digitação. Falha de publicação preserva a recuperação anterior e permite
  uma nova tentativa.
- O snapshot de uma geração já autorizada conserva tabelas e assets
  independentes após expiração da sessão. A cópia devolvida ao chamador não
  altera o snapshot; ao fechar, ele limpa seu conteúdo.
- Exportação protegida com senha de transporte e importação com nova senha
  local preservam as tabelas e criam uma identidade nova. As referências de
  assets podem mudar legitimamente ao reempacotar; o teste compara tabelas
  e verifica proteção/assinaturas, sem exigir os mesmos nomes de assets.

Nenhum conteúdo ou chave de modelos pessoais é usado nas evidências. Logs
e JSON de medição permanecem ignorados pelo Git; entram os testes, runners,
documentação e a correção.

## Desempenho

`benchmark_table_product.py`, em processo isolado e sem suítes pesadas
concorrentes: duas preparações, vinte amostras para geometria e cinco para
construção/pintura da prévia de 1.000 cartões a 1.200 pixels. Mesma máquina,
fonte e escala Qt 1. Inclui amostras, mediana/p95, RSS e hashes de
entrada/fontes. As três entradas têm hashes iguais antes/depois.

| Operação | Antes, mediana / p95 (ms) | Depois, mediana / p95 (ms) | Repetição depois, mediana / p95 (ms) |
|---|---:|---:|---:|
| Geometria sem tabela complementar | 0,052 / 0,058 | 0,116 / 0,127 | 0,111 / 0,131 |
| Geometria com tabela complementar de 800 células | 0,061 / 0,076 | 0,057 / 0,060 | 0,069 / 0,091 |
| Movimento da tabela e consulta da geometria | 0,143 / 0,173 | 0,170 / 0,200 | 0,193 / 0,291 |
| Construir e desenhar prévia de 1.000 cartões | 1.055,94 / 1.293,90 | 983,44 / 1.021,55 | 997,91 / 1.010,98 |

RSS ao fim das operações: **158,96 MiB antes / 158,91 MiB depois /
158,87 MiB na repetição**.
É memória residente do processo de teste, não pico nem uma garantia de
memória para qualquer modelo. A referência calcula limites incorretos;
depois o instrumento confirma limites corretos.

### Pioras e interpretação

O movimento seguido do cálculo passou de 0,143 para 0,170 ms, com 0,193 ms
na repetição. A correção
adiciona o cálculo necessário dos limites da tabela e a expansão do contorno
rotacionado, antes ausentes. O custo absoluto permanece abaixo de 0,3 ms
no cenário medido; não se sacrificou conteúdo ou validação para reduzi-lo.

O cenário sem tabela também ficou mais lento nas duas rodadas após a
correção: 0,116 e 0,111 ms, frente a 0,052 ms na referência. Há trabalho
adicional de identificação de tabelas e composição da chave geométrica,
mas a medição não isola quanto disso explica a diferença e quanto depende
do estado da máquina. Trata-se de aproximadamente 0,06 ms a mais numa
consulta, sem evidência de piora perceptível na interação. Registrar a
piora medida, sem inventar uma justificativa de segurança nem descartar
o resultado inteiro como ruído.

A geometria com 800 células variou de 0,057 a 0,069 ms; essa operação lê
medidas/traços, sem percorrer o conteúdo das 800 células. A repetição
isolada confirmou os limites corretos e a reutilização das rotas. Nenhum
desses tempos mede pintura de toda a cena ou atualização completa do painel.

A prévia aparentou ficar mais rápida, mas o renderer não foi alterado nesta
etapa. Essa diferença não é apresentada como ganho provocado pela correção.
O objetivo demonstrado é integrar corretamente o recurso ao produto.

## Limites e próxima etapa

- 1.000 cartões testados com tabela de uma célula e 20 conjuntos, sem
  imagens externas nem 100 conexões. Não equivale a 1.000 blocos individuais
  ou a 1.000 tabelas densas, nem garante o mesmo tempo para esses cenários.
- Testes automáticos em Linux/offscreen. Não houve validação nativa no
  Windows, de impressora, touchpad ou fluxo de foco em desktop real.
- A tabela não calcula fórmulas, não pagina automaticamente e não adiciona
  impressão direta. Geração usa os formatos e decisões de layout existentes.
- A restauração completa do histórico de tabelas densas permanece conforme
  registrado na etapa 06; esta etapa não acrescenta restauração incremental.
- **Etapa 08 concluída:** ajuda, termos visíveis/traduções, revisão visual
  final e fechamento estão no [relatório final](../etapa-08/RELATORIO_FINAL.md).

## Reprodução

```bash
.venv/bin/python tests/performance/run_table_product_checks.py --output /tmp/fornax-tabelas-produto
.venv/bin/python tests/performance/benchmark_table_product.py --output /tmp/fornax-tabelas-produto.json
```

O benchmark deve rodar sozinho. Para a matriz anterior, usar os runners de
dados, renderer, canvas, controles, integração e
`run_regressions.py --include-contracts`, documentados no README de desempenho. As evidências
locais desta etapa ficam em `docs/implementacao_tabelas/etapa-07/`.
