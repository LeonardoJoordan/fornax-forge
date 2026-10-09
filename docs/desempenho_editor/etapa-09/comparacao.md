# Etapa 09 — Reutilizar cenas ao trocar de página

Data: 09/10/2026. Etapa concluída; medições antes/depois finalizadas.

## Mudança

O editor mantém uma cena inativa e a reativa quando a página e suas dependências
continuam compatíveis com o documento. A troca conecta os callbacks somente à
cena ativa e restaura seleção, controles, papel, guias, propriedades e réguas.
Alças e caneta textual voltam à geometria inicial do carregador para que seu
estado dependente do zoom não altere o enquadramento da página. As alças do
fundo materializado são restauradas com o mesmo ajuste de zoom feito por
`bind_document` no carregador, inclusive quando ele reconhece o fundo pelo
nome histórico em arquivos sem a marca explícita.
Na reativação também se aplica a normalização de `layer_order` já usada pelo
carregador, com os valores locais das imagens em máscaras e a ordem das guias.
Isso conserva a equivalência do histórico depois de editar e alternar páginas,
sem reconstruir os objetos nem mudar as regras de ordenação.

A validação inclui conteúdo completo da página, assets por SHA-256, fontes,
idioma, tema e geração/revisão da autorização. O organograma inclui também a
Página 1 e seus assets. Não se usa apenas um contador de edição nem os metadados
dos arquivos externos. Um arquivo substituído no mesmo caminho, tamanho e data
é reconhecido pelo conteúdo. Recursos alterados enquanto a página estava ativa
impedem associar seus pixels anteriores à nova chave.

A retenção tem orçamento **estimado** de 64 MiB e teto de 5.000 itens, incluindo
filhos e adornos. Há no máximo uma cena inativa por editor. A estimativa combina
8 KiB por item, HTML e pixels; não é um limite absoluto do RSS do processo.
Documentos acima do orçamento usam a reconstrução completa.
Fundos no formato legado também usam esse caminho até a conversão ser
persistida: o carregador cria a identidade da imagem convertida e uma cena
antecipadamente reutilizada ainda não pode corresponder a ela com segurança. Histórico,
carregamento de outro documento e limpeza/remoção de páginas invalidam as cenas.
Ao fechar o editor, a cena inativa é descartada; no encerramento protegido,
também se descartam imediatamente os itens e referências visuais da cena ativa.

Alterações de produto: `features/editor/document_session.py`,
`features/editor/editor_window.py` e o novo `features/editor/page_scenes.py`.
Não houve alteração de formato, gerador, templates, regras de agrupamento,
disposição de camadas, dados ou semântica de Undo/Redo.

## Método

O estado anterior é a cópia preservada ao começar esta etapa, já contendo as
etapas 00–08 e as mudanças locais anteriores. Os processos de referência usam
um overlay desses módulos, sem reverter o workspace nem usar `HEAD` como base.
`patch-etapa-09.diff`, `identidade-patch.json` e `verificacao-patch.json` registram
o patch exclusivo e sua reversão exata em uma cópia temporária.

Oito cenários: frente/verso com 20, 60 e 200 objetos; cartão/organograma com
5, 40 e 100 blocos; frente/verso e cartão/organograma com edição do cartão antes
de alternar. As páginas densas incluem textos, formas, imagens, assinaturas,
máscaras, grupos e guias. Dados e preferências ficam em pastas temporárias.

Cada cenário executa em processo próprio, com dois aquecimentos e vinte
amostras, em sequência. A medição abrange ida e volta com processamento dos
eventos e pintura. Verificações e capturas do backing store ficam fora do tempo
medido. O profiler executa em uma rodada adicional, fora das amostras. Nos casos
editados, a preparação fora do cronômetro restaura a posição original e visita
a outra página antes de voltar ao cartão. A cena dependente fica correspondente
a essa entrada; a edição medida volta a invalidá-la. Não se acumula deslocamento
entre amostras. `edit_start_x` registra e verifica a posição inicial das vinte
amostras nas duas versões.

Há 100 ciclos adicionais de memória nos cenários simples, cinco no caso de
200 objetos e vinte nos demais cenários densos,
além das trocas da medição. Os registros de RSS correspondem ao estado atual,
não ao pico. O limite de proteção do benchmark é 2 GiB. Abertura a frio não é
medida nesta etapa; a primeira visita e a reconstrução são verificadas pelos
contratos de comportamento.

Linux, Qt offscreen, escala 1, Inter embutida, tema escuro e janela 1280×800.
Fontes, viewport, identidade das entradas, hashes de produto e scripts são
registrados em `ambiente-antes.json`, `ambiente-depois.json` e resultados brutos.
As amostras originais de diagnóstico foram descartadas: incluíam execuções
concorrentes; o caso de 200 objetos excedeu 600 segundos nas configurações
exploratórias de 100 e 20 ciclos adicionais. O diagnóstico separado encontrou
trabalho de reconstrução de camadas e atribuição de IDs. A execução definitiva
mantém vinte amostras, usa cinco ciclos adicionais nesse caso e timeout de
1.800 segundos por processo. Esses parâmetros são iguais nas duas versões.
Ver `diagnostico-inicial/NOTA.md`; esses tempos não compõem a comparação final.

Os dois cenários com edição inicialmente escolhiam o primeiro texto retornado
pela cena; a reconstrução pode mudar essa ordem. O alvo passou a ser uma caixa
com `layer_id` fixo e os dois cenários foram repetidos nas duas versões com essa
mesma entrada. Os outros seis não executam o ramo de edição. Essa revisão do
harness está registrada em `ambiente-casos-editados.json`; os resultados
anteriores ficam em `diagnostico-inicial/alvo-indefinido`.
A comparação com o alvo fixo revelou ainda a necessidade de reproduzir a
normalização de camadas do carregador na cena reativada. Após corrigir isso,
todos os oito cenários da versão final foram repetidos. As medições anteriores
da implementação ficam em `diagnostico-inicial/antes-da-normalizacao-das-camadas`.
Uma verificação complementar encontrou `KeyError` ao reativar fundo no formato
legado, ainda sem identidade persistida. Foi adicionado um contrato comum às
duas versões e a retenção desse caso passou a usar a reconstrução segura. A
execução anterior do benchmark foi interrompida e arquivada; as regressões e
todos os cenários finais foram repetidos após a proteção. A referência executou
novamente os 16 contratos comuns; a prova e identidade do teste complementar
estão em `ambiente-contrato-legado.json`. Ver
`diagnostico-inicial/fundo-legado-sem-guard.log` e
`diagnostico-inicial/antes-da-protecao-do-fundo-legado`.
A comparação seguinte confirmou documentos e histórico iguais, mas encontrou
diferenças de zoom/pixels nos casos editados: as alças ocultas do fundo
materializado tinham outra geometria na reativação. A restauração passou a
reproduzir `bind_document`; o contrato foi ampliado para comparar a pintura
com uma única chamada a ajustar à tela após editar. Os resultados intermediários
ficam em `diagnostico-inicial/antes-da-geometria-do-fundo`.
Os dois cenários editados também foram repetidos na referência com a preparação
da posição inicial descrita acima. Essa revisão final é registrada em
`ambiente-casos-editados-final.json`; os seis cenários sem edição não executam
a preparação de geometria. Todos os oito cenários da implementação final usam
o harness final e foram medidos novamente após esses ajustes.

O overlay de referência não importa `page_scenes.py`: esse módulo novo não
participa da execução anterior. Seu hash listado nos metadados daquela execução
descreve o arquivo que existia no workspace, não código executado pela referência.

## Resultados

| Cenário (ida e volta) | Antes, mediana / p95 (ms) | Depois, mediana / p95 (ms) | Redução da mediana |
|---|---:|---:|---:|
| duplex-20 | 462.88 / 648.49 | 266.20 / 321.81 | 42.5% |
| duplex-60 | 1497.97 / 1707.40 | 549.49 / 664.64 | 63.3% |
| duplex-200 | 11333.24 / 13244.63 | 11824.20 / 15254.75 | -4.3% |
| board-5 | 150.05 / 234.84 | 141.99 / 205.88 | 5.4% |
| board-40 | 233.42 / 319.05 | 222.89 / 289.08 | 4.5% |
| board-100 | 275.58 / 294.85 | 306.80 / 350.25 | -11.3% |
| duplex-edit | 1616.49 / 1914.01 | 758.05 / 1025.78 | 53.1% |
| board-edit | 221.37 / 250.73 | 278.79 / 375.59 | -25.9% |

O ganho não é uniforme. Frente/verso teve reduções de 42,5% a 63,3% nos casos
elegíveis; os organogramas de 5 e 40 blocos reduziram a mediana em 5,4% e 4,5%,
com dispersão relevante. O caso de 100 blocos aumentou 11,3% na mediana, apesar
de evitar reconstruções. Após editar o cartão do organograma, a mediana aumentou
25,9%. O quadro dependente ainda precisa ser reconstruído e a validação e
restauração da outra cena acrescentam trabalho; a contribuição individual
desses custos não foi isolada nesta medição. O caso de 200 objetos, que usa
a reconstrução, aumentou 4,3%. Esses aumentos estão registrados como limites
da implementação; não há ganho geral de tempo comprovado para o organograma.

As 160 amostras pareadas e a verificação final das duas páginas de cada caso
produziram documentos, histórico, índices, botões, seleção, estado da cena e
pixels iguais. `verificacao-comparacao.json` registra zero diferenças.

| Cenário | Reconstruções de cena por ciclo, antes → depois | Blocos de organograma reconstruídos, antes → depois |
|---|---:|---:|
| duplex-20 | 2 → 0 | 0 → 0 |
| duplex-60 | 2 → 0 | 0 → 0 |
| duplex-200 | 2 → 2 | 0 → 0 |
| board-5 | 2 → 0 | 5 → 0 |
| board-40 | 2 → 0 | 40 → 0 |
| board-100 | 2 → 0 | 100 → 0 |
| duplex-edit | 2 → 0 | 0 → 0 |
| board-edit | 2 → 1 | 40 → 40 |

As contagens são de uma rodada separada de profiler, não das verificações.
As funções completas e as construções de objetos/decodificações estão nos JSON
brutos. Os cinco cenários sem edição e dentro do orçamento evitam reconstruir
as cenas nas revisitas. Edição do cartão invalida o organograma dependente.

O cenário de 200 objetos inclui quarenta formas, cujos proxies transparentes
de 1000×1000 pixels ultrapassam o orçamento de retenção. Ele usa a reconstrução
nas duas versões; a otimização não beneficia esse caso. O orçamento não foi
aumentado para favorecer o benchmark.

| Cenário | Ciclos adicionais | RSS antes, início → fim (MiB) | RSS depois, início → fim (MiB) | Cena inativa estimada depois (MiB) |
|---|---:|---:|---:|---:|
| duplex-20 | 100 | 132.73 → 131.94 | 139.27 → 138.41 | 9.48 |
| duplex-60 | 20 | 232.02 → 235.13 | 242.96 → 242.22 | 58.18 |
| duplex-200 | 5 | 480.27 → 480.98 | 488.57 → 489.16 | 0.00 |
| board-5 | 100 | 124.79 → 124.97 | 128.65 → 128.85 | 0.93 |
| board-40 | 20 | 126.00 → 126.00 | 129.71 → 129.79 | 1.48 |
| board-100 | 20 | 127.05 → 127.16 | 131.89 → 132.07 | 2.41 |
| duplex-edit | 20 | 238.81 → 242.58 | 248.68 → 251.62 | 58.18 |
| board-edit | 20 | 131.46 → 132.73 | 134.56 → 135.86 | 1.48 |

O início desta tabela é após aquecimento e medições, não abertura a frio.
A cena adicional aumenta a memória residente, mas não houve crescimento
contínuo relevante nos ciclos observados. O maior cenário reteve zero cenas.
Todos ficaram abaixo da proteção de 2 GiB; isso não é uma garantia de consumo
para qualquer modelo. `verificacao-final.json` confere os hashes do produto
e harness medidos contra os arquivos finais.

## Testes

**Antes: 366 testes; depois: 376 testes.** São 350 regressões existentes,
16 contratos de comportamento comuns às duas versões e dez contratos
específicos de reutilização. Os 26 contratos da etapa passaram também no tema
claro; essa repetição não aumenta o número de testes distintos.

Cobertura: seleção por página, máscaras e coleta de wrappers, guias,
finalização da edição textual, atalhos, dimensões compartilhadas, alteração
direta de página inativa, cartão e assets atualizados no organograma, imagens
externas com metadados idênticos, limpar/adicionar/remover páginas, Undo/Redo,
outro documento, pixels, zoom, callbacks ativos, ausência de callbacks na cena
inativa, teto de retenção, fontes, tema, wrappers destruídos, fechamento público
e fechamento real protegido. As regressões anteriores abrangem também
recuperação concorrente, publicação de pacotes e encerramento da aplicação.

Logs e comandos: `checks-antes.json`, `checks-depois.json`,
`regressoes-antes.log`, `regressoes-depois.log`, demais `*.runner.log`,
`pages-depois-light.log` e `contagem-testes.json`.

## Reprodução

```bash
.venv/bin/python tests/performance/run_page_regressions.py --output /tmp/fornax-etapa09-checks --label depois
.venv/bin/python tests/performance/run_page_checks.py --reuse --theme light
.venv/bin/python tests/performance/benchmark_pages.py --output /tmp/fornax-etapa09-bench --label depois
```

Para reconstruir a referência a partir do produto desta etapa, copie os
arquivos do patch para uma árvore temporária com os mesmos caminhos e aplique
`patch -R -p1` nessa cópia. O módulo novo será removido somente da cópia.
Passe a pasta temporária `features/editor` em `--reference` aos drivers de
regressão e benchmark, usando `--label antes`. Então compare:

```bash
.venv/bin/python tests/performance/compare_pages.py /tmp/fornax-etapa09-bench
```

## Limitações

A reativação ainda atualiza controles e linhas de camadas e verifica hashes
de assets. Assets grandes ou armazenamento lento podem aumentar o custo dessas
verificações. A primeira visita, dependências alteradas e restauração do
histórico continuam usando a reconstrução segura. A cena adicional aumenta
a memória retida dentro do orçamento estimado; o cache não elimina os outros
consumidores de memória do editor.

Os resultados cobrem este ambiente e as entradas sintéticas descritas. Backend
nativo Linux/Windows, sessões prolongadas e documentos reais com assets grandes
continuam como validação complementar. A etapa 10 não foi iniciada.
