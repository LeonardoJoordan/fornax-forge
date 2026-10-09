# Etapa 07 — Evitar capturas de histórico desnecessárias

**Concluída em 09/10/2026.** Autorizada em 08/10/2026. A etapa 08 aguarda autorização.

## Mudança aplicada

`save_snapshot()` passou a conferir entradas síncronas da cena antes de montar outra cópia completa do documento. A leitura acompanha posição, dimensões, rotação, ordem nativa de camadas, visibilidade, bloqueio, opacidade, texto e revisão do documento Qt, atributos Python simples dos itens, estilos, grupos, conectores, relações de máscaras e controles globais. A comparação conserva valores e tipos dos atributos congelados e não depende de hashes ou de sinais assíncronos do Qt. Além disso, compara o documento em memória com o estado atual do histórico para detectar alterações globais e em páginas inativas.

O último conjunto de entradas só é reutilizado para o mesmo estado, documento e página ativa. A cache é refeita após a captura completa e a restauração de Undo/Redo; é descartada ao carregar outro documento e ao encerrar a janela, incluindo o descarte de conteúdo protegido. Guarda tuplas de entradas, sem wrappers Qt, sem bytes de imagens e sem outra cópia completa do documento. Tipos de item desconhecidos, subclasses não cobertas ou atributos que não possam ser congelados exigem o caminho completo original. Novas propriedades persistentes nativas devem ser incluídas na leitura antes de serem consideradas cobertas.

A conferência continua percorrendo os objetos da cena e comparando o documento: **não é uma verificação de tempo constante**. O ganho vem de evitar a captura, normalização e cópias profundas quando as entradas continuam iguais. Uma alteração real ou duvidosa conserva a captura completa e a comparação anterior. A finalização de interação continua registrando edições numéricas ainda sem `editingFinished` e invalidando Redo quando há uma nova edição após Undo. Aviso ao fechar, exportação e recuperação continuam usando seus caminhos completos.

`HistoryManager.push()` reutiliza a serialização do estado novo para comparar e calcular seu tamanho UTF-8. Em inserções medidas, passa de três chamadas a `json.dumps` para duas. O estado atual continua sendo serializado a cada comparação: seus caminhos de assets podem ser reescritos em memória. Não foi criado um cache persistente de JSON nem substituída a equivalência de JSON por igualdade simples de dicionários. Os formatos de estados e os limites de passos/bytes permanecem iguais.

A primeira validação da implementação revelou um efeito colateral de consultar `parentItem()` em itens sem pai no PySide 6.11 deste ambiente: a propriedade de guias passava para Python e elas desapareciam ao liberar as referências locais. A leitura agora identifica relações de máscaras por `childItems()` do retângulo pai, sem essa consulta nos itens sem pai. Os contratos que passavam na referência detectaram a diferença antes da aprovação; a versão corrigida preserva guias, navegação entre páginas e atualização de assets. Os diagnósticos iniciais foram preservados em `diagnostico-instrumentos/`.

Mudaram somente `core/history_manager.py` e `features/editor/editor_window.py`; foi adicionado `features/editor/history_capture.py`. O patch exclusivo está em `alteracoes-etapa-07.patch`. Sua reversão foi feita numa pasta temporária e recuperou exatamente os hashes anteriores, sem desfazer mudanças da pasta de trabalho. Fontes, modelos prontos e demais arquivos de produto do manifesto permanecem iguais.

## Medição antes/depois

Linux x86_64, ThinkPad com Intel i5-8350U, Python 3.13.13, PySide/Qt 6.11, fonte Inter do aplicativo, tema escuro, Qt offscreen em escala 1 e janela solicitada de 1.280 × 800. Dados, configurações e caches usam diretórios temporários. Cada cenário roda num processo próprio, sequencialmente, com duas preparações, **vinte amostras aquecidas** e uma rodada adicional de perfil cujo tempo não entra nas estatísticas. A restauração da mesma entrada fica fora do cronômetro; a operação e o processamento de eventos/pintura ficam dentro dele. A verificação dos estados e dos pixels ocorre depois do intervalo medido.

A referência foi medida antes de aplicar a etapa 07, mantendo as etapas 00–06. São **doze cenários e 240 amostras por versão**. Manifestos, entradas, instrumentos e contratos foram conferidos pela auditoria. Tempos em milissegundos:

| Operação | Mediana antes | Mediana depois | p95 antes | p95 depois | Desvio antes | Desvio depois |
|---|---:|---:|---:|---:|---:|---:|
| Sem alteração — 20 objetos | 4,43 | 0,91 | 5,86 | 1,07 | 0,80 | 0,06 |
| Sem alteração — 60 objetos | 11,22 | 2,30 | 14,51 | 2,61 | 2,12 | 0,14 |
| Sem alteração — 200 objetos | 38,39 | 8,47 | 42,07 | 11,71 | 1,63 | 1,37 |
| Sem alteração — 40 conjuntos conectados | 10,84 | 5,61 | 13,32 | 5,79 | 4,14 | 0,11 |
| Sem alteração — 100 conjuntos conectados | 24,04 | 13,38 | 31,22 | 15,28 | 4,04 | 1,28 |
| Sem alteração — conjunto com 2.500 cartões | 1,80 | 0,88 | 2,30 | 1,37 | 0,21 | 0,23 |
| Sem alteração — frente/verso, 60 objetos | 11,98 | 2,24 | 15,58 | 2,40 | 1,28 | 0,11 |
| Sem alteração depois de Undo — 60 objetos | 11,66 | 2,43 | 13,59 | 3,17 | 0,84 | 0,36 |
| Mover e retornar à origem — 60 objetos | 17,56 | 7,21 | 20,40 | 7,70 | 2,59 | 0,22 |
| Mover um texto — 60 objetos | 23,46 | 21,94 | 25,40 | 29,79 | 1,14 | 5,28 |
| Editar dimensão sem perder foco — 60 objetos | 32,90 | 29,47 | 36,51 | 35,17 | 1,65 | 3,14 |
| Alterar contorno — 40 conjuntos conectados | 28,83 | 26,85 | 31,29 | 40,64 | 1,74 | 4,69 |

Nas chamadas sem alteração, as medianas diminuíram entre **44% e 81%**. O retorno à origem caiu cerca de 59%, incluindo os dois movimentos e sua pintura. A presença de 2.500 cartões não significa 2.500 itens de cena: nesse cenário há um único conjunto, cuja quantidade de slots é preservada. Por isso o ganho e o custo desse caso são menores que os de cem conjuntos independentes.

Nas três edições reais, as medianas diminuíram aproximadamente 6%–10%, mas **o ganho de latência não é conclusivo nessa rodada**: mover texto e alterar contorno apresentaram p95 e dispersão maiores. Não há garantia de aceleração de toda edição ou da reconstrução de Undo/Redo. Esses caminhos ainda capturam/copiam o documento completo e fazem duas leituras de entradas para conferir e atualizar a cache. O ganho determinístico adicional confirmado neles é eliminar uma serialização JSON redundante, mantendo os mesmos estados.

No perfil separado, todas as nove operações que terminam sem alteração fizeram **zero capturas completas, zero normalizações e zero chamadas a `deepcopy`**, contra uma captura e duas normalizações antes. Na página com sessenta objetos, eram 11.624 chamadas recursivas de `deepcopy`; com duzentos, 37.552. Essas contagens incluem cada chamada recursiva da função, não milhares de cópias completas de documentos. As edições reais conservaram exatamente as contagens de captura, normalização e cópias da referência, com `json.dumps` passando de três para duas chamadas.

| Cenário | RSS antes (MiB) | RSS depois (MiB) |
|---|---:|---:|
| Sem alteração — 60 objetos | 233,02–233,07 | 233,54–233,81 |
| Sem alteração — 200 objetos | 476,77–481,00 | 478,20–483,86 |
| Sem alteração — 100 conjuntos conectados | 129,95–130,04 | 131,19–131,66 |
| Sem alteração depois de Undo — 60 objetos | 286,48–287,02 | 287,08–288,09 |

RSS é memória residente corrente, não pico nem somente memória Python. A cache acrescenta entradas e pode elevar modestamente o RSS; essa etapa não promete reduzir a memória residente ou o tamanho dos estados completos. O orçamento em bytes de **cada estado** e o conteúdo/índice do histórico permaneceram exatamente iguais nas 240 amostras comparadas. Nenhuma amostra ultrapassou o limite de 2 GiB. As medições não equivalem a uma prova de ausência de vazamentos em sessões prolongadas.

## Validação

**317 testes distintos passaram na referência e 319 na versão final.** Repetições por tema não aumentam esse total.

- 209 regressões gerais: editor, organograma, histórico, prévia, assinatura, proteção/recuperação, fidelidade de texto, modelos prontos, frente/verso e exportação em ladrilhos.
- 18 contratos de seleção, 19 de camadas, 13 de organograma/conexões, 13 de texto, 15 de colagem/duplicação e 11 de pintura: 298 testes existentes, antes e depois.
- Quinze contratos novos de comportamento, antes e depois nos temas claro e escuro: alterações imediatas em texto/itens/estilos, máscaras, guias, páginas inativas, estrutura do documento, edição numérica antes de perder foco, nova edição após Undo, fechamento com alterações pendentes, referências de assets e limites/equivalência do histórico.
- Dois contratos de redução de trabalho passaram depois: repetir snapshot sem alteração e repetir depois de Undo não chama a captura completa. Os dois falhavam na referência como diagnóstico esperado de trabalho excessivo, registrado em `diagnostico-trabalho-antes.log`; não integram seus 317 testes aprovados.

Os quatro contratos suplementares de `verificar_limites.py` passaram contra o módulo preservado da referência e o módulo atual, com origens e hashes registrados. Exercitam a remoção efetiva de estados por orçamento em bytes UTF-8, a retenção de um único estado maior que o orçamento, limite de passos, sinais/Undo/Redo/nova ramificação, distinção entre inteiro/float/bool e escape literal Unicode, e comparação após mutar uma referência de asset no estado atual. Seus quatro registros são idênticos (`limites-antes.json` e `limites-depois.json`).

Quatro registros por tema com documento, estados completos do histórico, índice, tamanhos, botões e hashes dos pixels efetivamente pintados totalizam **oito registros exatamente iguais** entre as versões. A auditoria das 240 amostras de cada versão também exigiu igualdade de documento, histórico, índice, tamanhos, disponibilidade de Undo/Redo, botões e pixels, sem tolerância visual. Nenhuma exceção de callback Qt foi aceita como sucesso.

A auditoria verificou os instrumentos, contratos, fontes/modelos, ambiente, patch e todos os resultados. Seu registro está em `verificacao-comparacao.json`; a reversão exata do patch está em `verificacao-patch.json`. Os dados brutos estão em `antes.json`, `depois.json` e `raw/`; os manifestos próprios de cada versão, em `ambiente-antes.json` e `ambiente-depois.json`.

## Reproduzir e limites

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-etapa07-regressoes.log
.venv/bin/python tests/performance/run_history_checks.py --theme dark --evidence /tmp/fornax-etapa07-dark.json
.venv/bin/python tests/performance/run_history_checks.py --theme light --evidence /tmp/fornax-etapa07-light.json
.venv/bin/python tests/performance/benchmark_history.py --output /tmp/fornax-etapa07-medicoes --label depois
.venv/bin/python docs/desempenho_editor/etapa-07/verificar_limites.py --output /tmp/fornax-etapa07-limites.json
.venv/bin/python docs/desempenho_editor/etapa-07/verificar_comparacao.py
```

As medições devem rodar sozinhas. Para recuperar a referência, reverter o patch exclusivo numa cópia isolada do projeto. Não desfazer a implementação ou as etapas anteriores na pasta de trabalho. Os demais contratos são reproduzíveis pelos runners de seleção, camadas, organograma, texto, colagem e pintura em `tests/performance/`.

A medição de retorno à origem usa dois movimentos nativos dos itens; não simula todo um arraste físico de mouse/touchpad. Backend nativo do Linux/Windows, ponteiro real e uso prolongado continuam como verificações complementares. Não foi alterado o tratamento de conteúdo ou autorização de arquivos externos: a leitura de atributos de histórico não substitui a identificação/verificação de assets. Recuperação automática e reaproveitamento de cenas permanecem nas etapas seguintes.
