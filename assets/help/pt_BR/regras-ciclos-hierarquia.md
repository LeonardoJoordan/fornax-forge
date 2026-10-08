## O que é

O organograma valida suas relações: um bloco não pode ser superior de si mesmo, ter dois superiores ou formar um ciclo de subordinação.

## Para que serve

Conservar uma árvore de responsabilidades consistente.

## Como usar

1. Defina o superior usando a árvore, o campo Superior ou Conectar a elemento.
2. Se aparecer uma mensagem de relação inválida, reveja o caminho de subordinados.
3. Retire a ligação antiga quando necessário e crie a relação coerente.

## Exemplo de uso

Se Coordenação já responde à Direção, a Direção não pode passar a responder à Coordenação.

## Dica de uso

Antes de transferir um ramo, verifique se o novo superior já está dentro daquele próprio ramo.

## Particularidades e limites

- O programa impede ciclos, mas não valida a adequação institucional dos cargos.
- Vários blocos podem ficar sem superior, formando mais de um ramo principal.
- Posição no canvas não cria hierarquia por si só.

## Veja também

- [Arrastar blocos na árvore para alterar o superior](help:HIE-05).
- [Conectar a elemento pelo menu Blocos ou pelo painel da estrutura](help:HIE-08).
- [Alterar a hierarquia sem reposicionar automaticamente os blocos](help:HIE-16).
