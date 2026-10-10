## O que é

**Conteúdo excedente**, também chamado overflow, acontece quando o texto não cabe na área útil fixa de uma célula. O editor sinaliza essa situação; a geração produz avisos identificando a tabela e a célula.

## Para que serve

Encontrar cortes de conteúdo antes de distribuir um boletim ou ficha com texto incompleto.

## Como usar

1. Observe os indicadores de excesso na tabela e os avisos da geração.
2. Confira o valor real que substituiu o campo, não apenas o nome do placeholder.
3. Amplie a linha/coluna, ajuste a fonte, reduza o espaçamento interno ou revise o texto.
4. Gere uma amostra e confira novamente.

## Exemplo de uso

Uma observação de três parágrafos não cabe na linha de 8 mm. Aumente a altura reservada ou reduza o conteúdo antes de gerar o boletim.

## Dica de uso

Teste registros com os maiores nomes e observações. Um modelo correto com “Ana” pode cortar um nome composto longo.

## Particularidades e limites

- O desenho recorta o excesso para não invadir a célula vizinha; não aumenta a linha nem reduz a fonte automaticamente. O texto salvo não é truncado pelo recorte visual.
- Há no máximo **100 linhas**, **100 colunas** e **1.000 posições lógicas por tabela**, além de **20 tabelas** e **2.000 posições por documento**, somando páginas e organograma.
- Mesclar não reduz a contagem de posições. Replicar cartões no organograma não cria novas tabelas no documento salvo.
- Limites de conteúdo: **32 KiB de HTML por célula**, **512 KiB por tabela** e **1 MiB no documento**. A formatação também ocupa esse orçamento.
- Uma operação inválida é recusada antes de publicar. Na digitação, o último texto aceito é conservado quando o orçamento é excedido.
- Células aceitam texto e formatação; não aceitam imagens, recursos externos ou tabelas aninhadas. Não há fórmulas nem paginação própria.

## Veja também

- [Medidas](help:TBL-05).
- [Texto, quebra e alinhamento](help:TBL-06).
- [Boletim escolar](help:TBL-14).
