# Sombra externa de texto — implementação e benchmark

Data: 12/10/2026.

## Resultado

Sombra externa disponível em **Texto → SOMBRA EXTERNA**, aplicada à caixa
inteira, com ativação, cor, opacidade, direção, distância e desfoque. Os valores
numéricos atualizam a prévia durante o ajuste e registram um passo de histórico
ao confirmar o campo. Os textos continuam editáveis e os placeholders continuam
herdando o efeito. Sombra interna e contorno não integram esta implementação.

| Exportação de 100 JPEGs | Mediana | Menor–maior | Mediana do pico de RAM do processo |
| --- | ---: | ---: | ---: |
| Código anterior | 4,805 s | 4,485–5,900 s | 217,65 MiB |
| Código novo, sombra desligada | 4,583 s | 4,348–4,956 s | 217,96 MiB |
| Código novo, sombra na caixa “Texto” | 5,246 s | 5,018–5,624 s | 222,38 MiB |

- **Custo de ligar a sombra na versão nova:** +0,663 s por lote, ou **14,47%**.
  Isso corresponde a aproximadamente 6,6 ms adicionais por cartão no tempo
  total do lote; não é uma medição isolada de CPU de cada cartão.
- **Comparação com o código anterior:** +0,442 s, ou **9,20%**.
- A diferença de −4,60% com o efeito desligado está dentro da dispersão das
  rodadas e não deve ser anunciada como otimização.
- O pico de memória mediano aumentou aproximadamente **4,42 MiB** ao ligar o
  efeito. O pico da rodada mais alta com sombra foi 225,4 MiB. Esses valores
  são do processo completo, não apenas do bitmap do cartão.
- Os 100 JPEGs sem sombra permaneceram **idênticos byte a byte** aos da
  referência anterior, em todas as cinco amostras aceitas.
- Com sombra, os 100 arquivos mudaram e permaneceram consistentes entre as
  repetições. O lote passou de 61.897.151 para 62.123.161 bytes (+0,37%).

Conclusão: o efeito tem custo mensurável, porém pequeno em tempo absoluto neste
modelo. Os resultados não autorizam extrapolar o mesmo custo para sombras em
todas as caixas, textos variáveis extensos ou organogramas de mil cartões.

## Método

O benchmark foi preparado e executado **antes de modificar a aplicação**.
Script: `tests/performance/benchmark_text_shadow.py`.

- Modelo: **1.1.1 - Cartão - Aniversário - Pessoal do Rgt**.
- Caixa: **Texto**, camada 6, 1600 × 400 unidades lógicas; fonte Amiri 40.
  A fonte efetivamente resolvida no computador foi Amiri.
- Documento: 148 × 105 mm; saída nativa preservada em **1748 × 1240 pixels**,
  300 DPI, JPEG **95%**, um cartão por arquivo.
- 100 registros fictícios distintos, com nome, posto, cônjuge e data.
- Sombra: preta, opacidade 50%, direção 45°, distância 8 unidades lógicas
  (aproximadamente 0,68 mm) e raio de desfoque 6 (aproximadamente 0,51 mm).
- Mesma máquina: Intel Core i5-8350U, 8 CPUs lógicas, **6 workers** em todos os
  cenários; Linux, Python 3.13.13, Qt 6.11.0, execução pela `.venv`, sem Nuitka.
- Uma execução de aquecimento e **cinco amostras válidas por cenário**. Cada
  execução usou processo novo, diretório de saída temporário e configuração Qt
  isolada, com plataforma `offscreen` e fator de escala 1.
- Cronômetro inclui criação dos renderizadores, planejamento, base estática,
  workers, desenho, codificação JPEG e publicação dos arquivos. Leitura inicial
  do pacote, inicialização das fontes e conferência posterior dos JPEGs ficam
  fora do intervalo. Não se força esvaziamento do cache de disco do sistema.
- Cada rodada verifica quantidade, decodificação, dimensões e SHA-256 dos
  **100 arquivos**. Avisos de desenho e divergências entre repetições invalidam
  a amostra. O SHA-256 do modelo de origem permaneceu igual antes/depois:
  `d712a7bb436c267cb82c9aeef3d4e1effd7cda1ec07b0a07b8f4e31bbfa74816`.
- Não foram modificados nem substituídos o modelo e os dados da biblioteca.

Tempos individuais, em segundos:

| Cenário | 1 | 2 | 3 | 4 | 5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Antes | 5,900 | 4,835 | 4,805 | 4,485 | 4,719 |
| Depois, desligada | 4,555 | 4,956 | 4,627 | 4,348 | 4,583 |
| Depois, ligada | 5,246 | 5,195 | 5,469 | 5,624 | 5,018 |

Há variação de carga/frequência do processador entre rodadas. Não foi realizado
um ensaio de laboratório com frequência fixa; as casas decimais registram as
medições, não uma garantia de precisão absoluta.

## Implementação e limites

- `core/text_effects.py` centraliza a máscara das letras, o desfoque separável
  e a composição da sombra, usados pelo editor e pelo renderizador. O texto
  original continua sendo desenhado pelo mecanismo existente.
- O efeito usa `QImage`/`QPainter`; nenhum widget, `QPixmap` ou cena gráfica é
  criado nos workers. Não foi acrescentada dependência ao projeto.
- O deslocamento acompanha o documento, o zoom e a rotação. A sombra pode
  ultrapassar a caixa sem alterar alinhamento, entrelinha ou quebra de texto.
- Cache LRU de até **16 MiB**, compartilhado entre os renderizadores de um
  trabalho. Cor, conteúdo, fonte, layout e desfoque distinguem as máscaras;
  opacidade, direção e distância aproveitam a máscara existente.
- A máscara tem até **1 milhão de pixels** e 4096 pixels por lado. Sombras de
  textos gigantes e raios amplos reduzem sua resolução de trabalho, mantendo
  as letras na renderização original. O desfoque usa até 17 amostras por eixo.
- O orçamento dos workers reserva também o cache e até quatro buffers de
  máscara por worker. Falhas de alocação propagam erro de geração em vez de
  produzir silenciosamente um cartão sem o texto afetado.
- Os parâmetros persistidos são validados. Modelos sem a propriedade mantêm
  o efeito desligado. Salvamento, duplicação e histórico preservam os valores.
- A interface reutiliza títulos, controles de cor e opacidade do editor;
  traduções em inglês/espanhol e a ajuda do painel Texto foram atualizadas.

Embora “Texto” seja fixo, a base estática anterior não incorporava caixas de
texto: elas eram redesenhadas em cada cartão. O novo cache reaproveita **a
máscara da sombra**, sem mudar esse tratamento do conteúdo original. Textos
com placeholders diferentes exigem máscaras diferentes.

## Verificação funcional

Foram aprovados **110 testes distintos**, considerando as execuções e as
reexecuções após correções, nos módulos:

- `test_text_shadow`, `test_text_shadow_controls`, `test_text_fidelity`;
- `test_text_floating`, `test_i18n_catalog`;
- `test_workspace_pipeline`, `test_performance_profiles`, `test_large_documents`;
- `test_tiled_export`, `test_editor_history_capture`.

Cobertura específica: igualdade dos pixels editor/prévia/geração, preservação
da geometria, saída sem efeito idêntica, sombra além da caixa, invalidação do
cache, orçamento de memória, falha de alocação, parâmetros inválidos, edição
de placeholders, atualização imediata com um undo por confirmação, undo/redo,
duplicação e salvamento/reabertura de `.fornax`.

Na comparação entre imagem inteira e recortes de uma sombra girada, o Qt
apresentou diferença máxima de **1/255 por canal** em dez componentes de pixels
de um recorte. O teste admite somente esse arredondamento, sem faixa perdida
ou interrupção do efeito. Editor e saída na mesma escala passaram por igualdade
exata. Foram inspecionados também o JPEG real e os controles nos temas claro
e escuro. Windows e macOS não foram executados nesta validação.

### Ocorrência anterior à implementação

Uma rodada exploratória do código anterior registrou o aviso
`QGradient has no attribute Preset`, e um dos 100 JPEGs ficou diferente da
referência. Essa rodada **não foi usada na tabela de resultados**. O instrumento
foi reforçado para rejeitar avisos e diferenças de arquivos, e a referência foi
repetida integralmente antes da implementação.

Não houve rejeições nos três conjuntos finais. A ocorrência intermitente
preexistente fica registrada para investigação separada; não foi considerada
resolvida pelo recurso de sombra.

## Evidências locais e repetição

Resultados brutos (ignorados pelo Git) nesta pasta:
`antes.json`, `depois-sem-sombra.json`, `depois-com-sombra.json` e
`diagnostico-inicial.json`. Cada JSON guarda tempos, pico de memória, ambiente
e hashes por arquivo. Imagens de inspeção ficam em
`build/text-shadow-benchmark/`, também fora dos commits.

```bash
.venv/bin/python tests/performance/benchmark_text_shadow.py \
  --model '/caminho/111_cartao_aniversario_pessoal_do_rgt.fornax' \
  --output docs/desempenho_editor/sombra-texto/repeticao-sem-sombra.json \
  --mode off

.venv/bin/python tests/performance/benchmark_text_shadow.py \
  --model '/caminho/111_cartao_aniversario_pessoal_do_rgt.fornax' \
  --output docs/desempenho_editor/sombra-texto/repeticao-com-sombra.json \
  --mode on
```
