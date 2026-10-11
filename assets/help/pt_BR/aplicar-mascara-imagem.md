## O que é

Uma máscara vincula uma imagem comum a uma forma fechada. A imagem passa a aparecer somente dentro do contorno geométrico da forma, sem destruir seu arquivo original.

## Para que serve

Enquadrar fotos em retângulos, cantos arredondados ou elipses.

## Como usar

1. Importe uma imagem e crie a forma que delimitará seu recorte.
2. Selecione a forma e abra o botão de máscara da barra flutuante. Escolha **Selecionar imagem no canvas ou em Camadas** e clique na imagem que será recortada.
3. Você também pode começar pela imagem: abra **Aplicar máscara → Selecionar forma no canvas ou em Camadas** e clique na forma de recorte.
4. Ajuste o enquadramento e conclua.

Na lateral, **Propriedades → MÁSCARA** continua oferecendo a escolha por lista:
selecione o destino e confirme com **Inserir imagem** ou **Aplicar**, conforme o objeto selecionado.

Na barra flutuante da forma, o atalho de máscara oferece duas opções:

- **Selecionar imagem no canvas ou em Camadas**: ativa a seleção por clique.
  Clique na imagem no desenho ou na sua linha em **Camadas** para iniciar o
  enquadramento. Clicar em outro tipo de item, fora da seleção ou pressionar
  **Esc** cancela sem aplicar a máscara.
- **Imagem variável**: usa a forma para receber imagens diferentes por linha
  da tabela de dados. Ajuste o **Campo da tabela** e o **Enquadramento** em
  **Propriedades → IMAGEM VARIÁVEL**; a pasta das imagens é escolhida na tela principal.

Quando a forma já tem máscara, esse atalho passa a removê-la, soltando suas
imagens sem apagá-las. Para uma imagem variável, ele desativa o campo variável.
Quando a **imagem** já está mascarada, seu botão abre **Editar máscara** e
**Remover máscara**. A remoção pela imagem libera somente essa imagem;
a remoção pela forma libera todas as imagens vinculadas à forma.
Durante o enquadramento, use **Concluir/Cancelar** na barra flutuante, os
controles da lateral ou **Enter/Esc**.

## Exemplo de uso

Use uma elipse para recortar uma foto de perfil circular no cartão.

## Dica de uso

Nomeie a imagem e a forma antes de vincular quando houver vários objetos; fica mais fácil localizar o destino em Camadas ou na lista da lateral.

## Particularidades e limites

- A máscara aceita retângulos e elipses/círculos; linhas e o plano de fundo do documento não são destinos.
- Uma forma com imagem variável não pode receber simultaneamente a máscara de imagens fixas.
- Assinaturas não são imagens comuns para esse vínculo.
- A imagem que já pertence a uma máscara precisa ser desvinculada antes de receber outra.

## Veja também

- [Editar máscara](help:MAS-09).
- [Relação entre recorte da máscara, preenchimento, contorno e arredondamento](help:MAS-16).
- [Disponibilidade do recurso em formas e relação com máscaras de imagens fixas](help:DIN-08).
