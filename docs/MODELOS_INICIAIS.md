# Exemplos para iniciar modelos e organogramas

**Arquivo → Novo modelo** abre um painel com miniaturas. Escolha um exemplo e
clique em **Usar modelo**, ou escolha **Começar em branco**. O exemplo vira uma
cópia editável; o nome e o destino são escolhidos no primeiro salvamento.
Cancelar o painel mantém a janela atual.

Cada miniatura mostra, abaixo do nome, **largura × altura em milímetros**.
O formato da folha aparece entre parênteses quando as medidas correspondem
exatamente a um tamanho padrão, por exemplo **148 × 105 mm (A6)** ou
**210 × 297 mm (A4)**. Tamanhos personalizados mostram somente as medidas.
As dimensões dos organogramas incluem a margem de saída e acompanham os
ajustes de linhas e colunas da grade.

No editor, **+ → Adicionar organograma** oferece estruturas prontas. Os cartões
usam a Página 1 atual. Na opção **Quadro em grade**, escolha colunas e linhas
antes de entrar no editor. Depois, os blocos e conectores podem ser alterados
normalmente, inclusive seus nomes para a coluna **Bloco** da tabela.

Os exemplos são locais e acompanham a instalação. O catálogo inicial contém
cinco modelos (cartão de aniversário de pessoal, certificado de estágio, prisma de identificação, convite institucional
e identificação de turma) e cinco estruturas (grade, responsável e equipe,
hierarquia em três níveis, organograma escolar e setores e equipes). Os espaços de foto são formas
com imagem variável ligada ao campo **Foto**; selecione a pasta de imagens ao
preencher a tabela. Os textos fixos, como “INSTITUIÇÃO”, podem ser editados.

O **Organograma escolar** oferece 12 cartões em três níveis: Direção;
Coordenação pedagógica, Secretaria e Coordenação administrativa; e equipes de
Professores (quatro cartões), Atendimento (dois) e Apoio escolar (dois).
Cada equipe se conecta ao seu responsável. A estrutura usa o cartão da Página 1;
na tabela, preencha a coluna **Bloco** com o nome do grupo correspondente.
Os nomes, a quantidade de cartões e as conexões podem ser ajustados no editor.

Nas propriedades do organograma, **Editar contorno** alterna entre cartão,
conjunto ou ambos. Cartão e conjunto conservam cor, espessura, transparência,
posição e cantos próprios; alternar a opção não desabilita o outro contorno.
As conexões têm sua própria cor na seção **Conectores**. Arredondar um cartão
recorta seu conteúdo nos cantos. O raio do conjunto respeita a folga até os
cartões, e seu contorno não cobre o conteúdo nem os contornos deles.

## Substituir pelos seus próprios exemplos

1. Desenhe e teste um modelo no FORNAX e salve uma cópia `.fornax` sem proteção.
2. Copie o arquivo para `assets/templates/models/` no projeto.
3. Em `assets/templates/catalog.json`, adicione ou substitua uma entrada de
   `kind: "model"`, com `id` único, `title`, `description` e `file` relativo à
   pasta `assets/templates`. O painel calcula a miniatura a partir do arquivo.
4. Execute o projeto novamente. Para distribuir os exemplos, recompile o pacote.

Exemplo de entrada:

```json
{
  "id": "meu-cracha",
  "kind": "model",
  "title": "Meu crachá",
  "description": "Uma descrição curta do ponto de partida.",
  "file": "models/meu-cracha.fornax"
}
```

Para uma estrutura desenhada no editor, salve um modelo com organograma em
`assets/templates/organograms/` e use `kind: "organogram"`. A escolha reaproveita
os blocos, conexões, suas propriedades e os espaçamentos. A altura dos cartões e
as posições verticais acompanham a proporção da Página 1 atual. Os textos e
imagens adicionais do quadro podem ser inseridos depois no editor; esse tipo de
exemplo contém a estrutura, enquanto os cartões vêm do modelo do usuário.

As estruturas iniciais usam pequenos arquivos JSON com `preset_version: 1`,
uma lista `groups` (nome, linhas, colunas, coluna de posicionamento e nível) e
uma lista `connections` (nomes de superior e subordinado). O arquivo da grade
tem `configurable_grid: true` na entrada do catálogo para habilitar os controles.

Os arquivos em `assets/templates` fazem parte da seleção de recursos usada nas
compilações. O primeiro exemplo é o **Cartão de aniversário de pessoal**, criado
no editor, com os campos **nome**, **data** e **cargo** e suas imagens incorporadas
em `models/birthday-personnel.fornax`. Sua tipografia usa a fonte **Amiri** do
modelo original. O segundo exemplo, **Certificado de estágio**, contém
uma folha A4 horizontal (**297 × 210 mm**) com os campos **artigo**, **nome**,
**area**, **data_inicial**, **data_final**, **carga_horaria** e **data**, e imagens
incorporadas em `models/internship-certificate.fornax`.
O terceiro exemplo, **Prisma de identificação**, usa uma folha A4 horizontal
(**297 × 210 mm**) com os campos **nome**, **tratamento** e **funcao**, e imagens
incorporadas em `models/identification-prism.fornax`.
O quarto exemplo, **Convite institucional**, vem do modelo **006 - Convite**,
em A5 horizontal (**210 × 148 mm**), com os campos **tratamento**, **convidado**,
**evento**, **nome_diretor**, **Link Whats**, **Link Mapa** e **Link E-mail**,
e imagens incorporadas em `models/formal-invitation.fornax`.
Os demais exemplos iniciais usam textos e formas vetoriais criados para o projeto.
