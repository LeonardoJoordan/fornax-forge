## O que é

O editor adapta os controles ao **tipo de objeto selecionado** e à quantidade
de elementos na seleção. Por isso, uma opção pode aparecer, ficar desabilitada
ou deixar de ser exibida quando você muda de objeto.

## Para que serve

Essa adaptação apresenta os recursos que fazem sentido para a edição atual
e evita aplicar uma configuração a um objeto que não a suporta.

## Como usar

1. Selecione o elemento que deseja editar no canvas ou em **Camadas**.
2. Confira o resumo **Seleção** e os controles disponíveis na barra superior
   e nas seções da direita.
3. Para uma configuração específica, como fonte ou imagem variável, selecione
   um objeto individual compatível.
4. Para transformar vários objetos juntos, faça uma seleção múltipla e use
   os controles de posição, tamanho e transformação disponíveis.

## Exemplo de uso

Ao selecionar uma caixa de texto, o painel Texto permite ajustar a fonte.
Ao selecionar um retângulo, Propriedades oferece preenchimento e contorno.
Ao selecionar um conector do organograma, aparecem seus controles de aparência.

## Dica de uso

Se um controle esperado estiver indisponível, confira a seleção antes de
procurar outro menu. Pode haver vários objetos selecionados ou um elemento
diferente daquele que você pretendia editar.

## Particularidades e limites

- A seleção múltipla oferece operações conjuntas, mas não reúne automaticamente
  todos os controles específicos de cada objeto.
- Linhas não têm os mesmos recursos de imagem variável e máscara de outras formas.
- O plano de fundo possui restrições próprias de transformação e contorno.
- Durante o enquadramento de uma máscara, o painel conserva o contexto da
  edição, mesmo que a imagem interna seja a seleção técnica do canvas.
- Selecionar um objeto e selecionar caracteres dentro de uma caixa de texto
  produzem contextos diferentes de formatação.

## Veja também

- [Resumo Seleção](help:UI-03).
- [Painel Propriedades](help:UI-08).
- [Seleção múltipla](help:OBJ-03).
- [Editar máscara](help:MAS-09).
