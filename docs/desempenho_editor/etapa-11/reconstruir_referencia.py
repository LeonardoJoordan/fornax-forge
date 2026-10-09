"""Reconstrói a referência inicial numa pasta nova, sem editar o workspace."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('core', 'features'):
        shutil.copytree(ROOT / name, destination / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (destination / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
    steps = []
    for stage in range(10, 0, -1):
        folder = HERE.parent / f'etapa-{stage:02}'
        patch = folder / (f'patch-etapa-{stage:02}.diff' if stage >= 9 else f'alteracoes-etapa-{stage:02}.patch')
        command = ['git', 'apply', '--reverse', '--whitespace=nowarn', str(patch)]
        result = subprocess.run(command, cwd=destination, capture_output=True, text=True)
        steps.append({'stage':stage,'command':command,'returncode':result.returncode,'error':result.stderr})
        if result.returncode:
            raise RuntimeError(f'Reversão da etapa {stage}: {result.stderr}')
    manifest = json.loads((HERE.parent / 'etapa-00/ambiente.json').read_text())
    mismatches = [name for name,digest in manifest['product_sha256'].items()
                  if not (destination/name).is_file() or sha256((destination/name).read_bytes()).hexdigest()!=digest]
    evidence = {'reference':str(destination),'steps':steps,'recorded_files':len(manifest['product_sha256']),
                'mismatches':mismatches}
    (destination/'identidade.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    assert not mismatches, mismatches
    print(f'Referência conferida: {destination}')


if __name__ == '__main__':
    main()
