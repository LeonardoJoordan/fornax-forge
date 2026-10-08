## O que é

Os **campos de transformação** usam unidades e precisões próprias.
X/Y e L/A são medidas em milímetros; a rotação usa graus; a opacidade geral
usa porcentagem.

## Para que serve

Serve para inserir valores na unidade correta e entender por que o editor
arredonda um número ou limita uma dimensão.

## Como usar

1. Confira o rótulo e a unidade do campo na barra superior.
2. Selecione um objeto compatível com o ajuste.
3. Digite o valor desejado sem misturar unidades na expressão.
4. Confirme e confira o número que permaneceu no campo.
5. Revise a composição, principalmente quando chegar ao limite do controle.

## Exemplo de uso

Para definir 2,5 cm de largura, informe **25** em L, pois o campo usa mm.
Para metade da opacidade, informe **50** no campo de porcentagem, não 0,5.

## Dica de uso

Zoom muda o tamanho que você vê na tela, mas não muda a unidade dos campos.
Use as medidas físicas para projetar o material no tamanho desejado.

## Particularidades e limites

- X/Y mostram duas casas decimais e aceitam de -5000 a 20000 mm nesses controles.
- L/A mostram duas casas decimais e normalmente aceitam de 1 a 5000 mm.
  A altura de uma linha pode ter mínimo de 0,01 mm.
- A rotação mostra uma casa decimal, entre 0 e 359,9 graus.
- A opacidade geral usa percentuais inteiros de 0 a 100.
- Os limites do campo não garantem que qualquer combinação seja aceita pelo
  formato do modelo ou pela geração; documento e objetos têm validações próprias.
- Medidas do documento e dos cartões do quadro usam seus controles específicos.
- Os passos de X/Y podem acompanhar a grade no organograma. A posição efetiva
  pode ser ajustada pelo magnetismo.
- Campos indisponíveis indicam uma seleção incompatível com aquela operação.

## Veja também

- [Zoom e tamanho físico](help:NAV-11).
- [Cálculos nos campos](help:TRA-15).
- [Documento](help:UI-07).
- [Referência das coordenadas](help:TRA-03).
