#!/usr/bin/env python3
"""Instala associação .fornax por usuário; não inicia o app nem toca em modelos."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys

APP_ID = 'com.leobelisario.FornaxForge'
MIME = 'application/x-fornax-template'
ROOT = Path(__file__).resolve().parents[1]


def desktop_argument(value):
    # Exec usa escape do Desktop Entry, não shell. %% é um percentual literal.
    value = str(value).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return '"' + value.replace('\\', '\\\\') + '"'


def install(data_home, appimage=None, set_default=True):
    if sys.platform != 'linux':
        raise RuntimeError('Esta integração é específica do Linux.')
    required = ['update-mime-database', 'update-desktop-database']
    if set_default:
        required.append('xdg-mime')
    for command in required:
        if not shutil.which(command):
            raise RuntimeError(f'Comando necessário não encontrado: {command}')
    if appimage:
        executable = Path(appimage).expanduser().absolute()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError('O AppImage deve existir e ter permissão de execução.')
        command = desktop_argument(executable)
    else:
        # Não resolve symlinks: preservar o Python do ambiente virtual.
        executable = ROOT / '.venv/bin/python'
        if not executable.is_file():
            raise RuntimeError('Ambiente .venv ausente; crie-o ou informe --appimage.')
        command = f'{desktop_argument(executable)} {desktop_argument(ROOT / "main.py")}'
    desktop = (
        '[Desktop Entry]\nType=Application\nName=FORNAX Forge\n'
        'Comment=Geração de material personalizado em lote\n'
        f'Exec={command} %F\nIcon={APP_ID}\nTerminal=false\n'
        f'Categories=Graphics;\nMimeType={MIME};\n'
    )
    data_home = Path(data_home).expanduser().absolute()
    applications = data_home / 'applications'
    packages = data_home / 'mime/packages'
    applications.mkdir(parents=True, exist_ok=True)
    packages.mkdir(parents=True, exist_ok=True)
    target = applications / f'{APP_ID}.desktop'
    if target.exists() and target.read_text() != desktop:
        # Preservar a associação local anterior, sem sobrescrever seu backup.
        backup = target.with_suffix('.desktop.before-fornax-integration')
        if not backup.exists():
            shutil.copy2(target, backup)
    target.write_text(desktop, encoding='utf-8')
    shutil.copy2(ROOT / 'assets/linux' / f'{APP_ID}.xml', packages / f'{APP_ID}.xml')
    for size in (32, 48, 64, 128, 256, 512):
        icon = ROOT / 'assets/icons' / f'fornax-forge_{size}.png'
        for context, name in [('apps', APP_ID), ('mimetypes', 'application-x-fornax-template')]:
            directory = data_home / 'icons/hicolor' / f'{size}x{size}' / context
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(icon, directory / f'{name}.png')
    subprocess.run(['update-mime-database', str(data_home / 'mime')], check=True)
    subprocess.run(['update-desktop-database', str(applications)], check=True)
    cache = shutil.which('gtk-update-icon-cache')
    if cache:
        subprocess.run([cache, '--force', '--ignore-theme-index', str(data_home / 'icons/hicolor')], check=True)
    if set_default:
        subprocess.run(['xdg-mime', 'default', target.name, MIME], check=True)
    print(f'Integração instalada em {data_home}; .fornax.bak não é associado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appimage', help='AppImage instalado em caminho permanente')
    parser.add_argument('--data-home', default=os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    parser.add_argument('--no-default', action='store_true', help='Não muda o aplicativo padrão (validação isolada)')
    args = parser.parse_args()
    install(args.data_home, args.appimage, not args.no_default)
