# Tabelas — etapa 00: referência e preparação

09/10/2026. **Etapa concluída.** A referência atual foi preservada, as
verificações passaram e os cenários de aceitação ficaram preparados.
Não houve alteração em `core/`, `features/`, `main.py`, requisitos, build
ou assets. O editor ainda não possui o elemento Tabela.

## Entregas

- Identificação da branch `upgrade-01`, commit
  `19c686fb2ae686eff1b2795fe5465a8b52ee157e` e alterações locais existentes.
- Cópia de 171 arquivos de fontes/configurações, incluindo código ainda não
  commitado; inventário de hashes e conferência dos 111 assets empacotados.
- Quatro especificações sintéticas: boletim, escala, mesclagens e frente/verso.
- Runner reproduzível de quinze cenários existentes, sem implementar o recurso.
- [Mapa confirmado da integração](MAPA_INTEGRACAO.md), incluindo os caminhos
  de geração e a diferença entre avisos e erros fatais.
- Logs de testes, amostras brutas, resumos e verificação de integridade.

## Referência preservada

[referencia.json](referencia.json) registra ambiente, branch/commit, estado
inicial e hashes por arquivo. O commit sozinho não representava o código
testado, pois as otimizações anteriores continuam na árvore de trabalho.

[referencia-fontes.tar.gz](referencia-fontes.tar.gz) preserva os fontes Python
de produção/testes e configurações de build. Os membros foram lidos novamente
e comparados aos hashes. Não contém dependências instaladas, assets, biblioteca
pessoal, preferências ou credenciais de sessão. Os assets estão identificados
por hash no inventário, para conferir a mesma entrada numa reprodução.

[alteracoes-locais-iniciais.patch](alteracoes-locais-iniciais.patch) complementa
o arquivo de fontes com o diff dos arquivos versionados; não substitui a cópia
dos módulos que ainda não estavam no Git. Para recuperar a referência, usar
uma pasta isolada, disponibilizar os assets/dependências correspondentes e
preservar os drivers registrados. Não extrair por cima do projeto em uso.

[verificacao-referencia.json](verificacao-referencia.json) confirma que os
fontes originais e assets mantiveram seus hashes e que nenhum módulo de
produção foi acrescentado durante a etapa. Os instrumentos medidos e as
fixtures também coincidem com seus registros.

## Cenários para a próxima etapa

Os arquivos e suas instruções estão em `tests/fixtures/tables/`:

| Cenário | Preparação |
|---|---|
| Boletim | 10 × 6, títulos mesclados, notas por placeholder, conteúdo vazio, zero numérico, negrito e observação multilinha. |
| Escala | 8 × 5, cinco posições fixas preenchidas por um registro, formatação de intervalos e alterações de linhas/colunas. |
| Mesclagens | 4 × 4, áreas horizontais/verticais, texto a preservar numa mesclagem, Unicode, placeholder dividido entre spans, bloco opcional e overflow. |
| Frente/verso | Grades 3 × 3 e 4 × 2, páginas independentes e campo exclusivo do verso. |

Essas fixtures são **especificações de aceitação, não modelos `.fornax`**.
Não declaram `schema_version`, não foram adicionadas à biblioteca e não
antecipam o contrato persistente da etapa 02. O gerador conferiu cobertura
completa, ausência de sobreposição, medidas e referências de expectativas.
Os nomes e dados são inventados. Nenhuma tabela foi renderizada por elas.

## Testes de referência

| Bateria | Execuções de testes | Resultado |
|---|---:|---|
| Suíte principal, incluindo contratos de desempenho | 209 | Todos passaram. |
| Cenas, caches, conectores, recuperação e otimizações Pareto | 126 | Todos passaram. |
| Texto, captura de histórico, cópia, camadas, planilha, foco e ajuda | 96 | Todos passaram. |

**Há sobreposição e herança entre as baterias. Não somar como testes
distintos.** São verificações dos recursos já existentes, não uma certificação
das funções de tabela ainda não implementadas. Os runners também recusam
exceções não tratadas de callbacks Qt encontradas nos logs.

Evidências: [testes-resumo.json](testes-resumo.json),
[regressoes-antes.log](regressoes-antes.log),
[pareto-antes/results.json](pareto-antes/results.json) e
[integracoes-antes/results.json](integracoes-antes/results.json).

## Medições de referência

Linux no ThinkPad i5-8350U, Python 3.13.13, PySide6/Qt 6.11.0, Qt offscreen,
tema escuro, Inter e escala 1. Processos e dados/preferências isolados, com
execução sequencial. Duas preparações; vinte amostras para as oito ações do
editor/histórico e cinco para os sete cenários caros da rodada Pareto.
Os perfis, quando previstos no instrumento original, ficaram fora dos tempos.

| Operação | Mediana | p95 | Amostras |
|---|---:|---:|---:|
| Digitar ` equipe` numa caixa de texto do cenário curto | 34,22 ms | 37,25 ms | 20 |
| Colar texto com acentos/Unicode no mesmo cenário | 20,97 ms | 28,48 ms | 20 |
| Colar dez objetos numa página de sessenta | 231,89 ms | 288,16 ms | 20 |
| Duplicar um grupo numa página de sessenta objetos | 230,95 ms | 341,70 ms | 20 |
| **Vinte idas e voltas** entre frente/verso de sessenta objetos | 14.543,86 ms | 15.916,60 ms | 20 |
| Snapshot sem alteração, sessenta objetos | 3,18 ms | 6,39 ms | 20 |
| Snapshot sem alteração após undo | 3,77 ms | 4,58 ms | 20 |
| Mover objeto e registrar snapshot | 29,21 ms | 34,86 ms | 20 |
| Uma ida e volta entre páginas de duzentos objetos | 2.378,97 ms | 2.459,27 ms | 5 |
| Calcular rotas de cem grupos / 99 conexões | 4.706,89 ms | 4.928,77 ms | 5 |
| Mover um grupo num quadro de mil cartões em cem grupos | 3.943,65 ms | 5.134,21 ms | 5 |
| Recuperação pública pequena | 79,33 ms | 131,77 ms | 5 |
| Recuperação pública com imagens grandes | 197,69 ms | 226,07 ms | 5 |
| Recuperação de assinaturas com imagens grandes | 280,00 ms | 310,20 ms | 5 |
| Recuperação integral com imagens grandes | 225,30 ms | 240,66 ms | 5 |

O ciclo de páginas executa **quarenta trocas por amostra**. Seus 14,54 s não
são o tempo de abrir uma única página. Movimento do quadro inclui histórico
e pintura; recuperação mede até o arquivo publicado/verificado, não só o
agendamento. Os instrumentos conferem os estados esperados, e pixels/rotas
nos caminhos em que essas evidências já são capturadas.

Resumo e caminhos das amostras: [medicoes-resumo.json](medicoes-resumo.json).
Comandos e retornos: [execucoes-antes.json](execucoes-antes.json).
Identidade dos drivers: [instrumentos-antes.json](instrumentos-antes.json).
Cada diretório de medições também preserva o ambiente, estados, amostras,
contagens e logs previstos no driver original.

Os valores desta rodada não foram tratados como melhora/piora contra o
relatório Pareto anterior: os fontes permaneceram iguais, e são execuções em
momentos diferentes. Há dispersão, particularmente nas rotas e na recuperação
pequena. Esta é a referência a repetir nas mesmas condições após implementar
tabelas; diferenças próximas da dispersão precisam de mais amostras antes
de atribuir ganho ou regressão.

## Cuidados confirmados

- Placeholder vazio hoje pode ocultar uma caixa inteira. A política da célula
  precisa ser distinta, preservando grade e texto fixo.
- Camadas, serialização, fontes, campos e desenho complementar enumeram tipos
  explicitamente. Não existe uma inclusão única que resolva todos os caminhos.
- Os PDFs comuns já usam imagens do cartão/folha. Manter esse caminho é
  compatível com uma tabela editável no modelo; não prometer saída vetorial
  nem ampliar esta tarefa para reescrever a exportação.
- Existe log de geração, mas não uma coleta uniforme de avisos de overflow
  por célula/registro nos renderers e workers. Sua integração precisa ser
  planejada, incluindo deduplicação em ladrilhos e ausência de acesso à UI
  pela thread de geração.
- O quadro de mil cartões usa cem grupos e 99 conexões, com uma prévia de
  cartão compartilhada. Não representa mil blocos individuais, mil fotos ou
  mil editores de célula. O roteamento desse cenário continua custoso.

O [mapa de integração](MAPA_INTEGRACAO.md) detalha os consumidores encontrados.
Não houve correção desses pontos nesta etapa preparatória.

## Reprodução e continuidade

A partir da raiz, sem executar suítes pesadas junto das medições:

```bash
.venv/bin/python tests/performance/table_fixtures.py --check
.venv/bin/python tests/performance/run_table_baseline.py --output /tmp/fornax-tabelas-repeticao --label antes
```

O README de `tests/performance/` documenta os instrumentos. Manter os arquivos
originais desta rodada; repetições devem ir para outra pasta. Para a comparação
posterior, usar `--label depois` e registrar quaisquer mudanças dos drivers.

Validação nativa em Linux/Windows, uso de mouse/touchpad e desempenho/fidelidade
do novo elemento não foram certificados nesta etapa. A próxima entrega é
a **etapa 01: prova técnica isolada de layout e edição**, com escolha do motor
e conferência de medidas, mesclagens, clipping e saída. As etapas 01–08
continuam pendentes.
