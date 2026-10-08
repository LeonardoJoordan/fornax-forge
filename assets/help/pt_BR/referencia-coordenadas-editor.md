## O que é

A **referência das coordenadas** é o ponto usado para interpretar X e Y.
Nas páginas comuns, esses campos indicam a origem do objeto. No organograma,
objetos compatíveis usam seu centro ou o centro da seleção.

## Para que serve

Serve para posicionar elementos de tamanhos diferentes sem confundir sua
origem com seu centro ou com o limite externo da arte.

## Como usar

1. Confira se a aba ativa é uma página comum ou Organograma.
2. Selecione um objeto e observe os campos **X** e **Y** na barra superior.
3. Em uma página comum, use a origem do objeto como referência.
4. No organograma, use o centro indicado para objetos de topo compatíveis.
5. Após alterar uma coordenada, confira o resultado e o encaixe na grade.

## Exemplo de uso

No organograma, um bloco de 40 mm e um texto de 25 mm podem ficar centralizados
na mesma coluna ao receber o mesmo X. Em uma página comum, igualar X de objetos
sem rotação alinha suas origens à esquerda, não seus centros.

## Dica de uso

Ao girar um objeto, sua origem continua sendo uma referência de posição,
mas pode deixar de coincidir visualmente com o canto do contorno que você vê.

## Particularidades e limites

- Na página comum, a origem normalmente corresponde ao canto superior esquerdo
  do objeto sem rotação.
- No quadro, a referência central vale para elementos compatíveis sem um objeto
  pai, como blocos, textos, imagens e formas livres.
- Imagens dentro de máscaras têm uma relação de posição com a forma; use o
  modo de enquadramento para ajustá-las.
- A grade pode ajustar a posição pedida. Confira os valores resultantes.
- As réguas contam a partir do limite do documento. No organograma, esse limite
  pode acompanhar a composição e sua margem; não presuma que o zero da régua
  coincide sempre com a origem fixa das coordenadas dos objetos.

## Veja também

- [Posição X](help:TRA-01).
- [Posição Y](help:TRA-02).
- [Coordenadas da seleção múltipla](help:TRA-04).
- [Ancoragem pelo centro](help:GUI-20).
