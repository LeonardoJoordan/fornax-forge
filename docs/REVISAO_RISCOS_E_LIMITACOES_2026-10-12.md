# Revisão de riscos e limitações do FORNAX Forge

**Data:** 12/10/2026. **Versão examinada:** 1.1.0.  
**Código de referência:** `2c3aa64f0ce2860f23dc56495132f873dfcb9eb2`.  
**Objetivo:** subsidiar melhorias futuras de segurança, confiabilidade, uso e distribuição. Nenhuma correção foi aplicada ao programa nesta revisão.

## 1. Avaliação geral

O projeto já tem proteções relevantes e uma base funcional considerável. Não encontrei motivo para recomendar uma reescrita ou retirar recursos para torná-lo utilizável. O maior retorno está em proteger melhor o trabalho preenchido pelo usuário, aplicar limites antes das operações custosas e consolidar a manutenção das dependências e dos pacotes.

O ponto de segurança mais importante desta revisão é a presença de **Qt 6.11.0**, versão incluída na faixa afetada por uma vulnerabilidade publicada no processamento de SVG. O aplicativo aceita SVG dentro de modelos `.fornax`; portanto, o fato de funcionar offline não elimina essa superfície de entrada. A versão afetada e o caminho de processamento foram confirmados; **não foi executado um SVG malicioso nem demonstrada a exploração da falha no aplicativo**.

Os problemas funcionais mais claros são a perda do preenchimento da planilha em determinadas transições, a expansão antecipada de quantidades de cópias sem teto e a omissão silenciosa de modelos inválidos na biblioteca. Eles podem prejudicar a confiança no produto mesmo quando o editor e a geração funcionam corretamente.

Não foi demonstrada execução arbitrária de código, quebra da criptografia, exfiltração automática ou escape de diretório pelos caminhos examinados. Isso delimita o resultado desta análise; não constitui garantia de ausência de outras falhas.

## 2. Escopo, método e grau de confirmação

Foram examinados os caminhos de abertura/importação, biblioteca, proteção de modelos, planilha, prévias, geração, nomes de arquivos, armazenamento, empacotamento e documentação. A revisão do editor concentrou-se nas interfaces com esses caminhos e em acessibilidade; não repetiu toda a campanha anterior de desempenho.

Foram realizadas dez sondagens específicas, com documentos, senhas e configurações sintéticos em `/tmp`. A interface foi instanciada com Qt `offscreen`, usando pastas de dados e configurações isoladas. Não foram utilizados documentos pessoais da biblioteca para reproduzir problemas. Foram consultados também avisos oficiais das dependências.

Ambiente observado: Linux, Python 3.13.13, PySide6 Essentials/Qt 6.11.0, pypdf 6.16.1 e cryptography 50.0.1. As dependências declaradas estão em [requirements.txt](../requirements.txt).

Classificação usada:

- **Reproduzido:** o comportamento foi observado em uma sondagem local e delimitada.
- **Confirmado por código:** o caminho existe, mas seu impacto extremo não foi provocado.
- **Risco a validar:** há evidência suficiente para investigar, mas falta comprovação no ambiente ou cenário correspondente.
- **Limitação de produto:** comportamento deliberado ou capacidade ainda não oferecida; não equivale automaticamente a defeito.

As prioridades abaixo expressam a ordem sugerida de trabalho, não uma pontuação CVSS. **P1** merece atenção antes de ampliar a disseminação; **P2** cabe no próximo ciclo de confiabilidade; **P3** depende da demanda. O esforço é relativo e inclui testes, não apenas alteração de linhas.

Não foram realizados testes destrutivos de falta de RAM/disco, fuzzing abrangente, ataques contra instalações reais, auditoria jurídica, certificação de acessibilidade ou validação nativa em Windows/macOS. A suíte completa de regressão não foi repetida nesta revisão sem alterações de código.

## 3. Mapa de prioridades

| ID | Ponto | Prioridade | Evidência | Esforço estimado |
|---|---|---|---|---|
| R01 | Dependências com avisos de segurança posteriores às versões fixadas | P1 | Versões e avisos confirmados; exploração não demonstrada | Médio, com regressão visual e novos pacotes |
| R02 | Importação legada lê conteúdo grande antes de aplicar limites equivalentes aos de `.fornax` | P1 | Leitura excessiva reproduzida | Pequeno/médio |
| R03 | Cópias e colagens podem expandir o trabalho sem orçamento prévio | P1 | Expansão reproduzida; esgotamento não provocado | Pequeno para contenção; médio para expansão sob demanda |
| R04 | Dados da planilha não sobrevivem a troca/reabertura; exclusão sem desfazer global | P1 | Reproduzido | Pequeno para aviso; médio para recuperação e histórico |
| R05 | Modelos inválidos ou incompatíveis desaparecem da listagem sem explicação | P2 | Caso inválido reproduzido | Pequeno |
| R06 | Proteção integral deixa metadados locais; sessão ativa não expira por inatividade | P2 | Reproduzido com dados e relógio sintéticos | Pequeno/médio |
| R07 | Orçamento de imagem não cobre todo o custo de um lote/PDF agrupado | P2 | Confirmado por código; pico de carga não medido | Médio, precedido de medição |
| R08 | Nome de saída limitado por caracteres pode ultrapassar o limite de bytes do destino | P2 | Reproduzido | Pequeno |
| R09 | Colagem pode descartar colunas; texto copiado pode ser interpretado como fórmula fora do FORNAX | P2/P3 | Código e clipboard confirmados; destino externo não testado | Pequeno/médio |
| R10 | Inventário da biblioteca reabre modelos públicos duas vezes | P3 | Contagem reproduzida; ganho em biblioteca grande não medido | Pequeno/médio |
| R11 | Acesso por teclado/leitor de tela precisa de validação, especialmente no canvas | P2 | Evidência parcial de código | Médio e incremental |
| R12 | Distribuição e suporte ainda dependem bastante de trabalho manual | P1 para divulgação ampla | Scripts e documentação examinados | Médio/contínuo |
| R13 | Testes existentes não estão ligados a uma rotina de CI versionada | P2 | Inventário do repositório | Pequeno/médio |
| R14 | Documentação de entrada contém informações de fases anteriores | P2 | Confirmado por comparação com o código | Pequeno |

## 4. Achados detalhados

### R01 — Atualização de dependências deve entrar na manutenção regular

**Problema.** `requirements.txt` fixa PySide6 Essentials 6.11.0 e pypdf 6.16.1. A consulta local confirmou essas versões e `qVersion() == 6.11.0`.

O aviso **CVE-2026-6210** inclui Qt 6.11.0 e descreve falha no processamento de marcadores/máscaras SVG, com possibilidade de encerramento do aplicativo. A correção indicada começa em Qt 6.11.1 nessa série. [Aviso oficial do Qt](https://www.qt.io/blog/security-advisory-type-confusion-and-heap-buffer-overflow-vulnerability-in-qt-svg-marker-handling).

O contêiner aceita assets `.svg`; `_validate_svg` bloqueia scripts, entidades e referências externas, mas permite referências locais `#id`. Em seguida o conteúdo chega a `QImageReader`. Um `.fornax` sintético com SVG inofensivo foi salvo, reaberto e renderizado com sucesso. Isso confirma que SVG não se limita aos ícones confiáveis distribuídos com o programa. **Não foi demonstrado que um payload dessa CVE atravessa o sanitizador atual**; é um risco concreto a tratar pela versão da dependência, sem afirmar uma exploração já comprovada.

No pypdf, três avisos consultados indicam versões anteriores a 6.19.0: geração de aparência de formulários, leitura de rótulos alfabéticos e acesso a arquivos incorporados. O FORNAX processa principalmente PDFs que ele mesmo acabou de gerar; não encontrei nesses caminhos a importação arbitrária de PDFs nem o uso das três operações vulneráveis. A versão está na faixa afetada, mas o alcance no produto é menor que o número de avisos sugere. [Formulários](https://github.com/py-pdf/pypdf/security/advisories/GHSA-php9-fj8v-98fj), [rótulos](https://github.com/py-pdf/pypdf/security/advisories/GHSA-w23x-9jrw-r45c), [anexos](https://github.com/py-pdf/pypdf/security/advisories/GHSA-v247-6f48-mgcj).

Como controle contra falsos positivos: o aviso consultado de PKCS#7 em cryptography informa correção em 50.0.0; o projeto usa 50.0.1 e sua proteção de modelos usa AES-GCM/Argon2id, não aquele fluxo PKCS#7. Não atribuo essa vulnerabilidade ao FORNAX. [Aviso oficial](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5).

**Sugestão.** Planejar atualização para versões corrigidas e compatíveis, revisar os demais avisos vigentes e regenerar locks, hashes, inventário, avisos/fontes correspondentes e pacotes. Atualizar Qt exige comparação visual de texto, máscaras, tabelas, PDF e fontes nas plataformas alvo. A lista acima é uma triagem de avisos, não um inventário completo de CVEs de todas as bibliotecas nativas.

**Aceite futuro:** dependências e binários identificados por versão/hash; avisos triados por alcance; regressões visuais/funcionais aprovadas. Evitar substituir bibliotecas isoladas dentro de um pacote já pronto.

**Referências:** [requirements.txt](../requirements.txt); `core/fornax_container.py:419`, `:431`, `:469`; `features/generator/renderer.py:139`.

### R02 — Importação legada tem proteção de recursos inferior à do formato atual

**Problema.** `_on_import_legacy_zip` permite até 10.000 entradas e 4 GiB descompactados. Embora verifique caminhos, duplicidades, links simbólicos e métodos de compressão, lê o JSON com `f.read()` inteiro antes de decodificar e normalizar. `load_model_document` também lê integralmente o JSON legado antes da normalização. O orçamento geral de JSON não é aplicado uniformemente antes da leitura nos esquemas antigos.

**Reprodução.** Um ZIP sintético de **9.409 bytes** levou **9.437.257 caracteres ASCII** ao parser JSON. Isso ultrapassa o teto de **8.388.608 bytes** utilizado pelo formato `.fornax`. O teste interceptou a abertura do diálogo de escolha e cancelou; não extraiu gigabytes nem tentou derrubar o processo.

Há uma segunda diferença: depois da escolha, `extractall` extrai o pacote inteiro, inclusive modelos não selecionados. Essa operação ocorre no fluxo da interface e não tem orçamento de espaço livre próprio.

**Impacto.** Um pacote defeituoso, excessivo ou deliberadamente preparado pode consumir muita RAM/disco e bloquear a interface antes de ser rejeitado. O ataque exige que o usuário abra o pacote; não é uma vulnerabilidade de rede. **Não foi encontrado zip-slip nesse caminho**: o problema apontado é de recursos e momento da validação.

**Sugestão.** Limitar bytes por entrada antes de ler; usar leitura limitada; aplicar limites de profundidade/quantidade também ao legado; extrair somente o necessário. Depois, se a medição justificar, mover a importação custosa para trabalho cancelável fora da interface.

**Aceite futuro:** JSON acima do limite rejeitado antes de sua leitura integral; seleção de um modelo não extrai os demais; cancelamento e disco insuficiente deixam a biblioteca íntegra.

**Referências:** `features/workspace/main_window.py:1410`; `core/model_document.py:921`; [core/json_limits.py](../core/json_limits.py); `core/fornax_container.py:304`.

### R03 — Quantidade de cópias pode comprometer a responsividade antes de gerar

**Problema.** Para modelos comuns, `_scrape_table_data` cria dois dicionários e uma entrada de origem por cópia solicitada. `_preview_source_rows` também materializa uma lista com todas as cópias. Não há teto de quantidade ou orçamento total antes dessas expansões. Colagens na planilha aumentam a quantidade de linhas sem uma validação global prévia de tamanho.

**Reprodução.** Uma linha com `Cópias = 10000` produziu três listas de 10.000 entradas, além da lista de navegação da prévia. A sondagem da extração observou aproximadamente **3,94 MB de alocações Python**, sem renderizar cartão algum. Esse número ilustra a expansão; não representa o consumo total do aplicativo nem um teste de carga máxima.

**Impacto.** Um zero a mais ou uma colagem na coluna errada pode criar trabalho desproporcional. O limite de MP não protege essa etapa, pois ele controla imagens. Para organogramas, as cópias não multiplicam pessoas; esse caso específico está tratado.

**Sugestão.** Validar quantidade total e tamanho da colagem antes da alocação. Como evolução, representar quantidades por contadores e expandir apenas o trecho necessário à prévia/geração. Não é necessário impor um limite baixo a lotes legítimos para corrigir o problema.

**Aceite futuro:** uma quantidade absurda é recusada ou exige decisão explícita sem criar listas gigantes; um lote válido mantém a ordem e os nomes; organogramas mantêm o comportamento atual.

**Referências:** `features/workspace/main_window.py:2158`, `:2859`; `features/spreadsheet/table_panel.py:360`, `:393`; [features/spreadsheet/clipboard.py](../features/spreadsheet/clipboard.py).

### R04 — Proteção do preenchimento da planilha está abaixo da proteção do editor

**Problema.** A planilha principal guarda dados de trabalho em memória. Trocar de modelo reconstrói suas colunas e limpa seu conteúdo. O fechamento persiste preferências da interface, mas não os registros preenchidos. Exclusões/colagens não possuem um histórico global de desfazer equivalente ao editor.

**Reprodução.** Na janela principal real, com dois modelos sintéticos:

1. Preencher uma célula, trocar de modelo e voltar: a célula ficou vazia.
2. Preencher novamente, fechar e reabrir a janela: a célula ficou vazia.
3. Apagar uma célula selecionada e pressionar Ctrl+Z fora da edição textual: o valor não voltou.
4. Não apareceu confirmação para preservar esses dados.

**Distinção importante:** `_on_editor_saved` já captura/restaura as linhas ao salvar o modelo correspondente pelo editor. Portanto, não é correto dizer que qualquer salvamento apaga a planilha. O arquivo do modelo também não foi perdido nos testes.

**Impacto.** Digitação manual e correções feitas depois de colar uma planilha externa podem ser perdidas. É especialmente relevante para quadros de pessoal que serão atualizados periodicamente.

**Sugestão.** Primeiro, detectar preenchimento alterado e oferecer uma saída clara antes de descartá-lo. Depois, decidir um formato de sessão/dados separado do layout e adicionar histórico de operações da planilha. Se houver recuperação automática, definir onde fica, quando é removida e como proteger dados sensíveis; não salvar silenciosamente conteúdo de um modelo protegido em texto aberto.

**Aceite futuro:** troca, fechamento, falha e reabertura preservam o que foi prometido ao usuário; exclusão e colagem podem ser desfeitas; os dados restaurados continuam ligados às colunas e blocos corretos.

**Referências:** `features/workspace/main_window.py:238`, `:1766`, `:1988`, `:2640`; `features/spreadsheet/table_panel.py:241`, `:332`.

### R05 — Biblioteca esconde a causa de documentos ausentes

**Problema.** `scan_model_library` tenta recuperação por `.bak`, o que é positivo. Quando não consegue abrir uma entrada, ou encontra um formato futuro não suportado, termina ignorando o item. A listagem não devolve um diagnóstico por arquivo ao usuário.

**Reprodução.** Uma pasta contendo apenas `invalid.fornax`, com conteúdo sintético inválido, retornou uma biblioteca de zero itens. O arquivo continuou no disco. Com um modelo válido ao lado, apenas o válido apareceu.

**Impacto.** O usuário interpreta incompatibilidade ou corrupção como exclusão do modelo. Isso dificulta suporte e recuperação e pode motivar recriação desnecessária.

**Sugestão.** Manter os demais modelos acessíveis e mostrar um resumo das entradas com problema: arquivo, categoria, eventual backup recuperável e ação apropriada. Um arquivo de versão futura deve ser identificado como incompatível, sem tentativa de downgrade.

**Aceite futuro:** arquivo inválido permanece intacto e é explicado; backup válido continua recuperável; um item defeituoso não bloqueia a biblioteca.

**Referência:** [core/model_library.py](../core/model_library.py), especialmente linhas 29–111.

### R06 — Delimitar melhor o significado de “modelo protegido”

Há dois comportamentos locais distintos:

**a) Nome lembrado fora do arquivo criptografado.** `_remember_protected_model_name` grava o nome legível de modelos integrais nas configurações `workspace/protected_model_names`. A sondagem confirmou o título sintético em texto aberto no arquivo de configurações. Isso não revela a senha, imagens ou conteúdo do documento, mas o próprio nome pode conter informação institucional. Bloquear o modelo não equivale a apagar esse histórico local.

**b) Sessão ativa não expira por inatividade.** O prazo de tolerância se aplica ao modelo que deixou de ser ativo. `expire_due` pula o ativo e `suspend` expira apenas sessões inativas em tolerância. Com relógio sintético avançado em 24 horas, seguido de `suspend`, a sessão ativa continuou `AUTHORIZED_ACTIVE`. Não é uma falha de AES: é a política da sessão.

**Impacto.** Em computador compartilhado ou abandonado desbloqueado, o próximo usuário pode encontrar o conteúdo já autorizado; uma cópia das configurações também pode revelar títulos. O bloqueio da conta pelo sistema operacional continua sendo uma proteção importante.

**Sugestão.** Explicitar esses metadados na ajuda/privacidade; considerar um modo que não retenha títulos confidenciais; oferecer bloqueio opcional por inatividade/suspensão. Essa mudança deve respeitar trabalhos em andamento e a recuperação de edições, para não transformar proteção em perda de trabalho.

**Aceite futuro:** comportamento de título e prazo corresponde ao que a interface promete; testes cobrem ativo/inativo, suspensão, desbloqueio, editor com alterações e geração autorizada.

**Referências:** `features/workspace/main_window.py:520`, `:535`; `core/fornax_session.py:342`, `:356`, `:366`; [privacidade](PRIVACIDADE_E_ARMAZENAMENTO.md).

### R07 — O teto de MP é uma proteção parcial, não um orçamento de todo o trabalho

**O que já funciona:** o planejador limita imagens e concorrência, e os ladrilhos podem ser pintados por região sem montar um bitmap do documento inteiro.

**Lacunas observadas:**

- O pós-processamento de PDF clona o documento com pypdf. Em `memory_only`, serializa o PDF completo em `BytesIO` e depois o regrava. Esse custo depende do arquivo e do lote, não apenas dos MP de uma página.
- O modo híbrido de PDF agrupado mantém PNGs temporários antes da montagem. O código examinado não faz uma estimativa prévia do espaço livre necessário para o trabalho inteiro.
- Em macOS, `available_memory_bytes` não consulta a memória disponível: usa-se o orçamento nominal do perfil. Em Linux/Windows há consulta e redução para 70% quando a API funciona.
- Cancelamento/fechamento espera workers terminarem. Há checagens entre etapas, mas uma codificação, renderização ou reescrita em curso pode demorar a devolver o controle. Não foi constatado deadlock; existe possibilidade de espera longa.

**Impacto.** Um lote com páginas individualmente permitidas ainda pode pressionar RAM ou disco. “Até 600 MP” não significa que qualquer lote desse tamanho caberá em qualquer computador.

**Sugestão.** Medir picos reais de RSS e temporários em poucos cenários representativos; adicionar verificação de espaço e orçamento do lote; completar a consulta de RAM no macOS quando houver ambiente de teste; oferecer cancelamento e indicação da fase atual. Só então avaliar mudanças no pipeline. Trocar PNG intermediário por JPEG não é uma correção neutra: altera a fidelidade.

**Aceite futuro:** falha de espaço/memória é comunicada sem corromper o modelo; cancelamento tem comportamento previsível; comparar lote comum, protegido, frente/verso, itens por folha e ladrilhos. Esta revisão não provocou esgotamento de memória ou disco.

**Referências:** [core/performance.py](../core/performance.py); `features/generator/pdf_links.py:37`; `features/generator/manager.py:143`, `:217`; `features/generator/workers.py:480`; `features/workspace/main_window.py:238`.

### R08 — Nomes longos com Unicode podem impedir a geração

**Problema.** `sanitize_filename` limita o nome a 180 caracteres, sem considerar bytes do componente de caminho nem reservar a extensão/sufixos conforme o destino.

**Reprodução.** Um nome de 180 letras `á`, aceito pela função, somou 364 bytes UTF-8 com `.png`. A gravação no ambiente Linux falhou com `ENAMETOOLONG` (errno 36).

**Impacto.** Um padrão de nome que combina título, pessoa, setor e data pode falhar apesar de passar pela sanitização. Os controles de escape de diretório e nomes reservados continuam úteis; o problema é de comprimento.

**Sugestão.** Truncar respeitando o orçamento do destino e a codificação, reservar extensão/sufixo e manter unicidade após truncar. Testar também o comprimento do caminho completo no Windows.

**Aceite futuro:** acentos, caracteres multibyte, nomes repetidos e sufixos de frente/verso/ladrilho produzem arquivos válidos sem colisões.

**Referência:** [core/naming_engine.py](../core/naming_engine.py), linhas 13–61.

### R09 — Tornar a troca de dados com outras planilhas mais previsível

**a) Colunas excedentes são ignoradas.** `_paste_grid` interrompe a linha quando chega ao fim das colunas disponíveis. Não mostra uma prévia de mapeamento nem avisa que o restante foi descartado. Como a posição atual define o início da colagem, o usuário pode preencher a coluna errada e não perceber imediatamente. Isso é confirmado pelo código; não é ausência total de interoperabilidade: copiar e colar dados e formatação já existe.

**Sugestão de maior retorno:** avisar sobre colunas excedentes antes de alterar a planilha e oferecer conferência da correspondência das colunas. Importação direta de CSV/XLSX pode ser avaliada depois, se houver demanda; não é necessária uma integração online com Google Sheets.

**b) Conteúdo textual pode virar fórmula no destino.** O teste com `=1+1` confirmou que a cópia emite esse valor literalmente no texto tabulado. O FORNAX não executa a fórmula. A eventual interpretação ocorre no programa em que o usuário cola, conforme o formato e a versão. Essa classe de risco é documentada pela [OWASP](https://community.owasp.org/attacks/CSV_Injection).

Não foi testada a execução de fórmulas no Excel/Sheets nesta revisão e não foi demonstrado roubo de dados. Se a planilha receber conteúdo não confiável e houver troca frequente com essas ferramentas, vale oferecer um modo de copiar como texto e validar o resultado nos destinos suportados. Não acrescentar caracteres a todos os valores sem testar a preservação dos dados.

**Aceite futuro:** nenhuma coluna desaparece sem aviso; colagem cancelada não modifica células; modo de texto preserva valores literais nos programas testados, inclusive após salvar/reabrir.

**Referências:** `features/spreadsheet/table_panel.py:393`, `:451`; `features/spreadsheet/copy_export.py:46`.

### R10 — Bibliotecas maiores têm trabalho repetido na listagem

**Problema.** Para um modelo público íntegro, `_inspect_recoverable` abre/valida o contêiner e, depois, `scan_model_library` abre novamente para obter o nome. A abertura carrega os assets referenciados. Essa varredura participa do fluxo da interface.

**Reprodução.** Um único modelo público sintético válido resultou em duas chamadas a `open_public_fornax` durante uma varredura.

**Impacto provável.** Custo perceptível em bibliotecas com muitos modelos ou imagens grandes. Esta revisão não mediu uma biblioteca grande; duas chamadas não significam automaticamente que o tempo total cairia pela metade.

**Sugestão.** Reutilizar o resultado validado na mesma varredura. Cache por revisão/arquivo e listagem assíncrona só devem ser considerados depois de medir. Não eliminar a validação de integridade para acelerar a abertura.

**Aceite futuro:** uma abertura validada por modelo público íntegro; corrupção, alteração externa, backup e modelos protegidos continuam corretamente tratados. Medir tempo e pico de memória antes/depois com o mesmo conjunto sintético.

**Referências:** `core/model_library.py:29`, `:38`, `:98`; `features/workspace/main_window.py:454`.

### R11 — Acessibilidade precisa ser tratada como uma jornada de uso

**Evidência.** Há nomes de acessibilidade em diversos controles, o que é positivo. Porém, os botões das barras flutuantes e os seletores externos de linhas/colunas usam `NoFocus`; a alça é operada por eventos do mouse. Isso exige caminhos alternativos para quem depende do teclado. Não foi comprovado que todas as ações exclusivas dessas interfaces têm alternativa equivalente.

**Impacto possível.** Dificuldade para pessoas com limitações motoras/visuais e para trabalho sem mouse. Uma instituição pode considerar isso um impeditivo de implantação, mesmo com boa qualidade visual. Não foi feita avaliação normativa nem teste com leitor de tela, portanto não se declara conformidade ou desconformidade global.

**Sugestão.** Fazer uma jornada curta somente por teclado: escolher modelo, preencher, editar texto, selecionar células, adicionar linha, ajustar propriedade e gerar. Testar depois com NVDA no Windows e Orca no Linux. Acrescentar alternativas de teclado/contexto onde faltarem, preservando o foco de edição de texto que motivou o desenho atual.

**Aceite futuro:** todas as ações essenciais têm caminho utilizável e anunciável; seleção/estado/erro são comunicados; foco não se perde ao formatar. Verificar também escala de tela e contraste nos temas, sem presumir que SVG resolve acessibilidade.

**Referências:** `features/editor/floating_bar.py:25`, `:195`; `features/editor/table_selectors.py:15`; [tests/test_table_i18n.py](../tests/test_table_i18n.py).

### R12 — Preparar a distribuição para além do computador de desenvolvimento

**Pontos encontrados:**

- A documentação de release reconhece a necessidade de testes nativos. Evidência de execução em Linux/offscreen não demonstra instalação, atualização, fontes, escala de tela e associações de arquivos em Windows/macOS.
- O instalador Windows exige privilégios administrativos e está direcionado a x64. Isso pode exigir intervenção da TI institucional; não é, isoladamente, uma falha de segurança.
- O fluxo macOS usa assinatura ad hoc. O próprio projeto documenta que isso não é assinatura Developer ID/notarização.
- O processo de release produz hashes e inventários, mas documenta `signed: false`. Checksums ajudam a detectar alterações; sua publicação ao lado do arquivo não fornece, sozinha, uma identidade independente do distribuidor.
- Não há atualização automática. Isso preserva o funcionamento offline, mas exige uma forma clara de comunicar quais versões permanecem recomendadas.
- `SECURITY.md` manda usar o canal privado do GitHub “se” habilitado e ainda descreve sua habilitação como pendência. O estado remoto desse canal não foi confirmado nesta revisão.

**Impacto.** Mais dificuldade de instalação, diagnóstico e manutenção em escala. Esses pontos pesam mais para disseminação do que adicionar novas ferramentas de desenho.

**Sugestão.** Manter uma matriz pequena de sistemas realmente testados, com requisitos mínimos explícitos; testar atualização preservando dados; estabelecer um canal privado funcional; definir a política de autenticidade dos pacotes e uma rotina de publicação. Avaliar instalação por usuário no Windows somente quando compatível com a política das instituições atendidas. Não é necessário transformar o aplicativo em serviço online nem obrigá-lo a consultar a internet.

**Aceite futuro:** instalação limpa e atualização verificadas em cada plataforma anunciada; versão/pacote/fontes/commit identificáveis; instruções honestas para plataformas sem pacote validado; forma de relatar falhas privadamente testada.

**Referências:** [docs/RELEASE.md](RELEASE.md), seções de atualização e assinatura; [checklist de distribuição](CHECKLIST_DISTRIBUICAO_FORNAX.md); `instalador.iss:37`; `script_nuitka.py:144`; [SECURITY.md](../SECURITY.md).

### R13 — Automatizar a proteção contra regressões e acompanhar componentes

**Problema.** O repositório contém uma suíte extensa de testes e relatórios de desempenho, mas não há workflows versionados em `.github` no commit examinado. Isso não prova que nenhuma automação externa exista; significa que não há uma rotina de CI reproduzível declarada ali para cada mudança.

Existem testes de persistência protegida, recuperação, fontes, tabelas, concorrência e geração. Portanto, não seria correto dizer que a segurança está sem testes. O que falta consolidar é uma suíte explícita das fronteiras de entrada: ZIP/JSON excessivos, SVGs não permitidos, caminhos hostis, rejeição antes de alocar e integridade diante de falhas. `pip check` valida consistência de dependências, não ausência de CVEs.

**Sugestão.** Começar com CI Linux para os testes existentes em processos isolados, verificações de tradução/recursos e varredura de dependências; depois acrescentar smoke tests nativos. O projeto já produz inventários: usá-los para verificar o que realmente foi distribuído, incluindo Qt e bibliotecas nativas, em vez de olhar apenas o venv.

**Aceite futuro:** uma regressão bloqueia a integração antes do pacote; falhas geram evidências curtas; alertas de segurança são triados por versão e alcance. Evitar criar centenas de testes que apenas repetem a implementação.

**Referências:** [tests](../tests); [scripts/release_tools.py](../scripts/release_tools.py); [requirements](../requirements); [orientação de segurança do cryptography](https://cryptography.io/en/latest/security/).

### R14 — Corrigir divergências na documentação mais visível

**Exemplos confirmados no README:** a apresentação inicial cita PNG/PDF sem JPEG; há seção intitulada “Protótipo de organogramas — branch upgrade-01”; a descrição da geração ainda menciona PNG em 150/300 DPI e um mosaico com margens/sobreposição fixas de uma fase anterior. O código e a documentação específica de limite de exportação já adotam 300 DPI fixos. A documentação de privacidade também ainda nomeia somente PNG/PDF na tabela de arquivos gerados.

**Impacto.** Usuários podem procurar opções removidas, interpretar mal os limites ou acreditar que um recurso está em estágio anterior ao real. Manter textos conflitantes aumenta o custo de suporte.

**Sugestão.** Revisar primeiro README, instalação e privacidade, usando os fluxos atuais como referência. Na explicação de PDF, diferenciar os caminhos: cartões comuns são rasterizados, enquanto organogramas/ladrilhamento possuem caminhos de pintura em PDF; não afirmar uma única arquitetura para todas as saídas.

**Aceite futuro:** exemplos reproduzíveis na versão anunciada; formatos, limites, nomes de menus e armazenamento concordam entre interface, ajuda e README.

**Referências:** `README.md:7`, `:34`, `:116`, `:133`; [limite de exportação](DESEMPENHO_E_QUALIDADE.md); [privacidade](PRIVACIDADE_E_ARMAZENAMENTO.md).

## 5. Limitações relevantes que não exigem necessariamente mudança

### Capacidades numéricas atuais

| Recurso | Limite/condição encontrado | Consequência prática |
|---|---|---|
| Página lógica comum | Até 10.000 mm por lado | Editar um documento grande não garante exportação como uma imagem única |
| Saída raster | 300 DPI; 40, 80, 150, 300 ou 600 MP; padrão 150 MP | O perfil limita cada imagem/folha, não o peso comprimido do arquivo nem o lote inteiro |
| Lado da saída raster | 32.760 px, aproximadamente 2,774 m a 300 DPI | Um documento muito comprido pode exceder o limite por lado mesmo abaixo do teto de MP |
| PDF de página única | Até 5 m por lado no caminho que aceita esse tamanho | Nos caminhos raster, os limites de imagem continuam valendo; pintura direta em PDF não exige o mesmo bitmap integral |
| Ladrilhamento | Até 1.000 folhas por plano | Não é uma promessa de saída sem limite; cada folha e o trabalho completo ainda têm custo |
| Organograma | Até 2.500 posições por quadro | É quantidade de cartões/posições, não recomendação de 2.500 blocos independentes |
| Tabela gráfica do editor | Até 100 linhas, 100 colunas e 1.000 posições por tabela | Não significa 100 × 100 simultaneamente; prevalece também o teto de posições |
| Tabelas no documento | Até 20 tabelas e 2.000 posições totais | Usos muito extensos precisam ser divididos; a planilha de dados principal é outro componente |
| HTML de células | 32 KiB por célula, 512 KiB por tabela, 1 MiB no documento | Limites evitam entradas textuais desproporcionais |
| Asset de imagem incorporado | Até 64 MP, 32.768 px por lado e 128 MiB por entrada | Uma imagem exportada em 150/600 MP não é necessariamente reimportável inteira como asset |
| Pacote `.fornax` | Até 512 MiB, 4.096 entradas e 512 MiB descompactados | Há ainda teto de 256 MiB no conteúdo interno protegido e limites menores por tipo de entrada |
| Documento JSON no contêiner | 8 MiB, profundidade 64, 100.000 valores contabilizados | A proteção não se resume às dimensões físicas |
| Páginas do modelo | Frente/verso ou Página 1 + organograma | Não é um editor geral de livros ou documentos com dezenas de páginas |

Fontes: [model_document](../core/model_document.py), [performance](../core/performance.py), [organogram](../core/organogram.py), [table_model](../core/table_model.py), [tiling](../core/tiling.py), [fornax_container](../core/fornax_container.py), [json_limits](../core/json_limits.py), `features/generator/workers.py:24`.

Esses tetos não devem ser elevados indiscriminadamente. Os testes desta revisão não validam cargas máximas de 600 MP ou 1.000 folhas. A prioridade é explicar e aplicar os limites corretamente, preservando o funcionamento em máquinas modestas.

### PDF, fontes e fidelidade

Nos cartões comuns, a geração PDF usa a imagem renderizada. Por isso o texto não oferece a mesma seleção, pesquisa ou semântica de um documento textual. Links, marcadores e rótulos de página ajudam a navegação, mas não substituem o conteúdo acessível de uma página.

Essa escolha foi feita para preservar a fidelidade e foi reafirmada pelo responsável pelo projeto. **Não recomendo refazer o pipeline para PDF vetorial como correção geral desta revisão.** Se houver demanda real por pesquisa ou acessibilidade documental, avaliar uma saída adicional, com validação própria. Os caminhos de organograma/ladrilho não devem ser generalizados como idênticos ao PDF de cartão.

A Inter 18pt é incorporada e registrada pelo aplicativo. Fontes adicionais escolhidas pelo usuário continuam dependendo de disponibilidade na outra máquina; `resolve_font_family` não incorpora automaticamente qualquer família. Isso pode mudar quebras e medidas em modelos compartilhados. Uma conferência de fontes ausentes ao abrir/compartilhar tem melhor relação esforço/benefício do que prometer portabilidade de todas as fontes.

Não foi encontrado um fluxo específico de PDF/A, PDF acessível marcado, prova de cores CMYK/ICC ou assinatura digital criptográfica. São requisitos possíveis de alguns usos profissionais, não condições para todo cartão ou quadro funcionar. “Assinatura” como imagem no layout não equivale a uma assinatura digital verificável.

Referências: `features/generator/workers.py:83`; `features/generator/organogram.py:264`; [tiled_document](../features/generator/tiled_document.py); [ui_font](../core/ui_font.py).

### Armazenamento, portabilidade e trabalho institucional

- **Flatpak e AppImage podem usar bibliotecas locais diferentes.** Isso acompanha o isolamento do Flatpak e já está documentado. Não é evidência de vazamento de modelos de desenvolvimento. O empacotamento atual seleciona recursos explicitamente; a biblioteca pessoal não está nessa seleção. É útil tornar o local da biblioteca fácil de descobrir e explicar exportação/importação.
- **Publicação segura exige recursos do sistema de arquivos.** `publish_new` usa hard links e falha preservando o arquivo de origem quando não há suporte. A falha foi simulada com `EOPNOTSUPP`; nenhum pendrive real foi testado. FAT32/exFAT não oferecem hard links, segundo a [comparação da Microsoft](https://learn.microsoft.com/windows/win32/fileio/filesystem-functionality-comparison). Isso afeta caminhos que criam novos contêineres diretamente nesse armazenamento. **Não significa que “Exportar modelos” para pendrive falha em geral:** esse fluxo prepara cópias na área temporária e tem publicação de destino distinta. Não substituir a operação segura por uma cópia parcial apenas para contornar a limitação.
- **Recuperação local não é backup externo.** `.bak` e recuperação ajudam contra certas falhas de gravação, mas não contra perda do disco ou remoção de toda a pasta. Exportação existe; um guia curto de backup/restauração e um teste de restauração têm alto valor.
- **O produto é local e voltado ao operador.** Não há contas institucionais, papéis de acesso, aprovação por superior ou colaboração simultânea de equipe. São necessidades possíveis de algumas organizações, mas acrescentá-las mudaria significativamente o escopo. O sistema operacional e os procedimentos da instituição continuam responsáveis por controlar o acesso aos arquivos e às saídas.
- **A permissão CUPS no Flatpak merece conferência de necessidade.** O programa gera arquivos e não oferece impressão direta. Pode haver oportunidade de reduzir uma permissão, mas não a classifico como falha crítica nem recomendo removê-la sem smoke test.

Referências: [core/paths.py](../core/paths.py), [core/file_transactions.py](../core/file_transactions.py), [core/fornax_export.py](../core/fornax_export.py), [scripts/release_tools.py](../scripts/release_tools.py), [manifesto Flatpak](../com.leobelisario.FornaxForge.yaml).

## 6. Proteções que devem ser preservadas

Não há benefício em reimplementar o que já está adequadamente protegido sem evidência de problema:

- Inventário e leitura limitada do `.fornax`: limites por entrada/total, recusa de caminhos inseguros, duplicidades, links simbólicos e formatos de compressão não aceitos.
- Validação de JSON no contêiner e de geometria antes de construir o documento.
- Sanitização de texto/SVG, bloqueio de recursos externos em texto e uso de `defusedxml` para SVG.
- Criptografia autenticada AES-GCM, derivação Argon2id com perfil fixo e separação entre conteúdo público e protegido. Não foi identificada razão para trocar essa arquitetura nesta análise.
- Verificação de revisão, locks de gravação, publicação transacional, backups e recuperação. Uma otimização não deve removê-los para ganhar alguns milissegundos.
- Restrição dos caminhos de imagens variáveis e saídas; tratamento de nomes reservados e colisões, apesar da lacuna de comprimento identificada.
- Geração com buffers limitados, controle de concorrência, prévias reduzidas e pintura por região nos ladrilhos.
- Fonte padrão incorporada, galeria interna de modelos e seleção explícita do que entra no pacote.
- Diagnósticos com redução de conteúdo sensível, rotação de logs, fontes/licenças de terceiros e documentação de armazenamento.
- Funcionamento offline e ausência de necessidade de conta. Não é preciso abrir mão disso para melhorar confiabilidade e distribuição.

Referências principais: [fornax_container](../core/fornax_container.py), [file_transactions](../core/file_transactions.py), [dynamic_images](../core/dynamic_images.py), [html_utils](../core/html_utils.py), [diagnostic_logs](../core/diagnostic_logs.py), [release_tools](../scripts/release_tools.py).

## 7. Evidências locais e como conferir os achados

As sondagens não foram incorporadas ao código nem à suíte do produto. Foram executadas a partir de `/tmp/fornax_audit_20261012.py`, com resultados da execução final em `/tmp/fornax-audit-u3u52jz_/results.json`. Esses caminhos são temporários; a tabela abaixo preserva o resultado necessário ao planejamento.

| Sondagem | Entrada controlada | Resultado |
|---|---|---|
| Expansão de cópias | 1 linha, 10.000 cópias | 10.000 registros plain, 10.000 rich e 10.000 origens; navegação também com 10.000 entradas |
| JSON legado | ZIP de 9.409 bytes com JSON de 9.437.257 bytes ASCII | Conteúdo integral chegou a `json.loads`, acima dos 8 MiB usados no contêiner atual |
| Nome Unicode | 180 letras `á` + `.png` | 364 bytes; erro 36 `File name too long` na gravação |
| Inventário de biblioteca | Arquivo inválido; depois inválido + válido | Inválido omitido e preservado no disco; duas aberturas públicas para o válido |
| Sessão protegida | Modelo integral sintético; relógio +24 h; chamada a `suspend` | Modelo ativo continuou autorizado; teste de política, não suspensão real do SO |
| Nome protegido | Chamada à persistência do título com configurações isoladas | Nome legível presente no arquivo de configurações |
| SVG inofensivo | Modelo público com retângulo SVG | Salvo, reaberto e renderizado; nenhum SVG de exploração executado |
| Falta de hard links | `os.link` simulado retornando `EOPNOTSUPP` | Falha preservou o staging e não criou destino parcial |
| Ciclo da planilha | Troca A→B→A; fechar/reabrir; apagar e Ctrl+Z | Valores vazios nas três situações; nenhuma confirmação de descarte |
| Clipboard | Texto `=1+1` | Emitido literalmente; interpretação por Excel/Sheets não testada |

Para repetir, usar sempre biblioteca descartável e configurações isoladas. As referências de linha do relatório correspondem ao commit informado; podem mudar depois de uma implementação.

## 8. Ordem sugerida para futuras melhorias

1. **Atualizar/validar dependências e reforçar entradas:** R01–R03. Reduz risco de travamento por arquivos e valores inesperados. A atualização de Qt deve vir acompanhada da regressão de fidelidade.
2. **Proteger o trabalho do usuário:** R04–R06 e R08. Começar pelo aviso de descarte, diagnóstico de modelos ausentes e nomes válidos; projetar recuperação/histórico com cuidado.
3. **Preparar divulgação e manutenção:** R12–R14. Matriz nativa pequena, CI, canal privado e documentação coerente. Esses passos não precisam esperar novas funcionalidades.
4. **Medir antes de alterar arquitetura:** R07 e R10. Otimizar apenas gargalos demonstrados de lote/biblioteca; preservar qualidade e controles de integridade.
5. **Validar jornadas de adoção:** R09 e R11. Interoperabilidade e acessibilidade com exemplos reais, sem ampliar o produto para uma suíte de escritório ou sistema multiusuário.

As recomendações são um roteiro para decisão, não autorização de implementação. Esta entrega acrescenta somente o relatório ao repositório.
