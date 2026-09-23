# Preparação verificável de releases

Não publicar um pacote apenas porque compilou. A validação instalada, fontes
correspondentes e obrigações dos componentes nativos exigem confirmação por
artefato. O processo abaixo não acrescenta rede ao aplicativo.

## Ambiente e seleção

1. Criar venv limpo com Python 3.13; instalar `requirements-build.txt`.
   Para regenerar locks, usar pip-tools em ambiente separado.
2. Gerar locks com hashes no SO/arquitetura alvo usando pip-compile:
   `pip-compile --generate-hashes --output-file build/runtime.lock requirements.txt`
   e repetir para `requirements-build.txt`. Arquivar os locks e os wheels/sdists.
   O lock `requirements/linux-py313-runtime.lock` foi validado apenas em Linux
   x86_64/Python 3.13; não presume validação em Windows/macOS ou outras arquiteturas.
3. Instalar em outro venv com `pip install --require-hashes -r <lock>`.
4. Validar os fluxos do aplicativo e a instalação no SO alvo. Esta árvore não
   inclui a suíte de testes nem o workflow do repositório de desenvolvimento anterior.
5. `python script_nuitka.py` prepara uma árvore permitida em `build/`, compila e
   gera relatório Nuitka, relatório de licenças e inventário dos arquivos reais.
   Testes, caches, planos e README.pdf não entram nessa árvore.

Os wrappers `PySide6_Essentials` e `shiboken6` ficam separados e substituíveis.
Não instalar o metapacote PySide6/Addons no ambiente de release. Não remover
DLLs/SOs por tentativa: conferir dependências nativas e executar a validação.
O handler `qpdf` é removido da saída standalone porque Essentials o inclui
sem sua dependência QtPdf; o FORNAX não usa esse handler e continua gerando PDFs
com pypdf. O inventário final registra a saída após essa remoção.
A redução do conjunto Qt não equivale a uma auditoria completa de suas licenças.

## Evidências e fontes

- `scripts/release_tools.py notices --output build/package-notices` copia avisos
  encontrados nos pacotes exatos e registra ausências. A pasta não é uma
  declaração de completude: componentes Rust, OpenSSL e dependências do Qt
  incorporadas estaticamente precisam de seus próprios avisos.
- `scripts/release_tools.py inventory --artifact <pasta> --output <pasta-externa>`
  produz SHA256SUMS, inventário, commit/árvore suja e SBOM CycloneDX de arquivos.
  Com `--nuitka-report build/compilation-report.xml`, também gera
  `components.cdx.json` com as distribuições Python efetivamente identificadas
  pelo compilador e suas versões. O inventário do ambiente está separado: instalado no venv não significa
  distribuído no binário. O SBOM de arquivos não substitui um SBOM de componentes
  nativos revisado. Não publicar relatórios com caminhos privados sem revisão.
- `python scripts/fetch_qt_sources.py build/corresponding-sources` baixa os
  fontes oficiais de QtBase, QtSvg, QtWayland, QtImageFormats e PySide/Shiboken
  6.11.0, verifica cada SHA-256 oficial e grava `qt-sources.json`. Esses arquivos
  precisam acompanhar a publicação pelo meio escolhido; estarem no computador
  do desenvolvedor não significa que foram entregues aos destinatários.
- `scripts/extract_qt_notices.py` preserva os avisos dos fontes Qt verificados;
  `scripts/fetch_rust_notices.py` faz a coleta das crates externas e seus avisos
  a partir do SBOM upstream de cryptography, verificando checksums do crates.io.
  Esses scripts são exclusivos da preparação de release.
- Arquivar as fontes correspondentes exatas de Python, Qt, PySide/Shiboken e
  demais componentes que as exigem, com hashes, alterações e instruções de build.
  Não considerar um link genérico upstream suficiente. Para o código próprio,
  usar o commit exato e também todas as mudanças locais; não lançar árvore suja.
- Preservar GPL/LGPL, licenças de ícones e fonte, exceção do runtime Nuitka e
  avisos de cada dependência efetivamente incluída. `docs/licenses` acompanha
  os três formatos de distribuição. Conferir o artefato final instalado.
- Testar a substituição/recombinação das bibliotecas Qt compatíveis em uma cópia
  do pacote e registrar o resultado por plataforma. Não prometer suporte à
  biblioteca modificada; não impedir os direitos previstos na licença.

## Flatpak

O manifesto antigo usava GNOME 47 e downloads pip durante o build. O manifesto
atual requer runtime/SDK 50 e um wheelhouse preparado para o Python/arquitetura
exatos do SDK, em `build/flatpak-wheels`, mais seu `requirements.lock` com hashes.
O build instala sem rede (`--no-index --require-hashes`); não reutilizar wheels
nativos do Python do host sem conferir a ABI. Preparar wheels com `pip download
--require-hashes -r <lock> --dest build/flatpak-wheels` e copiar o lock para
`build/flatpak-wheels/requirements.lock`. Testar o pacote dentro da sandbox.
Verificar novamente suporte da base antes de publicar:
https://release.gnome.org/calendar/

## Checksums, assinatura e publicação

Gerar SHA-256 dos instaladores finais, após todas as modificações. SHA256SUMS
sozinho detecta corrupção; não autentica o distribuidor. Os scripts registram
`signed: false`; não há chave configurada ou assinatura de release implantada.
Antes de publicar, definir quem controla a chave e fornecer instruções de
verificação, ou informar expressamente que o release não está assinado.

Antes de enviar código, executar uma varredura de segredos. Resultados não devem
expor os segredos encontrados. Se houver credencial real, revogar/rotacionar antes
de limpar o histórico. Não reescrever o histórico automaticamente.

## AppImage Linux — preparação local

O AppImage usa o standalone Nuitka; não usa o SDK ou wheelhouse do Flatpak.
Criar um ambiente separado evita incluir PySide6/Addons do ambiente de edição:

```bash
python3 -m venv .venv-appimage
.venv-appimage/bin/python -m pip install --require-hashes -r requirements/linux-py313-build.lock
.venv-appimage/bin/python -m pip check
.venv-appimage/bin/python script_nuitka.py
```

Esse lock foi validado em Linux x86_64/Python 3.13. Em outra combinação, gerar
um lock correspondente. Compilação exige compilador e ferramentas do Nuitka.

Colocar `appimagetool` executável na raiz, obtido do repositório oficial
`AppImage/appimagetool`, verificando o hash. Para usar um runtime previamente
baixado e verificado de `AppImage/type2-runtime`:

```bash
FORNAX_APPIMAGE_RUNTIME="$PWD/build/appimage-tools/runtime-x86_64" bash script_appimage.sh
./FORNAX_Forge.AppImage
sha256sum FORNAX_Forge.AppImage
```

O script reconstrói `FORNAX_Forge.AppDir` e gera `FORNAX_Forge.AppImage` na raiz.
Sem `FORNAX_APPIMAGE_RUNTIME`, o appimagetool pode baixar seu runtime ao empacotar.
Preservar versões, URLs e hashes: o rótulo upstream `continuous` é mutável.
A preparação usa rede; isso não adiciona atualização automática ao aplicativo.

Antes de distribuir, testar o AppImage em outro computador/distribuição alvo,
sem Python/venv do projeto. Bibliotecas do host podem impor requisitos mínimos;
gerar AppImage não garante compatibilidade com toda distribuição antiga.
Validar interface, geração, importação/exportação e associação separadamente.
