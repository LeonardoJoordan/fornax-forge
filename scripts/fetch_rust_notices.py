"""Coleta fontes/avisos das crates externas declaradas no SBOM de cryptography."""
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from release_tools import sha256


def download(url,path):
    subprocess.run(['curl','--fail','--location','--silent','--show-error',
                    '--proto','=https','--proto-redir','=https','--retry','2',
                    '--connect-timeout','15','--max-time','90',
                    '-A','FORNAX-release-inventory',url,'-o',str(path)],check=True)


def fetch(sbom,archives,notices):
    archives.mkdir(parents=True,exist_ok=True);notices.mkdir(parents=True,exist_ok=True)
    records=[]
    for component in json.loads(sbom.read_text())['components']:
        if 'download_url=file://' in component.get('purl',''):continue
        name,version=component['name'],component['version']
        if not all(re.fullmatch(r'[a-zA-Z0-9_.+-]+',v) for v in (name,version)):
            raise ValueError('Identificador de crate inválido.')
        prefix=f'{name}-{version}'
        info=archives/(prefix+'.json')
        download(f'https://crates.io/api/v1/crates/{name}/{version}',info)
        expected=json.loads(info.read_text())['version']['checksum']
        archive=archives/(prefix+'.crate')
        url=f'https://static.crates.io/crates/{name}/{prefix}.crate'
        if not archive.exists() or sha256(archive)!=expected:download(url,archive)
        if sha256(archive)!=expected:raise ValueError('Checksum de crate divergente.')
        copied=[]
        with tarfile.open(archive) as bundle:
            for member in bundle:
                path=PurePosixPath(member.name)
                if not member.isfile() or not path.name.lower().startswith(('license','copying','notice','copyright')):continue
                if path.is_absolute() or '..' in path.parts or member.size>2_000_000:
                    raise ValueError('Aviso de crate inválido.')
                target=notices/Path(*path.parts)
                target.parent.mkdir(parents=True,exist_ok=True)
                with bundle.extractfile(member) as stream:target.write_bytes(stream.read())
                copied.append(path.as_posix())
        records.append({'name':name,'version':version,'sha256':expected,'source':url,
                        'notices':copied,'licenses':component.get('licenses',[])})
        (notices/'sources.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
        print(f'{prefix}: {len(copied)} avisos',flush=True)
    if any(not r['notices'] for r in records):raise ValueError('Crate sem arquivo de aviso; conferir manifestos e upstream.')

if __name__=='__main__':fetch(*map(Path,sys.argv[1:4]))
