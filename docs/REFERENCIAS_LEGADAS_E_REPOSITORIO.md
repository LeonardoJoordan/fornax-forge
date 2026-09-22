# Referências preservadas e repositório oficial

Repositório oficial: https://github.com/LeonardoJoordan/fornax-forge.
O histórico de desenvolvimento anterior permanece no Projeto ComSoc.

## Compatibilidade que deve permanecer

| Local | Referência | Motivo |
|---|---|---|
| `core/paths.py` | `com.leobelisario.ProjetoComSoc`, `ProjetoComSoc`, `.comsoc-migration.json` | Encontrar dados antigos e retomar a migração sem duplicá-los |
| `core/settings.py` | `Projeto ComSoc` / `MainApp` | Copiar preferências antigas sem sobrescrever valores atuais |
| Repositório Projeto ComSoc | Testes e histórico anteriores | Não incluídos nesta árvore de distribuição do código |

Preservar também o AppId do Inno Setup, `com.leobelisario.FornaxForge`, o namespace das preferências atuais e o tipo MIME `application/x-fornax-template`. Trocar a marca ou o endereço do repositório não exige trocar essas identidades.

## Endereços do projeto

| Local | Endereço atual | Ação futura |
|---|---|---|
| `.git/config`, remoto `origin` | `https://github.com/LeonardoJoordan/fornax-forge.git` | Repositório independente, sem importar o histórico anterior |
| `instalador.iss`, `AppPublisherURL` | `https://github.com/LeonardoJoordan/fornax-forge` | Página do novo repositório |
| `instalador.iss`, `AppSupportURL` | Mesmo endereço, `/issues` | Canal real de suporte |
| `instalador.iss`, `AppUpdatesURL` | Mesmo endereço, `/releases` | Releases do novo repositório |

A varredura do código de execução não encontrou outros URLs do repositório antigo. Links de fornecedores e textos de licenças não devem ser alterados. Documentos históricos mantêm os links originais. Na separação, revisar novamente toda a árvore, habilitar/testar o canal privado descrito em `SECURITY.md` e executar o workflow remoto; a existência do YAML local não comprova execução no GitHub.
