# Plano de otimização do editor — FORNAX Forge

Data: 08/10/2026.

**Status: etapas 00 a 10 concluídas. Etapa 11 autorizada em 09/10/2026, com medições, regressão automatizada e relatório final executados. Validação nativa/manual e revisão das observações do canvas pendentes.**

Este plano cobre o editor de modelos, o editor de organograma e seus diálogos.
Cada etapa terá medições e verificações de comportamento antes e depois da
implementação. Alterações no gerador, no contêiner ou em outros componentes
compartilhados só entram quando forem necessárias para os processos descritos,
com verificação de seus consumidores.

As correções e otimizações de undo/redo já presentes no código são o ponto de
partida. As alterações locais existentes serão preservadas. Nenhuma etapa
autoriza modificar regras de agrupamento, disposição das camadas, nomes de
blocos, magnetismo, formatos de arquivo ou o comportamento aprovado pelo usuário.

## 1. Objetivos e critérios gerais

- Reduzir trabalho repetido na interface e na cena.
- Evitar reconstruções completas em operações que alteram poucos objetos.
- Manter os estados completos do histórico e a fidelidade entre editor,
  prévia e arquivo gerado.
- Preservar foco, seleção, máscaras, conectores, camadas, guias e dados.
- Limitar o consumo de memória e liberar recursos ao trocar de documento,
  encerrar uma sessão protegida ou fechar o editor.
- Medir o resultado de cada etapa, sem apresentar suposições como ganhos comprovados.

Uma etapa só estará concluída quando seus testes funcionais passarem, suas
medições forem registradas e as regressões relevantes forem verificadas.
Uma redução no tempo não compensa perda de fidelidade, dados, histórico ou
segurança. Se uma abordagem falhar, corrigir ou retirar apenas a mudança daquela
etapa, preservando as alterações anteriores e as do usuário.

## 2. Método de comparação antes e depois

### 2.1. Condições reproduzíveis

Antes de alterar o comportamento de uma etapa:

1. Criar ou completar os cenários de teste necessários.
2. Rodá-los no código atual, incluindo os testes de comportamento.
3. Salvar resultados brutos, resumo, ambiente e identidade dos arquivos relevantes.
4. Implementar o ajuste.
5. Repetir os mesmos cenários com as mesmas entradas e condições.
6. Comparar desempenho, comportamento e resultado visual.

Os dois resultados devem usar a mesma máquina, versão do Python/PySide6,
fontes, tema, resolução, escala da interface e modo de execução. Registrar
sistema operacional, branch/commit e hashes dos arquivos relevantes: apenas o
commit não identifica as alterações locais ainda não versionadas.

Cada execução começa com uma cópia idêntica do cenário. Colagens, movimentos
e mudanças de propriedades não podem acumular objetos ou modificar a entrada
entre as repetições. Usar diretórios temporários e preferências isoladas;
não editar os modelos pessoais nem as configurações reais do usuário.

Separar abertura/carregamento com cache vazio das operações com cache aquecido.
Nas medições aquecidas, fazer duas repetições de preparação e pelo menos vinte
repetições medidas. Para abertura e gravação, usar processos ou sessões novos
e pelo menos cinco repetições; aumentar a amostra se houver muita variação.
Registrar todas as amostras, mediana, percentil 95 e dispersão.

Medir desempenho sem profiler. Fazer execuções adicionais com instrumentação
para contar chamadas e localizar custos. Os tempos instrumentados do diagnóstico
anterior são exploratórios e não serão usados como referência oficial.

Operações assíncronas devem ser medidas até a conclusão esperada: atualização
da interface, pintura ou publicação do arquivo. Não encerrar o cronômetro
apenas no retorno da função nem incluir pausas fixas artificiais. Usar o mesmo
critério de conclusão e um timeout explícito nas duas versões.

### 2.2. Cenários de referência

| Cenário | Conteúdo e finalidade |
|---|---|
| Página simples | 20 caixas de texto; seleção, colagem, camadas e histórico. |
| Página densa | 60 e 200 objetos mistos; texto, formas, imagens, assinaturas, grupos, máscaras e guias. |
| Modelos prontos | Cartão, certificado, prisma e convite; fidelidade e situações próximas do uso real. |
| Organograma institucional | Exemplo aprovado, com 7 conjuntos e 6 conectores; referência dos conectores e propriedades. |
| Organograma ampliado | Geometria fixa e reproduzível, com 40 e 100 blocos conectados; seleção e arraste individual/coletivo. |
| Conjunto grande | Um conjunto de 40, 400 e até 2.500 cartões, respeitando os limites atuais; desenho com zoom próximo e distante. |
| Frente e verso | Duas páginas distintas, com objetos mascarados, seleção e recursos compartilhados. |
| Documento público/protegido | Assets sintéticos pequenos e grandes; recuperação, autorização e liberação de memória. |

Os cenários maiores precisam caber na memória disponível. Registrar quando
um cenário não puder ser executado e o motivo, sem contabilizá-lo como aprovado.

### 2.3. Evidências a guardar

Durante a implementação, criar uma pasta por etapa em
`docs/desempenho_editor/etapa-XX/`, com:

- `ambiente.json`: condições, versões e identificação do código testado.
- `antes.json` e `depois.json`: amostras, tempos, contagens e memória, quando aplicável.
- `testes-antes.txt` e `testes-depois.txt`: comandos, resultados e falhas encontradas.
- `comparacao.md`: problema, mudança, resultados, diferenças visuais e limitações.
- Capturas, diferenças de imagens e perfis quando forem necessários para explicar o resultado.

Guardar o script reproduzível dos benchmarks em `tests/performance/`.
Esses caminhos serão criados durante a implementação. Não depender de arquivos
em `/tmp` como registro permanente. Usar somente dados sintéticos ou exemplos
públicos; não incluir senhas, chaves, conteúdo protegido ou dados pessoais nas evidências.

### 2.4. Verificação de falhas

- Comparar estados normalizados do documento, identidades, ordem, seleção e histórico.
- Comparar pixels do caminho otimizado com o caminho de referência no mesmo ambiente.
  Para regiões equivalentes, exigir igualdade; diferenças inevitáveis de plataforma
  devem ser identificadas e avaliadas, não ocultadas por tolerâncias amplas.
- Comparar pintura parcial com uma repintura completa de referência.
- Verificar prévia e exportação quando a etapa afetar texto, máscaras, camadas ou geometria.
- Capturar também exceções de callbacks do Qt: elas podem aparecer no log sem
  fazer um teste `unittest` falhar automaticamente.
- Validar o driver de eventos antes de interpretar memória e latência. Sem o
  loop normal do aplicativo, processar `DeferredDelete` explicitamente e aguardar
  pintura/descarte entre trocas de página, para não medir widgets acumulados pelo teste.
- Executar módulos em processos isolados quando necessário para evitar interferência
  entre janelas, temas e preferências de testes anteriores.
- Complementar os testes automatizados com uso manual nos temas claro e escuro,
  com mouse e touchpad, conforme a etapa.

Não usar um limite de milissegundos dependente da máquina como teste funcional.
Contagens de trabalho redundante, estados e imagens são verificações determinísticas;
os tempos servem para avaliar o ganho e possíveis regressões. Resultado dentro
da variação das medições será descrito como inconclusivo.

## 3. Sequência das etapas

| Etapa | Trabalho | Dependência principal | Sensibilidade |
|---|---|---|---|
| 00 | Preparar cenários, medições e referência inicial | Nenhuma | Baixa; sem otimização do comportamento. |
| 01 | Seleção e atualização de painéis em lote | 00 | Baixa a média. |
| 02 | Atualização incremental das camadas | 01 | Média; referências e ordem de objetos. |
| 03 | Conectores, propriedades e recortes compartilhados | 01 | Média a alta; geometria e seleção. |
| 04 | Layout de texto e métricas reutilizáveis | 01 | Alta; fidelidade e edição textual. |
| 05 | Colagem e duplicação sem reconstruir a cena inteira | 02 e 04 | Alta; máscaras, grupos e histórico. |
| 06 | Pintura parcial e cartões visíveis | 03 e 04 | Alta; artefatos visuais. |
| 07 | Evitar captura de histórico sem alterações | 01 a 06 | Alta; cobertura das alterações. |
| 08 | Recuperação automática eficiente | 07 | Alta; dados, concorrência e proteção. |
| 09 | Reutilização das cenas entre páginas | 05 a 08 | Alta; ciclo de vida e invalidação. |
| 10 | Reutilização de miniaturas da galeria | 04 e 07 | Média; invalidação e conteúdo protegido. |
| 11 | Integração, comparação geral e revisão manual | Todas | Verificação final. |

Seguir a ordem da tabela. Medir cada etapa contra seu estado imediatamente
anterior; ao final, comparar também com a referência da etapa 00. Assim, um
ganho anterior não será atribuído novamente a uma etapa posterior.

## Etapa 00 — Preparar a referência e os instrumentos

**Problema:** ainda não há uma referência formal e reproduzível para todos os
processos identificados.

**Trabalho:** preparar os cenários acima, os benchmarks e os testes de comportamento
faltantes. Mapear as formas de modificar o documento, as ligações de sinais da
cena e os caminhos de autorização/fechamento. Registrar a situação atual, incluindo
falhas existentes. Não alterar o funcionamento para melhorar as medições.

**Medições:** seleção, colagem, camadas, movimentos, propriedades, texto, repintura,
histórico sem alterações, recuperação automática, troca de páginas e abertura da galeria.
Medir tempo, chamadas relevantes e memória nos processos que mantêm caches ou cenas.

**Conclusão:** referência salva e scripts reproduzíveis. Cenários funcionais com
falhas anteriores devem ficar identificados; não exigir que o teste de um problema
conhecido passe antes de sua correção, nem escondê-lo do relatório posterior.

**Registro da execução:** [relatório da etapa 00](desempenho_editor/etapa-00/comparacao.md).
Foram concluídos 43 cenários, com 20 amostras por operação aquecida e cinco por
cenário de abertura/recuperação. As regressões passaram antes (201 testes) e
depois (209 testes, com oito contratos novos). Nenhum funcionamento do aplicativo
foi alterado; a identidade dos arquivos foi verificada por hash.

## Etapa 01 — Seleção e painéis em lote

**Problemas:** selecionar tudo atualiza a interface por objeto; a identificação
dos objetos agrupáveis percorre repetidamente a cena; painéis recebem notificações
intermediárias durante operações coletivas.

**Ajustes propostos:** concluir as seleções em lote e sincronizar os painéis uma
vez. Reutilizar o levantamento dos objetos durante a operação. Consolidar as
notificações sem retardar a atualização do estado real do documento.

**Antes/depois:** selecionar tudo em páginas de 20/60/200 objetos; selecionar
grupos, conjuntos e conectores por área e pelas camadas. Contar atualizações dos
painéis e varreduras da cena, além do tempo até a seleção aparecer.

**Verificações:** objetos ocultos/bloqueados, guias, grupos completos, imagens
mascaradas, Ctrl para adicionar/remover seleção, Ctrl+A durante edição de texto,
foco, alças, propriedades e exceções. Preservar a regra atual de seleção e agrupamento.

**Conclusão:** nenhuma atualização dos painéis para seleções intermediárias da
mesma operação; seleção final e controles equivalentes à referência.

**Registro da execução:** [relatório da etapa 01](desempenho_editor/etapa-01/comparacao.md).
Oito cenários medidos antes/depois. A seleção de 200 objetos passou de 52,82 s
para 0,115 s; as atualizações de painéis passaram de 199 para uma. Passaram 222
testes antes e 227 depois, com verificação adicional nos temas claro/escuro e
igualdade exata de estado/pixels em nove cenários por tema. As seleções exclusivas
de blocos/conectores não apresentaram ganho conclusivo de tempo. Uso manual com
mouse/touchpad reais e backend nativo permanece uma verificação complementar.

## Etapa 02 — Reutilizar as linhas de camadas

**Problema:** a lista recria todas as linhas e seus widgets mesmo quando apenas
um objeto precisa ser atualizado.

**Ajustes propostos:** identificar linhas por identidade estável e inserir,
remover ou atualizar somente as afetadas. Preservar os controles, a aparência e
o comportamento existentes. Manter reconstrução completa para abertura de outro
documento ou situações em que a lista não possa ser reconciliada com segurança.

**Antes/depois:** renomear, editar texto, bloquear/ocultar, adicionar/excluir,
agrupar/desagrupar e reordenar em páginas simples e densas. Contar widgets criados,
reconstruções, tempo e memória após ciclos repetidos.

**Verificações:** seleção e rolagem da lista, nomes, ícones, máscara e seus filhos,
camada Organograma, ordem de sobreposição, temas e callbacks ligados ao objeto
correto depois de colagem, undo/redo e remoção. Não mudar a regra de movimentação
dos grupos entre camadas.

**Conclusão:** mudanças locais preservam as linhas não afetadas; nenhuma referência
a um objeto removido permanece utilizável.

**Registro da execução:** [relatório da etapa 02](desempenho_editor/etapa-02/comparacao.md).
Treze cenários medidos antes/depois, com vinte amostras cada. Atualizar a lista
de 200 objetos passou de 1.055,18 ms para 9,86 ms; renomear passou de 324,66 ms
para 23,99 ms. Atualizações sem mudanças não criam linhas; agrupamento e máscaras
atualizam somente os controles cuja estrutura mudou. A regra de movimentação dos
grupos foi preservada. Passaram 235 testes antes e 246 depois; os 19 testes de
camadas passaram nos dois temas, com igualdade exata de documentos e pixels das
linhas em nove cenários por tema. Bloquear não apresentou ganho de tempo. Arraste
com mouse/touchpad e backend nativo continuam como verificação complementar.

## Etapa 03 — Conectores, propriedades e recortes

**Problemas:** o arraste coletivo calcula rotas para posições intermediárias de
cada bloco; alterações de aparência recalculam geometria desnecessariamente;
limites e painéis são atualizados mais de uma vez; cada conector redescobre os
recortes de texto durante pintura e seleção.

**Ajustes propostos:** atualizar os conectores uma vez por atualização visual
do arraste e garantir o resultado final ao soltar/cancelar. Separar alterações
de aparência das de geometria. Compartilhar caminhos, limites e recortes quando
suas entradas permanecerem iguais, com invalidação explícita.

**Antes/depois:** arrastar 1/4/10 blocos em quadros de tamanhos diferentes; alterar
cor, transparência, espessura, raio, portas e contornos; mover/editar textos sobre
conectores. Medir tempo por atualização, percentil 95, cálculos efetivos de rota,
capturas da cena, atualizações dos limites e reconstruções dos recortes.

**Verificações:** limites de entrada/saída, cruzamentos, obstáculos, conectores
para o mesmo superior, seleção por clique/área, textos rotacionados/ocultos,
camadas acima/abaixo, contornos dos cartões/conjuntos, teclado, touchpad,
soltura perdida, Esc e undo/redo.

**Cuidado:** mover um bloco pode alterar rotas de conexões de outros blocos,
pois ele também é um obstáculo. Não restringir o cálculo apenas às conexões
incidentes sem demonstrar equivalência. Espessura, raio, contorno e portas
podem modificar a geometria; cor e transparência devem ser avaliadas separadamente.

**Conclusão:** evitar cálculos para os estados intermediários de uma movimentação
coletiva e manter os caminhos finais, recortes e limites corretos.

**Registro da execução:** [comparação da etapa 03](desempenho_editor/etapa-03/comparacao.md).
Dezoito cenários, com vinte amostras antes/depois: mover dez blocos no quadro de
40 passou de 10.745,55 para 1.421,78 ms; no quadro de 20, de 1.617,37 para
175,39 ms. Os movimentos coletivos calculam uma geometria final por evento,
considerando todos os obstáculos. Aparência, limites e recortes reutilizam
resultados válidos. Passaram 252 testes distintos antes e 259 depois; os 13
contratos do quadro passaram nos dois temas. Os 23 estados por tema preservam
exatamente dados e pixels, com ruído geométrico de ponto flutuante documentado.
O arraste individual não mostrou ganho relevante; o quadro de 40 ainda tem
latência perceptível. O ensaio de 100 blocos foi interrompido por duração e não
é contabilizado como validado. Backend nativo e mouse/touchpad seguem como
verificação complementar.

## Etapa 04 — Reduzir cálculos repetidos de texto

**Problemas:** reconstruções disparam diversos cálculos de posição; métricas
de fonte são consultadas caractere por caractere nas linhas analisadas.

**Ajustes propostos:** consolidar notificações de layout em atualizações em lote;
reutilizar métricas e resultados válidos. Avaliar leitura por trechos de formatação
em vez de por caractere, preservando as fontes efetivamente usadas. Continuar
sincronizando o conteúdo digitado com o documento imediatamente.

**Antes/depois:** digitação e colagem de texto curto/longo, texto com fontes e
ênfases mistas, acentos e caracteres fora do BMP; carregamento de muitas caixas;
redimensionamento individual e coletivo. Contar reconstruções e cálculos de layout,
medir latência de edição e verificar consumo do cache.

**Verificações:** cursor, seleção textual, foco, undo/redo textual, negrito dos
placeholders, entrelinhas, recuo, alinhamento vertical/horizontal, rotação,
contorno, mudança de fonte/largura e renovação das prévias. Comparar os modelos
aprovados no editor, prévia, PNG e PDF renderizado no mesmo ambiente.

**Conclusão:** menos cálculos com conteúdo, geometria e resultado visual iguais
à referência; nenhum atraso ou perda na sincronização do texto.

**Registro da execução:** [comparação da etapa 04](desempenho_editor/etapa-04/comparacao.md).
Quatorze cenários, com vinte amostras nas oito operações aquecidas e cinco nos
seis carregamentos. Reconstruir a configuração de uma caixa passou de 137,72
para 107,35 ms; redimensionar quatro textos, de 682,59 para 517,94 ms. As 540
medições do carregamento de 60 caixas passaram para 120. A leitura de fontes
usa trechos de formatação, preservando a referência por caractere e os offsets
UTF-16; métricas são reutilizadas somente dentro de cada cálculo. O HTML continua
sincronizado imediatamente, sem bloquear sinais do documento. Passaram 266 testes
antes e 272 depois, com os 13 contratos de texto nos dois temas. Os vinte estados
por tema preservam exatamente dados, geometria e pixels, incluindo editor,
prévia, PNG e PDF dos quatro modelos publicados. Redimensionamento individual
não mostrou ganho; a redução de 5,51% na mediana de carregamento de 200 caixas
não foi considerada conclusiva diante da dispersão. Backend nativo e uso manual
continuam como validação complementar. Os modelos prontos não foram alterados.

## Etapa 05 — Inserir cópias sem recriar os objetos existentes

**Problema:** a colagem reconstrói toda a cena e atualiza repetidamente as camadas;
alguns caminhos de duplicação também dependem dessa reconstrução.

**Ajustes propostos:** reutilizar a lógica de construção de objetos para inserir
somente as cópias. Restaurar relações de máscara/grupo, nomes, IDs e ordem antes
de publicar a seleção e atualizar os painéis. Manter snapshots completos e uma
única ação de histórico por operação coletiva.

**Antes/depois:** colar 1/10/50 objetos em páginas com 20/60/200 objetos; colar
entre páginas; duplicar máscaras, grupos e conjuntos com conexões. Medir tempo,
objetos existentes recriados, atualizações de camadas e decodificações de imagens.

**Verificações:** nomes únicos, identidades, assinaturas, conteúdo/formatação,
posição/deslocamento, proporção, links, máscara e filhos, ordem das camadas,
seleção das cópias, clipboard interno, assets públicos/protegidos e undo/redo.
Guardar referências aos wrappers Python durante inserções para evitar falhas do PySide.

**Conclusão:** colagem comum preserva os objetos existentes e produz o mesmo
documento da referência, sem remover a cena inteira.

**Registro da execução:** [comparação da etapa 05](desempenho_editor/etapa-05/comparacao.md).
Quatorze cenários com vinte amostras antes e depois. Colar um item numa página
com 200 objetos passou de 7.981,72 para 308,70 ms; colar cinquenta, de 13.024,09
para 2.587,27 ms. Duplicar uma máscara passou de 839,37 para 123,70 ms. A colagem
mantém os objetos/widgets existentes, constrói somente as cópias, atualiza as
camadas uma vez e publica a seleção final em lote. Nomes, IDs, máscaras, ordem,
assets autorizados, clipboard e uma ação de histórico permanecem verificados.
Passaram 281 testes distintos antes e 287 depois; 21 estados por tema mantêm
documento e pixels exatamente iguais. A validação identificou e corrigiu falhas
de ciclo de vida do papel e das guias; os diagnósticos e o patch reversível estão
guardados. A duplicação simples de imagens embutidas também passou a usar seus
pixels autorizados. A duplicação de um texto isolado variou pouco. Fontes e
modelos prontos não mudaram. Backend nativo e uso prolongado continuam como
verificação complementar.

## Etapa 06 — Pintar somente o necessário

**Problemas:** uma alteração pequena repinta toda a área visível; conjuntos
percorrem e desenham cartões fora da área exposta; as réguas são atualizadas
inclusive quando a pintura não altera escala ou deslocamento.

**Ajustes propostos:** avaliar atualização parcial da view; limitar a pintura
dos conjuntos aos cartões que intersectam a área exposta; atualizar réguas
quando suas entradas mudarem. Manter repintura completa quando a transformação
ou a operação exigir, ou quando for a opção mais eficiente.

**Antes/depois:** pequenas alterações, seleção, arraste, edição de texto,
zoom/pan e rolagem. Usar conjuntos de 40/400/2.500 cartões, observando apenas
parte deles e depois o quadro inteiro. Medir duração das pinturas, cartões e
conectores pintados, atualizações das réguas e latência de interação.

**Verificações:** comparar a pintura parcial com uma repintura completa após
mover, redimensionar, girar, ocultar, excluir e desfazer. Cobrir antialiasing,
contornos grossos, sombras/efeitos existentes, transparência, máscaras, alças,
guias, seleção, textos atravessando conectores, temas e escalas de tela.

**Cuidado:** invalidar tanto a área antiga quanto a nova, incluindo a extensão
dos contornos e realces. A eliminação de cartões fora da tela vale para a pintura
do editor; não pode remover cartões da prévia completa nem da exportação.

**Conclusão:** operações locais pintam menos conteúdo sem rastros ou recortes
indevidos. Se a atualização parcial apresentar artefatos, revisar os limites
e a invalidação antes de torná-la padrão.

**Registro da execução:** [comparação da etapa 06](desempenho_editor/etapa-06/comparacao.md).
Quinze cenários com vinte amostras antes e depois. A visão aproximada de 2.500
cartões passou de 1.117,71 para 13,26 ms, desenhando seis cartões que alcançam
a área visível. A invalidação local passou de 1.075,97 para 1,98 ms, com um
cartão desenhado e área delimitadora de pintura reduzida de 401.056 para 169
pixels lógicos. Rolagem passou de 1.082,79 para 15,55 ms. A view usa atualização
por retângulo delimitador; cartões fora da área exposta são ignorados apenas
na pintura do editor, e réguas evitam pedidos repetidos sem mudança de suas
entradas. A validação corrigiu também a invalidação das alças individuais e
da seleção coletiva, preservando os pixels sem forçar pintura completa.
Passaram 297 testes distintos antes e 302 depois; 152 registros nos dois temas
em escala normal/200%, mais 14 estados complementares, mantêm pixels e documento
exatamente iguais. As 300 amostras de cada versão e os hashes/patch foram
conferidos. Prévia/PNG continuam completos e os 2.500 slots foram preservados;
fontes e modelos prontos não mudaram. O quadro inteiro de 2.500 cartões ainda
leva 929,34 ms nesta rodada. Backend nativo e uso prolongado continuam como
verificação complementar.

## Etapa 07 — Evitar capturas de histórico desnecessárias

**Problemas:** chamadas sem mudanças ainda capturam, normalizam e copiam o
documento; estados novos passam por comparações/serializações redundantes.

**Ajustes propostos:** introduzir rastreamento confiável das alterações para
evitar capturas sem mudança, mantendo snapshots completos. Usar a matriz de
mutações da etapa 00, atualizada pelas etapas anteriores. Conservar a comparação
completa nos caminhos ainda não cobertos ou quando houver dúvida.

**Antes/depois:** repetir snapshots sem alterações; concluir arrastes que voltam
à origem; modificar texto, formas, imagens, guias, máscaras, camadas, páginas,
conjuntos e conectores. Medir captura, cópias, serializações e memória por histórico.

**Verificações:** edição numérica ainda sem `editingFinished`, nova edição depois
de undo invalidando redo, ações coletivas como um passo, alterações globais,
limites de memória/passos e fechamento com aviso de alterações. Verificar também
que seleção, zoom e abertura de painéis não criem estados de documento indevidos.

**Cuidado:** uma alteração fora do rastreamento não pode desaparecer do histórico.
Mudanças externas em assets continuam exigindo a verificação apropriada do recurso;
um contador interno não substitui a identificação do conteúdo desses arquivos.

**Conclusão:** chamadas realmente sem alteração evitam a captura completa,
com a mesma sequência de estados e resultados de undo/redo da referência.

**Registro da execução:** [comparação da etapa 07](desempenho_editor/etapa-07/comparacao.md).
Concluída em 09/10/2026, após autorização em 08/10/2026. Doze cenários com vinte
amostras antes e depois. Snapshot sem alteração em página com sessenta objetos
passou de 11,22 para 2,30 ms; com duzentos, de 38,39 para 8,47 ms. Depois de Undo,
de 11,66 para 2,43 ms; mover e retornar à origem, de 17,56 para 7,21 ms. A leitura
síncrona continua percorrendo a cena e conferindo o documento, mas evita capturas,
normalizações e cópias completas sem alteração. Tipos/atributos não cobertos
mantêm o caminho completo. Estados novos continuam completos e passam de três
para duas serializações JSON; suas medianas caíram modestamente, mas p95 e
dispersão maiores em alguns casos impedem afirmar ganho consolidado de latência.
Passaram 317 testes distintos na referência e 319 depois, incluindo quatro
contratos suplementares dos limites/equivalência do histórico contra ambos os módulos. As 240 amostras de cada versão
e oito registros nos dois temas preservam exatamente documento, histórico,
índice, tamanhos, botões e pixels. A validação corrigiu também uma consulta
nativa que alterava a propriedade das guias no PySide deste ambiente. Fontes,
modelos e formato do histórico não mudaram; hashes e reversão do patch foram
conferidos. Backend nativo, ponteiro real e uso prolongado seguem como validação
complementar. Os resultados da recuperação automática estão na etapa 08.

## Etapa 08 — Recuperação automática sem trabalho repetido

**Problemas:** o timer pode regravar uma recuperação idêntica a cada minuto;
montagem, compressão, verificação e escrita do pacote executam na interface.

**Ajustes propostos, em dois passos verificáveis:**

1. Registrar a versão recuperada com sucesso e evitar regravá-la enquanto
   documento, assets e condições relevantes permanecerem iguais. Manter separado
   esse controle do estado salvo manualmente: recuperação não significa modelo salvo.
2. Preparar um snapshot consistente na interface e executar o trabalho de arquivo
   em segundo plano. O trabalhador recebe dados próprios e não acessa a cena,
   widgets ou `QPixmap`. Serializar tarefas e validar a atualidade/autorização
   antes da publicação.

**Antes/depois:** documento alterado com vários disparos do timer sem novas
mudanças; edição contínua; assets grandes; alteração durante uma gravação;
salvamento manual simultâneo. Medir gravações efetivas, tempo total de recuperação,
memória e tempo em que a interface fica impedida de responder.

**Verificações:** abrir/restaurar a recuperação, proteção pública/completa/de
assinaturas, expiração de autorização, fechamento/troca de documento, falha de
disco/permissão, pacote corrompido, arquivo alterado externamente e recuperação
mais nova que uma tarefa em andamento. Preservar locks, verificação, publicação
atômica, escrita durável e limpeza dos recursos sensíveis.

**Conclusão:** sem regravação de recuperação idêntica; interface responsiva;
nenhuma publicação atrasada, perda de mudanças ou exposição de conteúdo protegido.

**Resultado da etapa:** concluída em 09/10/2026, após autorização no mesmo dia.
Relatório: [comparação antes/depois](desempenho_editor/etapa-08/comparacao.md).
A versão recuperada fica separada do estado salvo manualmente; documento,
assets, arquivo original, recuperação existente e autorização são conferidos.
Snapshot próprio, compressão, criptografia, verificação e preparação dos arquivos
executam numa tarefa de fundo, com uma fila que conserva somente a última versão.
A interface valida a atualidade e executa apenas a publicação final curta, sem
processar edições entre a validação e a publicação. Carregar, salvar, trocar
proteção/senha, remover ou fechar revoga as tarefas antes da ação; encerrar o
aplicativo aguarda sua limpeza antes de destruir os recursos do Qt.

Oito cenários, vinte amostras aquecidas por cenário e versão. No caso público
com assets grandes, a mediana do maior atraso no atendimento da interface
caiu de 272,19 para 17,81 ms; com proteção completa, de 281,90 para 18,25 ms.
Três disparos iguais passam de três gravações para uma. O tempo total de uma
recuperação nova aumentou pelas verificações e coordenação adicionais; disparos
iguais reduzem seu tempo total. A captura e a publicação final ainda custam tempo.
A medição usa o ciclo de eventos do Qt, após corrigir a distorção de polling no
instrumento e normalizar apenas os nomes aleatórios dos assets por SHA-256.

Passaram 337 testes distintos na referência e 350 na versão final, incluindo
falhas de disco/permissão, corrupção, reabertura, proteção/credenciais, edição
concorrente, fila, salvamento, troca/fechamento, expiração, mudanças externas e
encerramento real do aplicativo com uma tarefa ativa. As 160 comparações pareadas
preservam documento, estado salvo, histórico, assets/multiplicidade, foco, cursor,
original e pixels. RSS após a conclusão ficou abaixo do guard de 2 GiB; não é
medição de pico. Hashes dos instrumentos, fontes, modelos e demais módulos,
e reversão do patch exclusivo foram conferidos. Linux offscreen; backend nativo,
filesystem lento e uso prolongado seguem como validação complementar. A etapa 09
não foi iniciada.

## Etapa 09 — Reutilizar cenas ao trocar de página

**Problema:** voltar a uma página não alterada recria seus objetos, camadas e
layout mesmo que ela já tenha sido carregada durante a sessão.

**Ajustes propostos:** manter a cena inativa válida e reativá-la quando seu estado
for compatível com o documento. Centralizar a troca da cena e a conexão dos seus
sinais. Aplicar limite de memória e reconstruir quando necessário, preservando
o caminho de carregamento como alternativa segura.

**Antes/depois:** repetir frente/verso e cartão/organograma com páginas simples e
densas; editar antes de alternar; undo/redo mudando de página. Medir tempo de troca,
objetos reconstruídos, renderizações/decodificações e memória após muitos ciclos.

**Verificações:** seleção por página, foco, alças, guias, máscaras, propriedades,
réguas, retângulo do documento, botões de páginas e callbacks sem duplicação.
Alterações compartilhadas de dimensões, fontes e assets devem invalidar ou
atualizar as cenas dependentes. Mudanças no cartão devem renovar o organograma.
Cobrir adicionar/remover página/organograma, carregar outro modelo, histórico,
encerrar proteção e fechar o editor, sem reutilizar wrappers destruídos.

**Cuidado:** referências a cenas inativas não podem fazer ações atingirem a página
errada. A invalidação deve considerar o conteúdo restaurado pelo histórico,
não apenas um contador que coincida com um estado antigo.

**Conclusão:** voltar à página inalterada evita reconstrução; documentos e recursos
protegidos permanecem isolados; memória não cresce indefinidamente.

**Resultado da etapa:** concluída em 09/10/2026. Relatório:
[comparação antes/depois](desempenho_editor/etapa-09/comparacao.md).
Uma cena inativa por editor, com orçamento estimado de 64 MiB e teto de 5.000
itens, valida conteúdo, assets, fontes, tema, idioma e autorização. Mudanças no
cartão invalidam o organograma dependente. Histórico, novo documento e fechamento
descartam a retenção. Fundos legados ainda não convertidos e cenas acima do
orçamento continuam usando a reconstrução. A reativação conserva a normalização
de camadas, a ordem das guias e a geometria das alças do carregador.

Oito cenários com vinte amostras pareadas: documentos, histórico, seleção,
estado da cena e pixels iguais nas 160 amostras e na conferência das duas páginas.
Passaram 366 testes na referência e 376 depois; os 26 contratos de páginas
passaram também no tema claro. Nos casos elegíveis sem edição, as reconstruções
por ida e volta caíram de duas para zero. Frente/verso com 20 objetos passou de
462,88 para 266,20 ms; com 60, de 1.497,97 para 549,49 ms. Os cenários de 5 e 40
blocos tiveram reduções menores, de 5,4% e 4,5%.

O ganho não foi uniforme: 100 blocos aumentaram 11,3% na mediana, e a troca após
editar o cartão do organograma aumentou 25,9%. O quadro dependente continua
exigindo reconstrução e há custos de validação/restauração; a contribuição
individual desses custos não foi isolada nesta medição. O caso de 200 objetos
ultrapassou o orçamento, reteve zero cenas e aumentou 4,3% no tempo medido.
A memória adicional ficou estável nos ciclos observados: 100 nos casos simples,
cinco no maior e vinte nos demais. Isso não substitui a validação de sessões
prolongadas e do backend nativo Linux/Windows. A etapa 10 estava pendente ao concluir esta medição.

## Etapa 10 — Reutilizar miniaturas da galeria

**Problema:** abrir o painel gera novamente todas as miniaturas; estruturas de
organograma repetem trabalho ligado ao mesmo cartão da Página 1.

**Ajustes propostos:** manter um cache limitado de miniaturas e recursos comuns.
Identificar exemplos pelo conteúdo e dependências relevantes, não apenas pelo nome.
Para organogramas, incluir o cartão atual e os parâmetros da estrutura na chave.
Conteúdo derivado de documento protegido fica apenas na memória da sessão autorizada.

**Antes/depois:** abrir/reabrir as galerias de modelos e organogramas; alterar o
cartão, um asset, um exemplo ou os parâmetros da grade; trocar documento/fonte/tema.
Medir tempo até o painel ficar pronto, miniaturas geradas e memória retida.

**Verificações:** dimensões, ordem, títulos, seleção, começar em branco,
personalização independente, atualização dos exemplos, fontes, grade configurável,
assets substituídos no mesmo caminho e mesmo tamanho/data, expiração da autorização
e liberação ao fechar. O tema da interface não pode alterar as cores da arte.

**Conclusão:** reabertura sem alterações reutiliza as miniaturas, mas qualquer
dependência modificada produz uma prévia atual e autorizada.

**Resultado em 09/10/2026:** concluída. Cache LRU em memória de até 16 MiB por
janela, com identidade por conteúdo do exemplo, cartão, bytes dos assets,
parâmetros da grade, fontes, idioma e sessão autorizada. Os cinco organogramas
compartilham o snapshot de assets do cartão durante a abertura. Trocas de documento,
fontes, revogação da autorização e fechamento descartam as entradas. Os diálogos
liberam imagens/providers ao cancelar ou transferir o modelo escolhido.

Reaberturas: galeria de modelos **913,37 → 484,01 ms (47,0%)**; organogramas
**502,11 → 45,37 ms (91,0%)**, medianas de 20 amostras após dois aquecimentos.
Ambas passaram de cinco renderizações de miniaturas para zero. Primeira abertura
em cinco processos independentes: modelos **1.405,85 → 1.621,80 ms**, cerca de
**15,4% mais lenta** nesta amostra; organogramas **568,71 → 561,13 ms**, diferença
pequena que não sustenta uma conclusão de ganho. A conferência das dependências
continua necessária para renovar a arte corretamente.

Antes: 32 testes específicos/contratos passaram. Depois: 44 testes de
modelos/cache/galeria, 209 regressões gerais (incluem 26 desses 44) e 26 testes de
cenas por página passaram: 253 verificações distintas. Os últimos ajustes de
transferência/liberação foram verificados novamente pelos 44 testes específicos.
40 pares de reaberturas e dez pares de primeiras aberturas tiveram igualdade
exata de miniaturas, painel pintado, ordem, títulos e dimensões. O cache retido
ficou em 1,40/1,44 MiB e foi zerado na limpeza; 20 reaberturas adicionais
mantiveram o RSS dentro do limite, sem crescimento contínuo na versão otimizada.

Evidências, ambiente, amostras, limitações e patch exclusivo com reversão
conferida: [relatório da etapa 10](desempenho_editor/etapa-10/comparacao.md).
A verificação foi automatizada no Qt offscreen; uso manual no backend nativo
Linux/Windows permanece para a etapa 11; seu resultado automatizado está registrado abaixo.

## Etapa 11 — Verificar o conjunto e apresentar os resultados

Reexecutar os benchmarks da etapa 00 nas mesmas condições e consolidar os
resultados por processo e por fluxo completo:

- Abrir um modelo, selecionar, editar, duplicar/colar, ordenar camadas e desfazer/refazer.
- Editar o cartão, alternar para o organograma, mover conjuntos, ajustar conexões
  e contornos, acrescentar texto e voltar ao cartão.
- Alternar páginas com edição pendente e histórico, salvar/reabrir e verificar
  recuperação e fechamento de documentos públicos/protegidos.
- Abrir galerias repetidamente, substituir recursos e confirmar a renovação visual.

Antes da comparação final, revisar a preparação dos cenários legados `text_insert`:
a leitura pública do documento encerra a edição, então a sessão deve ser aberta
depois dessa captura. Usar os contratos de digitação nativa da etapa 04 para exigir
conteúdo sincronizado e sessão ativa. Não interpretar os tempos antigos desse
driver como referência equivalente de digitação nativa; registrar essa limitação
na consolidação da etapa 00.

Executar regressões de editor, texto, assinaturas, modelos prontos, organograma,
camadas, máscaras, atribuição de blocos, autosave, troca de janelas e geração,
incluindo ladrilhos quando afetados por componentes compartilhados.

Verificar manualmente temas, zoom, rolagem, mouse/touchpad, redimensionamento e
sessões prolongadas. Fazer comparações antes/depois dentro de cada plataforma.
Os testes automatizados locais podem usar Qt offscreen, mas não substituem a
verificação com backend nativo no Linux e no Windows. Se o Windows não estiver
disponível, registrar sua validação como pendente, sem declarar compatibilidade testada.

O relatório final deve apresentar ganhos medidos, consumo adicional de memória,
regressões resolvidas, testes executados, verificações pendentes e situações em
que a reconstrução ou repintura completa continua sendo necessária.

### Execução da etapa 11 — 09/10/2026

A referência inicial foi reconstruída numa árvore temporária, revertendo os
dez patches e conferindo os 101 hashes registrados na etapa 00. O projeto em
uso não foi revertido. Os dois cenários legados de digitação foram medidos
novamente no código inicial com o driver corrigido; a recuperação aguarda
a conclusão antes de conferir o arquivo.

Os **43 cenários iniciais** foram repetidos: **710 amostras finais**, com
entradas, fonte, viewport e ambiente conferidos; **35 medianas menores e oito
maiores**. Os oito cenários complementares de recuperação tiveram **160
amostras**, separando tempo total, retorno da solicitação e atendimento da UI.
Quatro perdas incertas foram repetidas na referência completa e na versão
final, com 65 amostras por versão, sem substituir os resultados oficiais.

Passaram **394 testes distintos** (376 regressões integradas e 18 da galeria).
Cinco fluxos completos passaram na referência e na versão final, também no
tema claro. O complemento inclui arraste coletivo e novo texto no quadro:
nos 27 estados, documentos, índices de histórico e pixels das prévias geradas
coincidem; as 81 capturas dos três percursos confirmam pintura parcial igual
à repintura completa.

O relatório contém uma seção dedicada aos **resultados que ficaram piores**,
com medianas/p95, perdas intermediárias, repetição, memória, causas prováveis
e causas não isoladas. Não atribui automaticamente uma piora a uma proteção
nova: o roteamento de 100 blocos manteve um cálculo nas duas versões e a
perda de 18,1% caiu para 1,6% na repetição. Pinturas do quadro inteiro
inverteram o sentido; a primeira galeria voltou a piorar. Recuperações novas
demoram mais no total, mas atendem a interface antes.

O canvas não é binariamente idêntico em todos os fluxos: há uma diferença de
uma unidade por canal em um pixel na interseção das guias em 13 estados após
ajustar à tela, e algumas trocas diferem em 1–2 pixels de rolagem. Esses pontos
foram registrados sem tolerância nem alteração no produto e permanecem
para revisão. Documentos/prévias geradas coincidem.

A sonda Qt/xcb não conseguiu conectar ao display Linux `:0`; Windows e
mouse/touchpad físicos não estão disponíveis para validação nesta sessão.
Por isso, a etapa não é marcada integralmente concluída. A homologação manual
nativa, sessões prolongadas e revisão dessas observações permanecem abertas.

Evidências, tabelas e reprodução:
[relatório final da etapa 11](desempenho_editor/etapa-11/RELATORIO_FINAL.md).

## 4. Controle de execução

- [x] Primeira etapa autorizada: etapa 00, referência e instrumentos.
- [x] Etapa 00 — Referência e instrumentos.
- [x] Etapa 01 — Seleção e painéis.
- [x] Etapa 02 — Camadas.
- [x] Etapa 03 — Conectores, propriedades e recortes.
- [x] Etapa 04 — Texto.
- [x] Etapa 05 — Colagem e duplicação.
- [x] Etapa 06 — Pintura parcial e cartões visíveis.
- [x] Etapa 07 — Histórico sem alterações.
- [x] Etapa 08 — Recuperação automática.
- [x] Etapa 09 — Cenas por página.
- [x] Etapa 10 — Miniaturas.
- [ ] Etapa 11 — Integração e relatório final (parte automatizada executada; homologação nativa/manual e observações do canvas pendentes).

Durante a execução, marcar uma etapa somente após seu relatório antes/depois
estar salvo e os critérios de conclusão atendidos. As técnicas propostas podem
ser refinadas conforme as medições, mantendo o escopo, os comportamentos aprovados
e o registro das decisões.
