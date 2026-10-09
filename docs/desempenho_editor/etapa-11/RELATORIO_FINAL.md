# Etapa 11 — Revisão integrada das otimizações do editor

Data: 09/10/2026. Medições, regressão automatizada e relatório final executados.
Etapa 11 com validação nativa/manual e revisão das observações do canvas pendentes.

## Escopo e método

Esta etapa verifica o produto resultante das etapas 01–10. Não aplica novas
otimizações ao código de produção. Os ajustes desta etapa estão nos instrumentos
de medição, nas verificações de fluxos completos e neste relatório.

A referência inicial foi reconstruída numa árvore temporária, revertendo os
dez patches em ordem inversa. Os 101 arquivos de produto registrados na etapa
00 coincidem por SHA-256; nenhuma reversão foi feita no projeto em uso.
Os registros estão em [reconstrucao-referencia.json](reconstrucao-referencia.json)
e [identidade-referencia.json](identidade-referencia.json).

A rodada final repete os 43 cenários iniciais. A referência é o resultado
preservado da etapa 00, com duas referências de digitação recalibradas no
código inicial reconstruído. Cada cenário executa num processo isolado, em
sequência, sem outras suítes pesadas simultâneas: duas preparações e vinte
amostras aquecidas; cinco amostras nos casos de sessões novas. A estabilização
dos eventos e a pintura fazem parte do intervalo; preparação, verificação e
profiler ficam fora dele. “Frio” significa uma sessão nova do editor/diálogo,
não esvaziar os caches de fontes e disco do sistema.

Linux x86_64 no ThinkPad, Intel i5-8350U, Python 3.13.13, PySide/Qt 6.11.0,
Inter embutida, tema escuro, Qt offscreen, escala 1 e janela solicitada
de 1280 × 800. Dados e preferências são temporários. Comparações de datas
diferentes não eliminam variações de carga, escalonamento ou temperatura;
pequenas diferenças não comprovam causalidade. Mediana menor nesta rodada
não equivale a um ganho garantido em qualquer modelo ou plataforma.

### Calibração necessária

O driver antigo de `text_insert` capturava o documento depois de iniciar a
edição; essa leitura a encerrava. Os tempos iniciais de 22,34/26,12 ms não são
referência equivalente de digitação. O driver corrigido inicia a edição após
a captura, envia teclas com QTest e exige sessão ativa e HTML sincronizado.
Os dois casos foram medidos novamente na árvore inicial e na versão final,
com o mesmo instrumento. Os resultados antigos permanecem preservados.

O driver legado de autosave agora aguarda a conclusão pelo ciclo de eventos
Qt antes de conferir o arquivo. A comparação mede a recuperação concluída,
incluindo a coordenação assíncrona, e não somente o retorno do timer. Uma
rodada complementar repete os oito cenários da etapa 08 para separar retorno
da solicitação, intervalo de atendimento da interface e tempo total.

## Resultado acumulado das etapas 01–10

Dos **43 cenários iniciais, 35 tiveram mediana menor e oito tiveram mediana
maior**. São 710 amostras finais, com entradas, fonte, viewport, número de
amostras e condições de ambiente conferidos contra a referência. Nenhuma
medição terminou com erro. Não se calcula uma média das porcentagens: cada
processo representa um trabalho e uma frequência de uso diferentes.

| Processo | Mediana inicial → final | Redução observada |
|---|---:|---:|
| Selecionar 200 objetos | 52819,69 → 113,02 ms | 99,8% |
| Atualizar camadas de 200 objetos | 771,29 → 13,80 ms | 98,2% |
| Colar numa página de 60 objetos | 974,71 → 109,81 ms | 88,7% |
| Repetir snapshot sem mudanças, 200 objetos | 36,59 → 9,90 ms | 73,0% |
| Pintar visão aproximada de 2500 cartões | 91,45 → 7,42 ms | 91,9% |
| Vinte idas e voltas frente/verso | 37136,34 → 10901,86 ms | 70,6% |
| Reabrir galeria de modelos | 970,87 → 370,69 ms | 61,8% |
| Reabrir galeria de organogramas | 702,64 → 72,53 ms | 89,7% |

A tabela completa, incluindo **mediana, p95 e memória dos 43 casos**, está em
[COMPARACAO_ACUMULADA.md](COMPARACAO_ACUMULADA.md); os números sem arredondamento
estão em [comparacao-acumulada.json](comparacao-acumulada.json). Os JSON brutos
da rodada ficam em `final/raw/`. Perfis separados registram contagens de
trabalho, sem contaminar os tempos das amostras.

### Recuperação: responsividade e conclusão são medidas diferentes

O complemento usa a referência preservada da etapa 08, que já contém as
etapas 01–07; não é outra referência inicial. As 160 amostras finais coincidem
com seus estados anteriores em documento, assets, histórico, proteção,
cursor, foco, original e pixels.

| Cenário | Tempo total antes → final (ms) | Maior intervalo de atendimento da UI, mediana antes → final (ms) | Gravações por amostra antes → final |
|---|---:|---:|---:|
| Público pequeno | 41,67 → 48,87 | 41,64 → 16,04 | 1 → 1 |
| Assinaturas pequeno | 50,45 → 60,01 | 50,42 → 15,70 | 1 → 1 |
| Completo pequeno | 38,97 → 47,12 | 38,95 → 15,99 | 1 → 1 |
| Público grande | 273,20 → 416,07 | 272,19 → 17,56 | 1 → 1 |
| Completo grande | 282,93 → 421,63 | 281,90 → 18,16 | 1 → 1 |
| Três pedidos públicos iguais | 138,73 → 103,59 | 47,85 → 16,56 | 3 → 1 |
| Três pedidos completos/grandes iguais | 1066,18 → 631,70 | 387,88 → 17,90 | 3 → 1 |
| Três edições públicas sucessivas | 158,23 → 233,32 | 56,36 → 27,77 | 3 → 3 |

O timer independente mede intervalos entre atendimentos, incluindo pintura e
escalonamento; não mede exclusivamente um método. O resultado confirma a
troca: um pacote novo pode demorar mais até ficar pronto, enquanto a interface
volta a atender eventos antes. Disparos iguais evitam remontar/gravar o pacote.
[comparacao-recuperacao.json](comparacao-recuperacao.json) inclui mediana/p95
do total, retorno das solicitações, intervalos da UI, memória e contagens.

## Resultados que ficaram piores

Esta seção distingue a comparação acumulada com a etapa 00 das perdas
observadas entre etapas consecutivas. Uma melhora acumulada não apaga uma
perda intermediária. São registrados aumentos de mediana, de p95 e de memória.
As causas abaixo descrevem mecanismos observados no código e hipóteses;
as medições não isolam a contribuição de cada mecanismo.

### Perdas acumuladas na rodada final

| Cenário | Mediana inicial → final (ms) | Aumento | P95 inicial → final (ms) | Causa provável / evidência |
|---|---:|---:|---:|---|
| Mover um bloco num quadro de 100 | 4441,01 → 5243,32 | 18,1% | 5519,75 → 8130,55 | O roteamento completo continua caro. O profiler conta um cálculo de rotas nas duas versões; não demonstra uma etapa extra de segurança causando a piora. A repetição reduziu o aumento a 1,6%, compatível com dispersão/carga. |
| Pintar todo o quadro de 400 cartões | 32,84 → 38,60 | 17,6% | 36,37 → 48,24 | Todos os cartões seguem visíveis. Calcular a região exposta não elimina desenhos nesse enquadramento; pode acrescentar custo. Variação da pintura também é possível; contribuição não isolada. |
| Pintar todo o quadro de 2500 cartões | 108,66 → 114,47 | 5,3% | 127,82 → 142,03 | Mesmo limite da visão inteira. A economia ocorre sobretudo no zoom aproximado e na invalidação local; não há ganho universal de pintura. |
| Primeira galeria de modelos | 1030,36 → 1062,55 | 3,1% | 1071,61 → 1111,95 | Confere dependências e registra miniaturas no cache, ainda precisando renderizá-las. Só cinco amostras; diferença pequena para estabelecer regressão consistente. |
| Recuperação pública pequena | 40,15 → 52,39 | 30,5% | 40,35 → 54,83 | Snapshot independente, conferências e coordenação/publicação assíncrona. Protegem contra estado antigo e perda de autorização; o total inclui esperar a tarefa terminar. |
| Recuperação de assinaturas pequena | 47,75 → 58,09 | 21,7% | 50,33 → 63,65 | Mesmo trabalho adicional da recuperação. A interface retorna antes, como mostra a medição complementar. |
| Recuperação completa pequena | 36,35 → 55,27 | 52,1% | 40,96 → 72,46 | Mesma coordenação e validação; criptografia/verificação continuam necessárias. Não foi isolado o peso de cada parcela. |
| Recuperação completa grande | 290,99 → 369,12 | 26,8% | 305,29 → 400,41 | Mesmo custo de consistência e snapshot com bytes próprios. Aumento do total não significa bloqueio da interface por todo esse intervalo. |

Os mesmos oito casos tiveram aumento de p95. Não houve um caso adicional com
p95 pior e mediana melhor nesta comparação acumulada. As quatro perdas não
relacionadas a recuperação têm uma repetição independente, preservada sem
substituir as amostras oficiais, para verificar a estabilidade da observação.

| Repetição independente | Mediana antes → depois (ms) | Variação | Conclusão |
|---|---:|---:|---|
| Mover um bloco num quadro de 100 | 4312,87 → 4383,75 | +1,6% | A piora grande não se repetiu; não há evidência para atribuir os 18,1% a uma alteração específica. |
| Pintar todo o quadro de 400 cartões | 33,88 → 29,27 | -13,6% | O sentido se inverteu; a piora da primeira rodada não é consistente. |
| Pintar todo o quadro de 2500 cartões | 114,74 → 112,41 | -2,0% | Mediana próxima e com sentido invertido; p95 ainda cresceu 4,2% (149,55 → 155,80 ms). Não há ganho conclusivo na visão inteira. |
| Primeira galeria de modelos | 1062,86 → 1203,43 | +13,2% | A piora se repetiu, também observada na etapa 10. Conferência das dependências/cache é a explicação provável, com contribuição individual não isolada. |

São 65 amostras por versão nesta repetição, com mesma entrada, fonte,
viewport e instrumento entre as duas versões. Resultados em
[comparacao-repeticao-pioras.json](comparacao-repeticao-pioras.json) e
`repeticao-pioras/`. O antes usa os pacotes completos da referência inicial
reconstruída. A segunda rodada não substitui nem se mistura com a primeira;
as oito pioras observadas originalmente permanecem registradas.

### Perdas intermediárias e causa provável

| Etapa / processo | Mediana antes → depois | Aumento | Explicação e limite da conclusão |
|---|---:|---:|---|
| 01 — seleção pela árvore, 40 blocos | 38,70 → 44,40 ms | 14,7% | A repetição inverteu o sentido: 43,35 → 40,77 ms. Provável dispersão; não há regressão consistente comprovada. |
| 02 — bloquear camada | 70,29 → 71,90 ms | 2,3% | Operação ainda sincroniza controles e histórico. Diferença pequena e dispersa; causa não isolada, pode ser ruído. |
| 04 — redimensionar texto | 63,97 → 64,48 ms | 0,8% | O layout do texto ainda é recalculado. Não houve ganho conclusivo; p95 também aumentou. |
| 08 — recuperação pública pequena | 41,67 → 56,95 ms | 36,7% | Snapshot independente, validações e confirmação no ciclo de eventos acrescentam trabalho. Evitam publicar um estado antigo ou uma tarefa sem autorização. O atendimento da UI melhorou; o total piorou. |
| 08 — recuperação de assinaturas pequena | 50,45 → 63,37 ms | 25,6% | Mesma coordenação e validações da recuperação assíncrona; contribuição de cada custo não isolada. |
| 08 — recuperação completa pequena | 38,97 → 55,65 ms | 42,8% | Mesma proteção contra corrida/estado antigo; o total inclui conclusão da tarefa, não só liberar a interface. |
| 08 — recuperação pública grande | 273,20 → 414,63 ms | 51,8% | Bytes independentes, hashes/consistência e coordenação passam a fazer parte do caminho assíncrono. O atraso mediano de atendimento caiu de 272,19 para 17,81 ms. |
| 08 — recuperação completa grande | 282,93 → 428,00 ms | 51,3% | Mesmo custo adicional; compressão, criptografia e conferência continuam necessárias. Atraso mediano da UI: 281,90 → 18,25 ms. |
| 08 — três edições sucessivas | 158,23 → 234,31 ms | 48,1% | São três estados distintos, sem eliminar gravações. A coordenação/validação aparece em cada um; impede reutilizar indevidamente um pacote antigo. |
| 09 — frente/verso, 200 objetos | 11333,24 → 11824,20 ms | 4,3% | Excede o orçamento estimado de 64 MiB: reconstrói as duas cenas, além de avaliar a elegibilidade da retenção. Não beneficia esse caso; custo individual não isolado. |
| 09 — alternar organograma, 100 blocos | 275,58 → 306,80 ms | 11,3% | Evita reconstrução, mas valida dependências e restaura estado/controles. Esses custos podem superar a economia numa cena barata; hipótese sem decomposição causal. |
| 09 — alternar após editar cartão | 221,37 → 278,79 ms | 25,9% | A alteração invalida o organograma, que precisa ser reconstruído. Validação e restauração da outra cena acrescentam trabalho para manter conteúdo e estado corretos. |
| 10 — primeira abertura da galeria de modelos | 1405,85 → 1621,80 ms | 15,4% | Ainda renderiza os exemplos e acrescenta conferência dos bytes das dependências e registro no cache. Cinco amostras, com dispersão relevante; custos individuais não isolados. |

Fontes: relatórios e amostras das etapas
[01](../etapa-01/comparacao.md), [02](../etapa-02/comparacao.md),
[04](../etapa-04/comparacao.md), [08](../etapa-08/comparacao.md),
[09](../etapa-09/comparacao.md) e [10](../etapa-10/comparacao.md).
Essas tabelas usam protocolos próprios de cada etapa, não podem ser somadas
nem usadas como uma única porcentagem de aceleração do aplicativo.

### P95 que piorou sem piora da mediana, entre etapas

| Etapa / processo | P95 antes → depois | Aumento | Interpretação |
|---|---:|---:|---|
| 01 — seleção por área, quadro de 40 blocos | 60,33 → 69,22 ms | 14,7% | Dispersão de seleção/pintura; não há ganho conclusivo nesse caminho. |
| 04 — carregar cartão de pessoal | 483,49 → 488,27 ms | 1,0% | Cinco amostras de sessões novas; diferença pequena, causa não isolada. |
| 07 — histórico após mover texto | 25,40 → 29,79 ms | 17,3% | Edição real ainda captura/copia o documento e confere entradas do cache. Aumento de cauda observado, sem causa isolada. |
| 07 — histórico após mudar contorno | 31,29 → 40,64 ms | 29,9% | Mesmo limite do caminho de edição real; eliminar JSON redundante não garante menor latência em todas as amostras. |
| 08 — três pedidos públicos iguais | 148,79 → 153,60 ms | 3,2% | A mediana melhora e gravações caem de três para uma; coordenação e escalonamento podem explicar a cauda, hipótese não isolada. |

As etapas 03, 05 e 06 não apresentaram aumento de mediana/p95 nos cenários
oficiais próprios. A etapa 07 não apresentou aumento de mediana, mas apresentou
as duas pioras de p95 acima. Os demais casos com p95 maior também têm mediana
maior e permanecem nos resultados brutos e na tabela de perdas intermediárias.

## Memória e situações que continuam custosas

RSS significa memória residente corrente do processo. As observações após
operações não medem o pico durante compressão/renderização nem somente memória
Python. Os limites dos caches não são limites absolutos do RSS.

Na comparação acumulada, **22 dos 43 casos tiveram RSS máximo observado
maior**, com acréscimos de 0,29 a 11,36 MiB; os outros tiveram valores menores.
Os maiores acréscimos foram no carregamento do certificado (+11,36 MiB),
reabertura da galeria de modelos (+9,89 MiB) e pintura local (+8,55 MiB).
Caches e alocações do Qt são explicações possíveis; não foi isolada a origem
de cada diferença entre processos. O máximo final observado nesses 43 casos
foi 314,36 MiB. A tabela completa conserva também os resultados de memória
que pioraram, sem atribuir automaticamente todo aumento a um vazamento.

- Cenas: no máximo uma cena inativa por editor, orçamento estimado de 64 MiB
  e teto de 5000 itens. A etapa 09 mediu aproximadamente 6–11 MiB adicionais
  de RSS nos casos frente/verso elegíveis; a estimativa retida de um caso
  de 60 objetos foi 58,18 MiB. O caso de 200 excedeu o orçamento e reteve zero.
- Galeria: orçamento LRU de 16 MiB por janela; nos casos medidos da etapa 10
  reteve 1,40/1,44 MiB e retornou a zero na limpeza. Isso troca memória por
  menor custo de reabertura, sem cache persistente em disco.
- Recuperação: mantém dados independentes de uma tarefa ativa e de até um
  estado pendente mais recente. Há custo transitório de cópia/compressão,
  não representado integralmente pelo RSS medido depois da conclusão.
- Geometria/histórico: os caches guardam o estado atual e são invalidados;
  não removem os estados completos de Undo/Redo nem seus limites de bytes.

Reconstrução completa continua correta ao carregar outro documento, restaurar
estados que mudam a cena, invalidar dependências, exceder o orçamento ou abrir
fundos legados ainda sem identidade persistida. Editar a Página 1 invalida o
quadro que usa seus cartões. Trocar imagens no mesmo caminho é reconhecido
pelos bytes; a validação não foi removida para favorecer os tempos.

Transformações, exposição da janela, desenho de todos os cartões e exportação
podem exigir pintura completa. O roteamento de conexões continua proporcional
ao quadro inteiro: a etapa 03 elimina rotas intermediárias num gesto coletivo,
mas não substitui o algoritmo. Os casos legados `drag_one/drag_four` usam
`moveBy` sequencial, não o lote de arraste nativo; seus tempos não demonstram
o ganho do gesto coletivo medido separadamente na etapa 03.

## Testes e verificações pendentes

Passaram **394 testes distintos**: 376 da regressão integrada das etapas 00–09
e 18 específicos da galeria. Os comandos e saídas estão em
[checks/checks-depois.json](checks/checks-depois.json), nos logs daquela pasta
e em [galeria.log](galeria.log). Repetições entre temas não aumentam esse total.

Cobertura: seleção, camadas, máscaras, conectores, contornos, texto e
placeholders, assinaturas, histórico, modelos prontos, recuperação concorrente,
publicação de pacotes, perda de autorização, encerramento do Qt, troca de
janelas, prévias, exportação e ladrilhos. Os contratos de texto incluem
fidelidade de PNG/PDF; exceções nos callbacks Qt também reprovam as suítes.

Cinco fluxos adicionais encadeiam edição nativa, colagem, Undo/Redo,
reordenação, páginas, organograma, recuperação, salvamento/reabertura e
fechamento, com modelos públicos, totalmente protegidos e protegidos por
assinaturas. São cinco fluxos, não quinze testes distintos ao repeti-los na
referência e nos dois temas. A comparação semântica conserva conteúdo,
camadas e referências de assets, normalizando somente a ordem irrelevante
das guias, profundidades equivalentes à ordem explícita e nomes internos
aleatórios de assets por SHA-256, como os contratos anteriores.

### Fidelidade e observações do canvas

O complemento amplia o fluxo do organograma com arraste nativo de três
conjuntos e criação/edição de um texto no quadro. Nos **27 estados** desses
cinco fluxos, documentos, índices de histórico e pixels das prévias geradas
coincidem exatamente entre a referência e a versão final. O tema claro
preserva esses mesmos resultados. Salvamento e recuperação conservaram
conteúdo/assets/proteção e o encerramento protegido liberou o documento.

As 81 capturas dos três percursos (referência escura, final escura e final
clara) têm igualdade entre a pintura parcial real e a repintura completa.
Não houve rastro ou recorte demonstrado nesses fluxos. A comparação global
do canvas entre versões, entretanto, **não é exatamente igual**:

- Em 13 estados, depois de ajustar à tela, resta **um pixel diferente**,
  na interseção das guias, com diferença máxima de **uma unidade por canal**
  na escala 0–255. A causa provável é arredondamento da composição raster
  quando a ordem de empilhamento das guias muda após a reconstrução/normalização;
  ambas têm a mesma profundidade. Não foi isolada essa causa por uma alteração
  de produto. Os pontos e canais diferentes ficam registrados, sem aplicar
  tolerância para declarar igualdade.
- Algumas trocas de página diferem em **1–2 pixels de rolagem**, conservando
  a transformação de escala. A restauração/ajuste dos limites da cena é a
  causa provável, sem isolamento causal. O ajuste à tela remove essa diferença
  de enquadramento; as diferenças residuais são as da interseção das guias.

Essas observações são da interface. A conferência não encontrou diferença
nos documentos nem nas prévias geradas, e as guias não são exportadas.
Permanecem para revisão/homologação; não se declara fidelidade binária total
do canvas nem se altera produção nesta etapa para encobri-las.
Evidências: [auditoria-fluxos-completos.json](auditoria-fluxos-completos.json),
capturas em `fluxos-completos/` e [comparacao-fluxos.json](comparacao-fluxos.json).

### Regressões corrigidas durante a implementação

As versões intermediárias reprovadas não integram as medições oficiais:

- Etapa 05: corrigido o ciclo de vida nativo do papel da cena e a retenção dos
  itens durante a inserção, após falha ao alternar página/desfazer.
- Etapa 06: invalidados os limites antigos/novos das alças para remover rastros
  e recortes ao mover seleção, inclusive seleção coletiva.
- Etapa 07: evitada a consulta que transferia a posse de guias sem pai para
  Python, preservando sua permanência após coleta.
- Etapa 08: tarefas antigas/canceladas não publicam depois de editar, salvar,
  fechar ou perder autorização; a limpeza é acompanhada no encerramento do Qt.
- Etapa 09: protegida a reativação de fundo legado sem identidade; reproduzidas
  normalização de camadas e geometria das alças do carregador.

Os relatórios dessas etapas contêm diagnósticos, correções e contratos que
passaram depois. A regressão integrada voltou a verificar os caminhos finais.

O backend nativo Linux não inicializou na sonda isolada: não foi possível
conectar o Qt/xcb ao display `:0`. A mensagem também menciona xcb-cursor, mas
a causa da inicialização não foi isolada. Isso não é um crash observado no
editor. Windows não está disponível nesta sessão. Evidência:
[validacao-nativa.json](validacao-nativa.json).

Ainda precisam de validação manual antes de encerrar integralmente a etapa:

- [ ] Linux nativo: temas claro/escuro, zoom, rolagem, redimensionamento,
  digitação e prévia durante uma sessão prolongada.
- [ ] Mouse/touchpad reais: arraste coletivo, soltura fora da janela,
  seleção por área e retorno do foco.
- [ ] Windows nativo: mesmos fluxos, fontes, DPI e estabilidade.
- [ ] Revisar as diferenças pontuais de guias/enquadramento registradas acima.
- [ ] Impressão física, se necessária para homologar o fluxo de ladrilhos.

O Qt offscreen verifica comportamento e pixels naquele backend; não substitui
essas verificações. Esta etapa não declara compatibilidade nativa homologada.

## Auditoria e reprodução

[verificacao-final.json](verificacao-final.json) confere os 43 pares de
entradas/fontes/viewport, ambiente e hashes do produto/harness. Os arquivos
de produto coincidem também com a versão final da etapa 10, incluindo a
janela principal, que não fazia parte do inventário amplo do driver legado.
Os instrumentos de fluxos documentam a correção de metadados do tema claro:
o helper genérico informava `dark`, embora o argumento e o campo do próprio
fluxo registrassem corretamente `light`. Os estados/pixels não foram alterados.

Comandos em [tests/performance/README.md](../../../tests/performance/README.md).
`reconstruir_referencia.py` foi executado e voltou a conferir os 101 hashes
iniciais numa pasta nova. `consolidar.py` gera as tabelas a partir das amostras;
`auditar_fluxos.py` compara as capturas suplementares. `repetir_pioras.py`
reexecuta os quatro casos incertos sem sobrescrever a rodada oficial.

O relatório automatizado está entregue. O controle da etapa permanece aberto
até a validação nativa/manual e a revisão das observações; as etapas 01–10
mantêm seus registros anteriores de conclusão.
