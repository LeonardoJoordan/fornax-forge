# Etapa 05 — Colagem e duplicação sem reconstruir a cena

**Concluída em 08/10/2026.** A etapa 06 aguarda autorização.

## Mudança aplicada

A colagem constrói somente as cópias, usando a mesma rotina de restauração da carga completa. Os objetos existentes e os widgets das suas camadas permanecem na cena. A rotina restaura propriedades, assets autorizados, identidades, máscaras e relações entre os novos objetos antes de publicar a seleção. A normalização da ordem das camadas continua igual à referência; não exige reconstruir a página.

Colagem, duplicação comum e duplicação de conjuntos do organograma consolidam a seleção e seus painéis ao final da operação. Na colagem comum, as camadas são atualizadas uma vez. Snapshots completos e uma ação de histórico por operação coletiva permanecem; carregamento, troca de página e restauração que precisem reconstruir a cena continuam disponíveis.

Permanecem nomes únicos, IDs novos, assinatura, formatação, links, proporção, rotação, visibilidade, bloqueio e vínculos de máscara. A colagem na mesma página mantém o deslocamento de 12 unidades; entre páginas mantém a posição original. A duplicação simples continua sobrepondo a cópia ao original, como antes. A duplicação de grupos/máscaras recupera o clipboard anterior mesmo diante de uma exceção. Conjuntos recebem nomes/identidades novos e preservam suas conexões internas.

Imagens e assinaturas na duplicação simples agora usam o provedor autorizado e o proxy existente, assim como a colagem. O teste anterior revelou cópias vazias quando o asset estava embutido no arquivo e não existia no disco: esse caso foi corrigido. Não há cache novo nem mudança na autorização dos arquivos protegidos.

Mudaram somente `features/editor/editor_window.py`, `features/editor/organogram_editor.py` e `features/editor/controls.py`. O patch exclusivo e a recuperação exata dos hashes anteriores estão em `alteracoes-etapa-05.patch` e `verificacao-patch.json`. Fontes, modelos prontos e os demais arquivos de produto do manifesto permaneceram iguais. As alterações locais das etapas anteriores foram preservadas.

## Método

- ThinkPad i5-8350U, Linux, Python 3.13.13, PySide6/Qt 6.11.0, Inter, Qt `offscreen`, tema escuro e janela solicitada de 1280 × 800. Ambiente, viewport efetivo e fonte coincidem por cenário.
- **14 cenários, 20 amostras por cenário antes e depois**, duas preparações e uma rodada separada de profiler. São 280 amostras em cada versão. Processos em sequência, sem outros testes simultâneos. Pintura e estabilização dos eventos entram no tempo; preparação do clipboard e restauração da cena ficam fora dele.
- Destinos de 20 textos ou 60/200 objetos mistos, colagem entre frente/verso, duplicação de texto, máscara, grupo e quatro conjuntos conectados. O clipboard de 1/10/50 textos usa dados completos do comando real de copiar, com identidades/posições distintas; permite medir 50 cópias num destino de 20 objetos. Não mede importação de clipboard externo.
- Somente nos instrumentos, a fonte de UUIDs é determinística e os quatro conjuntos do clipboard são ordenados, pois o Qt não garante a ordem de enumeração da seleção. Os IDs novos continuam distintos. O produto mantém seu comportamento anterior.
- Todas as amostras exigem o documento final, quantidade/seleção dos itens, histórico, linhas das camadas, clipboard, entrada, viewport e fonte iguais à referência. Retenção dos objetos/widgets e contagens de trabalho são diferenças pretendidas. Guias são ordenadas na evidência, pois não têm ordem semântica; a comparação de undo/redo normaliza z pela ordem das camadas, como a restauração anterior já fazia. A comparação entre versões preserva os valores z reais.
- Os instrumentos temporizados mantêm exatamente os mesmos hashes. Após a referência foram acrescentados o contrato de ciclo de vida do papel e a asserção explícita das guias; a diferença está em `contratos-adicionais-depois.json`. Os manifestos anteriores não foram reescritos. Ao finalizar houve apenas remoção de espaços em quatro linhas vazias; `ajuste-espacos.patch` permite recuperar exatamente o código medido. A auditoria verifica essa equivalência e a referência anterior.

## Tempos

Milissegundos; p95 interpolado. Dados completos, dispersão, memória e perfis estão em `antes.json`, `depois.json` e `raw/`.

| Operação | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|
| Colar 1 item — página com 20 objetos | 344,23 | 75,02 | 405,44 → 89,15 |
| Colar 10 itens — página com 20 objetos | 504,97 | 168,16 | 706,88 → 191,89 |
| Colar 50 itens — página com 20 objetos | 1.658,67 | 715,34 | 1.910,55 → 833,72 |
| Colar 1 item — página com 60 objetos | 1.059,81 | 126,75 | 1.157,23 → 149,94 |
| Colar 10 itens — página com 60 objetos | 1.281,65 | 250,50 | 1.433,19 → 281,59 |
| Colar 50 itens — página com 60 objetos | 2.853,46 | 1.064,01 | 3.166,63 → 1.304,74 |
| Colar 1 item — página com 200 objetos | 7.981,72 | 308,70 | 8.175,53 → 391,98 |
| Colar 10 itens — página com 200 objetos | 6.587,02 | 576,02 | 6.854,43 → 723,42 |
| Colar 50 itens — página com 200 objetos | 13.024,09 | 2.587,27 | 14.696,67 → 3.013,22 |
| Colar entre frente e verso | 851,12 | 117,99 | 1.289,37 → 135,72 |
| Duplicar um texto | 112,39 | 106,44 | 123,17 → 122,23 |
| Duplicar uma máscara | 839,37 | 123,70 | 942,70 → 135,00 |
| Duplicar um grupo | 975,02 | 227,37 | 1.203,60 → 271,42 |
| Duplicar quatro conjuntos conectados | 111,69 | 71,77 | 141,81 → 80,74 |

A redução principal vem da retirada da reconstrução completa na colagem e duplicação de máscaras/grupos. Duplicação simples e de conjuntos já inseriam objetos sem refazer a cena; nesses casos a mudança consolida a seleção. As medianas desta rodada não devem ser extrapoladas para todas as plataformas ou sessões de uso. O custo de serializar o documento e manter os snapshots continua existindo. A duplicação de um texto isolado variou pouco (112,39 → 106,44 ms), com p95 quase igual; não se considera esse cenário um ganho relevante. Os cenários são medidos em processos separados e sofrem variação do ambiente: suas medianas não formam uma curva estritamente crescente pelo número de cópias.

## Trabalho e memória

Contagens de uma execução adicional com profiler, fora dos tempos medidos. Construções de texto contam `DesignerBox`, não os handles ou outros objetos auxiliares.

| Operação | Reconstruções completas | Construções de texto | Atualizações das camadas | Sincronizações da seleção |
|---|---:|---:|---:|---:|
| Colar 1 item — página com 60 objetos | 1 → 0 | 25 → 1 | 3 → 1 | 3 → 1 |
| Colar 1 item — página com 200 objetos | 1 → 0 | 81 → 1 | 3 → 1 | 3 → 1 |
| Colar 50 itens — página com 200 objetos | 1 → 0 | 130 → 50 | 3 → 1 | 52 → 1 |
| Colar entre frente e verso | 1 → 0 | 25 → 1 | 3 → 1 | 2 → 1 |
| Duplicar uma máscara | 1 → 0 | 24 → 0 | 3 → 1 | 4 → 1 |
| Duplicar um grupo | 1 → 0 | 28 → 4 | 3 → 1 | 4 → 1 |
| Duplicar um texto | 0 → 0 | 1 → 1 | 1 → 1 | 3 → 1 |
| Duplicar quatro conjuntos conectados | 0 → 0 | 0 → 0 | 0 → 0 | 5 → 1 |

| Operação | Objetos originais retidos | Widgets de camadas originais retidos |
|---|---:|---:|
| Colar 1 item — página com 20 objetos | 0 → 22 | 0 → 21 |
| Colar 1 item — página com 60 objetos | 0 → 62 | 0 → 61 |
| Colar 1 item — página com 200 objetos | 0 → 202 | 0 → 201 |
| Duplicar uma máscara | 0 → 62 | 0 → 61 |
| Duplicar um grupo | 0 → 62 | 0 → 61 |
| Duplicar um texto | 62 → 62 | 61 → 61 |
| Duplicar quatro conjuntos conectados | 79 → 79 | 1 → 1 |

Os objetos retidos contam itens de conteúdo dos tipos monitorados, incluindo fundo editável e filhos de máscaras, sem os handles ou o papel auxiliar. Por isso uma página de 200 objetos registra 202 itens retidos. As linhas e seus widgets são monitorados separadamente. O probe `verificar_controles.py` clicou nos botões reais de visibilidade e bloqueio das camadas existentes e no botão de visibilidade de uma cópia: os três funcionaram, sem exceções dos callbacks Qt. Depois da otimização, o objeto e o widget originais também permaneceram os mesmos.

As leituras nativas de imagem (`QImageReader.read`) foram zero nos perfis aquecidos das duas versões; o cache da etapa 02 já evitava a decodificação repetida. A etapa 05 elimina a construção/reconfiguração de imagens existentes, sem alegar nova economia de decodificação nesses cenários. O teste de duplicação de assets exige pixels autorizados válidos nas novas cópias.

| Cenário | RSS antes (MiB) | RSS depois (MiB) |
|---|---:|---:|
| Colar 1 item — página com 60 objetos | 251,62–302,52 | 243,54–251,13 |
| Colar 1 item — página com 200 objetos | 654,84–661,04 | 488,88–497,30 |
| Colar 50 itens — página com 200 objetos | 659,95–665,28 | 501,20–502,30 |
| Duplicar quatro conjuntos conectados | 134,08–137,77 | 134,12–137,82 |

RSS é a memória corrente do processo, não o pico nem somente as alocações Python. As rodadas incluem fontes, Qt, histórico e reconstrução fora do cronômetro. Essas faixas não demonstram ausência de vazamentos em sessões prolongadas nem economia permanente de memória. `visual_cache_bytes` é igual antes/depois em todas as amostras.

## Segurança da cena e falhas encontradas na validação

A primeira implementação foi reprovada antes de formar a referência posterior final: houve uma falha nativa durante a troca de página/undo e descarte do papel da cena. A investigação com faulthandler/GDB identificou o wrapper criado pela fábrica nativa `scene.addRect`. O papel agora é construído com `QGraphicsRectItem` no Python, adicionado à cena e liberado antes da substituição. O Qt continua responsável pela remoção do item, com ciclo de vida acompanhado pelo Shiboken. O contrato específico verifica criação, invalidação após `scene.clear` e coleta; falha na versão anterior e passa na atual. O papel inicial usa a mesma rotina. A aparência permanece idêntica.

A comparação de pixels também revelou perda de guias quando a ordenação consultava `parentItem()` em itens auxiliares sem pai, alterando sua posse no binding. A ordenação agora filtra o tipo e a identidade antes de consultar o pai. Guias não são tocadas ao inserir cópias. A construção completa preserva a sequência original de criação das guias para não alterar empates na ordem de pintura.

Referências fortes aos objetos novos permanecem até registrar as camadas e completar o parentesco das máscaras. Um teste força coleta durante esse processo. Os registros das falhas iniciais e da correção ficam em `diagnostico-insercao/`; não são resultados aprovados nem amostras de desempenho. A referência posterior oficial foi obtida somente após corrigir esses problemas e passar novamente nas regressões.

## Comportamento e fidelidade

- **Antes:** 209 regressões + 18 contratos de seleção + 19 de camadas + 13 do quadro + 13 de texto + 9 comportamentos de cópia = **281 testes distintos aprovados**. Os testes de redução de trabalho eram diagnósticos com falhas esperadas, identificados separadamente.
- **Depois:** os mesmos 272 testes das etapas anteriores + 15 de cópia = **287 testes distintos aprovados**. Os quinze de cópia passaram nos temas claro e escuro; repetições entre temas não aumentam o total. Não houve módulos de regressão com falha.
- **21 estados por tema, 42 ao todo:** documento, seleção, clipboard, histórico e pixels da cena exatamente iguais à referência. Cobrem colagens de 1/10/50, frente/verso, máscaras, grupos, conjuntos conectados, undo/redo, conteúdo oculto/bloqueado com links/rotação, colagens repetidas, arquivos públicos e protegidos e elementos da página 1 colados no quadro.
- Os seis contratos de trabalho verificam preservação de objetos/widgets, ausência da carga completa, uma atualização de camadas/seleção, coleta durante máscaras, assets embutidos nas duplicações simples e descarte seguro do papel. Exceções nos callbacks Qt também reprovam.
- A auditoria `verificacao-comparacao.json` confere 14 cenários completos, todas as amostras, hashes de produto/instrumentos/testes, ambiente e recuperação dos arquivos anteriores. Esta etapa compara os pixels da cena após cópias; não acrescenta uma nova comparação de PDFs dos modelos publicados. As regressões existentes continuam cobrindo os caminhos de geração e ladrilhos.

## Limites e repetição

Validação na mesma máquina/fontes com Qt `offscreen`. Uso prolongado no backend nativo Linux, interação real com touchpad e execução no Windows continuam como verificação complementar. As imagens de evidência mostram molduras do editor e são comparadas contra o mesmo canal/escala; não se promete identidade entre dispositivos de pintura diferentes. A otimização não altera os layouts dos modelos prontos nem elimina a reconstrução necessária no carregamento ou em restaurações do histórico.

```bash
.venv/bin/python tests/performance/run_copy_checks.py --theme dark
.venv/bin/python tests/performance/run_copy_checks.py --theme light
.venv/bin/python tests/performance/compare_copy_evidence.py docs/desempenho_editor/etapa-05/evidencia-antes-dark.json docs/desempenho_editor/etapa-05/evidencia-depois-dark.json
.venv/bin/python tests/performance/compare_copy_evidence.py docs/desempenho_editor/etapa-05/evidencia-antes-light.json docs/desempenho_editor/etapa-05/evidencia-depois-light.json
.venv/bin/python docs/desempenho_editor/etapa-05/verificar_comparacao.py
```

Os comandos de benchmark estão em `tests/performance/README.md`. Use outra pasta de saída para preservar estas evidências. A etapa 06 não foi iniciada.
