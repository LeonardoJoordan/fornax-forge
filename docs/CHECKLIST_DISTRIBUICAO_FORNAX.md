# Checklist de distribuição do formato `.fornax`

Não marcar aprovação de um sistema com base em testes offscreen de outro.
Executar com biblioteca sintética, sem assinaturas reais. Para cada linha,
registrar SO/versão, pacote e SHA-256, commit (e se havia alterações locais),
resultado, evidência e responsável/data. Campos vazios são pendências.

## Pré-requisitos de liberação

- [ ] Confirmar que `LICENSE`, `NOTICE`, `AUTHORS.md`, `TRADEMARKS.md`, a orientação
  de uso institucional e os avisos de terceiros estão presentes no pacote final.
- [x] Registrar a substituição declarada dos SVGs pelas coleções Lucide, Google Material e Bootstrap.
- [x] Registrar a origem dos 67 SVGs atuais em `ASSET_PROVENANCE.md`, incluindo
  os 11 declarados pelo autor como criações próprias no Inkscape.
- [ ] Conferir a entrega das licenças/créditos dos ícones e os avisos de modificação.
- [x] Registrar a procedência do ícone principal: declaração do autor, ChatGPT,
  ajustes no Photoshop, data/hora informada, PNGs/ICO finais e termos consultados.
  PSD não preservado; limites da evidência explicitados em `ASSET_PROVENANCE.md`.
- [ ] Conferir no pacote instalado os textos PT/EN/ES da recomendação de proteção,
  importação, exportação e erros de senha.
- [ ] Confirmar versão do produto; `instalador.iss` ainda declara `1.0.0`.
- [ ] Construir em ambiente limpo; registrar todas as dependências resolvidas,
  hashes de wheels/artefatos e ferramentas de build, não só requirements.
- [ ] Inventariar bibliotecas efetivamente distribuídas e entregar seus avisos
  completos em cada formato; conferir `THIRD_PARTY_LICENSES.md`.
- [ ] Resolver as pendências técnicas do relatório 4.5 antes de aprovação.
- [ ] Registrar revisão especializada independente, ou sua ausência explícita;
  não anunciar certificação ou garantia absoluta de segurança.

## Matriz nativa

As evidências anteriores permanecem no repositório Projeto ComSoc. Validar
novamente os pacotes gerados desta árvore; não considerar a matriz aprovada
apenas pela compilação ou pelos testes anteriores.

| Pacote | Instalação e abertura | Duplo clique/instância única | Reinício por idioma | Migração e geração | Estado |
|---|---|---|---|---|---|
| Windows / Inno Setup | — | — | — | — | Pendente |
| macOS / app + DMG | — | — | — | — | Pendente |
| Linux / standalone + AppImage | — | — | — | — | Pendente |
| Linux / Flatpak | — | — | — | — | Pendente |

Para cada pacote:

1. Instalar em conta limpa. Confirmar ícone, tradução selecionada, fontes
   incorporadas, licenças e caminho dos dados. Registrar versões reais.
2. Abrir `.fornax` de nome com espaços e acentos com o aplicativo fechado e aberto.
   Confirmar uma única instância, escolha de incorporação e uso temporário.
3. Repetir com editor modificado aberto; o trabalho atual não pode ser perdido.
4. Recusar incorporação, fechar e reabrir: o modelo temporário não reaparece.
   Aceitar incorporação: a cópia local existe e a origem recebida não mudou.
5. Trocar idioma/reiniciar: a nova instância abre; não repete importação anterior.
6. Testar público sem assinatura, público com assinatura aceita, assinaturas
   protegidas e proteção integral. Conferir senha errada/cancelamento, cinco minutos
   após sair do modelo, cópia sem assinaturas e nova senha local na importação.
7. Converter modelo legado de uma e duas páginas; conferir prévia/editor/PNG/PDF,
   assinatura visível e oculta, grupos, máscaras, clipboard e fotos variáveis.
8. Exportar/importar lote mantendo e retirando assinaturas, com destino público e
   protegido, senhas diferentes, falha parcial e nome conflitante.
   Nenhuma substituição sem escolha; não reaproveitar senha de transporte como
   chave adicional da cópia local.
9. Simular fechamento durante operação em biblioteca descartável; conferir
   retomada e principal/backup/recuperação. Não desligar hardware com dados reais.
10. Atualizar/desinstalar. Não remover modelos/preferências sem escolha explícita;
    conferir associação da extensão e coexistência com outras instalações.

No macOS testar também evento FileOpen e janelas após minimizar/restaurar.
No Flatpak testar seleção de arquivos externos via portal, lote e pastas de fotos
variáveis, saída escolhida pelo usuário e socket entre instâncias da sandbox.
No AppImage, declarar MIME no `.desktop` não garante associação automática no host:
verificar o mecanismo de integração realmente entregue ao usuário.

## Filesystems e falhas

- [ ] Volume local nativo com publicação e recuperação confirmadas.
- [ ] FAT/exFAT: verificar mensagem e preservação da origem quando hard links não
  forem suportados. A implementação atual não tem fallback de publicação nesse caso.
- [ ] Compartilhamento de rede: locks, renomeação, interrupção e reconexão;
  registrar como não suportado se não houver evidência suficiente.
- [ ] Pasta somente leitura, disco cheio e arquivo alterado por outro processo:
  erro compreensível e nenhuma substituição/limpeza indevida.
- [ ] Modelo/backup de versão futura não sofre downgrade automático.

## Desempenho e memória

- [ ] Executar `tools/capture_fornax_stage4.py --output CAMINHO_NOVO` com o Python
  do ambiente de teste; preservar o JSON e registrar CPU/RAM/armazenamento.
- [ ] Medir separadamente abrir/desbloquear, salvar autorizado, preview e geração.
- [ ] Repetir em máquina modesta, com fotos realistas e lote grande; observar RAM,
  cancelamento e responsividade. O fixture pequeno não valida esse cenário.
- [ ] Conferir tamanho físico/réguas do editor em modelo com DPI diferente de 300.
- [ ] Não reduzir parâmetros criptográficos apenas para atingir uma meta de tempo.

## Evidências locais já existentes

O relatório 4.4, preservado no repositório Projeto ComSoc, contém testes Linux offscreen,
IPC Linux real e comparações de render/desempenho. Use-os como referência; não
preencha a matriz nativa acima como aprovada sem testar o pacote instalado.

## Integração Linux por usuário

Para a execução pelo código, a partir da raiz do projeto:

```bash
python3 tools/install_linux_integration.py
```

Registra MIME, ícones e aplicativo padrão somente para o usuário atual. O launcher
usa `.venv/bin/python` e `main.py` com caminhos absolutos. Se mover o projeto,
execute novamente. Não associe `.fornax.bak`: é um backup, não um modelo principal.
Não é necessário converter modelos novamente.

Para um AppImage já salvo em local permanente e executável:

```bash
python3 tools/install_linux_integration.py --appimage /caminho/FORNAX_Forge.AppImage
```

A definição compartilhada fica em `assets/linux/com.leobelisario.FornaxForge.xml`;
o Flatpak a instala em sua área MIME e o AppImage a inclui em seu conteúdo.
O script de integração do usuário não deve ser executado de dentro do Flatpak.
Para ensaiar sem mudar a associação padrão, use `--data-home DIRETORIO_DE_TESTE
--no-default`. O instalador depende de `update-mime-database`,
`update-desktop-database` e, para definir o padrão, `xdg-mime`.

Verificação realizada na instalação de desenvolvimento Linux: consulta MIME
retornou `application/x-fornax-template`, padrão
`com.leobelisario.FornaxForge.desktop`, ícone explícito do FORNAX. O `.fornax.bak`
continuou `application/x-trash`. Isso não conclui a matriz de pacotes nativos.
O gerenciador de arquivos pode precisar atualizar a pasta para descartar ícones
já armazenados em cache.

## Revisão local de 22/09/2026

A etapa 6, documentada no repositório Projeto ComSoc, atualizou os guias,
verificou a seleção documental de release e repetiu testes funcionais e IPC Linux.
A observação de rede na inicialização do standalone encontrou apenas IPC local.
Essas evidências não marcam como concluídas as instalações da matriz acima.
