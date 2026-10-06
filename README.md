# FORNAX Forge

[Repositório oficial](https://github.com/LeonardoJoordan/fornax-forge) ·
[Releases](https://github.com/LeonardoJoordan/fornax-forge/releases)

Aplicativo desktop para criar modelos gráficos e gerar materiais personalizados
em lote, com editor visual, tabela de dados, prévia, PNG e PDF.

Suporta frente/verso, imposição, biblioteca `.fornax`, importação/exportação
individual ou ZIP e proteção opcional de modelos e assinaturas.

## Executar pelo código

Ambiente validado no Windows: Python 3.13, 64 bits.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

No Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

No editor, **Esc** encerra uma seleção ou um arraste preso, mantendo os
movimentos e redimensionamentos já feitos. Ao perder o foco ou detectar que o
botão foi solto, o editor também encerra a interação pendente automaticamente.

## Protótipo de organogramas — branch upgrade-01

1. Desenhe o cartão na **Página 1**, com os campos variáveis e a foto desejados.
2. No botão **+**, escolha **Adicionar organograma**. Uma segunda página e um
   organograma são opções exclusivas; remover a composição libera a outra opção.
3. Na aba Organograma, o botão **Quadro** ocupa o lugar de Assinatura e reúne
   **Adicionar bloco**, **Conectar a elemento** e **Editar bloco selecionado**.
4. Defina colunas, linhas, largura do cartão e espaçamentos. Um conjunto 4 × 10
   possui 40 posições; 1 × 1 representa um cartão individual. O nome do bloco
   identifica o destino dos dados, sem criar um título na arte. Use Texto para títulos.
5. Dê um nome único a cada bloco, como **Comando**, **SetorX** ou **Turma A**.
   Na tabela, preencha a coluna **Bloco** com esse nome. Os registros de cada
   destino ocupam suas posições na ordem das linhas, mesmo quando estão
   intercalados com registros de outros blocos. Nomes ignoram maiúsculas e
   espaços externos; nomes vazios ou repetidos são rejeitados no editor.
   Renomear um bloco e salvar atualiza seus destinos nos dados já colados.
   Uma planilha externa precisa usar o novo nome na próxima colagem.
6. Na **Estrutura do quadro**, selecione um ou mais blocos (Ctrl ou Shift), clique
   em **Conectar a elemento** e clique no superior no desenho ou na árvore.
   Os blocos selecionados ficam apagados e bloqueados até escolher o destino;
   **Esc** ou **Cancelar conexão** cancela. Também é possível arrastar os blocos
   na árvore para mudar o superior; solte na área vazia para remover o superior.
   Em **Conectores**, ajuste cor, espessura, transparência e **Raio de curva** em
   milímetros. Raio 0 mantém as quinas retas; valores maiores arredondam as linhas,
   limitados pelos trechos disponíveis e pelo espaço entre os blocos. Arraste uma
   área sobre trechos das linhas para selecionar vários conectores; Ctrl adiciona
   à seleção. As linhas selecionadas recebem um realce. Selecionar uma linha ou um bloco altera suas
   conexões com o superior; sem seleção, define a aparência das novas conexões. Caixas de texto
   interrompem as linhas em sua área, preservando o fundo.
   Em **Lados permitidos do bloco**, marque as bordas aceitas para **Entrada**
   e **Saída**. O padrão é entrada por baixo e saída por cima. Cada controle
   precisa de pelo menos um lado; vários lados permitem escolher uma rota mais
   curta. A alteração vale para todos os blocos selecionados. Conexões para o
   mesmo superior podem compartilhar trechos; outros superiores usam canais
   separados. Se não houver espaço para uma rota livre, a lateral mostra um aviso.
   O centro dos blocos encaixa em 5 mm e o dos textos em 2,5 mm. X e Y no topo
   mostram o centro do elemento ou da seleção. Mover vários itens mantém suas
   distâncias. A Página 1 usa o alinhamento habitual e modelos existentes abrem
   nas posições salvas. Duplicar ou colar blocos atribui nomes novos automaticamente.
   O desenho mantém posições vazias e
   sugere o tamanho físico pelo conteúdo e pela margem de saída.
7. Salve o modelo, retorne à tabela e preencha os registros. **Gerar material**
   oferece PDF no tamanho do quadro, mosaico A4/A3 ou PNG em 150/300 dpi.

Na prévia, **Item** mostra o cartão da Página 1 com os dados da linha selecionada.
Escolha **Organograma** no mesmo seletor para visualizar o quadro inteiro;
ao voltar para Item, a linha selecionada é mantida.

Um cartão aparece somente quando possui informação variável válida da página 1.
Textos fixos, fundo, assinatura e o valor automático do nome do modelo não
ativam posições vazias. Uma foto variável, sozinha, deve apontar para uma imagem
legível. Na edição, todas as posições aparecem para permitir organizar o modelo;
na prévia e na saída, as vazias ficam ocultas, assim como suas conexões.
Cada linha destinada a um bloco corresponde a uma posição; Cópias não duplica pessoas
no organograma, e zero oculta aquela linha mantendo sua posição. A coluna Bloco
sozinha não ativa um cartão. O rodapé indica pendências; passe o mouse sobre o
aviso para conferir as linhas. Destinos ausentes, desconhecidos ou registros que
excedem a capacidade impedem a exportação até a correção, para evitar perder pessoas.

O PDF mantém textos e formas vetoriais. O mosaico usa margens de 10 mm,
sobreposição de 5 mm e marcas de montagem; imprima em tamanho real/100%.
PNG continua sujeito aos limites seguros de memória. O protótipo aceita até
2.500 posições por quadro e 1.000 folhas por mosaico; PDF com página única aceita
até 5 m por lado. Quadros maiores devem usar mosaico.

Modelos anteriores continuam compatíveis. Modelos com organograma usam esquema
5 e precisam desta versão do aplicativo para abrir e editar; modelos comuns
continuam no esquema 4. Nenhuma dependência Graphviz foi adicionada.
Organogramas antigos com nomes vazios ou repetidos recebem nomes únicos ao abrir,
preservando os identificadores internos, posições e conexões. A migração fica em
memória até salvar; novos modelos continuam rejeitando nomes vazios ou repetidos.

Validação local:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

## Estrutura

- `core/`, `features/`, `shared/`: código do aplicativo.
- `tests/`: testes automatizados de regressão.
- `assets/`: ícones, fonte, temas, traduções e integração Linux.
- `docs/`: guias, avisos e licenças.
- `requirements.txt`: dependências de execução.
- `requirements-build.txt`, `scripts/`, `tools/`: preparação e integração de pacotes.
- `script_nuitka.py`, `instalador.iss`: standalone e instalador Windows.
- `com.leobelisario.FornaxForge.yaml`: receita Flatpak.

Esta árvore não inclui históricos internos, modelos de demonstração,
dados de usuários, ambientes virtuais ou instaladores. O desenvolvimento
anterior permanece no repositório Projeto ComSoc. Identificadores legados no
código são mantidos para compatibilidade e migração dos dados existentes.

## Gerar instaladores

Veja [RELEASE](docs/RELEASE.md). Para Windows, instale `requirements-build.txt`
em um venv limpo, execute `python script_nuitka.py` e compile `instalador.iss`
com Inno Setup. Não instale o metapacote PySide6/Addons no ambiente de build.

Para Flatpak, prepare no Linux os wheels e o lock correspondentes à ABI e
arquitetura do SDK, conforme a documentação. Os locks Windows não servem como
wheelhouse do Flatpak. Instaladores e fontes correspondentes de terceiros
devem ser preparados para os Releases, não adicionados à árvore de código.

A compilação não comprova funcionamento do pacote instalado. Ainda são
necessárias validações visuais, de instalação/atualização/desinstalação e do
Flatpak. Os pacotes atuais não têm assinatura digital.

## Uso e licença

- [Modelos e proteção](docs/GUIA_MODELOS_FORNAX.md)
- [Frente e verso](docs/MODELOS_FRENTE_VERSO.md)
- [Privacidade e armazenamento](docs/PRIVACIDADE_E_ARMAZENAMENTO.md)
- [Avisos de terceiros](docs/THIRD_PARTY_LICENSES.md)

Código próprio: **GPL-3.0-only**. Preserve [LICENSE](LICENSE), [NOTICE](NOTICE),
[AUTHORS](AUTHORS.md), [TRADEMARKS](TRADEMARKS.md) e os avisos de terceiros.
Modelos e materiais dos usuários não passam automaticamente a integrar o
programa ou sua licença.
