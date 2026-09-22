# Modelos `.fornax`: uso, migração e recuperação

Estado em 22/09/2026: implementação em validação. Consulte o
[checklist de distribuição](CHECKLIST_DISTRIBUICAO_FORNAX.md) antes de publicar.

## Arquivo individual e lote

Cada modelo da biblioteca passa a ser um arquivo `.fornax`, reunindo o documento
versionado e seus assets incorporados. Frente e verso pertencem ao mesmo modelo.
A extensão organiza o conteúdo; sozinha, não oferece proteção criptográfica.

A exportação individual usa `.fornax`. Um lote usa `.zip` contendo modelos
`.fornax`. ZIPs antigos de modelos continuam aceitos pelo fluxo de importação.
Não renomeie um ZIP antigo para `.fornax`: a estrutura interna é diferente.
Fotos variáveis referenciadas por pasta continuam externas ao modelo; configure
a pasta no computador de destino.

O contêiner versão 1 continua sendo usado para modelos públicos sem assinatura e
para os modos protegidos. O contêiner versão 2 identifica especificamente um
modelo público com assinaturas. Essa distinção permite que versões anteriores do
programa recusem a capacidade desconhecida, em vez de interpretar o arquivo como
corrompido. O documento gráfico interno permanece no schema v4.

Use **Arquivo > Importar modelos…** e **Arquivo > Exportar modelos…** para transportar modelos.
Ao abrir um `.fornax` externo, o programa oferece adicioná-lo à biblioteca.
Se o caminho já pertence à biblioteca, o modelo é selecionado sem pedir nova incorporação.
Recusar permite o uso temporário; ele não passa a fazer parte da biblioteca na
próxima execução. Importar cria uma cópia local, preservando o arquivo recebido.
Abertura por duplo clique depende da associação instalada pelo sistema; sua
validação nos pacotes está pendente. O ícone previsto é o do programa, sem
miniatura personalizada nesta versão.

## Armazenamento e proteção

| Modo | Sem senha | Com senha |
|---|---|---|
| Sem proteção | Abre e edita o modelo, inclusive assinaturas aceitas como públicas | Não se aplica |
| Proteger assinaturas | Permite uma cópia sem assinaturas | Libera as assinaturas e a edição do original |
| Proteger modelo inteiro | Não libera conteúdo nem prévia do modelo | Libera o documento completo |

Ao salvar ou converter um modelo com objetos do tipo **assinatura**, o programa
recomenda proteção. O usuário pode proteger somente as assinaturas, proteger o
modelo inteiro ou continuar sem senha depois de aceitar que essas imagens ficarão
acessíveis dentro do arquivo. Um modelo sem assinaturas também pode receber
proteção integral. Imagens comuns
não são classificadas automaticamente como assinaturas: inserir a foto de uma
assinatura como imagem comum não ativa essa política.

A senha tem entre 8 e 64 caracteres e é confirmada ao cadastrar. Não existe
recuperação da senha perdida. Guarde-a em local adequado; o backup do modelo
não contorna a senha. Mesmo com proteção integral, o nome do arquivo e parte dos
metadados técnicos do contêiner continuam visíveis. Evite dados sensíveis no nome.

A ação **Proteger modelo…** preserva arquivos abertos temporariamente: primeiro
salve uma cópia na biblioteca. Se houver recuperação pendente do editor, abra o
editor e salve ou descarte essa recuperação antes de ativar a proteção. Isso evita
deixar uma recuperação pública antiga ao lado do modelo recém-protegido.

**“Cópia sem assinaturas — o original está preservado”** significa que nenhuma
assinatura faz parte daquela cópia. Salvar suas alterações exige um novo modelo,
sem substituir o original protegido. Se forem adicionadas assinaturas, o novo
salvamento apresenta novamente a recomendação e as opções de proteção.

Enquanto um modelo autorizado permanece ativo, a senha não expira por um timer
de inatividade. Ao trocar de modelo, começa uma tolerância individual de cinco
minutos. Retornar dentro dela evita digitar novamente. Após expirar, o retorno
mostra apenas o conteúdo disponível sem senha.
Encerrar o programa encerra a autorização; não é um login permanente.

A seleção do modelo não abre automaticamente uma pergunta de senha. Para proteção de assinaturas, a prévia abre a cópia sem assinaturas; com proteção integral, o conteúdo permanece indisponível. Use **Desbloquear modelo** abaixo da prévia para inserir a senha. Após desbloquear, o mesmo botão passa a **Bloquear modelo**, encerrando esse acesso quando você desejar.

No editor, o escudo ao lado de **Salvar modelo** indica o nível atual e oferece **Sem proteção**, **Proteger assinaturas**, **Proteger modelo inteiro** e **Alterar senha**. A troca entre modos protegidos preserva a senha existente; a primeira proteção exige cadastro e confirmação. Alterar a senha exige a atual e a confirmação da nova.


## Compartilhar e receber

Na exportação, escolha se deseja incluir assinaturas. Sem elas, a cópia exportada
é pública; o original não é alterado. Um modelo integralmente protegido precisa
ser desbloqueado para que o programa possa produzir qualquer cópia de seu conteúdo.
Um modelo público com assinaturas pode ser enviado sem senha de transporte; suas
assinaturas permanecem extraíveis do arquivo recebido. Retirá-las produz uma
cópia pública sem esses objetos e sem seus assets exclusivos.

Para enviar conteúdo protegido, desbloqueie os modelos necessários e defina uma
senha de transporte. É possível tentar a mesma senha local em vários modelos;
os que falharem precisam de nova decisão. A senha de transporte não muda as
senhas locais dos originais. Envie essa senha ao destinatário pelo canal escolhido.

Na importação com conteúdo protegido, use a senha de transporte e cadastre a
proteção local para as cópias, individualmente ou com a mesma senha para o lote.
A nova cópia não mantém a senha do remetente como uma chave alternativa. Se você
escolher deliberadamente a mesma senha, ela continuará funcionando por ser igual.
Importar sem assinaturas é possível quando há uma parte pública disponível;
proteção integral não permite abrir conteúdo sem desbloqueio.

Ao incorporar um modelo público com assinaturas, a decisão tomada pelo remetente
não é herdada silenciosamente. O programa recomenda uma proteção local e permite
manter as assinaturas sem senha, protegê-las ou retirá-las. Incluir assinatura e
escolher proteção são decisões independentes.

## Converter os modelos antigos dos testers

1. Antes do teste, com o programa fechado, faça uma cópia da biblioteca antiga.
   Ela contém os dados no formato anterior e pode ter assinaturas sem proteção;
   não a trate como um arquivo já protegido pelo FORNAX.
2. Abra o programa normalmente. A biblioteca pode listar pastas antigas junto
   dos novos arquivos; a conversão ocorre ao selecionar o modelo antigo.
3. Se houver assinatura, escolha proteger as assinaturas, proteger o modelo inteiro
   ou continuar sem senha após o aviso. Cancelar preserva a pasta antiga e não
   publica uma conversão incompleta.
4. O programa normaliza o documento, preservando a página única dos modelos
   antigos e as páginas existentes, publica o `.fornax` e verifica o resultado.
5. A limpeza dos arquivos antigos só ocorre após as verificações. Arquivos que
   mudaram ou não puderam ser removidos ficam pendentes, com aviso; não apague
   manualmente diários ou resíduos para tentar forçar a conclusão.
6. Confira frente/verso, fontes, assinaturas, máscaras, fotos variáveis e uma
   geração de teste. Preserve a cópia anterior até terminar essa conferência.

A compatibilidade normaliza a estrutura; não inventa verso, fontes ausentes ou
assets inexistentes. Um modelo inválido pode exigir correção antes da conversão.
A migração do diretório antigo COMSOC para a área FORNAX é uma operação separada
anterior à conversão de cada modelo para `.fornax`.

## Alertas e recuperação

**Possível alteração do conteúdo público:** confira o modelo e sua origem antes
de continuar. Esse alerta não permite ignorar falha de autenticação de conteúdo
cifrado. Senha incorreta ou bloco cifrado adulterado não liberam assinaturas.

**Arquivo alterado durante uma operação:** recarregue o modelo e repita a decisão.
O aplicativo evita sobrescrever silenciosamente uma revisão que mudou.

**Interrupção ou salvamento com erro:** feche o aplicativo e preserve uma cópia
do conjunto antes de investigar. Não substitua nem exclua arquivos às cegas:

- `modelo.fornax`: arquivo principal;
- `modelo.fornax.bak`: backup, quando criado pelo salvamento;
- `.modelo.fornax.autosave.fornax`: recuperação do editor, quando disponível;
- diários e arquivos temporários da transação: podem ser necessários à retomada.

A biblioteca tenta recuperar um principal inválido a partir de um backup
estruturalmente válido. Conteúdo protegido ainda exige a senha para autenticação.
Versão futura não é tratada como corrupção: use uma versão compatível do programa.
O autosave é distinto do backup e segue o fluxo de recuperação do editor.

Ao aumentar a proteção ou trocar credenciais, o backup local pode representar a
**nova revisão protegida**, em vez da revisão anterior, para não deixar uma cópia
pública ou com senha anterior ao lado do modelo. Isso não modifica backups externos.
Não há promessa de recuperação em toda falha física de armazenamento.

## Limites da proteção

O objetivo é proteger conteúdo armazenado e compartilhado sem autorização.
Os PNGs/PDFs gerados incluem as assinaturas autorizadas e não recebem a senha do
modelo. Essa proteção não prova autoria, não é assinatura digital de documento
nem impede captura do material já exibido ou gerado. Arquivos antigos e backups
externos não são criptografados retroativamente.

No modo público, um `.fornax` é um contêiner organizado, não um cofre: quem recebe
o arquivo pode abrir sua estrutura e extrair assinaturas e demais assets. O aviso
registra uma decisão de uso, mas não adiciona criptografia. Para confidencialidade
do modelo armazenado, use uma das opções protegidas.

A revisão interna não é certificação nem auditoria independente. Evidências e
pendências anteriores permanecem no repositório Projeto ComSoc. Para novos
pacotes, consulte o [checklist de distribuição](CHECKLIST_DISTRIBUICAO_FORNAX.md).
