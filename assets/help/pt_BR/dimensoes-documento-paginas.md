## O que é

Documento → Dimensões define a largura L e a altura A em milímetros. O menu de formatos oferece A1 a A7, Carta, Cartão de visita e Quadrado (100 × 100 mm), além de Personalizado. Os três botões ao lado indicam orientação vertical, horizontal ou formato quadrado (1:1). Somente um permanece ativo por vez. O vínculo de proporção mantém a relação entre largura e altura. Nas páginas comuns, a dimensão é compartilhada.

## Para que serve

Preparar o tamanho físico do cartão, convite ou certificado antes de compor a arte.

## Como usar

1. Abra Documento e escolha um formato no menu acima das medidas.
2. Use os botões de orientação para trocar largura e altura. Para medidas próprias, informe L e A; o menu passa a indicar Personalizado. Mantenha o vínculo ligado para preservar a proporção, ou desligue para mudar cada lado livremente.
3. Confira os objetos e o plano de fundo depois da mudança.
4. Em modelos com duas páginas, confira também a outra página.

## Exemplo de uso

Defina 297 × 210 mm para um certificado A4 deitado antes de organizar o conteúdo.

## Dica de uso

Dimensão do documento, tamanho do cartão dentro do quadro e folha usada na geração são configurações diferentes.

## Particularidades e limites

- A página comum aceita de 10 a 10.000 mm (10 metros) em cada campo do editor.
- O limite da cena é independente da resolução de saída. Um documento de 3 × 3 metros pode ser aberto, editado e salvo mesmo quando a exportação inteira ultrapassa o limite escolhido.
- Abra **Configurações → Limite de exportação**, escolha **40, 80, 150, 300 ou 600 MP** em **Limite por imagem** e clique em **Aplicar**. O padrão é **150 MP**. A escolha é salva para as próximas sessões; Cancelar preserva o valor anterior. O painel mostra uma estimativa em MP do documento inteiro quando há um modelo aberto.
- MP significa megapixels: um milhão de pixels. O limite controla o tamanho máximo de cada imagem gerada para conter o consumo de RAM; não é um limite de tamanho do arquivo em MB nem da quantidade de cartões do lote. A resolução permanece fixa em **300 DPI**, e as medidas do modelo são preservadas. Em Itens por folha e Ladrilhos, o limite é verificado por folha raster, e a estimativa do documento inteiro pode ser maior que cada folha. Se a saída exceder o limite, escolha um valor maior ou use Ladrilhos. Um documento de 3 × 3 m ultrapassa 600 MP a 300 DPI e precisa ser dividido em folhas para exportação raster.
- A memória disponível também é verificada antes da geração, independentemente do limite escolhido. Cada buffer de 150 MP ocupa aproximadamente 600 MB; um buffer de 600 MP ocupa 2,4 GB; a geração pode usar vários buffers. Previews são reduzidos e não representam a qualidade final.
- PDFs individuais e agrupados de páginas comuns continuam contendo imagens, sem mudança para texto vetorial. Uma página PDF aceita até 5 metros por lado; documentos maiores devem ser divididos em ladrilhos. O PDF do organograma e dos ladrilhos conserva a pintura direta existente: o limite de MP aplica-se aos buffers raster, não a uma página vetorial sem bitmap inteiro.
- Para imprimir nas medidas planejadas, use tamanho real/100%. PNG e JPEG registram a densidade nos metadados, que o leitor precisa respeitar; existem pequenas tolerâncias de arredondamento, especialmente em JPEG. O PDF registra o tamanho da página em milímetros, corrigindo o arredondamento do Qt.
- Se a geração for bloqueada por capacidade, confira a memória disponível e acesse Configurações → Limite de exportação para escolher um limite maior, até 600 MP. Aumentar o limite não aumenta a memória livre; use Ladrilhos se necessário. Erros também aparecem em um aviso, mesmo com o log oculto. O limite técnico de 32.760 pixels por lado não é removido pela escolha do limite.
- Alterar a prancheta não redimensiona automaticamente textos e imagens livres.
- Trocar a orientação também preserva as posições dos objetos; confira a composição depois de trocar.
- Formato e orientação participam de Desfazer e Refazer. Em páginas quadradas, 1:1 fica ativo e os botões vertical e horizontal ficam desabilitados. Em páginas retangulares, 1:1 fica desabilitado e a orientação correspondente permanece ativa. Clicar no botão já ativo não o desmarca; 1:1 indica a proporção atual e não transforma uma página retangular em quadrada.
- Na página Organograma, estes controles ficam desabilitados: as dimensões do quadro são calculadas a partir de seu conteúdo. Volte à Página 1 para alterar o tamanho do cartão.
- O plano de fundo vinculado acompanha a página.
- Ao mudar a proporção da Página 1, a altura dos cartões do organograma é recalculada a partir da largura deles.

## Veja também

- [Página 1 como modelo de cartão do organograma](help:DOC-18).
- [Largura do cartão em milímetros](help:BLO-11).
- [Diferença entre dimensão do cartão, do quadro e da folha de impressão](help:QUA-11).
- [Contorno interno do plano de fundo e vínculo com as dimensões da página](help:FOR-30).
