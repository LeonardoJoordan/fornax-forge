"""Preserva avisos dos arquivos de fontes Qt previamente verificados."""
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
from release_tools import sha256


def extract(sources,output):
    manifest=json.loads((sources/'qt-sources.json').read_text())
    output.mkdir(parents=True,exist_ok=True)
    count=0
    for record in manifest:
        archive=sources/record['file']
        if sha256(archive)!=record['sha256']:raise ValueError('Fonte difere do manifesto verificado.')
        with tarfile.open(archive) as bundle:
            for member in bundle:
                path=PurePosixPath(member.name)
                lower=path.name.lower()
                legal=(lower.startswith(('license','copying','copyright','notice'))
                       or lower=='qt_attribution.json')
                if not member.isfile() or not legal:continue
                if path.is_absolute() or '..' in path.parts or member.size>2_000_000:
                    raise ValueError('Nome ou tamanho de aviso inválido no arquivo de fontes.')
                destination=output/Path(*path.parts)
                destination.parent.mkdir(parents=True,exist_ok=True)
                with bundle.extractfile(member) as stream:
                    destination.write_bytes(stream.read())
                count+=1
    (output/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'{count} arquivos de avisos/atribuição preservados; revisão por componente continua necessária.')

if __name__=='__main__':extract(Path(sys.argv[1]),Path(sys.argv[2]))
