# Central de ajuda local

A tela principal oferece **Ajuda → Central de ajuda…**, imediatamente abaixo
de **Tutorial interativo…**. O atalho é **F1**. A janela permite pesquisar,
filtrar por categoria e selecionar um tópico sem bloquear a tela principal.
Ao reabrir a central, a busca e a seleção são preservadas durante a sessão.
Clique no nome de uma categoria ou na setinha à esquerda para expandir ou
recolher seus tópicos. Essa navegação mantém o artigo aberto no painel de leitura.

## Conteúdo do editor

O catálogo inicial vem de [INVENTARIO_AJUDA_EDITOR.md](INVENTARIO_AJUDA_EDITOR.md).
São 402 tópicos públicos. **402 tópicos já têm conteúdo**, distribuídos em
**208 artigos**. Controles complementares podem compartilhar a explicação
quando fazem parte do mesmo fluxo. Todos os tópicos públicos estão documentados.
As duas entradas REV-01 e REV-02 permanecem no catálogo com estado `review`, fora da busca pública,
até a revisão do acesso desses atalhos pela interface.

A pesquisa ignora acentos e maiúsculas e consulta títulos, palavras relacionadas,
categorias e o texto dos artigos disponíveis. Os termos devem ocorrer no mesmo
tópico, ainda que em campos diferentes. Títulos recebem prioridade sobre palavras
relacionadas, categoria e conteúdo. A busca está vazia ao abrir a central e
apresenta as categorias; uma pesquisa expande os grupos com resultados.

O conteúdo inicial está em português. Se não existir um catálogo para o idioma
ativo, o aplicativo usa `pt_BR`. Os controles da janela seguem o sistema de
tradução da interface.

## Organização dos arquivos

- `assets/help/pt_BR/catalog.json`: categorias e metadados dos tópicos.
- `assets/help/pt_BR/*.md`: artigos em Markdown.
- `core/help_catalog.py`: leitura, cache e classificação dos resultados.
- `features/help/help_dialog.py`: janela e entrada pelo menu.

O leitor conserva a formatação Markdown e aplica espaçamento entre seções,
parágrafos e itens de listas. Esse padrão vale para todos os artigos e acompanha
os temas claro e escuro sem modificar a formatação dos documentos do editor.

O aplicativo carrega o catálogo e os textos uma vez, quando a ajuda é aberta,
e pesquisa em memória. O inventário em `docs` não é lido durante a execução.
Os arquivos da ajuda são incluídos na seleção de recursos dos pacotes por
`scripts/release_tools.py`, sem nova dependência de execução.

## Manter e acrescentar artigos

Cada tópico usa um identificador estável do inventário, título, categoria,
palavras relacionadas, arquivo opcional e estado. Por exemplo:

```json
{
  "id": "MAS-09",
  "title": "Editar máscara.",
  "category": "editor-12",
  "keywords": ["máscara", "recorte", "enquadramento"],
  "file": "enquadrar-mascara.md",
  "status": "published"
}
```

Criar o arquivo Markdown dentro da pasta do catálogo e preencher `file`.
Usar `file: null` enquanto o artigo não estiver escrito. Categorias e
identificadores devem ser únicos. Um arquivo indicado precisa existir; caminhos
que escapam da pasta do catálogo são rejeitados.

O texto pode incluir títulos, listas, negrito, exemplos e links internos como
`[Imagem variável](help:DIN-01)`. Vários tópicos podem apontar para um mesmo
artigo quando a explicação fizer sentido em conjunto. Ao adicionar ou revisar
arquivos, reiniciar o aplicativo para recarregar o catálogo.

O estado `review` reserva entradas para revisão interna e as oculta da central.
Uma entrada sem texto mostra apenas seu título, categoria e o aviso
“Descrição ainda não disponível.”.

A redação e as pendências são acompanhadas em
[PROGRESSO_AJUDA_EDITOR.md](PROGRESSO_AJUDA_EDITOR.md).
