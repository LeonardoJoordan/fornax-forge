# Privacidade e armazenamento local do FORNAX Forge

O FORNAX Forge funciona offline. O aplicativo não possui conta de usuário, telemetria, sincronização em nuvem ou atualização automática. O programa não transmite modelos, planilhas, imagens, assinaturas ou documentos gerados.

Essa característica não significa ausência de armazenamento. Todo o trabalho é realizado localmente e alguns arquivos podem conter dados pessoais ou institucionais.

## Dados armazenados

| Conteúdo | Local | Permanência |
|---|---|---|
| Biblioteca de modelos `.fornax` | Pasta de dados do FORNAX, em `models/` | Até o usuário excluir o modelo |
| Configurações da interface | Armazenamento de configurações do sistema operacional | Até redefinição ou desinstalação com remoção de dados |
| Pasta de imagens variáveis | Configuração local do modelo/computador | O FORNAX guarda a referência à pasta, não incorpora essas imagens ao modelo |
| Backups e recuperação de edição | Ao lado do modelo correspondente | Substituídos ou removidos pelo fluxo de salvamento/recuperação |
| Miniaturas e proxies de modelos legados | `.render_cache` dentro da antiga pasta do modelo | Cache reconstruível; modelos `.fornax` protegidos não usam esse cache em disco |
| Logs operacionais | Pasta de dados do FORNAX, em `logs/` | Rotação automática: arquivo atual e até três versões de 1 MiB |
| Arquivos temporários do FORNAX | Pasta de dados do FORNAX, em `temporary/`; se ela não estiver disponível, pasta temporária do sistema com nome exclusivo do aplicativo e usuário | Removidos ao concluir a operação e novamente na próxima inicialização após falha |
| PNGs e PDFs gerados | Pasta escolhida pelo usuário, dentro da pasta de cada forja | Até o usuário removê-los |

Locais padrão da pasta de dados:

- Linux: `$XDG_DATA_HOME/com.leobelisario.FornaxForge` ou `~/.local/share/com.leobelisario.FornaxForge`.
- Windows: `%APPDATA%\FornaxForge`.
- macOS: `~/Library/Application Support/com.leobelisario.FornaxForge`.

## Modelos protegidos e assinaturas

Um modelo pode ser público, proteger apenas as assinaturas ou proteger todo o conteúdo. A senha não é salva nas configurações nem nos logs. Durante um desbloqueio autorizado, chaves e conteúdo descriptografado permanecem em memória pelo período da sessão. O aplicativo reduz e limpa essas referências quando a sessão é bloqueada ou encerrada, mas nenhum programa de usuário pode garantir apagamento físico imediato de RAM ou swap.

Backups e arquivos de recuperação seguem o modo de proteção do modelo. Exportações finais em PNG ou PDF são documentos de saída deliberadamente legíveis e não herdam a criptografia do modelo.

## Logs e falhas

O painel pode mostrar detalhes úteis durante a sessão. A versão persistida do log remove caminhos absolutos, nomes dos arquivos gerados e detalhes multilinha. O registro de falha guarda o tipo da exceção e as posições técnicas usando apenas o nome de cada arquivo de código; não grava valores da exceção nem linhas de conteúdo.

Ao usar a ação de limpar o log, o FORNAX limpa o painel e também os arquivos rotacionados do log operacional. O log de falhas é independente para preservar diagnóstico de encerramentos inesperados.

## Arquivos temporários e encerramento inesperado

Importação, exportação e geração intermediária usam uma pasta temporária exclusiva do FORNAX com acesso restrito ao usuário no Linux e macOS. Operações normais removem seu próprio espaço ao terminar. Se o processo for encerrado abruptamente, a próxima instância principal remove o conteúdo remanescente dessa pasta.

A limpeza se limita à área temporária pertencente ao FORNAX. Modelos, backups, recuperações, arquivos gerados e outras pastas do usuário não são removidos por essa rotina. O programa não afirma realizar apagamento seguro dos blocos físicos do disco.

## Responsabilidade do usuário e da instituição

O acesso aos dados segue as permissões da conta do sistema operacional. A instituição deve controlar acesso ao computador, às pastas de saída, aos backups e às senhas utilizadas. Ao compartilhar um modelo ou documento final, o usuário deve conferir quais assinaturas e dados foram incluídos.
