# Inventário para a ajuda do editor — FORNAX Forge

Mapeamento da interface e dos comportamentos do editor em 07/10/2026.
Esta é uma lista de tópicos para desenvolver e revisar, não o texto final da
ajuda. As caixas marcadas indicam artigos escritos e integrados à central;
as desmarcadas indicam artigos ainda não escritos. Elas não indicam
funcionalidades ausentes. A revisão editorial é acompanhada em
[PROGRESSO_AJUDA_EDITOR.md](PROGRESSO_AJUDA_EDITOR.md).

Escopo: editor de modelos, editor de organograma e diálogos associados.
A tabela de dados, a biblioteca da tela principal, as configurações de geração
e a exportação em ladrilhos ficam para inventários próprios. As relações desses
recursos com o modelo aparecem aqui apenas como assuntos do editor.

Cada identificador representa um assunto pesquisável. Nomes entre parênteses
incluem termos alternativos, atalhos ou o contexto para distinguir controles
parecidos. Um mesmo artigo poderá atender a mais de um controle.

Para cada tópico, preencher posteriormente, quando aplicável:

- Descrição e finalidade.
- Localização e modo de usar, incluindo atalhos.
- Um ou dois exemplos de utilidade.
- Dica ou insight de uso.
- Limitações e condições de disponibilidade.
- Particularidade, curiosidade ou relação com outro recurso.

## 01. Pontos de partida e modelos prontos

- [x] INI-01 — Painel “Escolha um ponto de partida” ao criar novo modelo.
- [x] INI-02 — Começar em branco.
- [x] INI-03 — Miniaturas e seleção de modelo pronto.
- [x] INI-04 — Nome e descrição do modelo pronto.
- [x] INI-05 — Dimensões em milímetros e identificação do formato da folha.
- [x] INI-06 — Usar modelo.
- [x] INI-07 — Cancelar a escolha de modelo.
- [x] INI-08 — Personalização e independência da cópia de um modelo pronto.
- [x] INI-09 — Cartão de aniversário de pessoal.
- [x] INI-10 — Certificado de estágio.
- [x] INI-11 — Prisma de identificação.
- [x] INI-12 — Convite institucional.
- [x] INI-13 — Organograma institucional.

## 02. Organização da interface

- [x] UI-01 — Nome do modelo no cabeçalho do editor.
- [x] UI-02 — Barra superior de transformação, guias e histórico.
- [x] UI-03 — Resumo “Seleção” e identificação do objeto selecionado.
- [x] UI-04 — Painel esquerdo “Adicionar ao modelo”.
- [x] UI-05 — Painel esquerdo “Camadas”.
- [x] UI-06 — Área de desenho (canvas, prancheta, página).
- [x] UI-07 — Painel direito “Documento”.
- [x] UI-08 — Painel direito “Propriedades”.
- [x] UI-09 — Painel direito “Texto”.
- [x] UI-10 — Painel direito “Estrutura do quadro” no organograma.
- [x] UI-11 — Expandir e recolher seções da barra lateral.
- [x] UI-12 — Controles disponíveis conforme o tipo de seleção.
- [x] UI-13 — Redimensionar painéis pelas divisórias laterais.
- [x] UI-14 — Rolagem das barras e painéis quando faltar espaço.
- [x] UI-15 — Dicas dos controles ao passar o mouse sobre ícones.
- [x] UI-16 — Aparência dos controles nos temas claro e escuro.

## 03. Navegação e visualização do desenho

- [x] NAV-01 — Ajustar à janela.
- [x] NAV-02 — Ampliar e reduzir com Ctrl + roda do mouse.
- [x] NAV-03 — Zoom por gesto de pinça no touchpad.
- [x] NAV-04 — Ponto de referência do zoom junto ao cursor.
- [x] NAV-05 — Deslocar a visualização segurando Espaço (mãozinha).
- [x] NAV-06 — Deslocar a visualização com o botão do meio do mouse.
- [x] NAV-07 — Barras de rolagem horizontal e vertical.
- [x] NAV-08 — Encerrar uma interação de arraste ou navegação com Esc.
- [x] NAV-09 — Área externa à página e conteúdo exibido com aparência atenuada.
- [x] NAV-10 — Fundo quadriculado e indicação visual de transparência.
- [x] NAV-11 — Diferença entre zoom da visualização e tamanho físico do documento.

## 04. Seleção e operações sobre objetos

- [x] OBJ-01 — Selecionar um objeto no canvas.
- [x] OBJ-02 — Selecionar objetos pelas camadas.
- [x] OBJ-03 — Seleção de vários objetos com modificadores de teclado.
- [x] OBJ-04 — Seleção por área ao clicar e arrastar no espaço vazio.
- [x] OBJ-05 — Limpar a seleção ao clicar no espaço vazio.
- [x] OBJ-06 — Selecionar tudo na página ativa (Ctrl+A).
- [x] OBJ-07 — Mover objetos por arraste.
- [x] OBJ-08 — Mover a seleção com as setas do teclado.
- [x] OBJ-09 — Movimento ampliado com Shift + setas.
- [x] OBJ-10 — Alças de redimensionamento dos objetos.
- [x] OBJ-11 — Moldura e alças de transformação da seleção múltipla.
- [x] OBJ-12 — Transformação conjunta preservando a disposição dos objetos.
- [x] OBJ-13 — Copiar objetos (Ctrl+C).
- [x] OBJ-14 — Colar objetos (Ctrl+V).
- [x] OBJ-15 — Copiar e colar objetos entre páginas do modelo.
- [x] OBJ-16 — Duplicar objetos (Duplicar / Ctrl+D).
- [x] OBJ-17 — Nomes e identidades das cópias e duplicações.
- [x] OBJ-18 — Excluir objetos (Excluir / Delete).
- [x] OBJ-19 — Agrupar objetos (Agrupar / Ctrl+G).
- [x] OBJ-20 — Desagrupar objetos (Ctrl+Shift+G).
- [x] OBJ-21 — Selecionar, mover e redimensionar um grupo.
- [x] OBJ-22 — Diferença entre seleção múltipla, grupo de objetos e conjunto de cartões.
- [x] OBJ-23 — Diferença entre copiar objetos e copiar texto durante a edição.
- [x] OBJ-24 — Objetos ocultos, bloqueados e especiais nas operações de seleção.

## 05. Posição, tamanho, rotação e opacidade

- [x] TRA-01 — Posição X, em milímetros.
- [x] TRA-02 — Posição Y, em milímetros.
- [x] TRA-03 — Referência das coordenadas em páginas comuns e no organograma.
- [x] TRA-04 — Coordenadas de uma seleção múltipla.
- [x] TRA-05 — Largura (L), em milímetros.
- [x] TRA-06 — Altura (A), em milímetros.
- [x] TRA-07 — Manter ou liberar proporção ao redimensionar um objeto.
- [x] TRA-08 — Proporção e redimensionamento de grupos e seleções múltiplas.
- [x] TRA-09 — Girar 90° no sentido anti-horário.
- [x] TRA-10 — Girar 90° no sentido horário.
- [x] TRA-11 — Ângulo de rotação em graus.
- [x] TRA-12 — Opacidade geral do objeto.
- [x] TRA-13 — Diferença entre opacidade geral, do texto, do preenchimento e do contorno.
- [x] TRA-14 — Restaurar original: tamanho e rotação de imagens e assinaturas.
- [x] TRA-15 — Cálculos nos campos numéricos que aceitam expressões matemáticas.
- [x] TRA-16 — Unidades, casas decimais e limites dos campos de transformação.

## 06. Réguas, guias e magnetismo

- [x] GUI-01 — Régua horizontal.
- [x] GUI-02 — Régua vertical.
- [x] GUI-03 — Origem, escala e medidas em milímetros nas réguas.
- [x] GUI-04 — Criar guia horizontal arrastando a régua superior.
- [x] GUI-05 — Criar guia vertical arrastando a régua lateral.
- [x] GUI-06 — Adicionar guia horizontal pelo botão da barra superior.
- [x] GUI-07 — Adicionar guia vertical pelo botão da barra superior.
- [x] GUI-08 — Prévia da guia durante a criação e cancelamento com Esc.
- [x] GUI-09 — Selecionar e mover uma guia.
- [x] GUI-10 — Exibir ou ocultar guias.
- [x] GUI-11 — Bloquear ou desbloquear a movimentação das guias.
- [x] GUI-12 — Remover uma guia selecionada.
- [x] GUI-13 — Remover uma guia arrastando-a de volta para a régua.
- [x] GUI-14 — Encaixe das guias no centro e nos limites da página.
- [x] GUI-15 — Magnetismo de objetos em guias e referências da página.
- [x] GUI-16 — Magnetismo no redimensionamento por alças.
- [x] GUI-17 — Magnetismo de seleções múltiplas.
- [x] GUI-18 — Grade de magnetismo do organograma.
- [x] GUI-19 — Passo de 5 mm para blocos e de 2,5 mm para textos no organograma.
- [x] GUI-20 — Ancoragem pelo centro dos elementos no organograma.
- [x] GUI-21 — Diferença entre guia de edição, limite da página e elemento da arte.

## 07. Camadas e ordem visual

- [x] CAM-01 — Lista de camadas e tipos de objeto.
- [x] CAM-02 — Seleção múltipla na lista de camadas.
- [x] CAM-03 — Ordem das camadas e sobreposição de objetos.
- [x] CAM-04 — Reordenar camadas por arrastar e soltar.
- [x] CAM-05 — Renomear camada (Renomear / F2 / duplo clique na lista).
- [x] CAM-06 — Exibir ou ocultar camada pelo ícone de olho.
- [x] CAM-07 — Bloquear ou desbloquear camada pelo cadeado.
- [x] CAM-08 — Identificação e seleção de grupos pelos indicadores da lista.
- [x] CAM-09 — Reordenar um grupo pelo indicador de grupo.
- [x] CAM-10 — Identificação de máscaras e imagens vinculadas na lista.
- [x] CAM-11 — Selecionar o grupo de uma máscara pelo indicador.
- [x] CAM-12 — Ordem das imagens dentro de uma máscara.
- [x] CAM-13 — Camada especial do plano de fundo do documento.
- [x] CAM-14 — Restrições de movimentação, duplicação e exclusão do plano de fundo.
- [x] CAM-15 — Camada especial “Organograma”.
- [x] CAM-16 — Reordenar a camada Organograma em relação a textos, imagens e formas.
- [x] CAM-17 — Elementos à frente ou atrás do organograma.
- [x] CAM-18 — Diferença entre camadas da arte e hierarquia de subordinação.

## 08. Texto e tipografia

- [x] TXT-01 — Adicionar uma caixa de texto (Texto / Campo dinâmico).
- [x] TXT-02 — Iniciar a edição por duplo clique no texto.
- [x] TXT-03 — Iniciar a edição de uma caixa selecionada com Enter.
- [x] TXT-04 — Selecionar caracteres, palavras e trechos de texto no canvas.
- [x] TXT-05 — Encerrar a edição do texto com Esc ou mudança de seleção.
- [x] TXT-06 — Selecionar a família da fonte.
- [x] TXT-07 — Tamanho da fonte.
- [x] TXT-08 — Negrito (Ctrl+B).
- [x] TXT-09 — Itálico (Ctrl+I).
- [x] TXT-10 — Sublinhado (Ctrl+U).
- [x] TXT-11 — Formatação de um trecho e formatação da caixa de texto.
- [x] TXT-12 — Cor do texto pelo seletor de cor.
- [x] TXT-13 — Cor do texto pelo código hexadecimal.
- [x] TXT-14 — Opacidade da cor do texto.
- [x] TXT-15 — Alinhar texto à esquerda.
- [x] TXT-16 — Centralizar texto horizontalmente.
- [x] TXT-17 — Alinhar texto à direita.
- [x] TXT-18 — Justificar texto.
- [x] TXT-19 — Alinhar texto ao topo da caixa.
- [x] TXT-20 — Alinhar texto ao meio da caixa.
- [x] TXT-21 — Alinhar texto à base da caixa.
- [x] TXT-22 — Entrelinha (espaçamento entre linhas).
- [x] TXT-23 — Recuo da primeira linha do parágrafo.
- [x] TXT-24 — Quebras de linha e parágrafos.
- [x] TXT-25 — Quebra automática e espaço disponível na caixa de texto.
- [x] TXT-26 — Copiar, recortar e colar texto durante a edição.
- [x] TXT-27 — Colagem de texto externo e tratamento da formatação recebida.
- [x] TXT-28 — Desfazer e refazer durante a edição de texto.
- [x] TXT-29 — Disponibilidade de fontes e fidelidade entre editor, prévia e arquivo gerado.

## 09. Campos variáveis e trechos opcionais

- [x] VAR-01 — Placeholder de texto (variável / campo dinâmico / `{campo}`).
- [x] VAR-02 — Texto fixo e texto variável na mesma caixa.
- [x] VAR-03 — Nomes de placeholders e identificação dos campos.
- [x] VAR-04 — Reutilização de um campo em várias caixas e páginas.
- [x] VAR-05 — Formatação aplicada ao placeholder e ao conteúdo substituído.
- [x] VAR-06 — Trecho opcional delimitado por barras verticais (`|trecho|`).
- [x] VAR-07 — Trechos opcionais com uma ou mais variáveis.
- [x] VAR-08 — Campos vazios e regras de exibição do texto preenchido.
- [x] VAR-09 — Lista “Campos da tabela” no painel Documento.
- [x] VAR-10 — Reordenar campos da tabela por arrastar e soltar.
- [x] VAR-11 — Campos de texto, de link e de imagem variável na lista do documento.
- [x] VAR-12 — Relação dos campos do modelo com as colunas da tabela de dados.
- [x] VAR-13 — Placeholders visíveis no desenho sem dados preenchidos.

## 10. Formas, preenchimento e contorno

- [x] FOR-01 — Menu Elementos (antigo Formas).
- [x] FOR-02 — Quadrado / retângulo.
- [x] FOR-03 — Círculo / elipse.
- [x] FOR-04 — Linha.
- [x] FOR-05 — Desenhar uma forma clicando e arrastando no canvas.
- [x] FOR-06 — Restringir proporções com Shift durante o desenho.
- [x] FOR-07 — Restringir o ângulo da linha com Shift durante o desenho.
- [x] FOR-08 — Cancelar o desenho de uma forma com Esc.
- [x] FOR-09 — Cor de preenchimento pelo seletor.
- [x] FOR-10 — Cor de preenchimento pelo código hexadecimal.
- [x] FOR-11 — Opacidade do preenchimento.
- [x] FOR-12 — Arredondamento do canto superior esquerdo.
- [x] FOR-13 — Arredondamento do canto superior direito.
- [x] FOR-14 — Arredondamento do canto inferior esquerdo.
- [x] FOR-15 — Arredondamento do canto inferior direito.
- [x] FOR-16 — Sincronizar ou liberar os quatro raios de arredondamento.
- [x] FOR-17 — Habilitar ou desabilitar contorno.
- [x] FOR-18 — Cor do contorno pelo seletor.
- [x] FOR-19 — Cor do contorno pelo código hexadecimal.
- [x] FOR-20 — Opacidade do contorno.
- [x] FOR-21 — Espessura do contorno em milímetros.
- [x] FOR-22 — Posição do contorno: Interno.
- [x] FOR-23 — Posição do contorno: Centralizado.
- [x] FOR-24 — Posição do contorno: Externo.
- [x] FOR-25 — Cantos retos do contorno.
- [x] FOR-26 — Cantos arredondados do contorno.
- [x] FOR-27 — Diferença entre arredondar a forma e arredondar a junção do contorno.
- [x] FOR-28 — Particularidades de preenchimento e contorno em linhas e elipses.
- [x] FOR-29 — Preenchimento, transparência e contorno do plano de fundo.
- [x] FOR-30 — Contorno interno do plano de fundo e vínculo com as dimensões da página.

## 11. Imagens e assinaturas

- [x] IMG-01 — Adicionar imagem (Imagens / Foto, logo ou QR).
- [x] IMG-02 — Selecionar arquivo de imagem e formatos aceitos.
- [x] IMG-03 — Tamanho inicial e proporção da imagem importada.
- [x] IMG-04 — Orientação da imagem importada.
- [x] IMG-05 — Redimensionamento, rotação e opacidade de imagens.
- [x] IMG-06 — Restaurar original de uma imagem.
- [x] IMG-07 — Usar imagens como fundo pela ordem das camadas.
- [x] IMG-08 — Adicionar assinatura opcional.
- [x] IMG-09 — Diferença entre imagem comum e assinatura opcional.
- [x] IMG-10 — Nome da assinatura e sua identificação na tabela de dados.
- [x] IMG-11 — Restaurar original de uma assinatura.
- [x] IMG-12 — Relação entre assinatura do modelo e marcação na tabela.
- [x] IMG-13 — Assinaturas em modelos com duas páginas.
- [x] IMG-14 — Disponibilidade da ferramenta Assinatura na página comum e sua troca por Blocos no organograma.
- [x] IMG-15 — Arquivos de imagem incorporados ao modelo salvo.
- [x] IMG-16 — Qualidade da imagem original, visualização no editor e resultado final.

## 12. Máscaras de imagem

- [x] MAS-01 — Usar como máscara / Aplicar máscara.
- [x] MAS-02 — Formas compatíveis e formas indisponíveis para máscara.
- [x] MAS-03 — Aplicar uma forma a uma imagem já existente.
- [x] MAS-04 — Adicionar imagem a uma forma pelo botão “+ Imagem”.
- [x] MAS-05 — Escolher a imagem ou a forma de destino no menu da máscara.
- [x] MAS-06 — Confirmar a aplicação da máscara.
- [x] MAS-07 — Várias imagens vinculadas à mesma máscara.
- [x] MAS-08 — Escolher a imagem vinculada para editar.
- [x] MAS-09 — Editar máscara.
- [x] MAS-10 — Mover e redimensionar a imagem dentro da máscara.
- [x] MAS-11 — Visualização atenuada da imagem fora da máscara durante o enquadramento.
- [x] MAS-12 — Concluir o enquadramento (Concluir / Enter).
- [x] MAS-13 — Cancelar o enquadramento (Cancelar / Esc).
- [x] MAS-14 — Remover máscara.
- [x] MAS-15 — Mover, redimensionar, copiar e duplicar uma máscara com suas imagens.
- [x] MAS-16 — Relação entre recorte da máscara, preenchimento, contorno e arredondamento.

## 13. Imagem variável

- [x] DIN-01 — Usar imagem variável em uma forma.
- [x] DIN-02 — Nome do campo da tabela para a imagem variável.
- [x] DIN-03 — Enquadramento: Preencher e cortar.
- [x] DIN-04 — Enquadramento: Ajustar imagem inteira.
- [x] DIN-05 — Relação entre valor da célula, nome do arquivo e pasta de imagens.
- [x] DIN-06 — Forma de recorte da imagem variável.
- [x] DIN-07 — Imagem variável em cartões replicados no organograma.
- [x] DIN-08 — Disponibilidade do recurso em formas e relação com máscaras de imagens fixas.
- [x] DIN-09 — Imagens ausentes, campos vazios e representação no layout de edição.

## 14. Links clicáveis

- [x] LNK-01 — Habilitar ou desabilitar link.
- [x] LNK-02 — Nome do “Campo da tabela” para o link.
- [x] LNK-03 — Link em uma caixa de texto.
- [x] LNK-04 — Link em imagem ou assinatura.
- [x] LNK-05 — Link em forma ou máscara.
- [x] LNK-06 — Área clicável do objeto no PDF.
- [x] LNK-07 — Links variáveis por registro e em cartões do organograma.
- [x] LNK-08 — Tipos de endereço e validação dos links fornecidos.
- [x] LNK-09 — Diferença entre imagem de QR code importada e link clicável.
- [x] LNK-10 — Disponibilidade do link no PDF e nos demais formatos de saída.

## 15. Documento e páginas

- [x] DOC-01 — Largura do documento (L), em milímetros.
- [x] DOC-02 — Altura do documento (A), em milímetros.
- [x] DOC-03 — Manter ou liberar proporção do documento.
- [x] DOC-04 — Alteração da página em relação aos objetos já posicionados.
- [x] DOC-05 — Limites de tamanho da página comum.
- [x] DOC-06 — Botão “+” para adicionar página ou organograma.
- [x] DOC-07 — Adicionar página.
- [x] DOC-08 — Alternar entre Página 1 e Página 2.
- [x] DOC-09 — Ações da página pelo botão de três pontos.
- [x] DOC-10 — Limpar página.
- [x] DOC-11 — Remover página.
- [x] DOC-12 — Conteúdo próprio e dimensões compartilhadas entre páginas.
- [x] DOC-13 — Campos compartilhados entre as páginas do modelo.
- [x] DOC-14 — Exclusividade entre segunda página e organograma.
- [x] DOC-15 — Adicionar organograma.
- [x] DOC-16 — Alternar entre Página 1 e Organograma.
- [x] DOC-17 — Limpar ou remover o organograma pelas ações da página.
- [x] DOC-18 — Página 1 como modelo de cartão do organograma.

## 16. Estruturas prontas de organograma

- [x] EST-01 — Painel de escolha de estrutura ao adicionar organograma.
- [x] EST-02 — Começar organograma em branco.
- [x] EST-03 — Miniaturas, nomes e descrições das estruturas.
- [x] EST-04 — Quadro de pessoal.
- [x] EST-05 — Colunas e linhas do quadro de pessoal.
- [x] EST-06 — Comando e responsáveis.
- [x] EST-07 — Setores e equipes.
- [x] EST-08 — Turmas e grupos.
- [x] EST-09 — Equipe de atividade.
- [x] EST-10 — Usar estrutura.
- [x] EST-11 — Cancelar a escolha de estrutura.
- [x] EST-12 — Diferença entre um modelo completo pronto e uma estrutura aplicada ao cartão atual.

## 17. Blocos, conjuntos e dados do organograma

- [x] BLO-01 — Menu Blocos e conexões do quadro.
- [x] BLO-02 — Adicionar bloco.
- [x] BLO-03 — Editar bloco selecionado.
- [x] BLO-04 — Abrir a edição de um bloco por duplo clique.
- [x] BLO-05 — Nome do bloco e identificador de destino dos dados.
- [x] BLO-06 — Regra de nomes únicos e aviso de nome já utilizado.
- [x] BLO-07 — Nomes automáticos de blocos novos, copiados e duplicados.
- [x] BLO-08 — Número de colunas do conjunto.
- [x] BLO-09 — Número de linhas do conjunto.
- [x] BLO-10 — Capacidade do conjunto (quantidade de cartões / posições).
- [x] BLO-11 — Largura do cartão em milímetros.
- [x] BLO-12 — Altura proporcional ao modelo da Página 1.
- [x] BLO-13 — Espaçamento horizontal entre cartões.
- [x] BLO-14 — Espaçamento vertical entre cartões.
- [x] BLO-15 — Confirmar ou cancelar a criação e a edição do bloco.
- [x] BLO-16 — Selecionar e mover um ou vários blocos no canvas.
- [x] BLO-17 — Copiar, colar e duplicar blocos e suas conexões internas.
- [x] BLO-18 — Excluir um bloco e relação com suas conexões.
- [x] BLO-19 — Relação entre nome do bloco e coluna Bloco da tabela de dados.
- [x] BLO-20 — Ordem dos registros dentro de cada conjunto.
- [x] BLO-21 — Cartões vazios, informação válida e ocultação de posições sem dados.
- [x] BLO-22 — Capacidade insuficiente e dados sem destino correspondente.
- [x] BLO-23 — Atualizar a Página 1 e refletir o layout nos cartões.
- [x] BLO-24 — Diferença entre representação do layout e organograma preenchido.
- [x] BLO-25 — Diferença entre nome do bloco e título visível na arte.

## 18. Hierarquia e criação de conexões

- [x] HIE-01 — Árvore “Hierarquia” em Estrutura do quadro.
- [x] HIE-02 — Nomes e dimensões dos conjuntos na árvore.
- [x] HIE-03 — Seleção de um ou vários blocos pela árvore.
- [x] HIE-04 — Expandir e recolher ramos da hierarquia.
- [x] HIE-05 — Arrastar blocos na árvore para alterar o superior.
- [x] HIE-06 — Campo “Superior”.
- [x] HIE-07 — Opção “Sem superior” e remoção da subordinação.
- [x] HIE-08 — Conectar a elemento pelo menu Blocos ou pelo painel da estrutura.
- [x] HIE-09 — Escolher vários subordinados antes de iniciar uma conexão.
- [x] HIE-10 — Estado atenuado e bloqueado dos blocos durante a escolha do superior.
- [x] HIE-11 — Escolher o superior clicando no canvas.
- [x] HIE-12 — Escolher o superior clicando na árvore.
- [x] HIE-13 — Cancelar conexão pelo botão ou por Esc.
- [x] HIE-14 — Diferença entre subordinado, superior, saída e entrada de conectores.
- [x] HIE-15 — Restrições de conexão ao próprio bloco e de ciclos na hierarquia.
- [x] HIE-16 — Alterar a hierarquia sem reposicionar automaticamente os blocos.

## 19. Lados permitidos e aparência dos conectores

- [x] CON-01 — Entrada: permitir pelo lado de cima.
- [x] CON-02 — Entrada: permitir pelo lado de baixo.
- [x] CON-03 — Entrada: permitir pelo lado esquerdo.
- [x] CON-04 — Entrada: permitir pelo lado direito.
- [x] CON-05 — Saída: permitir pelo lado de cima.
- [x] CON-06 — Saída: permitir pelo lado de baixo.
- [x] CON-07 — Saída: permitir pelo lado esquerdo.
- [x] CON-08 — Saída: permitir pelo lado direito.
- [x] CON-09 — Entrada por baixo e saída por cima como padrão.
- [x] CON-10 — Permitir vários lados e manter ao menos um lado permitido.
- [x] CON-11 — Estados diferentes dos lados permitidos em seleção múltipla.
- [x] CON-12 — Selecionar conector por clique.
- [x] CON-13 — Selecionar conectores por área de seleção.
- [x] CON-14 — Selecionar e editar vários conectores simultaneamente.
- [x] CON-15 — Excluir conectores selecionados.
- [x] CON-16 — Aparência de novas conexões e de conexões selecionadas.
- [x] CON-17 — Cor do conector pelo seletor.
- [x] CON-18 — Cor do conector pelo código hexadecimal.
- [x] CON-19 — Espessura do conector em milímetros.
- [x] CON-20 — Transparência do conector em porcentagem.
- [x] CON-21 — Raio de curva em milímetros.
- [x] CON-22 — Quinas retas com raio zero.
- [x] CON-23 — Limite do raio conforme o espaço disponível.
- [x] CON-24 — Roteamento automático e ajuste ao mover os blocos.
- [x] CON-25 — Conectores em relação ao contorno do cartão ou do conjunto.
- [x] CON-26 — Cruzamentos, desvios e trechos compartilhados de conectores.
- [x] CON-27 — Ocultação de trechos dos conectores sob caixas de texto.
- [x] CON-28 — Aviso de falta de espaço para rotear conexões.

## 20. Contornos de cartões e conjuntos

- [x] BOR-01 — Habilitar ou desabilitar contorno no bloco selecionado.
- [x] BOR-02 — Aplicar em: Em cada cartão.
- [x] BOR-03 — Aplicar em: Ao redor do conjunto.
- [x] BOR-04 — Aplicar em: Cartões e conjunto.
- [x] BOR-05 — Configurações independentes para cartão, conjunto e conectores.
- [x] BOR-06 — Preservação das configurações ao alternar o destino do contorno.
- [x] BOR-07 — Cor do contorno pelo seletor.
- [x] BOR-08 — Cor do contorno pelo código hexadecimal.
- [x] BOR-09 — Opacidade do contorno.
- [x] BOR-10 — Espessura do contorno em milímetros.
- [x] BOR-11 — Posição do contorno: Interno.
- [x] BOR-12 — Posição do contorno: Centralizado.
- [x] BOR-13 — Posição do contorno: Externo.
- [x] BOR-14 — Cantos retos do contorno.
- [x] BOR-15 — Cantos arredondados do contorno.
- [x] BOR-16 — Raio do canto superior esquerdo.
- [x] BOR-17 — Raio do canto superior direito.
- [x] BOR-18 — Raio do canto inferior esquerdo.
- [x] BOR-19 — Raio do canto inferior direito.
- [x] BOR-20 — Sincronizar ou liberar os quatro raios.
- [x] BOR-21 — Recorte do conteúdo do cartão com cantos arredondados.
- [x] BOR-22 — Folga do conjunto em milímetros.
- [x] BOR-23 — Limite do arredondamento do conjunto em relação à folga dos cartões.
- [x] BOR-24 — Edição de contornos em vários blocos selecionados.
- [x] BOR-25 — Indicações “Contornos diferentes” e “Posições diferentes”.

## 21. Arte adicional e dimensões do organograma

- [x] QUA-01 — Adicionar texto livre ao quadro.
- [x] QUA-02 — Adicionar imagem livre ao quadro.
- [x] QUA-03 — Adicionar forma livre ao quadro.
- [x] QUA-04 — Posição em Camadas do quadro: À frente do organograma.
- [x] QUA-05 — Posição em Camadas do quadro: Atrás do organograma.
- [x] QUA-06 — Imagem de fundo do quadro e relação com a camada Organograma.
- [x] QUA-07 — Área de montagem expansível do organograma.
- [x] QUA-08 — Saída do quadro: Margem de saída.
- [x] QUA-09 — Tamanho sugerido do quadro em milímetros.
- [x] QUA-10 — Dimensões calculadas a partir de cartões, contornos e arte adicional.
- [x] QUA-11 — Diferença entre dimensão do cartão, do quadro e da folha de impressão.
- [x] QUA-12 — Relação do quadro com a prévia do cartão e a prévia da composição completa.

## 22. Histórico, salvamento e proteção

- [x] SAL-01 — Desfazer (Ctrl+Z).
- [x] SAL-02 — Refazer (Ctrl+Y / Ctrl+Shift+Z).
- [x] SAL-03 — Disponibilidade dos botões conforme o histórico.
- [x] SAL-04 — Histórico de edição entre páginas e organograma.
- [x] SAL-05 — Limites do histórico e diferença entre desfazer texto e desfazer objetos.
- [x] SAL-06 — Salvar modelo (Ctrl+S).
- [x] SAL-07 — Nome solicitado no primeiro salvamento.
- [x] SAL-08 — Modelo salvo em arquivo `.fornax` e recursos incorporados.
- [x] SAL-09 — Salvamento de cópia quando a edição exigir um novo modelo.
- [x] SAL-10 — Arquivo alterado fora do editor: recarregar ou salvar nova cópia.
- [x] SAL-11 — Encerrar edição após salvar.
- [x] SAL-12 — Continuar editando após salvar.
- [x] SAL-13 — Fechar o editor com alterações não salvas.
- [x] SAL-14 — Salvar, descartar alterações ou cancelar o fechamento.
- [x] SAL-15 — Cópia de recuperação automática e diferença em relação a salvar o modelo.
- [x] SAL-16 — Menu de proteção ao lado de Salvar modelo.
- [x] SAL-17 — Sem proteção.
- [x] SAL-18 — Proteger assinaturas.
- [x] SAL-19 — Proteger modelo inteiro.
- [x] SAL-20 — Definir e confirmar senha.
- [x] SAL-21 — Alterar senha: senha atual, nova senha e confirmação.
- [x] SAL-22 — Remover ou alterar o nível de proteção.
- [x] SAL-23 — Aviso ao salvar assinaturas sem proteção.
- [x] SAL-24 — Autorização e disponibilidade da edição em modelos protegidos.

## 23. Atalhos registrados que precisam de revisão de acesso

Estes comandos existem no código, mas dependem do editor de texto auxiliar,
que permanece oculto na interface atual. Verificar o acesso pela edição no
canvas antes de apresentá-los como atalhos disponíveis na ajuda. A sintaxe
manual correspondente já está listada em VAR-01 e VAR-06.

- [ ] REV-01 — Transformar seleção em placeholder (Ctrl+1).
- [ ] REV-02 — Transformar seleção em trecho opcional (Ctrl+2).

## 24. Tabelas gráficas e células

- [x] TBL-01 — Tabela gráfica: inserir e distinguir da planilha de dados.
- [x] TBL-02 — Selecionar células e editar texto na tabela.
- [x] TBL-03 — Adicionar ou remover linhas e colunas da tabela.
- [x] TBL-04 — Mesclar e separar células da tabela.
- [x] TBL-05 — Medidas da tabela, linhas e colunas em milímetros.
- [x] TBL-06 — Texto, alinhamento, quebra e espaço interno das células.
- [x] TBL-07 — Preenchimento e transparência das células.
- [x] TBL-08 — Contornos externos, internos e compartilhados da tabela.
- [x] TBL-09 — Campos variáveis e placeholders nas células da tabela.
- [x] TBL-10 — Copiar e colar células, intervalos ou texto na tabela.
- [x] TBL-11 — Atalhos e desfazer/refazer por contexto na tabela.
- [x] TBL-12 — Tabela inteira: camadas, cópias, grupos e organograma.
- [x] TBL-13 — Texto excedente (overflow) e limites das tabelas.
- [x] TBL-14 — Exemplo: boletim escolar com tabela e dados variáveis.

## Referências usadas no mapeamento

Estas referências servem à revisão interna do inventário; não são artigos da ajuda.

- [Interface e composição dos painéis](../features/editor/frontend.py).
- [Controles e conexões de ações](../features/editor/controls.py).
- [Operações, atalhos, camadas, histórico e salvamento](../features/editor/editor_window.py).
- [Propriedades e comandos de texto](../features/editor/properties.py).
- [Edição direta de texto no canvas](../features/editor/canvas_edit.py).
- [Objetos, alças, guias e magnetismo](../features/editor/canvas_items.py).
- [Desenho de formas por arraste](../features/editor/draw_shapes.py).
- [Réguas e criação de guias](../features/editor/rulers.py).
- [Documento e operações de páginas](../features/editor/document_session.py).
- [Estrutura, blocos e ferramentas de organograma](../features/editor/organogram_editor.py).
- [Galeria de pontos de partida](../features/editor/starter_dialog.py).
- [Catálogo atual de modelos e estruturas](../assets/templates/catalog.json).
- [Campos numéricos com expressões](../core/custom_widgets.py).

## Critério para a próxima etapa

Antes de redigir um artigo, confirmar o comportamento e os limites do recurso
na interface atual. Os tópicos sobre condições, validações, qualidade, dados
vazios e formatos de saída são itens a explicar e verificar, não garantias
antecipadas de comportamento. Manter os identificadores ao revisar nomes ou
reunir assuntos em um único artigo.
