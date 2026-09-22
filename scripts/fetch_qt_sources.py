"""Arquiva fontes oficiais Qt/PySide e verifica seus SHA-256. Uso no release."""
import json
from pathlib import Path
import re
import subprocess
import sys

from release_tools import sha256

VERSION='6.11.0'
BASE=f'https://download.qt.io/official_releases/qt/6.11/{VERSION}/submodules/'
SOURCES={f'{name}-everywhere-src-{VERSION}.tar.xz':BASE
         for name in ('qtbase','qtsvg','qtwayland','qtimageformats')}
SOURCES[f'pyside-setup-everywhere-src-{VERSION}.tar.xz']=(
    f'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{VERSION}-src/')


def download(url,path):
    subprocess.run(['curl','--fail','--location','--silent','--show-error',
                    '--proto','=https','--proto-redir','=https',
                    '--connect-timeout','15','--max-time','300',url,'-o',str(path)],check=True)


def fetch(output):
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,base in SOURCES.items():
        checksum=output/(name+'.sha256')
        download(base+name+'.sha256',checksum)
        expected=checksum.read_text().split()[0].lower()
        if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Checksum oficial inválido.')
        archive=output/name
        if not archive.exists() or sha256(archive)!=expected:
            temporary=output/(name+'.download')
            download(base+name,temporary)
            if sha256(temporary)!=expected:raise ValueError(f'Fonte adulterada/incompleta: {name}')
            temporary.replace(archive)
        records.append({'file':name,'url':base+name,'sha256':expected})
        (output/'qt-sources.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
        print(f'Verificado: {name}',flush=True)
    return records

if __name__=='__main__':fetch(Path(sys.argv[1]))
