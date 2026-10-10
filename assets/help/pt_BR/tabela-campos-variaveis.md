## O que é

Uma célula pode conter texto fixo e **placeholders**, como `{nome}` e `{nota_portugues}`. Os valores vêm das colunas correspondentes da planilha de dados da tela principal.

## Para que serve

Gerar um boletim por aluno, mantendo a mesma estrutura, sem preencher cada tabela manualmente no editor.

## Como usar

1. Edite a célula e escreva o campo entre chaves, com nome simples, sem espaços: `{nota_portugues}`.
2. Formate o placeholder no modelo, por exemplo, com negrito.
3. Confira **Documento → Campos da tabela**, salve e preencha os dados na tela principal.
4. Revise a prévia com registros curtos, longos e vazios antes da geração.

## Exemplo de uso

Na linha Português, use `{nota_1}`, `{nota_2}` e `{resultado}` nas três colunas de valores.

## Dica de uso

Use nomes distintos quando os valores são distintos. Repetir `{resultado}` em todas as disciplinas mostra o mesmo valor em todas elas.

## Particularidades e limites

- Campos vazios retiram o valor variável, mas não apagam a grade, o preenchimento ou o texto fixo da tabela. Zero é um valor válido.
- Sem dados, a prévia de layout mostra os placeholders. Trechos opcionais entre barras podem ser usados no texto da célula.
- A formatação do placeholder participa da substituição, assim como a formatação presente no dado. Confira o resultado de estilos combinados.
- O cálculo de notas e resultados deve ser feito na planilha de origem; a tabela gráfica não executa fórmulas.
- No cartão de um organograma, um campo válido apenas na tabela também pode tornar o registro apto a preencher um cartão.

## Veja também

- [Boletim escolar](help:TBL-14).
- [Campos da tabela no painel Documento](help:VAR-09).
- [Formato herdado pelo placeholder](help:VAR-05).
