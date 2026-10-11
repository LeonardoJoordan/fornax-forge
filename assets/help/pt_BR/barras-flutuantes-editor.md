## O que é

A barra flutuante reúne atalhos próximos ao objeto selecionado no canvas.
As ferramentas mudam conforme o objeto, enquanto arraste, ancoragem,
recolhimento e aparência seguem o mesmo padrão.

## Para que serve

Ajustar as propriedades mais usadas sem percorrer a lateral a cada alteração,
mantendo o acesso aos controles completos dos painéis.

## Como usar

1. Selecione um objeto compatível e confira os atalhos próximos a ele:
   - **Texto:** fonte, tamanho, alinhamentos horizontal e vertical, cor e opacidade das letras.
   - **Imagem comum:** opacidade geral e máscara, incluindo edição ou remoção de uma máscara existente.
   - **Retângulo ou elipse:** preenchimento, ativar/desativar contorno, opacidade geral e máscara ou imagem variável.
   - **Tabela:** linhas, colunas, mesclar/separar, alinhamentos e preenchimento das células.
   - **Seleção agrupável ou grupo:** agrupar ou desagrupar, conforme o estado atual.
   - **Blocos do organograma:** conectar a um elemento superior.
2. Arraste pela alça de pontinhos, à direita na barra horizontal ou embaixo na vertical.
3. Solte em um destino destacado. Há **oito posições**: duas acima, duas abaixo e duas em cada lateral.
4. Use **−** para recolher e **+** para expandir. Recolhida, a barra conserva apenas esse botão e a alça; a extremidade direita ou inferior fica ancorada.
5. Nos seletores de alinhamento, escolha o ícone. A barra mostra a opção atual; o menu acompanha sua orientação horizontal ou vertical.

A posição mais próxima deixa 20 px entre o objeto e a barra. A segunda deixa,
além desses 20 px, a espessura da barra e mais 30 px, evitando sobrepor os dois
destinos. Essas distâncias são da interface e não são medidas do documento.

O fundo e o contorno da barra usam 75% de opacidade; os botões ficam opacos.
Durante o arraste, os destinos têm 35% de opacidade e o destino sob o mouse,
50%. O destaque mantém a espessura da barra, mas seu comprimento pode ser
limitado pela largura ou altura do objeto. A barra conserva seu tamanho ao encaixar.

## Exemplo de uso

Uma barra sobre a tabela encobre o título. Arraste-a para a posição mais afastada
à direita; ela fica vertical. Recolha-a enquanto organiza o restante da página
e expanda quando precisar acrescentar uma coluna.

## Dica de uso

Use a posição mais afastada quando houver texto ou imagens junto ao objeto.
Passar o mouse sobre os ícones mostra a função de cada atalho. A barra de texto
usa opacidade das letras; a de imagem ou forma usa opacidade geral do objeto.

## Particularidades e limites

- A barra acompanha a seleção e o zoom; a posição escolhida vale durante a sessão do editor, não como uma configuração da arte salva.
- Linhas, assinaturas, plano de fundo e conectores não recebem essa barra; seus controles continuam nos painéis.
- Objetos bloqueados ou seleções incompatíveis podem não oferecer atalhos.
- **Esc** durante o arraste, ou soltar fora dos destinos, mantém a posição anterior.
- Perto dos limites da área visível, destinos podem ser deslocados ou coincidir. Afaste a visualização ou o objeto para acessar mais posições.
- Durante o enquadramento de uma máscara, a barra oferece **Cancelar** e **Concluir**, com uma orientação acima, em vez dos atalhos normais.
- Barras e destinos de arraste são controles do editor; não aparecem na prévia nem nos arquivos gerados.

## Veja também

- [Controles disponíveis conforme a seleção](help:UI-12).
- [Tipos de opacidade](help:TRA-13).
- [Selecionar células e editar tabelas](help:TBL-02).
- [Usar como máscara / Aplicar máscara](help:MAS-01).
- [Conectar blocos a um superior](help:HIE-08).
