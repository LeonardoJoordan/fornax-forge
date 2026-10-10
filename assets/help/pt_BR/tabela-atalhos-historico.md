## O que é

Os atalhos da tabela distinguem a edição do texto, a seleção da grade e o objeto inteiro. Desfazer/refazer respeita esse contexto.

## Para que serve

Editar rapidamente sem apagar a tabela quando a intenção era limpar uma célula.

## Como usar

| Contexto | Comando | Resultado |
|---|---|---|
| Grade selecionada | Enter, F2 ou digitação | Inicia edição da célula |
| Grade selecionada | Setas / Shift + setas | Navega / amplia o intervalo |
| Células ou texto | Tab / Shift + Tab | Visita próxima / anterior |
| Texto em edição | Enter | Insere quebra de linha |
| Texto em edição | Ctrl+A, Delete, Ctrl+C/V | Atua no texto |
| Grade selecionada | Ctrl+A | Seleciona todas as células |
| Grade selecionada | Delete ou Backspace | Limpa conteúdo, conserva estrutura |
| Objeto sem seleção interna | Delete | Exclui a tabela inteira |
| Grade selecionada | Ctrl+D | Duplica a tabela inteira |
| Células ou trecho de texto | Ctrl+B/I/U | Negrito / itálico / sublinhado |
| Edição ou grade | Esc | Encerra edição / limpa seleção interna |

Use **Ctrl+Z** e **Ctrl+Y** para desfazer/refazer. Enquanto há edição ativa, as operações de texto usam primeiro seu histórico local; quando ele não possui mais a ação solicitada, o editor pode retornar ao histórico do documento.

## Exemplo de uso

Apague os valores de um intervalo com Delete e use Desfazer para recuperá-los, sem remover linhas.

## Dica de uso

Para excluir a tabela inteira, selecione a camada. Isso deixa claro que a operação é sobre o objeto.

## Particularidades e limites

- Durante digitação, Ctrl+D permanece no contexto do editor de texto; use o comando Duplicar da interface para uma cópia do objeto.
- **Ctrl+S** conclui a edição e aciona o salvamento normal do modelo.
- Desfazer/refazer em tabelas densas pode reconstruir a cena e levar mais tempo. O conteúdo completo continua no histórico.
- Comandos nativos podem variar conforme o sistema; os botões da interface continuam disponíveis.

## Veja também

- [Selecionar e editar células](help:TBL-02).
- [Copiar e colar](help:TBL-10).
- [Histórico do editor](help:SAL-01).
