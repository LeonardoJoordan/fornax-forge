## O que é

O campo **X**, na barra superior, mostra e ajusta a posição horizontal da
seleção em milímetros. A referência depende de você estar em uma página comum
ou na aba Organograma.

## Para que serve

Serve para posicionar um elemento com precisão no eixo horizontal e repetir
uma referência de alinhamento sem depender apenas do arraste.

## Como usar

1. Selecione o objeto que deseja posicionar.
2. Localize **X**, na barra superior do editor.
3. Digite a posição horizontal desejada, em milímetros, e confirme com Enter
   ou ao sair do campo.
4. Confira a posição no canvas e o valor exibido.
5. Use **Y** se também quiser ajustar a posição vertical.

## Exemplo de uso

Em uma página comum, uma caixa sem rotação deve começar a 15 mm da lateral
esquerda. Selecione apenas essa caixa e informe X = 15.
No organograma, X = 100 posiciona o centro do elemento compatível nessa
referência horizontal, conforme o magnetismo do quadro.

## Dica de uso

Para alinhar centros de elementos com larguras diferentes no organograma,
use o mesmo X. Em páginas comuns, igualar X alinha as origens dos objetos,
que normalmente correspondem ao canto superior esquerdo sem rotação.

## Particularidades e limites

- Nas páginas comuns, X usa a origem do objeto; não representa necessariamente
  a lateral visível de um objeto girado.
- No organograma, objetos de topo compatíveis usam o centro; vários selecionados
  usam o centro dos limites conjuntos e se deslocam pelo mesmo valor.
- Em páginas comuns, uma seleção múltipla usa um objeto de referência. Para
  posicionar toda uma composição de forma previsível, confira o agrupamento
  ou use o arraste conjunto; o campo não representa seu centro total.
- O magnetismo pode influenciar o posicionamento; confira o resultado após confirmar.
- Uma guia vertical pode ser posicionada por X. Uma guia horizontal usa Y.
- Sem seleção compatível ou com o plano de fundo, o campo pode ficar desabilitado.
- Valores negativos podem colocar o objeto fora da página; isso não amplia
  automaticamente a área gerada de uma página comum.

## Veja também

- [Posição Y](help:TRA-02).
- [Referência das coordenadas](help:TRA-03).
- [Coordenadas da seleção múltipla](help:TRA-04).
- [Área externa à página](help:NAV-09).
