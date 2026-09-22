# Licenças e avisos de terceiros

Inventário atualizado em 22/09/2026 a partir do ambiente limpo Linux
x86_64/Python 3.13.11 e dos metadados oficiais instalados. **Não representa
aprovação dos binários Windows, AppImage ou Flatpak.** O inventário de arquivos
reais e o relatório Nuitka devem ser comparados em cada release.

## Componentes de runtime e build

| Componente | Versão validada / origem | Licença e evidência |
|---|---|---|
| PySide6 Essentials e Shiboken6 | 6.11.0 | Metadados LGPL-3.0-only ou alternativas GPL; opção LGPL para os componentes elegíveis. Addons/metapacote removidos do conjunto solicitado. Textos GPL em `LICENSE` e LGPL em `docs/licenses/LGPL-3.0-only.txt`; avisos e arquivos de atribuição extraídos dos fontes oficiais em `docs/licenses/qt-6.11.0/`; a correspondência exata com o artefato deve ser revisada. |
| Qt | Bibliotecas trazidas por Essentials 6.11.0 | Copyright The Qt Company Ltd. e colaboradores. Módulos importados pelo programa: Core, Gui, Widgets, Network e Svg. Dependências nativas/plugins adicionais devem ser conferidos no relatório Nuitka. Não generalizar a licença de todos os arquivos Qt. |
| Python | 3.13.11 no ambiente local | PSF e avisos históricos em `docs/licenses/PYTHON-3.13.11-LICENSE.txt`; substituir pelo texto do runtime efetivamente distribuído se mudar a versão. |
| pypdf | 6.16.1 | BSD-3-Clause; aviso copiado do pacote exato em `docs/licenses/packages/pypdf-6.16.1/`. Atualizado após os avisos de segurança da 6.14.2. |
| cryptography | 50.0.1 | Apache-2.0 ou BSD-3-Clause; textos e SBOM upstream em `docs/licenses/packages/cryptography-50.0.1/`. |
| OpenSSL incorporado a cryptography | 4.0.2 no wheel Linux examinado | Apache-2.0; `docs/licenses/OPENSSL-4.0.2-LICENSE.txt` e SBOM upstream. Não inferir que todos os wheels/Qt usam a mesma versão. |
| Crates Rust incorporados a cryptography | 39 entradas no SBOM upstream | Incluem alternativas MIT/Apache/BSD, Unicode-3.0 e Apache-2.0 WITH LLVM-exception. SBOM preservado; 32 crates externas baixadas com checksums do crates.io e 62 arquivos de aviso em `docs/licenses/cryptography-rust/`. Sete crates internas seguem os avisos de cryptography. Revisar a correspondência ao artefato. |
| cffi | 2.1.1 | MIT-0 (não MIT tradicional); texto copiado dos metadados. Inventariar libffi nativo se incluído. |
| pycparser | 3.0 | BSD-3-Clause; texto copiado dos metadados. |
| defusedxml | 0.7.1 | PSF-2.0; texto copiado dos metadados. Parser usado na validação de SVG. |
| Inter | Arquivos incluídos | SIL OFL 1.1, `assets/fonts/ui/OFL.txt`. |
| Nuitka | 4.0.7, ferramenta de build | AGPLv3 para a ferramenta, com `LICENSE-RUNTIME.txt` para o runtime coberto; ambos preservados dos metadados. Verificar os componentes auxiliares realmente incorporados. |
| zstandard | 0.25.0, ferramenta de build | Avisos copiados dos metadados; instalado para o build não prova inclusão no runtime. |

PySide/Qt não fornecem todos os avisos de terceiros nos metadados do wheel.
`packages/packages.json` (sob `docs/licenses`) explicita a ausência de avisos nos
metadados dos wheels. Os avisos Qt foram complementados pelos fontes oficiais
verificados por SHA-256, com manifesto em `docs/licenses/qt-6.11.0/sources.json`.
Essa coleta não substitui a revisão das condições de cada componente nativo. Bibliotecas de sistema trazidas pelo standalone
(por exemplo, X11, compressão, imagens, SQLite e runtime C/C++) também precisam
da correspondência arquivo/versão/licença. Windows exige conferir os termos dos
runtimes Microsoft efetivamente usados. Nada nessa tabela licencia assets dos
usuários ou redistribui suas assinaturas/modelos.

## Ícones da interface

Coleções declaradas pelo autor em 22/09/2026:

- Lucide: ISC, incluindo os avisos MIT de Feather/Cole Bemis presentes no texto
  oficial completo em `docs/licenses/LUCIDE-LICENSE.txt`.
- Google Material Icons/Symbols: Apache-2.0, em
  `docs/licenses/MATERIAL-ICONS-LICENSE.txt`.
- Bootstrap Icons: MIT, em `docs/licenses/BOOTSTRAP-ICONS-LICENSE.txt`.

Consulte `docs/ASSET_PROVENANCE.md` para o inventário por arquivo e as
declarações de autoria dos 11 SVGs próprios feitos no Inkscape. Entregar os textos completos e créditos junto
aos recursos em cada distribuição; a inclusão e validação nos instaladores
será verificada na Etapa 5. Conferir os avisos de alterações nos SVGs modificados.

## Condições práticas da LGPL v3 para Qt/PySide6

- manter as bibliotecas Qt/PySide6 separadas do executável e não bloquear sua substituição por versões compatíveis modificadas;
- entregar os textos da GNU GPL v3 e GNU LGPL v3, avisos de autoria e licenças de terceiros correspondentes aos binários Qt distribuídos;
- informar que o usuário pode obter, modificar e substituir os componentes cobertos;
- disponibilizar o código-fonte correspondente da versão exata das bibliotecas LGPL distribuídas, por meio válido e pelo período exigido pela licença, ou acompanhar os binários com o material aplicável;
- não aplicar EULA, DRM ou outra restrição que retire os direitos concedidos pela LGPL;
- se o distribuidor usar Qt comercial, substituir esta declaração pelos termos e artefatos comerciais corretos. Pacotes comunitários instalados pelo PyPI não devem ser apresentados como Qt comercial.

Para máxima reprodutibilidade, registre os hashes dos wheels usados no release e arquive o código-fonte correspondente à versão exata juntamente com os artefatos da versão.

## Substituição das bibliotecas Qt

Feche o FORNAX Forge, faça backup da pasta de instalação e substitua somente DLLs/módulos Qt e PySide6 por uma compilação ABI-compatível. A LGPL não obriga o autor do aplicativo a garantir compatibilidade nem a prestar suporte à versão modificada. O instalador não impede essa substituição.

## Fontes e referências oficiais

- Qt for Python: https://doc.qt.io/qtforpython-6/
- Licenças do Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html
- GNU LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.html
- GNU GPL v3: https://www.gnu.org/licenses/gpl-3.0.html
- Código-fonte Qt: https://download.qt.io/official_releases/QtForPython/
- Licença Python: https://docs.python.org/3/license.html
- Licença OpenSSL: https://www.openssl.org/source/license.html
- pypdf: https://github.com/py-pdf/pypdf
- cryptography: https://cryptography.io/en/latest/about/license/
- Inter: https://github.com/rsms/inter

## Verificação antes de publicar

1. Crie um ambiente virtual limpo e instale o lock de build da plataforma com `--require-hashes`. Consulte `docs/RELEASE.md`.
2. Execute `python script_nuitka.py` e confira `build/main.dist`.
3. Compare a lista de DLLs e módulos com esta tabela; resolva qualquer item sem licença identificada.
4. Inclua no instalador os textos integrais da GNU GPL v3, GNU LGPL v3, PSF, Apache 2.0, BSD-3-Clause, MIT, OFL 1.1 e os avisos do Qt aplicáveis ao pacote exato.
5. Arquive requisitos, hashes, fontes correspondentes e o instalador na mesma versão do release.
6. Compile `instalador.iss`, instale em uma máquina limpa e confirme que a pasta `docs/licenses` está presente.

Este inventário auxilia a conformidade técnica, mas não é parecer jurídico. Titularidade do código, contribuições, marcas e contratos comerciais devem ser validados pelo responsável pela distribuição.
