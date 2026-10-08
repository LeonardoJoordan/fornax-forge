## O que é

O programa calcula as rotas considerando lados permitidos, limites dos conjuntos e outras ligações. Procura evitar obstáculos e cruzamentos entre relações distintas; conexões ao mesmo superior podem compartilhar trechos.

## Para que serve

Conservar a leitura da hierarquia ao mover ou redimensionar os blocos.

## Como usar

1. Organize os blocos deixando corredores entre eles.
2. Ajuste Entrada e Saída se o caminho estiver desnecessariamente longo.
3. Confira os conectores após mudar contornos, folgas ou dimensões.
4. Se aparecer aviso de falta de espaço, afaste os blocos ou permita outros lados.

## Exemplo de uso

Dê mais distância entre dois setores para que suas ligações alcancem superiores diferentes sem passar pelo mesmo corredor estreito.

## Dica de uso

Espaço livre costuma ajudar mais que reduzir o raio: primeiro separe os conjuntos, depois refine o traço.

## Particularidades e limites

- A busca procura rotas melhores, mas não garante ausência total de cruzamentos em qualquer disposição.
- A folga e o contorno externo do conjunto influenciam os limites dos conectores; com contorno só nos cartões, o conjunto continua sendo sua referência de estrutura.
- Quando não encontra rota livre, o programa mantém uma alternativa e mostra a condição de falta de espaço.
- O roteamento não reposiciona os blocos automaticamente.

## Veja também

- [Entrada: permitir pelo lado de cima](help:CON-01).
- [Saída: permitir pelo lado de cima](help:CON-05).
- [Folga do conjunto em milímetros](help:BOR-22).
- [Alterar a hierarquia sem reposicionar automaticamente os blocos](help:HIE-16).
