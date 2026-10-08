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
usam a Página 1 atual. Na opção **Quadro de pessoal**, escolha colunas e linhas
antes de entrar no editor. Depois, os blocos e conectores podem ser alterados
normalmente, inclusive seus nomes para a coluna **Bloco** da tabela.

Na visualização **Organograma**, a tabela sem dados mostra o layout completo,
com todos os cartões, placeholders, contornos e conectores. Ao preencher a
tabela, a prévia passa a mostrar os registros nos blocos correspondentes e oculta
as posições sem informações válidas. A geração dos arquivos usa os registros
preenchidos; a prévia do layout não cria dados na tabela.

Na lista de camadas do editor do quadro, **Organograma** representa os cartões
e conectores juntos. Arraste textos, imagens e formas para cima dessa camada
para exibi-los à frente, ou para baixo para colocá-los atrás. Também é possível
arrastar a própria camada **Organograma** entre esses elementos. Imagens ligadas
a uma máscara acompanham sua forma, mantendo o conjunto no mesmo plano.
A opção de posição nas propriedades continua disponível e acompanha essa ordem.

Em **Arquivo → Configurações de geração… → Impressão**, habilite
**Impressão em ladrilhos** para montar o desenho com várias folhas. Essa opção
e **Múltiplos itens por página** são alternativas. O ladrilhamento funciona
tanto com organogramas quanto com páginas comuns, inclusive modelos de duas páginas.
Escolha o papel (ou medidas personalizadas), a orientação e, se desejar,
margem na folha, marcas de corte e sobreposição. Ajuste a largura ou altura
final do desenho; a outra medida acompanha a proporção original.
**Restaurar tamanho original** recupera as dimensões do modelo, mantendo
papel, posição, margens e demais escolhas da impressão.
A margem da folha não altera a margem de saída definida no editor.
As opções ficam guardadas no próprio modelo. **Gerar material** usa diretamente
essas escolhas e o formato selecionado na janela principal, sem abrir outro painel.
Na orientação **Automática — menos folhas**, o programa compara retrato e
paisagem e escolhe a opção com menor quantidade de folhas; em caso de empate,
prefere uma grade com menos divisões e depois retrato. **Otimizar disposição**
ativa essa comparação e alinha o desenho ao início da grade.

**PDF — arquivo único** reúne todas as folhas. **PDF — arquivos separados**
gera `organograma_A1.pdf`, `organograma_B1.pdf`, `organograma_A2.pdf` etc.
**PNG — arquivos separados** usa os mesmos sufixos e grava a resolução física
escolhida. As letras identificam colunas e os números, linhas; depois de Z vêm
AA, AB e assim por diante. A ordem de geração é da esquerda para a direita,
descendo uma linha por vez. Os PDFs também identificam suas páginas como A1,
B1, A2 etc., inclusive quando não há marcas impressas.

O **Mapa das folhas** mostra as divisões e permite selecionar uma parte.
Os limites das folhas aparecem com linhas tracejadas finas. Arraste o desenho
para reposicioná-lo, ou informe as posições horizontal e vertical em milímetros;
a quantidade de páginas acompanha a mudança. Em organogramas, o tamanho planejado
é preservado quando algumas posições ficam sem dados.
**Folha selecionada** mostra o conteúdo exato do arquivo daquela posição.
Sem sobreposição, as partes se encostam. Com sobreposição, há conteúdo repetido
à direita/abaixo para facilitar a montagem; as marcas indicam onde recortar
para encaixar as partes sem repetir o desenho. Elas precisam de pelo menos
5 mm de margem na folha; a janela informa quando falta espaço, sem modificar
a configuração. Imprima os arquivos em **tamanho real / 100%**, preservando
as dimensões físicas. Cada desenho aceita até 1.000 folhas, e a geração pode ser cancelada.
Para páginas comuns, os arquivos separados mantêm o padrão de nomenclatura e
acrescentam a posição, por exemplo `Ana_A1.pdf`; modelos com duas páginas também
usam `_pag1` ou `_pag2`. O PDF único do lote é `ladrilhos.pdf`, com identificadores
que combinam o nome do registro e a posição da folha. As predefinições rápidas
da janela principal permitem alternar entre **Ladrilhos** e as opções de imposição
sem apagar suas configurações.

Os exemplos são locais e acompanham a instalação. O catálogo inicial contém
cinco modelos (cartão de aniversário de pessoal, certificado de estágio, prisma de identificação,
convite institucional e organograma institucional) e cinco estruturas por finalidade:
Quadro de pessoal, Comando e responsáveis, Setores e equipes, Turmas e grupos e Equipe de atividade. Os espaços de foto são formas
com imagem variável ligada ao campo **Foto**; selecione a pasta de imagens ao
preencher a tabela. Os textos fixos, como “INSTITUIÇÃO”, podem ser editados.

As estruturas de **Adicionar organograma** substituem os cinco exemplos anteriores,
sem modificar modelos já salvos ou o modelo completo **Organograma institucional**
de **Novo modelo**. Todas usam o cartão atual da Página 1 e um título genérico
editável como caixa de texto comum. Os contornos dos cartões começam em **1 mm**,
com cantos de **5 mm**; conjuntos com várias posições também têm contorno externo
com folga. Os conectores começam em **1,25 mm**, com raio de **15 mm**,
inspirados no acabamento do modelo institucional. Cores e demais propriedades
continuam editáveis, separadamente para cartões, conjuntos e conectores.

| Estrutura | Composição inicial | Finalidade |
|---|---|---|
| Quadro de pessoal | Grade de 5 × 4, configurável antes de abrir; sem conexões | Identificar integrantes de unidade, turma ou equipe |
| Comando e responsáveis | Principal ao centro, substituto à direita e três responsáveis à esquerda, acima e abaixo; 5 cartões | Apresentar comando ou chefias |
| Setores e equipes | Geral, três responsáveis e três equipes de seis; 22 cartões | Apresentar setores e seus integrantes |
| Turmas e grupos | Três responsáveis e três grupos de seis; 21 cartões; sem conexões | Reunir pessoas por turma ou grupo, sem impor subordinação |
| Equipe de atividade | Coordenação e três equipes de seis; 19 cartões | Organizar recepção, logística e execução de atividades temporárias |

Os nomes, capacidades, posições e vínculos são pontos de partida editáveis,
sem representar uma estrutura oficial de qualquer instituição. Os espaçamentos
acompanham as proporções do cartão atual, incluindo os contornos dos conjuntos.
**Comando e responsáveis** usa a composição revisada no modelo
**comando e responsaveis alterado**, preservando os lados de entrada e saída
dos cartões e o acabamento. O título conserva a folga lateral do modelo revisado.

Na tabela, clique em uma célula da coluna **Bloco** para escolher o grupo
correspondente no menu. Células vazias mostram **Selecione um bloco**, sem
adicionar esse texto aos dados. O campo acompanha a altura da linha da tabela.
**Sem bloco** limpa o destino. Também é possível colar
os nomes e os dados de uma planilha; nomes desconhecidos continuam visíveis
para correção. Esse menu aparece somente na coluna de destino do organograma.
Os nomes, a quantidade de cartões e as conexões podem ser ajustados no editor.

Nas propriedades do organograma, **Aplicar em** escolhe quais contornos exibir:
somente cartão, somente conjunto ou ambos. Cartão e conjunto conservam cor,
espessura, transparência, posição e cantos próprios mesmo quando ocultos.
Se o contorno estiver desabilitado, a opção prepara sua aplicação para quando
for habilitado; em uma seleção múltipla, cada bloco conserva esse estado.
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

As estruturas iniciais usam pequenos arquivos JSON com `preset_version: 2`,
uma lista `groups` (nome, linhas, colunas, coluna de posicionamento e nível),
`connections` (nomes de superior e subordinado), `border`, `connector_style`
e `title`. Também definem espaçamento entre colunas/níveis e margem de saída.
O Quadro de pessoal tem `configurable_grid: true` na entrada do catálogo para
habilitar os controles. Arquivos externos com `preset_version: 1` continuam
compatíveis; essa versão não adiciona automaticamente título ou decoração.

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

O último modelo, **Organograma institucional**, vem do **Teste organograma**
aprovado pelo desenvolvedor. Inclui o cartão de **90 × 130 mm**, com os campos
**nome**, **funcao**, **setor** e **Imagem**, e o quadro completo da Fornax Corporation:
um diretor, três gerentes e três equipes de seis pessoas, totalizando **22 cartões**.
O título, a imagem do quadro, os contornos e as conexões são preservados, com
as imagens incorporadas em `models/corporate-organogram.fornax`. Ele aparece na
última posição de **Novo modelo**, substituindo **Identificação de turma**, e abre
como uma cópia editável sem nome.
