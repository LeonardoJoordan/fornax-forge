## O que é

Página 1 define o cartão; o organograma define o quadro composto; as opções de **Arquivo → Configurar saída** definem a folha ou divisão em ladrilhos para a saída.

## Para que serve

Separar o tamanho dos elementos do tamanho do material completo e da forma de impressão.

## Como usar

1. Desenhe o cartão na Página 1.
2. Defina sua largura nos blocos e organize o quadro.
3. Confira o tamanho sugerido da composição.
4. Na tela principal, abra **Arquivo → Configurar saída** e escolha **Itens por folha** ou **Ladrilhos**. O botão verde indica o modo ativo.
5. Escolha a folha e o tamanho final. **Itens por folha** organiza os itens completos na folha; **Ladrilhos** divide o desenho em partes para montagem. O modo não muda automaticamente quando você altera as medidas. No organograma, a composição inteira é o item de saída: esse modo não separa os cartões internos em arquivos individuais.
6. Em **Ladrilhos**, arraste o desenho no mapa para ajustar sua posição. As folhas ficam paradas durante o arraste; ao soltar, o programa recalcula a distribuição.
7. Use **Restaurar tamanho original** para voltar às dimensões do modelo sem precisar lembrar as medidas anteriores.

Na tela principal, os formatos são **PNG**, **JPEG**, **PDF** e **PDF Agrupado**.
PNG preserva os pixels sem perdas; JPEG usa qualidade de 95% e compõe regiões
transparentes sobre branco. **PDF** cria arquivos separados; **PDF Agrupado**
reúne as páginas. Na geração dos cartões, o PDF conserva a arte como imagem
renderizada e pode conter links, mas não transforma o texto da arte em texto selecionável.

**PDF Agrupado** reúne as páginas e usa o nome da pasta da Forja para identificar
o arquivo. Nos cartões individuais, os marcadores e rótulos usam o nome que o
arquivo individual teria. Em folhas com vários cartões, indicam intervalos como
**Cartão de 1 a 8** e **Cartão de 9 a 16**. Frente e verso são identificados quando
existem. Em ladrilhos, as posições **A1, B1, A2…** identificam as partes; PNG,
JPEG e PDF separado geram arquivos por parte, enquanto PDF Agrupado as reúne.

## Exemplo de uso

Cartões de 45 × 65 mm podem formar um quadro maior que A4, exportado em partes para montagem.

## Dica de uso

Comece pelo tamanho de leitura do cartão; depois escolha a organização e o plano de saída.

## Particularidades e limites

- Mudar a folha de impressão não altera o desenho da Página 1.
- Ladrilhos geram arquivos para imprimir externamente; o FORNAX não envia a impressão diretamente à impressora.
- **Margem de sangria** reserva 5 mm em cada lado da folha, indicados em vermelho com 30% de opacidade na prévia. Essa indicação não aparece no arquivo gerado.
- Em **Ladrilhos**, duas folhas vizinhas têm 5 mm de margem cada uma na junção, totalizando 10 mm de papel a recortar. A arte continua na área útil da folha seguinte, sem uma sobreposição adicional de conteúdo. Uma folha A4 com apenas a margem de sangria oferece 200 × 287 mm de área útil.
- **Marcas de corte** reservam mais 5 mm em cada lado: 3 mm para os traços e 2 mm de distância até o conteúdo. As opções são independentes; ativar ambas reserva 10 mm por lado, reduzindo a área disponível para os itens.
- As medidas finais são definidas em milímetros. A exportação permanece em 300 DPI. Configurações → Limite de exportação permite escolher apenas o limite de megapixels por imagem, sem alterar automaticamente as medidas ou a resolução do resultado.
- Redimensionar na geração exige conferir a escala final de textos e fotos.
- Marcadores e rótulos são informações de navegação do PDF; não acrescentam títulos sobre a arte. A exibição depende do leitor de PDF.

## Veja também

- [Largura do documento (L), em milímetros](help:DOC-01).
- [Largura do cartão em milímetros](help:BLO-11).
- [Tamanho sugerido do quadro em milímetros](help:QUA-09).
