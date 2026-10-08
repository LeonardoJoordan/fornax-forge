## O que é

Barras verticais delimitam um trecho opcional com variável: `|texto {campo}|`. Quando falta um dos campos desse trecho, ele é removido; quando todos existem, o texto aparece sem as barras.

## Para que serve

Omitir complementos que nem todos os registros possuem, conservando o texto principal.

## Como usar

1. Digite a parte principal normalmente.
2. Envolva o complemento e seu placeholder em barras, como `| — {funcao}|`.
3. Teste uma linha com o campo preenchido e outra com o campo vazio.
4. Ajuste os espaços e a pontuação junto do trecho opcional.

## Exemplo de uso

Use `{nome}| — {funcao}|`: um registro sem função mostra apenas o nome, sem um travessão solto.

## Dica de uso

Inclua dentro das barras também o separador que só faz sentido com o complemento, como vírgula, hífen ou quebra de linha.

## Particularidades e limites

- Se faltar um placeholder obrigatório fora dos trechos opcionais, a caixa inteira é ocultada no resultado preenchido.
- Um trecho com várias variáveis só permanece quando todas têm conteúdo útil.
- Barras sem placeholder não são tratadas como trecho opcional; não há estrutura de opcionais aninhados.

## Veja também

- [Placeholder de texto (variável / campo dinâmico / `{campo}`)](help:VAR-01).
- [Placeholders visíveis no desenho sem dados preenchidos](help:VAR-13).
- [Cartões vazios, informação válida e ocultação de posições sem dados](help:BLO-21).
