## O que é

A **ancoragem pelo centro** faz os elementos livres do organograma encaixarem
seus centros na grade. Isso permite alinhar objetos de tamanhos diferentes
pela mesma referência.

## Para que serve

Serve para manter simetria entre blocos, títulos, imagens e formas sem
calcular separadamente a posição de cada canto.

## Como usar

1. Na aba Organograma, selecione um elemento livre compatível.
2. Observe X/Y, que representam seu centro.
3. Arraste ou ajuste as coordenadas para a referência desejada.
4. Selecione o outro elemento e use o mesmo X para alinhar os centros em uma coluna.
5. Use o mesmo Y para alinhar os centros em uma faixa horizontal.

## Exemplo de uso

Um bloco de 40 mm e uma caixa de título de 25 mm precisam compartilhar
uma coluna. Dê aos dois o mesmo X central para obter a simetria, mesmo
com larguras diferentes.

## Dica de uso

Na seleção múltipla compatível, a âncora é o centro dos limites conjuntos.
Mover esse centro não significa colocar todos os integrantes no mesmo ponto.

## Particularidades e limites

- O mecanismo vale para elementos livres da aba Organograma; páginas comuns
  usam a origem do objeto nos campos X/Y.
- Textos usam metade do passo da grade; os demais elementos compatíveis usam
  o passo maior.
- Os cantos dos objetos podem ficar entre linhas da grade, conforme seu tamanho.
- Uma seleção mista é deslocada pelo mesmo vetor para preservar as distâncias.
- Imagens dentro de máscaras usam enquadramento associado à forma, não esse
  fluxo de ancoragem como objeto livre.
- A referência dos objetos não é necessariamente o zero das réguas, que
  acompanha os limites do documento do quadro.

## Veja também

- [Referência das coordenadas](help:TRA-03).
- [Coordenadas da seleção múltipla](help:TRA-04).
- [Passos dos blocos e textos](help:GUI-19).
- [Origem das réguas](help:GUI-03).
