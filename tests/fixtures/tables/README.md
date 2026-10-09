# Cenários de aceitação para tabelas

Estes JSONs descrevem entradas sintéticas para a implementação planejada em
`docs/PLANO_IMPLEMENTACAO_TABELAS.md`. **Não são documentos do aplicativo,
não usam `schema_version` e não devem ser importados para a biblioteca.**
O modelo persistente de tabela será definido depois da prova técnica.

| Arquivo | Caso de uso |
|---|---|
| `boletim.json` | Grade 10 × 6; notas por placeholder, título mesclado, texto multilinha, valores vazios e zero numérico. |
| `escala.json` | Grade 8 × 5; cinco posições fixas preenchidas por um registro, seleção de intervalos e alterações de estrutura. |
| `mesclagens.json` | Grade 4 × 4; mesclagens horizontais/verticais, Unicode, estilos, conteúdo para mesclar, bloco opcional e excesso de texto. |
| `frente-verso.json` | Duas páginas com grades 3 × 3 e 4 × 2; campo exclusivo do verso e texto vazio acompanhado de rótulo fixo. |

As medidas são físicas, em milímetros, e não definem uma nova convenção de
coordenadas para o aplicativo. `cells` contém apenas âncoras visíveis; a área
ocupada por cada uma é descrita por `row_span` e `column_span`. Os índices de
linha/coluna começam em zero. Chaves como `boletim-r3c3` são identificadores
legíveis do cenário, não nomes obrigatórios do futuro contrato persistente.

`records` contém somente dados inventados. `expected_resolved_text` guarda
expectativas específicas de conteúdo, sem prometer a capacidade do renderer
atual. Os demais testes devem conferir geometria, formatação e histórico.

Gerar novamente ou conferir as fixtures a partir da raiz:

```bash
.venv/bin/python tests/performance/table_fixtures.py
.venv/bin/python tests/performance/table_fixtures.py --check
```

O gerador confere cobertura completa, ausência de sobreposição, medidas
positivas e referências de expectativas. Não cria objetos Qt, não implementa
mesclagem no produto e não altera qualquer modelo pessoal ou pronto.
