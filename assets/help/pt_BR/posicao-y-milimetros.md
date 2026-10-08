## O que é

O campo **Y**, na barra superior, mostra e ajusta a posição vertical da
seleção em milímetros. No sistema do canvas, aumentar Y desloca o elemento
para baixo; diminuir Y o desloca para cima.

## Para que serve

Serve para organizar alturas, alinhar elementos na mesma referência vertical
e ajustar a distância de um objeto em relação à parte superior da página.

## Como usar

1. Selecione o objeto que precisa ajustar.
2. Localize **Y**, na barra superior do editor.
3. Digite a posição vertical desejada, em milímetros, e confirme com Enter
   ou ao sair do campo.
4. Confira a altura resultante no canvas.
5. Ajuste **X** separadamente se precisar alterar a posição horizontal.

## Exemplo de uso

Em um certificado, uma caixa sem rotação deve começar a 30 mm do topo.
Selecione a caixa e informe Y = 30.
No organograma, use o mesmo Y para alinhar os centros de dois blocos compatíveis.

## Dica de uso

Mover um bloco para uma altura maior ou menor não troca sua posição na hierarquia.
Para mudar quem é seu superior, use a estrutura do quadro ou a ferramenta de conexão.

## Particularidades e limites

- Em páginas comuns, Y indica a origem do objeto, normalmente seu canto superior
  esquerdo sem rotação. Um objeto girado pode ter seu limite visível em outra altura.
- No organograma, objetos de topo compatíveis usam o centro. Para vários objetos,
  a referência é o centro dos limites conjuntos.
- Nas páginas comuns, o campo de uma seleção múltipla usa um objeto de referência;
  não equivale à coordenada central do conjunto. Confira quais objetos estão
  agrupados ou prefira o arraste para mover a seleção inteira.
- O magnetismo pode influenciar o posicionamento; confira o valor final.
- Guias horizontais usam Y; para guias verticais, esse eixo fica desabilitado.
- Sem seleção compatível ou com o plano de fundo, o campo pode ficar desabilitado.
- Um valor negativo pode colocar conteúdo acima da página; em páginas comuns,
  a área externa não é incluída automaticamente na geração.

## Veja também

- [Posição X](help:TRA-01).
- [Referência das coordenadas](help:TRA-03).
- [Mover com setas](help:OBJ-08).
- [Estrutura do quadro](help:UI-10).
