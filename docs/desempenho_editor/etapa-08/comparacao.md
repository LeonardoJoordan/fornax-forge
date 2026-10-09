# Etapa 08 — Recuperação automática eficiente

**Concluída em 09/10/2026**, após autorização para executar esta etapa. A etapa 09 permanece pendente de autorização.

## Resultado e funcionamento

A recuperação não monta novamente um pacote idêntico ao último publicado com sucesso. A chave compara documento completo, bytes dos assets por SHA-256, proteção, identidade/revisão e geração da autorização. Também confere o conteúdo do original e a recuperação existente. Mudar uma imagem externa, apagar/substituir a recuperação, alterar a proteção ou salvar manualmente invalida a reutilização pertinente. Esse controle é separado do estado salvo manualmente: não limpa o aviso de alterações nem modifica o histórico.

A interface captura um documento independente, bytes já autorizados e metadados dos arquivos externos. O trabalhador recebe dados próprios; não recebe cena, widgets, `QPixmap`, sessão mutável nem callbacks do editor para resolver assets. Lê os arquivos externos com o limite do formato, confirma a consistência da leitura e executa serialização, compressão, criptografia, hashes, verificação do pacote, preparação do backup e sincronização dos seus bytes em segundo plano. Imagens externas podem ser links simbólicos, como no salvamento normal; os pacotes de destino continuam recusando links simbólicos.

Cada editor mantém uma tarefa ativa e, quando necessário, um único snapshot pendente, substituído pela versão mais recente. Antes de publicar, o trabalhador confere novamente o original e solicita aprovação interna à interface. Ela valida documento atual, assets externos, gesto, geração e autorização. Uma edição de texto durante a preparação descarta o snapshot antigo e agenda o atual sem encerrar a digitação.

**A publicação final executa na interface**, sem processar eventos entre a validação e a publicação. Essa parte curta confirma metadados, adquire o lock do original, publica backup/destino e sincroniza o diretório; o lock da recuperação continua cobrindo toda a transação. Assim, uma edição não pode entrar entre a última validação e a publicação. Não se afirma bloqueio zero: a captura e essas operações finais ainda consomem tempo, sobretudo em um filesystem lento. A verificação completa do conteúdo ocorre antes, na tarefa de fundo; salvamentos normais mantêm suas verificações completas anteriores.

Carregar outro documento, salvar, trocar proteção/senha, remover a recuperação ou fechar revoga a permissão antes da ação. A sessão também revoga permissões ao perder autorização, mudar de modelo, recarregar, salvar, esquecer ou expirar. Tarefas canceladas não recriam arquivos removidos e não substituem recuperações posteriores. Falhas não marcam sucesso; conservam o pacote anterior e permitem tentar novamente. O original não é modificado pelo autosave.

A tarefa limpa suas referências e zera a cópia mutável da chave. Pacotes temporários de proteção completa permanecem criptografados. Fechar um editor não aguarda compressão nem verificação: descarta seu conteúdo e mantém apenas o ciclo de vida necessário à limpeza independente. Ao encerrar o aplicativo, as tarefas são canceladas e aguardadas antes da destruição dos serviços do Qt, inclusive as que esperavam aprovação da interface. Isso pode prolongar o encerramento enquanto um trabalho de arquivo termina sua limpeza.

Foram alterados `core/fornax_container.py`, `core/fornax_session.py` e `features/editor/editor_window.py`; foi adicionado `features/editor/recovery_worker.py`. Não houve mudança de formato, dependências, fontes, modelos prontos nem do gerador. O patch exclusivo e sua reversão conferida estão em `alteracoes-etapa-08.patch` e `verificacao-patch.json`.

## Medições antes/depois

Linux x86_64, Python 3.13.13, PySide/Qt 6.11, Inter, tema escuro, Qt offscreen/escala 1, janela de 1.280 × 800 e diretórios temporários isolados. O manifesto registra CPU, sistema, hashes e demais parâmetros. São **oito cenários, duas preparações e vinte amostras aquecidas por cenário: 160 amostras por versão**. Não há amostras frias nem rodada de perfil nesta medição. Casos grandes usam PNG determinístico de 1.024 × 1.024. A restauração, abertura da recuperação, comparação e captura de pixels ficam fora do cronômetro. O intervalo inclui a solicitação, conclusão e processamento de eventos.

A referência preservada contém as etapas 00–07. Foi medida antes da implementação; depois, a calibração dos instrumentos exigiu repetir a referência preservada e a versão final com o mesmo instrumento. As restaurações temporárias foram registradas em `reexecucao-referencia.json`; ao medir a referência, o módulo novo esteve ausente. Fontes, modelos e demais módulos permaneceram iguais. Os instrumentos finais têm hashes idênticos nas duas versões.

Um timer independente de 2 ms registra o maior intervalo entre atendimentos em cada amostra. A tabela mostra a mediana e o p95 desses máximos, em milissegundos. É uma medida de atraso observado no atendimento da UI, que inclui escalonamento, pintura e trabalho síncrono, não uma medição de um único método.

| Cenário | Mediana antes | Mediana depois | p95 antes | p95 depois |
|---|---:|---:|---:|---:|
| Público — pequeno | 41,64 | 16,34 | 50,89 | 17,87 |
| Assinaturas — pequeno | 50,42 | 15,85 | 55,21 | 17,83 |
| Proteção completa — pequeno | 38,95 | 16,53 | 46,85 | 30,74 |
| Público — assets grandes | 272,19 | 17,81 | 309,76 | 22,84 |
| Proteção completa — assets grandes | 281,90 | 18,25 | 316,35 | 22,41 |
| Público — três disparos iguais | 47,85 | 16,91 | 59,95 | 31,80 |
| Proteção completa/grande — três disparos iguais | 387,88 | 18,48 | 442,53 | 19,92 |
| Público — três edições sucessivas | 56,36 | 27,97 | 73,35 | 37,00 |

A tabela abaixo separa a soma dos tempos de retorno das solicitações do tempo até terminar todas as recuperações. Os valores são medianas. Em cada amostra dos cenários repetidos são feitos três disparos; no cenário contínuo existe uma nova edição em cada disparo. RSS é memória residente após a conclusão, **não pico durante compressão/criptografia**; seu máximo é calculado entre as vinte observações. Todas ficaram abaixo do guard de 2 GiB.

| Cenário | Retorno do timer antes → depois | Total antes → depois | Gravações antes → depois | RSS máxima observada antes → depois |
|---|---:|---:|---:|---:|
| Público — pequeno | 41,15 → 9,43 ms | 41,67 → 56,95 ms | 1 → 1 | 165,18 → 165,96 MiB |
| Assinaturas — pequeno | 49,99 → 8,81 ms | 50,45 → 63,37 ms | 1 → 1 | 165,90 → 166,73 MiB |
| Proteção completa — pequeno | 38,48 → 9,31 ms | 38,97 → 55,65 ms | 1 → 1 | 165,68 → 166,68 MiB |
| Público — assets grandes | 271,82 → 9,43 ms | 273,20 → 414,63 ms | 1 → 1 | 201,34 → 213,82 MiB |
| Proteção completa — assets grandes | 281,54 → 9,12 ms | 282,93 → 428,00 ms | 1 → 1 | 257,24 → 253,03 MiB |
| Público — três disparos iguais | 132,76 → 25,18 ms | 138,73 → 99,82 ms | 3 → 1 | 164,68 → 165,33 MiB |
| Proteção completa/grande — três disparos iguais | 1059,98 → 23,72 ms | 1066,18 → 635,57 ms | 3 → 1 | 300,78 → 256,12 MiB |
| Público — três edições sucessivas | 136,86 → 30,52 ms | 158,23 → 234,31 ms | 3 → 3 | 164,57 → 165,70 MiB |

O ganho principal é a responsividade e a eliminação de regravações, não acelerar toda recuperação nova. O pacote novo demora mais até concluir, devido ao snapshot independente, às validações adicionais, à confirmação no ciclo de eventos e à coordenação da tarefa. Nos disparos iguais, o total cai porque apenas o primeiro monta/grava o pacote. Ainda há leitura/conferência de hashes; não se promete ausência de I/O em um disparo reutilizado.

## Comportamento e testes

**337 testes distintos passaram na referência e 350 na versão final.** Repetições, temas e subtestes não aumentam esses números:

- 319 contratos das etapas anteriores: 209 regressões, 18 de seleção, 19 de camadas, 13 de organograma/conectores, 13 de texto, 15 de colagem, 11 de pintura, 17 de histórico e quatro verificações suplementares de limites/equivalência do histórico.
- Oito contratos de recuperação antes/depois: estado manual e histórico independentes, atualização de imagem externa, imagem por link simbólico, falha/retry, corrupção, perda de acesso, cópia que exige novo destino e reabertura de recuperação protegida como documento não salvo. As regressões também verificam texto, cursor, Undo e assets nos três modos de proteção e adiamento durante um gesto.
- Dez contratos de publicação antes/depois: pacote público/assets/backup, revisões protegidas completas e de assinaturas, aumento de proteção, troca de senha, falha de verificação, permissão, lock, fsync e mudança externa durante verificação ou após publicar o backup. Foram executados contra o módulo preservado e o atual.
- Dois contratos de trabalho passaram depois: três solicitações iguais resultam em uma montagem de pacote, e uma alteração externa do original impede a recuperação. Falhavam na referência; são diagnósticos esperados de problemas, não regressões aceitas nem testes aprovados da referência.
- Dez contratos específicos da execução assíncrona: UI continua atendendo eventos durante a preparação; texto mais novo substitui tarefa antiga; vários pedidos mantêm somente o último pendente; salvamento manual; fechamento público/protegido; troca de documento; expiração; alteração externa do original/destino; falha de publicação/retry; publicação na thread da UI.
- Um teste em processo próprio encerra o ciclo real do Qt enquanto uma recuperação completamente protegida aguarda publicação. Confirma cancelamento, término da thread, limpeza da chave/snapshot/staging e ausência de publicação tardia ou erro nativo ao encerrar.

As **160 comparações pareadas** preservam exatamente documento recuperado, estado salvo, histórico, assets e sua multiplicidade, modo de proteção, foco, cursor, original e pixels. Apenas os nomes internos aleatórios dos assets são substituídos por sua identidade SHA-256 para comparar versões; os conteúdos, ocorrências de referências e demais campos são conservados. Não se compara ZIP byte a byte, pois UUIDs e nonces variam por revisão. `verificacao-comparacao.json` e `verificar_comparacao.py` registram essa conferência.

## Calibração, limites e reprodução

A primeira espera usava `QTest.qWait(1)` em polling; isso disputava o GIL e inflava o tempo de segundo plano. A sonda com `QEventLoop` confirmou a distorção. A espera final executa o ciclo de eventos do Qt; a referência e a versão final foram repetidas assim. Também foi necessário normalizar os nomes aleatórios dos assets: os pixels já eram iguais, mas comparar UUIDs produzia diferenças artificiais. Os resultados descartados foram mantidos em `diagnostico-polling/` e `diagnostico-uuid/`, sem entrar nas tabelas finais.

A leitura de consistência e a preparação do snapshot ainda têm custos proporcionais ao documento/assets. O timer continua periódico e adia gestos: alterações posteriores à última recuperação concluída não são prometidas como recuperadas. O teste mede Linux offscreen, não prova latência de disco físico lento, Windows/Wayland, ponteiro real nem uso prolongado. Esses cenários são validação complementar; a etapa 09 não foi iniciada.

```bash
.venv/bin/python tests/performance/benchmark_recovery.py --output /tmp/fornax-recovery-benchmark --label depois
.venv/bin/python tests/performance/run_recovery_checks.py
.venv/bin/python tests/performance/run_recovery_checks.py --concurrency
.venv/bin/python -m unittest discover -s tests -p test_editor_recovery_shutdown.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=tests .venv/bin/python -m unittest test_recovery_package_publication -v
.venv/bin/python docs/desempenho_editor/etapa-08/verificar_comparacao.py
```

O auditor da referência/patch depende das cópias de referência em `/tmp/fornax-etapa08-reference`; os resultados e hashes ficam preservados neste diretório. O benchmark de uma versão atual usa somente o repositório e arquivos temporários. A comparação é baseada na etapa 07 preservada, não no `HEAD`, que não representa necessariamente a pasta de trabalho com as etapas anteriores.
