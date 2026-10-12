# Limite de exportação

## Uso

Abra **Configurações → Limite de exportação…**. As preferências são locais
à instalação e persistem entre sessões. Não alteram os modelos existentes,
as coordenadas do editor ou a resolução dos assets originais.

O painel possui uma única seleção **Limite por imagem**: **40, 80, 150 (padrão),
300 ou 600 MP**. Aplicar salva a escolha; Cancelar preserva a preferência anterior.
Não há seleção de perfil ou Personalizado. Preferências antigas continuam sendo
lidas para preservar o limite escolhido.

A explicação informa que o limite controla o consumo de memória. Com um modelo
aberto, o painel mostra somente a estimativa em MP do documento inteiro. Essa
estimativa não aloca a imagem e não consulta a RAM. Os detalhes estão na ajuda,
pesquisáveis por “limite de exportação”, “limite por imagem”, “megapixels” e “RAM”.

A exportação permanece fixa em **300 DPI**. O limite vale para cada imagem/folha,
não para o arquivo comprimido em MB ou o total do lote. Itens por folha e Ladrilhos
validam cada folha raster; a estimativa do documento inteiro pode ultrapassá-la.
Uma saída acima do limite é recusada antes da alocação, com orientação para
verificar memória e aumentar o limite ou dividir em ladrilhos. Um modelo grande
permanece aberto e editável. Não há redução automática de resolução ou dimensões.
Preferências antigas de DPI são ignoradas; Aplicar remove a preferência antiga.

## Documento, preview e saída são independentes

- Páginas comuns aceitam até **10.000 mm por lado**. A cena lógica mantém
  **300 unidades por polegada**, incluindo texto, tabelas, guias e coordenadas.
- `canvas_size` descreve a geometria lógica, não uma imagem que precisa ser
  alocada. A validação lógica está separada da validação de buffers.
- A prévia de documento grande usa até 1600 pixels no maior lado; a prévia de
  folhas usa até 1800. São desenhadas diretamente em buffers pequenos.
- A saída raster usa 300 DPI, preservando as dimensões nativas dos modelos
  existentes. Alterar o limite não modifica a quantidade de pixels de uma saída
  que caiba nos limites; modifica apenas o limite permitido e o orçamento de memória.
- A base estática é dispensada acima de 32 MP. O cache opcional de fundo não
  aloca o canvas lógico de documentos grandes. Os assets originais continuam
  disponíveis para a pintura final.
- Frente/verso, imposição, links, máscaras e tabelas usam a mesma geometria
  lógica; a escala de saída não é persistida nos objetos.

## Proteções e limites

O máximo configurável é 600 MP e **32.760 pixels por lado** para imagens de
saída. O orçamento de buffers é de 768, 1024, 2048, 4096 ou 8192 MiB conforme o limite
de 40, 80, 150, 300 ou 600 MP. O planejador considera bases compartilhadas, folhas,
cartões e composição branca do JPEG antes de definir a concorrência.

Em Linux e Windows, quando a consulta do sistema está disponível, o orçamento
é também limitado a 70% da memória disponível naquele momento. Isso não é uma
reserva de RAM nem impede outros aplicativos de consumirem memória durante a
geração. Falhas de alocação são tratadas. As proteções de imagens importadas,
assets, arquivos protegidos e quantidade de cartões/folhas são mantidas.

Uma página PDF isolada aceita até **5 metros por lado**. Para uma página comum
maior, use Ladrilhos ou um formato raster que caiba nos limites. Organogramas
mantêm seus limites de composição e o teto de 2500 posições já existente.

## Medidas físicas e fidelidade

Milímetros continuam sendo a referência física. PNG e JPEG recebem metadados
de densidade calculados a partir dos pixels efetivos e das medidas solicitadas,
após a pintura, mantendo os dispositivos lógicos de texto inalterados.

PNG armazena densidade inteira em pixels por metro; o JPEG gravado pelo Qt usa
densidade inteira em pixels por polegada. Há pequenas tolerâncias de
arredondamento. Leitores externos podem ignorar ou remover esses metadados;
imprima em tamanho real/100%, sem ajustar automaticamente à folha.

PDFs comuns individuais e agrupados continuam raster. A correção da página
PDF ajusta o MediaBox e a escala da arte para remover o arredondamento do Qt
para pontos inteiros. Links, rótulos e marcadores são preservados. O PDF do
organograma e dos ladrilhos mantém sua pintura direta existente: o limite de
MP é uma proteção de buffers raster, não da área de uma página vetorial sem
bitmap completo. A saída raster destes caminhos também fica em 300 DPI.

Um documento de **1 × 1 m** exige aproximadamente **139,5 MP** e pode caber no
limite de 150 MP, conforme a memória disponível. Um documento de
**3 × 3 m** exige aproximadamente **1.255,5 MP**, excedendo inclusive o limite de 600 MP:
para saída raster, use Ladrilhos. A edição e as prévias reduzidas continuam
funcionando independentemente desse limite.

## Avisos e limites de maior capacidade

Os limites de 300 e 600 MP não desabilitam a verificação de memória. Dois buffers
ocupam aproximadamente 2,4 e 4,8 GB, respectivamente. Com a proteção de 70%, o
último caso precisa de aproximadamente 6,9 GB disponíveis apenas para esse
orçamento; assets, codificação e outros processos podem exigir mais memória.

Preferências antigas de 12, 20 ou 36 MP no modo Personalizado migram para 40 MP;
as de 72 MP migram para 80 MP. O antigo perfil Econômico passa para 40 MP.
Os limites dos demais perfis antigos são preservados. O padrão para novas
preferências é 150 MP, com resolução fixa de 300 DPI.

Exceder os megapixels gera um aviso com a capacidade configurada e a necessária,
orientando a verificar memória e acessar Configurações → Limite de exportação.
Orçamento de memória insuficiente informa a necessidade estimada e o orçamento
permitido, com a mesma orientação. Aumentar o limite não cria memória livre.
Falha efetiva de alocação também recebe orientação. Erros de geração aparecem
uma vez por trabalho em uma janela de aviso e continuam registrados no log.

O limite técnico por lado tem mensagem própria, orientando a usar Ladrilhos:
aumentar o limite configurado não pode superar esse limite técnico. O limite de 600 MP equivale a
aproximadamente 2,074 × 2,074 m em uma imagem quadrada a 300 DPI.

Na revisão dos seis perfis, **147 testes passaram em 11 módulos isolados**,
incluindo limites, persistência e migração, bloqueio antes de renderizar,
propagação dos avisos, geração, traduções e leitura dos avisos no painel.
A inspeção visual com o tema Grafite confirmou que os parágrafos cabem no
diálogo. Os limites de 300 e 600 MP foram verificados com memória disponível
simulada e sem alocar buffers gigantes; não houve exportação real de 600 MP
nesta máquina. A compilação Python e a verificação do diff também passaram.

## Validação da resolução fixa

Os testes específicos verificam que todos os perfis mantêm os mesmos pixels
e medidas físicas em PNG, JPEG e PDF, ignoram preferências antigas de DPI,
preservam o limite personalizado e mantêm a prévia de 3 × 3 m reduzida. A saída
inteira acima do limite escolhido é recusada antes da alocação; a exportação em ladrilhos
A4 continua em 300 DPI sem gerar o bitmap inteiro do documento. Também são
verificadas concorrência, memória disponível, links e itens por folha.

Na revisão para 300 DPI fixos, **132 testes passaram em 10 módulos isolados**,
cobrindo perfis, documentos grandes, dimensões do editor, JPEG, ladrilhos,
distribuição por folha, traduções, ajuda e geração com tabelas. A compilação
dos módulos Python e a verificação de espaços do diff também passaram.

## Histórico da experiência com DPI variável — descartada

**Os resultados abaixo pertencem à implementação anterior. A opção de exportar
a 96 DPI foi removida por decisão do projeto; essas medições não descrevem uma
funcionalidade disponível na versão atual.**

A base anterior passou em 59 testes de documentos, presets, distribuição e
JPEG. Os testes específicos novos verificam persistência/cancelamento dos
perfis, limites antes da alocação, memória disponível, documento de 3 × 3 m,
previews reduzidos, links, imposição, propagação aos workers e medidas físicas
nos formatos PNG, JPEG e PDF às quatro resoluções.

Resultado final: **931 testes passaram em 80 módulos isolados**. Três módulos
que dependem dos auxiliares de `tests/performance` foram reexecutados com esse
diretório no `PYTHONPATH`. Também passaram 73 testes direcionados finais de
perfis, fidelidade de texto/tabelas, JPEG e documentos grandes. A inspeção visual
do diálogo foi feita com o tema da aplicação.

Exportação real de documento simples de **3 × 3 m a 96 DPI**, 128,6 MP:

| Formato | Dimensões | Pico do processo | Tempo observado |
|---|---|---:|---:|
| PNG | 11.339 × 11.339 px | 554,6 MiB | 7,34 s |
| JPEG (95%) | 11.339 × 11.339 px | 1021,0 MiB | 5,34 s |
| PDF raster | 3000 × 3000 mm | 664,1 MiB | 5,03 s |

Os formatos grandes foram verificações funcionais, não uma comparação de
velocidade entre formatos em condições isoladas. Conteúdo mais complexo pode
exigir mais tempo e memória. O preview deste documento ocupou um buffer de
1600 × 1600 pixels, cerca de 10,24 MB, sem bitmap lógico de 5 GB.

O PNG grande registrou aproximadamente 2999,735 mm nos metadados, uma diferença
de 0,265 mm em 3 metros. O PDF registrou 3000 mm em ambos os lados, dentro de
1 micrômetro. Em cartões de 120 × 80 mm, testes de releitura verificam tolerância
de 0,04 mm em PNG e 0,3 mm em JPEG em todas as resoluções. Isso valida o arquivo,
não a precisão mecânica de uma impressora.

Comparação com o mesmo documento simples de **300 × 300 mm em PNG**, três
execuções por resolução, mediana:

| Resolução | Buffer raster | Tempo de geração/gravação |
|---|---:|---:|
| 300 DPI | 50,21 MB | 0,880 s |
| 96 DPI | 5,14 MB | 0,093 s |

Neste cenário, a escolha de 96 DPI reduziu o buffer em aproximadamente 90% e o
tempo em aproximadamente 89%. É uma comparação entre resoluções com definição
diferente, não uma aceleração de 89% para a mesma qualidade de 300 DPI.

Evidências locais de testes, medições e captura visual ficam em
`build/performance-profiles-review/`, ignoradas pelo Git. Windows, macOS,
impressão física e novos pacotes Flatpak/AppImage não foram validados nesta
etapa.
