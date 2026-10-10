## O que é

Um exemplo de composição que usa a tabela gráfica para montar um boletim e a planilha de dados para preencher um registro por aluno.

## Para que serve

Gerar boletins consistentes em lote, com cabeçalhos e células editáveis no próprio modelo.

## Como usar

1. Crie o modelo no tamanho de papel desejado e insira uma tabela de **6 linhas × 4 colunas**.
2. Mescle a primeira linha inteira e escreva **BOLETIM ESCOLAR**.
3. Na segunda linha, escreva **Disciplina**, **1º período**, **2º período** e **Resultado**.
4. Nas quatro linhas restantes, escreva as disciplinas na primeira coluna e campos próprios nas outras, por exemplo, `{portugues_1}`, `{portugues_2}` e `{portugues_resultado}`.
5. Acrescente uma caixa de texto acima com `{nome}` e `{turma}`. Ajuste tipografia, fundo dos cabeçalhos e contornos.
6. Salve. Na tela principal, preencha uma linha de dados por aluno ou cole uma planilha preparada com essas colunas.
7. Confira a prévia e gere uma amostra antes do lote completo.

## Exemplo de uso

O registro de um aluno fornece nome, turma e notas. Todos os campos desse registro preenchem um único boletim; cada disciplina possui suas próprias colunas de dados.

## Dica de uso

Calcule médias e situações na planilha de origem e traga os resultados prontos. O modelo se concentra na apresentação.

## Particularidades e limites

- Linhas gráficas não correspondem a registros da planilha principal: as seis linhas do boletim são preenchidas pelo mesmo registro do aluno.
- Não repita o mesmo placeholder em disciplinas com valores diferentes.
- Campo vazio deixa a célula sem o valor, mas conserva a grade e textos fixos.
- Nenhuma fórmula é executada dentro da tabela. Cores de aprovação/reprovação não mudam automaticamente conforme a nota.
- Revise notas e textos longos para evitar recortes e confirme o tamanho físico escolhido para a saída.

## Veja também

- [Inserir uma tabela](help:TBL-01).
- [Campos variáveis nas células](help:TBL-09).
- [Conteúdo excedente e limites](help:TBL-13).
