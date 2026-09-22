"""Seleção explícita de conteúdo e evidências de build; nunca usado pelo aplicativo."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ('LICENSE', 'NOTICE', 'AUTHORS.md', 'TRADEMARKS.md', 'SECURITY.md')
DOCS = ('USO_INSTITUCIONAL.md', 'PRIVACIDADE_E_ARMAZENAMENTO.md',
        'THIRD_PARTY_LICENSES.md', 'AVISO-DISTRIBUICAO.txt', 'ASSET_PROVENANCE.md',
        'RELEASE.md', 'GUIA_MODELOS_FORNAX.md', 'MODELOS_FRENTE_VERSO.md',
        'CHECKLIST_DISTRIBUICAO_FORNAX.md', 'REFERENCIAS_LEGADAS_E_REPOSITORIO.md')
ASSETS = {'icons': {'.svg', '.png', '.ico'}, 'fonts': {'.ttf'},
          'themes': {'.json'}, 'translations': {'.qm'}, 'linux': {'.xml'}}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def selected_files(root=ROOT):
    files = [root / 'main.py']
    for folder in ('core', 'features', 'shared'):
        files.extend(p for p in (root / folder).rglob('*.py')
                     if not p.name.startswith(('test_', 'benchmark_'))
                     and not any(part in ('tests', '__pycache__') for part in p.parts))
    for folder, suffixes in ASSETS.items():
        files.extend(p for p in (root / 'assets' / folder).rglob('*') if p.is_file() and p.suffix in suffixes)
    files.extend(root / p for p in LEGAL)
    files.extend(root / 'docs' / p for p in DOCS)
    files.extend((root / 'docs' / 'licenses').rglob('*'))
    files.extend(root / p for p in ('assets/fonts/ui/OFL.txt', 'assets/fonts/ui/README.txt'))
    return sorted(set(p for p in files if not p.is_dir()))


def stage(output, root=ROOT):
    # Não apagar um diretório fornecido pelo operador nem mesclar resíduos antigos.
    if output.exists() and any(output.iterdir()):
        raise ValueError('O diretório de preparação deve estar vazio.')
    files = selected_files(root)
    for source in files:
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Recurso fora da árvore autorizada: {source}')
    for source in files:
        if not source.is_file():
            raise ValueError(f'Recurso obrigatório ausente: {source}')
    for source in files:
        target = output / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return len(files)


def environment():
    return sorted(({'name': d.metadata['Name'], 'version': d.version,
                    'license': d.metadata.get('License-Expression') or d.metadata.get('License')}
                   for d in metadata.distributions()), key=lambda d: d['name'].lower())


def remove_unused_pdf_plugin(artifact):
    """Essentials inclui o handler PDF, mas sua QtPdf pertence a Addons.

    O FORNAX usa pypdf na geração e não importa PDF via QImageReader.
    Remover somente esse plugin evita entregar um handler sem sua biblioteca.
    """
    folder=artifact/'PySide6'/'qt-plugins'/'imageformats'
    for name in ('libqpdf.so', 'libqpdf.dylib', 'qpdf.dll'):
        path=folder/name
        if path.is_file(): path.unlink()


def inventory(artifact, output, nuitka_report=None):
    artifact = artifact.resolve()
    output = output.resolve()
    if output.is_relative_to(artifact):
        raise ValueError('Relatórios devem ficar fora do artefato inventariado.')
    entries = []
    for path in sorted(artifact.rglob('*')):
        if path.is_symlink() and not path.resolve().is_relative_to(artifact):
            raise ValueError(f'Link fora do artefato: {path.relative_to(artifact)}')
        if path.is_file():
            entries.append({'path': path.relative_to(artifact).as_posix(),
                            'size': path.stat().st_size, 'sha256': sha256(path)})
    if not entries:
        raise ValueError('Artefato vazio ou inexistente.')
    output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    shipped = []
    if nuitka_report is not None:
        from defusedxml.ElementTree import parse
        xml = parse(nuitka_report, forbid_dtd=True)
        for node in xml.findall('.//distribution'):
            name, version = node.get('name'), node.get('version')
            installed = metadata.distribution(name)
            if installed.version != version:
                raise ValueError(f'Metadados não correspondem ao build: {name}')
            expression = installed.metadata.get('License-Expression')
            component = {'type': 'library', 'name': name, 'version': version,
                         'bom-ref': f'python:{name}@{version}'}
            if expression:
                component['licenses'] = [{'expression': expression}]
            elif installed.metadata.get('License'):
                component['licenses'] = [{'license': {'name': installed.metadata['License']}}]
            shipped.append(component)
    report = {'commit': commit, 'dirty_worktree': dirty, 'platform': platform.platform(),
              'python': platform.python_version(), 'files': entries,
              'build_environment_not_proof_of_shipment': environment(),
              'signed': False, 'license_review_complete': False,
              'distributions_confirmed_by_nuitka': shipped}
    (output / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    # SBOM de arquivos reais. Bibliotecas transitivas nativas exigem revisão do
    # relatório Nuitka e dos binários; não inventar versões/licenças por nome.
    bom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
           'serialNumber': 'urn:uuid:'+str(uuid.uuid4()),
           'components': [{'type': 'file', 'name': e['path'], 'bom-ref': e['path'],
                           'hashes': [{'alg': 'SHA-256', 'content': e['sha256']}]}
                          for e in entries]}
    (output / 'files.cdx.json').write_text(json.dumps(bom, indent=2)+'\n', encoding='utf-8')
    if shipped:
        component_bom = dict(bom, components=shipped + bom['components'])
        (output / 'components.cdx.json').write_text(json.dumps(component_bom, indent=2)+'\n', encoding='utf-8')
    (output / 'SHA256SUMS').write_text(''.join(f"{e['sha256']}  {e['path']}\n" for e in entries), encoding='utf-8')
    return report


def collect_notices(output):
    """Copia os textos disponíveis nos pacotes exatos; registra lacunas."""
    output.mkdir(parents=True, exist_ok=True)
    result=[]
    for name in ('PySide6_Essentials', 'shiboken6', 'pypdf', 'cryptography', 'cffi',
                 'pycparser', 'defusedxml', 'Nuitka', 'zstandard'):
        dist=metadata.distribution(name)
        copied=[]
        for entry in dist.files or ():
            # Somente metadados; não recolher licenças de cópias internas aleatórias.
            if '.dist-info/' in str(entry) and (any(word in entry.name.lower() for word in ('license', 'copying', 'notice')) or '/sboms/' in str(entry)):
                source=Path(dist.locate_file(entry))
                if source.is_file():
                    target=output / f'{name}-{dist.version}' / ('sboms' if '/sboms/' in str(entry) else '') / entry.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source,target)
                    copied.append(target.relative_to(output).as_posix())
        result.append({'name':name,'version':dist.version,'notices':copied,
                       'complete_native_license_inventory':False})
    (output/'packages.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    for name in ('stage','inventory','notices'):
        sub=subs.add_parser(name);sub.add_argument('--output',type=Path,required=True)
        if name=='inventory':
            sub.add_argument('--artifact',type=Path,required=True)
            sub.add_argument('--nuitka-report',type=Path)
    args=parser.parse_args()
    if args.command=='stage': print(f'{stage(args.output)} arquivos preparados.')
    elif args.command=='inventory': print(f"{len(inventory(args.artifact,args.output,args.nuitka_report)['files'])} arquivos inventariados.")
    else: collect_notices(args.output)

if __name__=='__main__': main()
