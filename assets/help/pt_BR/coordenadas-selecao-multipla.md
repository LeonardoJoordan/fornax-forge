## O que é

Os campos **X/Y de uma seleção múltipla** dependem do contexto.
No organograma, uma seleção compatível usa o centro dos limites conjuntos.
Nas páginas comuns, o editor mostra a posição de um objeto de referência.

## Para que serve

Serve para interpretar corretamente os números antes de reposicionar vários
elementos, evitando tratar a posição de um integrante como a posição do conjunto.

## Como usar

1. Selecione os elementos e confira seus destaques.
2. Na aba Organograma, observe a referência de centro nos campos X e Y.
3. Altere uma coordenada para deslocar a seleção compatível nesse eixo.
4. Nas páginas comuns, confira o agrupamento antes de alterar X/Y.
5. Para mover uma seleção temporária inteira na página comum, prefira o arraste
   conjunto ou as setas.

## Exemplo de uso

Dois blocos do organograma precisam ficar centralizados em uma coluna do quadro.
Selecione os dois e ajuste X. Eles recebem um deslocamento comum, mantendo sua
distância relativa, em vez de serem empilhados na mesma posição.

## Dica de uso

Não use X/Y de uma seleção temporária em página comum como se fossem o centro
geométrico de todos os objetos. Agrupar ou arrastar juntos oferece um fluxo
mais previsível para deslocar a composição.

## Particularidades e limites

- No organograma, a referência conjunta considera os retângulos dos elementos
  compatíveis na cena. Não é a média dos centros de cada objeto.
- O deslocamento no quadro acompanha a grade; seleções somente de textos usam
  o passo menor, e seleções mistas usam o passo dos blocos.
- Nas páginas comuns, editar X/Y desloca o objeto de referência ou os integrantes
  do grupo associado a ele. Uma seleção sem grupo não é movida inteira por essa ação.
- A seleção por Camadas pode conter apenas parte de um grupo; confira quais
  integrantes acompanham a operação.
- Guias, conectores e imagens dentro de máscaras têm tratamento próprio e
  não devem ser usados como referência de uma seleção comum de blocos.

## Veja também

- [Referência das coordenadas](help:TRA-03).
- [Mover por arraste](help:OBJ-07).
- [Mover com as setas](help:OBJ-08).
- [Agrupar](help:OBJ-19).
