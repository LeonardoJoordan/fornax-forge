# Modelos com frente e verso

O FORNAX Forge aceita modelos de uma ou duas páginas. A primeira página é a frente e a segunda é o verso. As páginas compartilham as dimensões físicas do documento, mas possuem camadas, objetos, guias e plano de fundo independentes.

## Edição

Os controles no centro do rodapé alternam entre as páginas. **+ Página** cria um verso em branco e o abre imediatamente. O menu de cada página oferece **Limpar página**; quando existem duas páginas, também oferece **Remover página**.

Limpar remove os objetos da página escolhida e recria seu plano de fundo branco. Remover exclui a página escolhida. Se a frente for removida, o verso passa a ser a nova página 1. As duas operações participam do histórico e podem ser desfeitas enquanto o editor permanecer aberto.

As dimensões editadas em **Documento** são aplicadas às duas páginas. Copiar e colar objetos entre elas preserva posição e aparência. A cópia possui identidade própria, enquanto arquivos de imagem podem continuar compartilhando o mesmo asset do modelo.

## Tabela e cópias

A tabela apresenta a união dos placeholders encontrados na frente e no verso. Um placeholder com o mesmo nome nas duas páginas usa o mesmo conteúdo da linha.

Cada linha representa um documento completo. **Cópias** multiplica documentos, não páginas. Uma linha com `Cópias = 3` em um modelo frente e verso produz três documentos, cada um com sua frente e seu verso.

## Arquivos gerados

- **PNG:** cada documento gera `_pag1.png` e `_pag2.png`. Modelos de uma página conservam a nomenclatura simples.
- **PDF por item:** cada documento gera um PDF com duas páginas, na ordem frente e verso.
- **PDF agrupado:** intercala `item 1/frente`, `item 1/verso`, `item 2/frente`, `item 2/verso` e assim por diante.
- **Imposição:** cada folha física possui uma face de frente e outra de verso. As posições do verso são reorganizadas para coincidirem com a frente após a impressão duplex e o corte.

Um verso existente é exportado mesmo quando está vazio. Links continuam vinculados à página e à região em que foram definidos.

## Impressão duplex

A imposição atual foi definida para uma impressora comum que alimenta a folha A4 de pé e usa virada lateral. A orientação da grade ainda pode ser escolhida automaticamente para aproveitar melhor o papel. Em uma grade paisagem, os cartões do verso recebem a rotação necessária para conservar a orientação depois da virada.

O arquivo não controla o driver da impressora. Antes de produzir um lote, gere uma prova identificada, imprima em duplex, corte uma unidade e confirme orientação e coincidência entre frente e verso. Desalinhamentos mecânicos da impressora não são compensados automaticamente.

## Formato e recuperação

A biblioteca atual usa arquivos `.fornax`. Ao selecionar uma pasta legada, o programa converte o modelo e normaliza seu documento interno para o schema v4. Um modelo antigo de uma página permanece com uma página; a migração não cria um verso automaticamente.

O documento versionado e os assets ficam dentro do contêiner. O salvamento transacional, o backup `.fornax.bak` e a recuperação do editor seguem as regras do [guia de modelos](GUIA_MODELOS_FORNAX.md). Não edite os JSONs ou backups manualmente como procedimento normal de uso.

Para transportar modelos, use **Arquivo > Exportar modelos…**: um modelo produz `.fornax`; vários produzem um ZIP com arquivos `.fornax`. No destino, use **Arquivo > Importar modelos…**. ZIPs antigos continuam aceitos; versões antigas do COMSOC não abrem necessariamente o formato atual.
