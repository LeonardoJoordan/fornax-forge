# Tabelas — etapa 02: contrato, operações e persistência

09/10/2026. **Etapa concluída.** Tabelas têm estrutura persistente própria,
validação e alterações atômicas em dados puros. Os pacotes e snapshots
preservam o conteúdo; a integração de desenho começa na etapa 03.
O [contrato técnico](CONTRATO.md) registra os campos e regras para essa continuidade.

## Entrega

- `core/table_model.py`: tabela, células, mesclagens, estilos e fronteiras
  canônicas; criação, duplicação, texto/formatação, medidas, inserção,
  remoção, mesclagem e divisão. As alterações retornam cópias validadas;
  erro mantém a entrada intacta. O módulo não importa Qt, inclusive
  transitivamente, conforme verificação em processo novo.
- `core/model_document.py`: coleção `tables` nas páginas/quadro, schema 6,
  validação antes da cópia, campos de células na reconciliação e helper
  `add_model_table`. Modelos 3/4/5 sem tabelas continuam compatíveis;
  modelos v6 não sofrem downgrade ao remover a última tabela ou organograma.
- `core/document_layers.py` e `features/editor/model_adapter.py`: tipo
  `table`, ordem de camadas e preparação de identidade de camada.
- `core/organogram.py`: preservação da versão, coleção vazia e limites de
  arte calculados pelas medidas das tabelas, incluindo contorno e rotação.
- `core/text_safety.py`: extração das regras textuais existentes, mantendo
  as funções públicas de `core/html_utils.py` e `TextOnlyDocument`.
  A parte de dados pode usar a mesma proteção sem carregar Qt.
- `core/json_limits.py`: compartilhamento dos tetos existentes do contêiner.
  Os valores, versões do contêiner, criptografia e protocolo de publicação
  não foram alterados.
- Editor, renderizadores e workspace: barreiras temporárias para impedir
  abertura com perda de conteúdo ou desenho parcial enquanto os consumidores
  não reconhecem tabelas. O workspace mostra o aviso e não abre o editor.

## Regras e limites verificados

Índices inteiros, números finitos, identidade, cobertura completa,
mesclagens sem sobreposição, medidas positivas, estilos e HTML seguro
são obrigatórios. Campos de seleção/cursor e recursos externos são recusados.
Largura/altura são derivadas das listas de medidas, sem geometria duplicada.

Limites iniciais: 100 linhas/colunas, 1.000 posições por tabela, 20 tabelas
e 2.000 posições por documento; HTML de 32 KiB por célula, 512 KiB por
tabela e 1 MiB no documento. Mesclagem não contorna a contagem de posições.
A entrada inteira também respeita 8 MiB de JSON, 100.000 elementos e
profundidade 64. Os testes exercitam limites e valores acima deles.
Essas contagens não multiplicam tabelas pelo número de cartões repetidos
no organograma. São limites iniciais conservadores; fluidez no canvas
será verificada com sua implementação e na etapa 08.

Mesclar conserva a âncora superior esquerda e reúne conteúdo em ordem de
leitura, preservando negrito, itálico, sublinhado e estilos próprios do texto.
Dividir mantém o conteúdo reunido na âncora e deixa as outras células vazias.
Inserir dentro de uma mesclagem expande seu alcance; remover a âncora
preserva identidade e conteúdo numa parte sobrevivente. As fronteiras
internas ficam ocultas, com estilos preservados para a divisão.

Os testes iniciais identificaram e corrigiram a perda de estilo de uma
divisa ao inserir/remover um intervalo e o descarte de tabelas numa entrada
aninhada que declarasse schema 3. O orçamento de mesclagem também pode
recusar um conteúdo muito grande, sem aplicar uma alteração parcial.

## Validação

| Bateria | Antes | Depois |
|---|---|---|
| Regressão existente: 19 módulos | 209 testes aprovados | Os mesmos 209 aprovados |
| Contrato e operações de tabelas | Recurso inexistente | 22 testes aprovados |
| Persistência/compatibilidade de tabelas | Recurso inexistente | 17 testes aprovados |
| Protótipo de layout da etapa 01 | 13 já aprovados na etapa 01 | 13 aprovados novamente |
| Publicação/recuperação de pacotes | Contratos existentes | 10 testes aprovados |

O runner complementar soma **62 testes**, dos quais **39 são novos** nesta
etapa. As repetições intermediárias não aumentam a quantidade de testes distintos.
Os runners isolam preferências e dados, e falhas em callbacks Qt também
reprovam; a suíte de persistência processa eventos e `DeferredDelete`.

Cobertura adicional:

- Quatro casos sintéticos da etapa 00 convertidos para v6 e reabertos:
  boletim, escala, mesclagens e frente/verso.
- JSON, adaptação e substituição de páginas/quadro com equivalência das
  tabelas, campos, medidas, identidades e estilos.
- Pacotes públicos, protegidos integralmente e com assinaturas protegidas;
  snapshots laterais nos três modos, mantendo os bytes do original.
- Backup e falhas de gravação/publicação; texto de célula sem estado da UI
  no JSON. A proteção total mantém o documento fora da área pública do ZIP.
- Leitor anterior executado em processo isolado contra sua cópia de fonte
  capturada antes das alterações: recusou schema 6. O hash do pacote original
  permaneceu idêntico. Esse teste depende de evidência local ignorada e é
  marcado como skip quando essa referência não existe em outro checkout.
- Sequência determinística de 70 operações e variação das posições legais
  de inserção/remoção, conferindo cobertura e independência da entrada.
- Recusa controlada no workspace/editor/renderizadores, preservando a cena
  anterior e sem abrir uma janela que possa salvar conteúdo incompleto.

Comandos da rodada final:

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output docs/implementacao_tabelas/etapa-02/regressoes-depois.log
.venv/bin/python tests/performance/run_table_data_checks.py --output docs/implementacao_tabelas/etapa-02/testes-complementares.log
.venv/bin/python tests/performance/benchmark_table_data.py --reference-source docs/implementacao_tabelas/etapa-02/model_document-anterior.txt --output docs/implementacao_tabelas/etapa-02/dados-antes.json
.venv/bin/python tests/performance/benchmark_table_data.py --output docs/implementacao_tabelas/etapa-02/dados-depois.json
```

A regressão anterior foi executada antes de modificar os fontes, em
`regressoes-antes.log`. A comparação de tempo da normalização antiga usa
uma reconstrução isolada do módulo capturado, com o mesmo hash de entrada;
não é uma execução anterior de tabelas, que ainda não existiam.

## Referência de desempenho dos dados

Linux, Python da `.venv`, duas preparações e vinte amostras por caso,
executadas sem suítes pesadas concorrentes. Valores da última rodada com
os fontes finais; mediana e p95 em milissegundos. São operações síncronas
de dados, sem pintura, interação no canvas ou exportação em lote.

| Operação | Mediana | p95 |
|---|---:|---:|
| Normalizar v4 com 60 textos — referência anterior | 1,325 | 1,830 |
| Normalizar o mesmo v4 — atual | 1,026 | 1,145 |
| Validar tabela com 800 posições | 14,895 | 20,070 |
| Alterar uma célula na tabela de 800 | 38,364 | 51,679 |
| Inserir uma linha na tabela de 800 | 48,464 | 55,316 |
| Mesclar 2 × 2 na tabela de 800 | 35,910 | 47,367 |
| Dividir 2 × 2 na tabela de 800 | 41,140 | 50,846 |
| Normalizar v6 com 800 células e 60 textos | 170,977 | 184,737 |

A diferença inferior a 0,3 ms no v4 não fundamenta uma promessa de melhoria
de velocidade. Os casos novos não têm um equivalente anterior para
calcular ganho percentual. O pico de alocação Python medido separadamente
ficou em cerca de 82 KiB para validar, 402 KiB para alterar texto e 725 KiB
para inserir linha; não representa a memória total do aplicativo ou do Qt.

O custo de 171 ms da normalização completa merece atenção nas próximas
etapas: ela confere o orçamento do documento, copia dados e valida novamente
ao reconciliar campos. As operações estruturais também validam antes e
depois da cópia. Essas garantias devem permanecer; não conectar a
normalização completa ou uma reconstrução da cena a cada tecla. Usar a
sessão temporária da célula e sincronização com checkpoints coerentes,
conforme o plano, antes de avaliar otimizações adicionais.

## Preservação e continuidade

A auditoria conferiu **331 assets existentes**, todos com os mesmos hashes.
Nenhum arquivo da referência desapareceu. Somente dez arquivos existentes
de produção foram alterados, além dos três módulos novos; os modelos
pessoais e prontos foram preservados. Logs, resultados JSON e fonte histórica
continuam ignorados pelo Git; relatórios, contrato e instrumentos são os
artefatos destinados ao versionamento.

Ainda não existe tabela utilizável na interface. Fontes/placeholder na
renderização, overflow, desenho compartilhado e dispatch pertencem à etapa
03. Seleção, foco, serialização da cena, histórico e painel seguem nas
etapas 04–06. Recuperação com célula ativa e todos os caminhos de saída
serão verificados na etapa 07. As barreiras temporárias só devem ser
retiradas quando seus respectivos consumidores preservarem o contrato.
