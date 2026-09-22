# Procedência dos recursos do FORNAX Forge

Data do inventário: 22/09/2026.

Este documento controla a origem e a autorização de redistribuição dos recursos incorporados ao aplicativo. Um arquivo só pode ser considerado liberado para publicação quando possuir autor ou fornecedor, origem verificável e licença ou declaração de criação própria.

## Situação conhecida

| Grupo | Arquivos | Situação | Evidência |
|---|---|---|---|
| Fonte Inter | `assets/fonts/ui/*.ttf` | Verificada | SIL Open Font License 1.1 em `assets/fonts/ui/OFL.txt`; origem indicada em `assets/fonts/ui/README.txt` |
| Traduções | `assets/translations/*.ts` e `*.qm` | Produzidas no projeto | Catálogos mantidos junto ao código; os `.qm` são compilados dos `.ts` |
| Temas | `assets/themes/*.json` | Produzidos no projeto | Configurações próprias do FORNAX; cobertas pela GPL-3.0-only |
| Integração Linux | `assets/linux/com.leobelisario.FornaxForge.xml` | Produzida no projeto | Metadado técnico próprio do formato `.fornax` |
| Marca e ícone do aplicativo | `assets/icons/fornax-forge.ico` e `assets/icons/fornax-forge_*.png` | Origem documentada por declaração do autor | Imagem gerada com ChatGPT; Leonardo Joordan Belisário Lima da Silva ajustou o arredondamento das bordas e acrescentou a constelação ao céu de fundo no Photoshop. Geração informada: 13 de setembro, às 01:33; PSD não preservado, PNGs exportados em diversos tamanhos disponíveis no projeto |
| Ícones funcionais SVG | `assets/icons/ui/**/*.svg` | Procedência registrada; conferir distribuição na Etapa 5 | Em 22/09/2026, o autor informou que os novos arquivos vieram de Lucide, Google Fonts Icons e Bootstrap Icons. Textos oficiais preservados em `docs/licenses/`; os 11 recursos sem identificação externa foram declarados pelo autor como criações próprias no Inkscape. |
| Documentação de ícones | `assets/icons/ui/README.md` e `README.pdf` | Não é recurso da interface | README atualizado na Etapa 6; PDF preservado como histórico. Ambos excluídos da seleção de release |

Metadados `sodipodi:docname` encontrados em alguns SVGs apenas registram nomes de edição. Eles não demonstram autoria nem autorização de redistribuição.

## Coleções declaradas e avisos preservados

| Coleção / autoria | Origem oficial | Licença preservada |
|---|---|---|
| Lucide Icons and Contributors; Cole Bemis nos ícones derivados de Feather | https://lucide.dev/ e https://github.com/lucide-icons/lucide | [ISC e avisos MIT/Feather completos](licenses/LUCIDE-LICENSE.txt) |
| Google Material Icons / Material Symbols | https://fonts.google.com/icons e https://github.com/google/material-design-icons | [Apache-2.0](licenses/MATERIAL-ICONS-LICENSE.txt) |
| The Bootstrap Authors | https://icons.getbootstrap.com/ e https://github.com/twbs/icons | [MIT](licenses/BOOTSTRAP-ICONS-LICENSE.txt) |

Textos obtidos dos repositórios oficiais em 22/09/2026. O registro em
[licenses/SOURCES.md](licenses/SOURCES.md) inclui URLs e hashes dos textos.
As licenças dos recursos externos são preservadas; a GPL-3.0-only do código
próprio não apaga os créditos ou as condições desses recursos.

Adaptações locais incluem renomeação de arquivos, cores para o tema, rotação de
símbolos de cantos e ajuste do viewBox das setas de dropdown. Antes da
publicação, conferir os avisos de modificação nos arquivos derivados sob
Apache-2.0 e a presença destes textos no pacote instalado (Etapa 5).

## Inventário dos SVGs presentes

A declaração do autor identifica as três coleções usadas. Classes SVG permitem
identificar diretamente Lucide e Bootstrap. A atribuição aos símbolos Google
abaixo combina a declaração com sua geometria característica; não é uma
comparação byte a byte com uma versão upstream. Os 11 arquivos sem identificação de coleção foram confirmados por Leonardo
Joordan Belisário Lima da Silva como criações próprias feitas no Inkscape,
em declaração de 22/09/2026. Essa declaração foi registrada sem presumir
origem externa por semelhança visual. Este inventário inclui
arquivos auxiliares e variantes, mesmo quando não utilizados na interface.

| Arquivo relativo a `assets/icons/ui/` | Origem | Evidência / limite |
|---|---|---|
| `actions/delete.svg` | Lucide | Classe SVG: lucide-trash |
| `actions/duplicate.svg` | Lucide | Classe SVG: lucide-layers-2 |
| `actions/edit.svg` | Lucide | Classe SVG: lucide-pen-line |
| `actions/expand-content.svg` | Lucide | Classe SVG: lucide-expand |
| `actions/group.svg` | Lucide | Classe SVG: lucide-link |
| `actions/lock ratio.svg` | Lucide | Classe SVG: lucide-link-2 |
| `actions/more-vertical.svg` | Lucide | Classe SVG: lucide-ellipsis-vertical |
| `actions/more.svg` | Lucide | Classe SVG: lucide-ellipsis |
| `actions/redo.svg` | Lucide | Classe SVG: lucide-arrow-right |
| `actions/rotate-left.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `actions/rotate-right.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `actions/undo.svg` | Lucide | Classe SVG: lucide-arrow-left |
| `actions/unlock ratio.svg` | Lucide | Classe SVG: lucide-unlink-2 |
| `align/bold.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `align/bot-alignment.svg` | Lucide | Classe SVG: lucide-arrow-down-to-line |
| `align/center-align.svg` | Bootstrap Icons | Classe SVG: bi-text-center |
| `align/center-align_2.svg` | Lucide | Classe SVG: lucide-text-align-center |
| `align/curved_edge.svg` | Lucide | Classe SVG: lucide-square-round-corner |
| `align/inf_dir.svg` | Lucide | Classe SVG: lucide-square-round-corner |
| `align/inf_esq.svg` | Lucide | Classe SVG: lucide-square-round-corner |
| `align/italic.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `align/justify.svg` | Bootstrap Icons | Classe SVG: bi-justify-left |
| `align/justify_2.svg` | Lucide | Classe SVG: lucide-text-align-justify |
| `align/left-align.svg` | Bootstrap Icons | Classe SVG: bi-text-left |
| `align/left-align_2.svg` | Lucide | Classe SVG: lucide-text-align-start |
| `align/line-space.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `align/mid-alignment.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `align/paragraph.svg` | Lucide | Classe SVG: lucide-pilcrow-right |
| `align/right-align.svg` | Bootstrap Icons | Classe SVG: bi-text-right |
| `align/right-align_2.svg` | Lucide | Classe SVG: lucide-text-align-end |
| `align/straight_edge.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `align/sup_dir.svg` | Lucide | Classe SVG: lucide-square-round-corner |
| `align/sup_esq.svg` | Lucide | Classe SVG: lucide-square-round-corner |
| `align/top-alignment.svg` | Lucide | Classe SVG: lucide-arrow-up-to-line |
| `align/underline.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `navigation/arrow_drop_down.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `navigation/arrow_drop_up.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `navigation/chevron-back.svg` | Lucide | Classe SVG: lucide-chevron-left |
| `navigation/chevron-down.svg` | Lucide | Classe SVG: lucide-chevron-down |
| `navigation/chevron-right.svg` | Lucide | Classe SVG: lucide-chevron-right |
| `navigation/chevron-up.svg` | Lucide | Classe SVG: lucide-chevron-up |
| `navigation/double-chevron-left.svg` | Lucide | Classe SVG: lucide-panel-right-open |
| `navigation/double-chevron-right.svg` | Lucide | Classe SVG: lucide-panel-left-open |
| `navigation/layer-child.svg` | Lucide | Classe SVG: lucide-corner-down-right |
| `navigation/left-arrow.svg` | Lucide | Classe SVG: lucide-arrow-left |
| `navigation/right-arrow.svg` | Lucide | Classe SVG: lucide-arrow-right |
| `objects/circle.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/image.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/line.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/shapes.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/signature.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/square.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `objects/text.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `state/eye-off.svg` | Lucide | Classe SVG: lucide-eye-off |
| `state/eye.svg` | Lucide | Classe SVG: lucide-eye |
| `state/guide.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `state/h.guide.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |
| `state/l.guide.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `state/lock.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `state/opacity.svg` | Bootstrap Icons | Classe SVG: bi-transparency |
| `state/rotate.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `state/settings.svg` | Lucide | Classe SVG: lucide-settings |
| `state/shield-ass.svg` | Bootstrap Icons | Classe SVG: bi-shield-shaded |
| `state/shield-full.svg` | Bootstrap Icons | Classe SVG: bi-shield-fill |
| `state/shield.svg` | Bootstrap Icons | Classe SVG: bi-shield |
| `state/unlock.svg` | Google Material (identificação técnica) | Declaração do autor + geometria/viewBox Material; nome original não registrado |
| `state/v.guide.svg` | Leonardo Joordan Belisário Lima da Silva — GPL-3.0-only | Criação no Inkscape declarada pelo autor em 22/09/2026 |

## Resultado da conferência dos SVGs

67 arquivos inventariados: 35 identificados como Lucide, 8 como Bootstrap,
13 como Google Material pela declaração e características técnicas, e
11 declarados como criação própria no Inkscape. Não resta origem individual
pendente para os SVGs atuais. A entrega dos avisos nos pacotes e a conferência
de modificações são checkpoints da Etapa 5.

## Marca do aplicativo — registro de procedência

Declaração de Leonardo Joordan Belisário Lima da Silva, registrada em 22/09/2026:

- Imagem-base gerada com o ChatGPT.
- Edição posterior no Adobe Photoshop pelo autor: ajuste do arredondamento das
  bordas e inclusão da constelação no céu ao fundo.
- Arquivos abrangidos: `assets/icons/fornax-forge.ico` e
  `assets/icons/fornax-forge_*.png`.

- Data/hora de geração informada pelo autor: **13 de setembro, às 01:33**.
  O ano é entendido como 2026 pelo contexto do desenvolvimento; não foi
  explicitado nessa declaração. O fuso horário não foi informado.
- O PSD não foi salvo. O Photoshop foi utilizado para os ajustes descritos e
  a exportação dos PNGs em diversos tamanhos. Não se afirma existir um
  arquivo editável, prompt ou imagem original separado dos arquivos atuais.
- A declaração e os arquivos finais disponíveis são as evidências deste
  inventário. Não equivalem a uma verificação independente da geração.

### Termos consultados

[Termos de Uso da OpenAI para fora do EEE, Suíça e Reino Unido](https://openai.com/policies/row-terms-of-use/),
com vigência indicada em 01/01/2026, consultados em 22/09/2026. Na seção
“Content”, os termos atribuem ao usuário, na relação com a OpenAI e na medida
permitida pela lei, os direitos da OpenAI sobre o conteúdo gerado. Também
ressalvam que resultados podem não ser exclusivos e que direitos de terceiros
continuam relevantes. Não há nessa condição uma exigência de preservar PSD.

O registro identifica a geração por IA e as intervenções humanas declaradas.
Não afirma exclusividade autoral sobre toda a imagem nem registro da marca.
A política de identificação do projeto está em `TRADEMARKS.md`.

### Arquivos finais preservados

Os hashes abaixo identificam os arquivos conferidos em 22/09/2026; não
comprovam por si só autoria ou data de geração.

| Arquivo | SHA-256 |
|---|---|
| `assets/icons/fornax-forge.ico` | `24f222a39ecc85816856114c6a994199c381dbd97d6c0e0532a847ac1878a92f` |
| `assets/icons/fornax-forge_1024.png` | `39cd360bfa5b5196006ffd22bfaf09a1d632f64bf7f57c3dc531ea4ba654e66a` |
| `assets/icons/fornax-forge_128.png` | `36cdd3c417794cc80fcb608f46db54df2722b02049bec153d3811a677fbfb6c6` |
| `assets/icons/fornax-forge_256.png` | `990174ed4ae7089fc42887e36d4b3b1b154d3ecdf83a5875aaceaad182393a60` |
| `assets/icons/fornax-forge_32.png` | `c8827fb2f62c97220663453f82a826c0a726b5b4b09eee1631c57f7867597435` |
| `assets/icons/fornax-forge_48.png` | `d919387fe802fe9d906b1dbb8399949238c23dac10e9dbf57faa3786f00938bf` |
| `assets/icons/fornax-forge_512.png` | `5d7f3a3e96f2af07c7ac19fcaefc6bbf2e05d47ed2d23fb9e7a97d03adbaf992` |
| `assets/icons/fornax-forge_64.png` | `c3e3fc385f21d9677991225aa4e209ea9396d9796f6ae94fee7b18880eb40324` |

## Como encerrar uma pendência

Para recurso criado por Leonardo Joordan Belisário Lima da Silva, registrar uma declaração simples com data aproximada e confirmar que não contém partes copiadas de outro conjunto sem autorização.

Para recurso obtido ou adaptado de terceiros, registrar:

1. autor ou fornecedor;
2. URL da página original ou comprovante preservado;
3. nome e versão da licença vigente quando o recurso foi obtido;
4. alterações realizadas;
5. texto de licença e atribuição exigida no pacote.

O bloqueio anterior que tratava todos os SVGs como Flaticon foi substituído
por este inventário atualizado, com base na declaração do autor e nos arquivos
atuais. O histórico Git e pacotes antigos podem conter versões anteriores;
não devem ser apresentados como se já contivessem apenas estes recursos.

Se a origem não puder ser comprovada, substituir somente o arquivo pendente por um recurso próprio ou de licença conhecida antes da publicação. Sem uma dessas evidências, o recurso permanece fora do conjunto considerado pronto para distribuição.
