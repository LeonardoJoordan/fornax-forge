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

## Estrutura

- `core/`, `features/`, `shared/`: código do aplicativo.
- `assets/`: ícones, fonte, temas, traduções e integração Linux.
- `docs/`: guias, avisos e licenças.
- `requirements.txt`: dependências de execução.
- `requirements-build.txt`, `scripts/`, `tools/`: preparação e integração de pacotes.
- `script_nuitka.py`, `instalador.iss`: standalone e instalador Windows.
- `com.leobelisario.FornaxForge.yaml`: receita Flatpak.

Esta árvore não inclui testes, históricos internos, modelos de demonstração,
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
