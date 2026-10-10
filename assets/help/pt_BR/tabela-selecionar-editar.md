## O que é

A tabela possui três contextos: objeto inteiro, seleção de células e edição do texto de uma célula. O primeiro clique em qualquer parte seleciona o objeto, mesmo que as células tenham preenchimento transparente.

## Para que serve

Formatar um intervalo de uma vez, escrever conteúdo ou mover a tabela sem confundir essas ações.

## Como usar

1. Clique na tabela para selecioná-la. Nesse contexto, arraste qualquer parte de seu corpo para mover o objeto; use as alças verdes dos cantos e bordas para redimensionar.
2. Com a tabela selecionada, clique novamente numa célula para entrar na seleção interna. A partir daí, arraste entre células ou use **Shift + clique** para ampliar o intervalo.
3. Dê duplo clique, pressione **Enter** ou **F2** para editar. Digitar com uma célula selecionada também inicia a edição.
4. Durante a edição, use o cursor normalmente para selecionar palavras e inserir quebras com **Enter**.
5. Use **Tab** e **Shift + Tab** para visitar as células. As mescladas são tratadas como uma célula.
6. **Esc** encerra a edição; outro **Esc** limpa a seleção interna, permitindo voltar ao arraste pelo corpo. A moldura e a camada também permitem selecionar o objeto inteiro.

Na seleção interna, segure **Ctrl** e clique para adicionar células separadas. Clique novamente com Ctrl numa célula escolhida para removê-la da seleção. Com **Ctrl + arrastar**, adicione uma área retangular sem perder as células escolhidas antes do arraste, mesmo se começar sobre uma delas. Uma célula mesclada entra ou sai por inteiro. **Shift + clique** volta a formar um intervalo contínuo. Fora da seleção interna, Ctrl + clique continua selecionando objetos no canvas.

Com a tabela selecionada, as setas acima selecionam colunas inteiras e as setas à esquerda selecionam linhas inteiras. A seta diagonal no canto superior esquerdo seleciona todas as células. Segure **Ctrl** ao clicar numa seta para acrescentar a linha ou coluna à seleção atual. Células mescladas entram por inteiro. Esses controles aparecem somente no editor e acompanham a tabela; se estiverem fora da área visível, mova a visualização para acessá-los. Em zoom muito reduzido, aumente o zoom para acessar os seletores das linhas ou colunas estreitas. Eles não aparecem na prévia nem nos arquivos gerados.

As células selecionadas recebem um realce suave e um contorno. Quando a seleção é separada, cada célula escolhida é destacada individualmente. Uma barra flutuante próxima à tabela oferece linhas, colunas, mesclar/separar, alinhamento e cor de preenchimento. Com células selecionadas, a formatação e Delete atuam apenas nelas; sem seleção interna, as ferramentas atuam na tabela inteira. Os controles da lateral continuam disponíveis.

Para reposicionar a barra, segure a alça de pontinhos e arraste para um dos destinos destacados em grafite claro. Solte para encaixar acima, abaixo, à esquerda ou à direita da tabela. Acima/abaixo a barra é horizontal; nas laterais é vertical. O lado escolhido permanece durante a sessão do editor, acompanhando a tabela e o zoom. **Esc** ou soltar fora dos destinos cancela o arrasto e mantém a posição anterior.

Os destinos ficam ao redor da tabela, mesmo quando você arrasta a barra recolhida.
Os destaques de cima e de baixo não ultrapassam a largura da tabela; os laterais
não ultrapassam sua altura. Essa redução afeta somente os destaques: ao encaixar,
a barra mantém seu tamanho normal ou continua recolhida, conforme estava.

O botão **−** recolhe as ferramentas, deixando apenas o botão **+** para expandir e a alça de arraste. A extremidade direita da barra horizontal ou inferior da barra vertical permanece no mesmo lugar. Mesmo recolhida, a barra pode ser arrastada para outro lado. O fundo e o contorno da barra usam 75% de opacidade; os botões e a alça permanecem opacos. O fundo cinza dos destinos de reposicionamento usa aproximadamente 35% de opacidade, aumentando para 50% quando o mouse está sobre o destino.

Os botões de alinhamento mostram o ícone da opção atual. Clique para abrir uma
faixa com os ícones de esquerda/centro/direita ou topo/meio/base e escolha o
alinhamento desejado. Se o intervalo contém alinhamentos diferentes, nenhuma
opção fica marcada até você uniformizá-los.

A faixa acompanha a orientação da barra: opções lado a lado quando a barra está
acima/abaixo, e uma abaixo da outra quando está à esquerda/direita. O menu abre
próximo ao botão correspondente.

O seletor usa a mesma espessura e os mesmos cantos arredondados da barra, com
fundo/contorno a 75% de opacidade e botões opacos.

## Exemplo de uso

Selecione o cabeçalho inteiro para aplicar negrito. Depois, entre apenas na célula “Disciplina” para corrigir uma palavra.

Para destacar notas específicas, selecione a primeira nota e use Ctrl + clique nas demais. Altere o preenchimento para destacar somente essas células.

## Dica de uso

Confira se há um cursor de texto ou um intervalo destacado antes de usar Delete ou colar conteúdo: o contexto muda o resultado.

## Particularidades e limites

- A seleção inclui mesclagens interceptadas por inteiro.
- Tab na última célula não acrescenta linhas.
- Uma tabela bloqueada não permite editar ou mover suas células.
- Uma tabela nova começa no contexto de objeto. As alças seguem a proporção configurada na barra superior; o texto não aumenta junto com as células.
- Clicar fora ou trocar de página conclui a edição aceita; não é necessário apagar o texto para sair.

## Veja também

- [Atalhos e histórico da tabela](help:TBL-11).
- [Copiar e colar células ou texto](help:TBL-10).
- [Tabela inteira, camadas e organograma](help:TBL-12).
