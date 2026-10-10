# Tabelas — etapa 08 e fechamento da implementação

09/10/2026. Etapas 00 a 08 concluídas no ambiente disponível: Linux,
Python 3.13, PySide6 6.11 e Qt offscreen. Os testes usam documentos,
biblioteca, preferências e credenciais sintéticos.

## Resultado para o usuário

O menu **Elementos**, que substitui o nome Formas, conserva retângulo,
elipse e linha e oferece **Tabela**. A tabela é editável no canvas, com
seleção de células/intervalos e um painel próprio abaixo de Texto.

- Inserir/remover linhas e colunas, mesclar/separar células e ajustar
  medidas em milímetros.
- Formatar texto, alinhamentos horizontal/vertical, entrelinha, quebra
  automática, espaço interno, preenchimento e transparência.
- Aplicar contornos externos, internos ou todos, com cor, espessura e
  opacidade, mantendo bordas compartilhadas entre células.
- Usar placeholders nas células, preservando a formatação do modelo e
  recebendo os dados de cada registro da planilha principal.
- Copiar/colar intervalos por TSV/MIME, editar texto por contexto e usar
  os comandos de camadas, grupos, transformações, cópia e histórico.
- Salvar/reabrir modelos, usar tabelas no cartão ou como desenho
  complementar do organograma e gerar PNG/PDF pelos fluxos existentes,
  incluindo frente/verso, múltiplos por folha e ladrilhos.

O documento usa versão 6 quando contém tabelas. Os leitores atuais
continuam aceitando versões anteriores; aplicações antigas não entendem
a nova versão. A versão do documento é distinta da versão do contêiner
`.fornax`. Os mecanismos de proteção/recuperação permanecem ativos.

## Mudanças desta etapa

**14 artigos completos**, TBL-01 a TBL-14, na categoria **Tabelas gráficas
e células**. Cada artigo segue as sete seções da ajuda: definição,
finalidade, instruções, exemplo, dica, particularidades/limites e links.
Cobrem seleção/edição, estrutura, mesclagem, medidas, texto,
preenchimento, contornos, placeholders, colagem, atalhos, objeto/camadas,
organograma, overflow e um boletim escolar de 6 × 4 células.

O exemplo explica que uma linha de dados alimenta o boletim de um aluno;
as linhas gráficas representam disciplinas. Ele não confunde uma tabela
do desenho com a planilha de dados da janela principal.

O catálogo passou de **402 tópicos / 208 artigos** para **416 tópicos /
222 artigos**. FOR-01 mantém seu identificador e atende às buscas por
**Formas** e **Elementos**. Foram atualizados os artigos relacionados e
o inventário, sem alterar a pesquisa em memória nem o fluxo da central.
Os novos textos são incluídos pela seleção de recursos de distribuição.

Inglês e espanhol receberam **114 mensagens por idioma**, totalizando
1.033 traduções concluídas em cada catálogo. Os `.qm` foram recompilados
e testados. Controles, tooltips, avisos e mensagens operacionais fixas
das tabelas acompanham o idioma. Campos de interpolação e chaves das
operações foram preservados. Diagnósticos dinâmicos de baixo nível
podem continuar em português; os artigos também permanecem em português,
seguindo o fallback já existente.

No código de produção, esta etapa altera somente `table_panel.py` e
`table_controller.py`: chamadas traduzíveis com literais para extração e
tradução das mensagens fixas no painel. Não altera os algoritmos de
layout, pintura, histórico, geometria, criptografia ou publicação.
A comparação de hashes de 439 fontes/assets anteriores registra 12
arquivos alterados: os dois módulos, seis arquivos da ajuda e quatro
catálogos TS/QM. Fontes, ícones e modelos existentes foram preservados.

## Verificação final

A referência da etapa 07 tinha 389 testes distintos passando. Antes de
editar a ajuda, os 15 testes existentes da central também passaram e
foram guardadas capturas do painel nos dois temas. Após as últimas
mudanças, todos os conjuntos abaixo passaram novamente.

| Conjunto | Testes distintos |
|---|---:|
| Regressões anteriores e contratos de desempenho do editor | 209 |
| Dados, persistência, protótipo e publicação de recuperação | 62 |
| Renderer, texto variável e fidelidade de saída | 27 |
| Canvas e edição de células | 25 |
| Operações de intervalos | 11 |
| Controles Texto/Tabela | 16 |
| Objetos, camadas, histórico e páginas | 20 |
| Integração de produto | 10 |
| Recuperação e transporte protegido | 9 |
| Central de ajuda existente | 15 |
| Artigos, busca e navegação de tabelas | 3 |
| Catálogos TS/QM e controles traduzidos | 3 |
| **Total** | **410** |

Repetições por tema/escala não entram como testes distintos. Foram
conferidos 25 logs finais, retorno dos runners e ausência de tracebacks,
incluindo exceções em callbacks Qt. Compilação Python e `git diff --check`
também passaram. A cobertura inclui exportações reais, PDF vetorial,
remontagem de ladrilhos, placeholders em negrito, texto ativo, limites e
recusas atômicas, biblioteca e autorização expirada.

### Revisão visual

Geradas **40 capturas finais**: em cada escala Qt 1/2, doze telas do
editor (três idiomas × dois temas × zooms 0,5/1,5), seis painéis Tabela e
duas telas de ajuda. A fonte Inter distribuída foi carregada e uma célula
usa DejaVu Sans. Os metadados registram fontes resolvidas, backend e
ausência de erros de callbacks.

Foram inspecionadas amostras dos dois temas/escalas, controles em inglês
e espanhol, zooms distintos e o artigo do boletim. Os controles de tabela
mantêm títulos centralizados, divisores, espaçamentos e legibilidade no
padrão do editor. Os placeholders longos exibem o indicador de overflow;
o zoom alto naturalmente mostra apenas parte da tabela no viewport.

**Validação nativa indisponível:** a tentativa de abrir Qt/xcb não
conseguiu conectar ao display `:0` e apresentou diagnóstico do plugin
xcb. Não foi executado teste manual de foco/touchpad no desktop Linux.
Não há Windows disponível neste ambiente. Capturas offscreen não
comprovam igualdade de fontes/pixels nem comportamento nativo entre
sistemas; essas verificações continuam necessárias antes de distribuição.

## Desempenho, ganhos e custos restantes

As medições completas mais recentes estão nos relatórios das
[etapas 06](../etapa-06/RELATORIO.md) e
[07](../etapa-07/RELATORIO.md). A etapa 08 não reescreve os algoritmos
medidos nem apresenta um novo ganho de velocidade. Os contratos que
evitam reconstruções desnecessárias passaram na rodada final. Os tempos
das suítes executadas em paralelo não são usados como benchmark.

| Cenário medido anteriormente | Resultado e interpretação |
|---|---|
| Checkpoint sem alteração, tabela de 800 células | 49,17 → 8,87 ms na etapa 06, cerca de 82% menor. A comparação dos dados persistentes evita normalização/cópia redundantes. |
| Undo + redo, 800 células | Cerca de 1,56 s por ciclo; restauração completa continua sendo usada. |
| Ações de painel com histórico, 800 células | Cerca de 0,87–1,32 s, conforme a operação; ainda podem ser perceptivelmente lentas. |
| Prévia de 1.000 cartões em 20 conjuntos | Cerca de 0,98–1,00 s nas duas rodadas após a etapa 07, com tabela de uma célula. Não comprova o mesmo tempo para cartões densos. |

### Pioras registradas

Na etapa 06, publicar uma célula com histórico passou de 156,13 para
182,77 ms, com 171,17 ms na repetição. A leitura adicional dos dados
persistentes é uma causa provável; ela detecta mudanças que uma revisão
isolada poderia omitir. Colagem e medidas de colunas também apresentaram
pequenas pioras. Não foram removidas validações para reduzir esses custos.

As primeiras medidas de pintura pioraram, mas uma repetição isolada
aproximou os resultados da referência; o caminho de pintura não havia
mudado. Não se atribui toda variação a uma falha de código ou a segurança.

Na etapa 07, movimento e consulta de geometria passaram de 0,143 para
0,170 ms, com 0,193 ms na repetição. A correção incluiu limites da tabela
e contorno rotacionado antes ignorados. Sem tabela complementar, a
consulta passou de 0,052 para aproximadamente 0,11 ms; identificação de
tabelas/chave geométrica adicionam trabalho, sem causa quantitativa
inteiramente isolada. Os resultados anteriores completos, p95 e memória
permanecem nos relatórios, inclusive os números desfavoráveis.

## Limites conhecidos

- Até 100 linhas/colunas, 1.000 posições por tabela, 20 tabelas e 2.000
  posições por documento. Mesclar não reduz o orçamento de posições.
- HTML limitado a 32 KiB por célula, 512 KiB por tabela e 1 MiB por
  documento. Texto, formatação e estrutura passam por validação.
- Células aceitam texto; recursos externos, imagens e tabelas aninhadas
  são recusados. Não há fórmulas, cores condicionais ou paginação própria.
- Excesso de texto é recortado visualmente, conservando o conteúdo salvo.
  Fonte/altura não mudam automaticamente; editor e geração avisam.
- O cenário de 1.000 cartões usa 20 conjuntos e tabela de uma célula.
  O editor compartilha o desenho do cartão; isso não equivale a 1.000
  tabelas densas ou blocos individuais. A geração ainda desenha os cartões.
- Histórico denso continua usando reconstrução completa. O diagnóstico
  de memória da etapa 06 demonstrou descarte de raízes/layouts antigos
  após `DeferredDelete`; RSS sozinho não comprova vazamento permanente
  nem garante memória baixa em qualquer sessão nativa.

## Reprodução e entrega

Os comandos de todas as suítes estão em
[tests/performance/README.md](../../../tests/performance/README.md).
As ferramentas finais são `run_table_help_checks.py` e
`table_final_evidence.py`, além dos runners de dados, renderização,
canvas, controles, integração, produto e regressões anteriores.

Logs, capturas, hashes e JSON de medição ficam localmente em
`docs/implementacao_tabelas/etapa-08/`, ignorados pelo Git conforme a
preferência do projeto. Entram no versionamento artigos, catálogos,
testes, instrumentos e documentação. Não foram instaladas dependências,
alteradas licenças, publicados pacotes ou modificados modelos pessoais.

## Ajustes posteriores — interação no canvas

09/10/2026, após os testes manuais do usuário:

- A tabela agora usa as oito alças de canto/lateral já utilizadas pelas
  formas, com cor do tema, proporção, magnetismo, ancoragem rotacionada e
  histórico. A seleção múltipla conserva a moldura conjunta; bloqueio e
  pintura sem overlays ocultam as alças.
- Primeiro clique em qualquer parte seleciona o objeto, inclusive com
  preenchimento transparente. Arrastar pelo corpo move a tabela sem
  reconstruir seu layout. Com o objeto selecionado, outro clique escolhe
  a célula; duplo clique/F2/Enter abre o texto. Seleção interna ativa
  continua permitindo arrastar intervalos. Esc retorna ao contexto de
  objeto. Uma tabela nova começa nesse contexto.
- Seções indisponíveis ficam recolhidas e bloqueadas, inclusive durante
  animação ou tentativa programática de expansão. Propriedades considera
  seu conteúdo lateral, independentemente dos controles da barra superior.
  Tabelas complementares do organograma ainda podem mostrar suas
  propriedades de camada quando aplicáveis.
- As alças são estado visual reconhecido pela captura rápida do histórico;
  atributos desconhecidos continuam exigindo o caminho completo. Uma
  regressão inicial demonstrou a perda dessa otimização e foi corrigida.
- Medidas inválidas são recusadas antes de reposicionar a âncora. A célula
  ativa é concluída ao iniciar o redimensionamento, conservando o texto.
- Corrigida também a carga de medidas na barra: sinais dos campos de
  largura/altura usavam a proporção anterior e podiam mostrar ambas iguais.
  A carga bloqueia esses sinais e o arraste pelas alças atualiza as medidas.

Os casos iniciais reproduziram os problemas de clique/arraste, ausência
das alças e painel vazio; outro caso reproduziu a largura incorreta.
Após os ajustes, **341 testes distintos pertinentes passaram**: 209 de
regressão/contratos, 25 de canvas, 11 de intervalos, 16 de controles,
20 de integração, 27 de renderer, 12 novos de interação e 21 de ajuda/idiomas.
Repetições de temas/escalas não aumentam a contagem. Não se trata de uma
nova execução dos 410 testes da rodada de fechamento descrita acima.

Runners de controles/integração/interação cobrem os dois temas e escalas
1/2; canvas/renderer/ajuda cobrem ambas as escalas. Os 24 logs finais foram
verificados, incluindo callbacks Qt. Compilação Python e `git diff --check`
passaram. Capturas sintéticas finais nos dois temas confirmam alças,
painel recolhido e medidas corrigidas. Evidências locais desta correção:
`/tmp/fornax-table-adjustments/`, sem envio de logs ao Git. Continua valendo
a limitação de validação nativa mencionada acima.

## Ajustes posteriores — barra flutuante, seleção e contornos

09/10/2026, protótipo solicitado pelo usuário, mantendo a lateral completa:

- Barra contextual no viewport, com menus de linhas/colunas (inserção de
  uma unidade ou remoção do intervalo), mesclar/separar, alinhamentos e cor
  de preenchimento. Reutiliza `TableController`, preflight e snapshots.
- A barra acompanha posição, zoom, rolagem e rotação sem virar objeto da
  cena ou reconstruir o layout. Mantém tamanho de interface, procura espaço
  acima/abaixo e evita a seleção ativa quando precisa ficar dentro do canvas.
  Em área estreita usa ícones e tooltips; se nem essa versão couber, a lateral
  permanece disponível. Ainda não há arraste manual/fixação da barra.
- Botões preservam o contexto; menus e diálogo de cor conferem a identidade
  do alvo. Texto e cursor são conservados nas operações de formatação; troca
  de tabela/página, bloqueio e seleção múltipla ocultam o contexto inadequado.
- Seleção interna recebe preenchimento suave e perímetro contínuo com cor
  do tema. É transitória e não altera os dados ou a saída sem overlays.
- Contornos compartilhados completam os encontros com meia espessura dos
  traços perpendiculares. Caminhos retidos por cor/opacidade evitam aplicar
  transparência várias vezes na mesma interseção. Mesclagens continuam
  ocultando segmentos internos. Editor, preview e exportação usam a mesma
  pintura; o conteúdo de PDF continua vetorial.
- Ajuda atualizada e um novo tooltip traduzido nos catálogos TS/QM, sem
  substituir os controles laterais existentes.

Os testes iniciais reproduziram ausência de realce, cantos incompletos e
interseções translúcidas inconsistentes. A validação posterior reúne **340
testes distintos**: 209 de regressão/contratos, 25 de canvas, 12 de interação
anterior, 10 novos, 16 de controles, 20 de integração, 27 de renderer e 21
de ajuda/idiomas. As 22 interações novas/anteriores também passaram nos dois
temas e escalas Qt 1/2; repetições não aumentam a contagem. Menus são
acionados por eventos reais Qt, incluindo continuação da digitação.

Capturas sintéticas dos temas claro/escuro foram inspecionadas. Logs e
capturas ficam em `/tmp/fornax-floating-*`; nenhum log é adicionado ao Git.
`git diff --check` e compilação Python passaram. A execução usa Qt offscreen:
posicionamento e foco no desktop nativo/Windows ainda exigem teste manual.

## Ajustes posteriores — encaixe da barra em quatro posições

09/10/2026, refinamento do protótipo:

- Alça de pontinhos com cursor de mão. Ao pressionar e arrastar, os outros
  três destinos aparecem em grafite claro; o destino sob o ponteiro recebe
  destaque adicional. Ao soltar, a barra se encaixa e os destinos desaparecem.
- Posição inicial acima; acima/abaixo usam barra horizontal, esquerda/direita
  usam coluna vertical de ícones com tooltips e os mesmos menus. O lado
  escolhido permanece durante a sessão do editor, acompanhando a tabela,
  o zoom e a rolagem, limitado à área visível do canvas.
- Soltura fora dos destinos, Esc, botão perdido, perda de captura,
  desativação, redimensionamento da janela ou troca de alvo/página encerram
  o arrasto. A barra retorna ao lado anterior em cancelamentos.
- Barra e destinos são widgets do viewport. Não alteram a seleção das
  células, os dados, a cena, o layout da tabela ou o histórico; texto ativo,
  cursor e digitação permanecem disponíveis após o encaixe.
- Ajuda/tooltip traduzido atualizados; nenhuma ferramenta lateral removida.

**109 testes distintos passaram**: 29 de interação/contornos/encaixe (nos
temas claro/escuro e escalas Qt 1/2), 74 de ponteiro/canvas/controles/integração
e 6 de ajuda/idiomas. As repetições da matriz não aumentam a contagem. Os sete
testes novos de encaixe usam eventos de ponteiro e teclado reais do Qt,
inclusive arraste durante a edição e menus na orientação vertical.

Capturas das quatro posições e dos três destinos foram produzidas nos dois
temas e inspecionadas. Evidências em `/tmp/fornax-docking-*`, sem adicionar
logs ao Git. `git diff --check` e compilação Python passaram. Validação Qt
offscreen; o comportamento no desktop nativo continua sujeito a teste manual.

## Ajustes posteriores — transparência e recolhimento da barra

09/10/2026:

- Opacidade da barra reduzida de 100% para 50%, incluindo os controles.
- Botão **−** junto à alça recolhe as ferramentas; vira **+** para expandir.
  Recolhida, somente o botão e a alça ficam visíveis. A extremidade direita
  na horizontal ou inferior na vertical permanece ancorada no mesmo lugar.
- O recolhimento permanece durante a sessão e permite arrastar a barra pelas
  quatro posições. Seleção das células, cursor, foco, dados e histórico são
  preservados. A lateral continua completa.
- Espaçamento do modo compacto ajustado para acomodar o novo botão em um
  viewport estreito, mantendo os tamanhos anteriores dos ícones e botões.
- Ajuda e traduções inglês/espanhol atualizadas.

**38 testes distintos passaram**: 32 de interação/contornos/encaixe/recolhimento
nos temas claro/escuro e escalas Qt 1/2, mais 6 de ajuda/idiomas. Os três novos
testes verificam a ancoragem nas quatro posições, expansão, arraste recolhido,
zoom/seleção, opacidade e digitação com foco preservado. Capturas abertas e
recolhidas nos dois temas foram geradas; as recolhidas horizontal/vertical foram
inspecionadas. Evidências em `/tmp/fornax-collapse-*`, sem adicionar logs ao Git.
Compilação Python e `git diff --check` passaram. Validação em Qt offscreen.

### Correção da transparência solicitada

O efeito geral de 50% na barra foi substituído: botões e alça voltaram a ser
opacos, enquanto fundo, contorno e divisores usam 75% de opacidade, acompanhando
o tema. Os destinos de reposicionamento usam metade da opacidade anterior,
incluindo o destaque do destino sob o ponteiro. Encaixe e recolhimento foram
preservados.

Passaram 24 testes distintos de barra/contornos/ajuda; os 11 de encaixe e
aparência também passaram com escala Qt 2. O teste de aparência verifica os
pixels do fundo (alpha 191/255) e dos botões (255/255) nos dois temas, além de
confirmar que o efeito nos destinos é de 50%. Capturas finais foram inspecionadas;
evidências em `/tmp/fornax-opacity-*`. Validação Qt offscreen e `git diff --check`.

Refinamento dos destinos: fundo cinza ajustado para aproximadamente **25% de
opacidade normalmente e 35% sob o mouse**. Os valores consideram o efeito de
50% já aplicado ao widget do destino. A leitura de pixels compostos confirmou
25,3% / 34,7% (arredondamento de canais de 8 bits); os 11 testes da barra passaram.
Evidências em `/tmp/fornax-target-opacity-*`; `git diff --check` passou.

### Tamanho inicial e seleção visual de alinhamento

- Destinos agora usam aproximadamente **35% / 50% de opacidade** (normal/sob o
  mouse). Opacidade da barra e dos botões preservada.
- Ao inserir uma tabela, cada coluna começa com 30 mm e cada linha com a altura
  mínima para uma linha da fonte padrão, mais espaçamento interno e contorno.
  A medição usa o mesmo documento Qt e DPI lógico da renderização; neste ambiente
  resultou em cerca de 6,18 mm. Conteúdo maior mantém o aviso de excedente e exige
  ajuste manual. Tabelas existentes conservam suas medidas.
- Menus de alinhamento horizontal/vertical mostram faixas de três ícones SVG do
  projeto. A escolha marcada atualiza o ícone da barra, inclusive ao mudar a
  seleção de células; intervalos mistos não indicam uma opção única. Escolher
  novamente a opção atual preserva o destaque. Foco e texto ativo são mantidos.

Passaram **57 testes distintos** de controles, barra, encaixe, ponteiro, idiomas
e ajuda. Os 23 de barra/encaixe/tamanho inicial também passaram no tema claro com
escala Qt 2. Capturas dos seletores nos dois temas foram inspecionadas. Evidências
em `/tmp/fornax-table-defaults-*`; compilação Python e `git diff --check` passaram.
Validação Qt offscreen.

### Aparência dos seletores de alinhamento

Os seletores agora reutilizam as cores, o raio de 8 px e a opacidade de 75%
do fundo/contorno da barra. O conteúdo interno é transparente e os botões
continuam opacos. Margens ajustadas para igualar a espessura: 44 px nas laterais
e 46 px acima/abaixo, neste ambiente. Cantos externos transparentes e sombra
nativa removida para preservar o contorno arredondado.

Passaram 25 testes de barra/encaixe/ajuda. A verificação de pixels nos dois temas
e quatro posições confirma fundo alpha 191/255, botões 255/255, cantos 0/255 e
espessura igual à barra; também passou em escala Qt 2. Capturas foram inspecionadas.
Evidências em `/tmp/fornax-picker-surface-*`; compilação Python e `git diff --check`
passaram. Validação Qt offscreen.

### Orientação dos seletores de alinhamento

Os seletores de ícones agora acompanham o lado da barra: opções em coluna nas
laterais e em linha acima/abaixo, mantendo a abertura próxima ao botão. O tamanho
do menu Qt é atualizado antes de posicioná-lo, evitando conservar as dimensões
da orientação anterior. Passaram os 22 testes da barra/encaixe, incluindo trocas
repetidas de alinhamento nas quatro posições; esse cenário também passou no tema
claro com escala Qt 2. Capturas dos dois temas foram inspecionadas. Evidências em
`/tmp/fornax-picker-orientation-*`; compilação Python e `git diff --check` passaram.

### Destinos de arraste com a barra recolhida

O deslocamento que preserva a extremidade da barra recolhida também era usado
para desenhar os destinos de encaixe, deslocando os destaques para a direita ou
para baixo. Agora os destinos usam as posições da barra completa ao redor da
tabela; somente a barra recolhida mantém sua ancoragem pela extremidade.

A regressão reproduziu a falha antes da correção e passou depois. Compara os
destinos com a barra aberta/recolhida em três cenários de zoom, rotação e posição,
verificando também encaixe, seleção, dados e ausência de alterações no histórico.
Passaram 35 testes distintos nos temas claro/escuro e escalas Qt 1/2. Capturas dos
destinos com a barra recolhida foram inspecionadas. Evidências em
`/tmp/fornax-collapsed-targets-*`; compilação Python e `git diff --check` passaram.
Validação Qt offscreen.

### Destaques de encaixe limitados ao tamanho da tabela

Os destaques horizontais agora usam no máximo a largura da tabela na tela;
os laterais usam no máximo sua altura. Permanecem centralizados no respectivo
eixo e respeitam o viewport. O tamanho real das ferramentas e a ancoragem
da barra recolhida continuam independentes do tamanho do destaque.

A nova regressão falhou antes do ajuste e passou depois. Exercita tabelas
menores/maiores que as ferramentas, as quatro posições e a barra aberta/recolhida,
verificando ausência de sobreposição entre destinos em torno da tabela visível,
encaixe real, seleção e dados preservados, sem gravar histórico. Capturas de
tabela pequena foram conferidas nos dois temas. Evidências em
`/tmp/fornax-target-limits-*`.

Passaram 36 testes distintos nos temas claro/escuro e escalas Qt 1/2, em Qt
offscreen. Compilação Python e `git diff --check` também passaram.

### Reaproveitamento da barra nos contextos aprovados

O encaixe, os destaques, o recolhimento e a aparência foram extraídos para
`features/editor/floating_bar.py`; a tabela mantém seus comandos e comportamento.
Uma segunda barra acompanha somente a seleção atual, fora da cena e dos arquivos:

- Retângulo/círculo: cor do preenchimento, contorno ligado/desligado,
  opacidade geral e máscara. A máscara lista imagens livres; quando ativa,
  o atalho solta as imagens sem apagá-las. O enquadramento usa a lateral existente.
- Seleção múltipla/grupo: somente Agrupar/Desagrupar, seguindo a regra atual.
- Blocos do quadro: somente Conectar a elemento, seguindo a escolha de superior.

Linhas, imagens, textos, assinaturas, conectores e plano de fundo não recebem
barra individual. A lateral permanece disponível. Atalhos acionam os controles
existentes; ações de menus/diálogos verificam o alvo e imagens ainda disponíveis.
Capturar/salvar uma página encerra o arraste sem deixar a barra oculta.

Passaram 87 testes de regressão (tabela, seleção, organograma, histórico, idiomas
e ajuda). A verificação adicional passou em 11 testes no tema claro/escala Qt 2,
incluindo um novo caso de menu de máscara com alvo antigo/imagem retirada: 88
testes distintos no total. Capturas dos dois temas foram inspecionadas.
Traduções EN/ES compiladas, compilação Python e `git diff --check` conferidos.
Evidências locais em `/tmp/fornax-objects-*`; validação Qt offscreen.
