# Exemplos para iniciar modelos e organogramas

## Biblioteca no primeiro uso

Uma biblioteca nova recebe somente **Cartão de aniversário de pessoal**, com
148 × 105 mm (A6 horizontal) e os campos **nome**, **data** e **cargo**. Sua fonte
é o mesmo `assets/templates/models/birthday-personnel.fornax` usado na galeria,
com as imagens incorporadas. O primeiro uso salva uma cópia pública `.fornax`
na biblioteca do usuário, sem copiar outros modelos de desenvolvimento.
Os cinco exemplos da galeria continuam recursos internos. Além desse primeiro
cartão, os demais só entram na biblioteca quando o usuário escolhe um deles e
salva sua própria cópia.

A inicialização é registrada no arquivo `.library-initialized`, na pasta de dados
do aplicativo. Bibliotecas existentes são preservadas. Excluir o último modelo
não recria o exemplo: a prévia exibe **Crie um modelo para começar**, com acesso
a **Criar modelo**. Esse aviso não é um documento; edição, configuração de saída
e geração ficam desabilitadas até criar ou importar um modelo.

Flatpak conserva a pasta de dados isolada pelo sandbox. AppImage e execução nativa
conservam a pasta de dados convencional do aplicativo, podendo compartilhar
os modelos desse mesmo usuário. A compilação inclui apenas recursos selecionados
em `assets/templates`, e não copia a biblioteca pessoal de desenvolvimento.

## Formatos do documento

Em **Documento → Dimensões**, o menu de formatos inclui **A1 a A7**, **Carta**,
**Cartão de visita** (50 × 90 mm) e **Quadrado** (100 × 100 mm). Os três botões SVG
ao lado indicam vertical, horizontal e quadrado (1:1). Apenas um fica ativo.
1:1 fica habilitado e selecionado somente em páginas quadradas, enquanto os
outros dois ficam desabilitados. Em páginas retangulares, 1:1 fica desabilitado. Medidas digitadas manualmente
mudam o menu para **Personalizado**. Alterar formato ou orientação muda apenas
a prancheta e os elementos vinculados a ela; não reposiciona nem escala a arte.
As operações são salvas no modelo e participam do histórico. No organograma,
o quadro acompanha seu conteúdo, e estes controles ficam desabilitados.

A cena lógica passou a aceitar até **10 metros por lado**, independentemente do
limite de exportação. O menu **Configurações → Limite de exportação** oferece
limites de 40, 80, 150, 300 e 600 MP por imagem, com exportação fixa em 300 DPI. O padrão
é 150 MP / 300 DPI; A1 a 300 DPI requer 80 MP ou um limite maior. Os detalhes,
limites e validação estão em [DESEMPENHO_E_QUALIDADE.md](DESEMPENHO_E_QUALIDADE.md).


## Galeria de pontos de partida

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

Em **Arquivo → Configurar saída**, escolha **Itens por folha** ou **Ladrilhos**.
O botão verde indica o modo ativo; mudar as medidas não alterna o modo automaticamente.
Itens por folha organiza itens completos; Ladrilhos divide o desenho para montagem.
O ladrilhamento funciona
tanto com organogramas quanto com páginas comuns, inclusive modelos de duas páginas.
Escolha o papel (ou medidas personalizadas), a orientação e, se desejar,
margem de sangria e marcas de corte. Ajuste a largura ou altura
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

Os formatos disponíveis são **PNG**, **JPEG**, **PDF** e **PDF Agrupado**.
PDF Agrupado reúne as folhas; PDF cria arquivos separados e
gera `organograma_A1.pdf`, `organograma_B1.pdf`, `organograma_A2.pdf` etc.
PNG e JPEG usam os mesmos sufixos. A saída permanece em **300 DPI**, com JPEG
a 95% de qualidade. As letras identificam colunas e os números, linhas; depois de Z vêm
AA, AB e assim por diante. A ordem de geração é da esquerda para a direita,
descendo uma linha por vez. Os PDFs também identificam suas páginas como A1,
B1, A2 etc., inclusive quando não há marcas impressas.

O **Mapa das folhas** mostra as divisões e permite selecionar uma parte.
Os limites das folhas aparecem com linhas tracejadas finas. Arraste o desenho
para reposicioná-lo: as folhas ficam paradas durante o arraste e, ao soltar,
o programa recalcula a distribuição. A quantidade de páginas acompanha a mudança.
Em organogramas, o tamanho planejado
é preservado quando algumas posições ficam sem dados.
**Folha selecionada** mostra o conteúdo exato do arquivo daquela posição.
**Margem de sangria** reserva 5 mm em cada lado, indicados na prévia por uma faixa
vermelha com 30% de opacidade, que não aparece na saída. Duas folhas vizinhas
têm 5 mm de margem cada uma na junção, totalizando 10 mm de papel a recortar;
o conteúdo continua na área útil seguinte, sem sobreposição adicional da arte.
**Marcas de corte** reservam outros 5 mm por lado: 2 mm de distância ao conteúdo
e traços de 3 mm. As opções são independentes; juntas reservam 10 mm por lado.
Imprima os arquivos em **tamanho real / 100%**, preservando
as dimensões físicas. Cada desenho aceita até 1.000 folhas, e a geração pode ser cancelada.
Para páginas comuns, os arquivos separados mantêm o padrão de nomenclatura e
acrescentam a posição, por exemplo `Ana_A1.pdf`; modelos com duas páginas também
usam `_pag1` ou `_pag2`. O PDF agrupado usa o nome da pasta da Forja, com identificadores
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
em `models/birthday-personnel.fornax`. Sua tipografia usa **Inter 18pt**, com
as referências antigas de fonte removidas. O segundo exemplo, **Certificado de estágio**, contém
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


## Revisão dos exemplos em 12/10/2026

Os cinco arquivos da galeria de **Novo modelo** foram substituídos pelas versões
revisadas no editor, preservando integralmente o documento e os assets incorporados:

| Exemplo da galeria | Modelo de origem revisado |
|---|---|
| Cartão de aniversário de pessoal | novo cartão de parabenizacao |
| Certificado de estágio | Modelo - Certificado de Estágio |
| Prisma de identificação | Modelo - Prima de identificação |
| Convite institucional | 006 - Convite |
| Organograma institucional | Teste organograma |

A atualização conserva os nomes, a ordem e as descrições do catálogo. Cada arquivo
incorporado foi inicialmente conferido por SHA-256 contra sua origem. A limpeza
posterior das referências residuais de fonte altera os bytes dos pacotes, mantendo
os bytes das imagens. A galeria carrega cópias
editáveis, preservando os modelos originais do usuário. As bibliotecas já usadas
não recebem substituições automáticas de documentos; mudanças do exemplo inicial
se aplicam somente ao primeiro uso de uma biblioteca vazia.

O cartão de aniversário revisado também substitui o exemplo inicial da biblioteca.
A inicialização reutiliza o arquivo da galeria e seu provedor de assets, mantendo
a mesma aparência. O antigo `initial-model.json` foi retirado para evitar uma
segunda fonte divergente. Excluir o cartão não o recria na próxima abertura.


### Conferência da Inter 18pt após a revisão das fontes

A primeira conferência procurou nomes nas propriedades e no HTML, mas isso
confundiu referências antigas com fontes efetivamente usadas. A nova conferência
carregou os textos no `QTextDocument` utilizado pelo aplicativo e examinou a
formatação de cada trecho com caracteres, incluindo os textos do quadro.

| Modelo de origem revisado | Situação encontrada |
|---|---|
| novo cartão de parabenizacao | Caracteres somente em Inter 18pt; referências residuais à Amiri removidas de 9 caixas na cópia incorporada |
| Modelo - Certificado de Estágio | Caracteres somente em Inter 18pt; referências residuais à Amiri removidas de 11 caixas na cópia incorporada |
| Modelo - Prima de identificação | Somente Inter 18pt; versão atualizada na galeria |
| 006 - Convite | Caracteres somente em Inter 18pt; referências residuais a EB Garamond e Cormorant Garamond removidas de 6 caixas na cópia incorporada |
| Teste organograma | Revisão final do autor incorporada; título “Fornax Corporation” e textos dos cartões usam somente Inter 18pt |

Cartão, certificado e convite foram incorporados novamente a partir das versões
revisadas, retirando somente as famílias residuais das propriedades e dos estilos
HTML. No convite também foi retirado o histórico `origin_info` da importação,
que ainda listava as antigas fontes. A cópia chamada **Modelo - Cartão de
Aniversário de Pessoal** foi examinada separadamente: todos os caracteres usam
Inter 18pt, e as referências à Amiri também são residuais.

Os originais da biblioteca pessoal não foram modificados. O cartão inicial de
uma biblioteca nova reutiliza a versão limpa da galeria. Após a correção do título
pelo autor, o organograma também foi atualizado com a nova cópia de **Teste
organograma**, conferida por SHA-256 contra a origem. A prévia completa foi
comparada com a origem revisada, com pixels idênticos. A conferência dos caracteres
dos cinco exemplos confirma somente **Inter 18pt**, incorporada ao aplicativo;
as referências às três famílias antigas não permanecem nos arquivos da galeria.

A validação comparou as cópias limpas com suas origens revisadas: imagens
incorporadas, conteúdo, medidas, posicionamento do texto e links foram preservados.
As prévias a 1.600 pixels foram idênticas, tanto com placeholders quanto com dados.
Na saída a 300 DPI com os dados de exemplo, os três modelos também tiveram pixels
idênticos. Na saída do certificado com placeholders literais, houve pequena
variação de suavização dos glifos, sem alteração das métricas ou do posicionamento;
essa comparação não foi classificada como igualdade exata de pixels.
