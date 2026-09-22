import subprocess
import sys
import platform
import os
import plistlib
import tempfile
from scripts.release_tools import stage, inventory, collect_notices, remove_unused_pdf_plugin
from pathlib import Path

def build_app():
    print("🚀 Iniciando a compilação do FORNAX Forge com Nuitka...")
    
    # Define o ponto de entrada e caminhos
    base_dir = Path(__file__).parent.absolute()
    os.chdir(base_dir)
    build_dir = base_dir / 'build'
    build_dir.mkdir(exist_ok=True)
    from importlib.metadata import distribution, PackageNotFoundError
    for unwanted in ('PySide6', 'PySide6_Addons'):
        try:
            distribution(unwanted)
        except PackageNotFoundError:
            continue
        raise RuntimeError('Use um venv limpo com requirements-build.txt, sem PySide6/Addons.')
    stage_dir = Path(tempfile.mkdtemp(prefix='release-stage-', dir=build_dir))
    stage(stage_dir)
    collect_notices(stage_dir / 'docs' / 'licenses' / 'packages')
    main_file = stage_dir / "main.py"
    exe_name = "FORNAX_Forge"

    # Usa o compilador suportado disponível no sistema.
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone", 
        f"--output-filename={exe_name}",
        f"--report={build_dir / 'compilation-report.xml'}",
        f"--report-template=LicenseReport:{build_dir / 'nuitka-licenses.rst'}",
        f"--output-dir={build_dir}",
        "--plugin-enable=pyside6",
        "--include-qt-plugins=imageformats,platforms",
        "--include-module=encodings",
        "--include-module=sqlite3",
        "--include-package=features",
        "--include-package=core",
        "--include-package=shared",
        "--include-package=pypdf",
        "--include-package=cryptography",
        f"--include-data-dir={stage_dir / 'assets'}=assets",
        f"--include-data-dir={stage_dir / 'docs'}=docs",
        *[f"--include-data-files={stage_dir / name}={name}"
          for name in ('LICENSE', 'NOTICE', 'AUTHORS.md', 'TRADEMARKS.md', 'SECURITY.md')],
        "--nofollow-import-to=*.test_*,*.tests,pytest",
        "--lto=no",                     
        f"--jobs={max(1, int(os.environ.get('FORNAX_BUILD_JOBS', min(4, os.cpu_count() or 1))))}",
        "--show-progress",              # Mostra o que está acontecendo no terminal
        "--follow-imports"
    ]

    # Injeção de argumentos específicos por Sistema Operacional
    sistema = platform.system()
    if sistema == "Windows":
        cmd.insert(cmd.index("--plugin-enable=pyside6") + 1, "--windows-console-mode=disable")
        
        # Verifica se o arquivo .ico existe na raiz
        icon_path = base_dir / "assets" / "icons" / "fornax-forge.ico"
        if icon_path.exists():
            cmd.append(f"--windows-icon-from-ico={icon_path}")
            print("🎨 Ícone do Windows (.ico) detectado e adicionado.")

    elif sistema == "Darwin": # macOS
        cmd.append("--macos-create-app-bundle")
        cmd.append("--macos-app-mode=gui") 
        cmd.append("--static-libpython=no") 
        cmd.append(f"--output-filename={exe_name}") # Garante o nome correto da pasta .app
        
        icon_path = base_dir / "assets" / "icons" / "fornax-forge_1024.png"
        if icon_path.exists():
            cmd.append(f"--macos-app-icon={icon_path}")
            print("🎨 Ícone do macOS (PNG 1024 px) detectado e adicionado.")
    
    cmd.append(str(main_file))
    
    try:
        os.makedirs("build", exist_ok=True)
        subprocess.run(cmd, check=True, cwd=stage_dir)
        standalone = build_dir / ('main.app' if sistema == 'Darwin' else 'main.dist')
        remove_unused_pdf_plugin(standalone)
        if sistema != 'Darwin':
            inventory(standalone, build_dir / 'release-inventory', build_dir / 'compilation-report.xml')
        print(f"\n✅ Compilação Nuitka concluída! O executável base está na pasta 'build'.")
        
        if sistema == "Darwin":
            print("\n🍎 Iniciando a criação do .DMG nativo para macOS...")
            app_path = Path("build") / f"{exe_name}.app"
            dmg_output = "FORNAX_Forge_Instalador.dmg"
            
            # Garante a renomeação caso o Nuitka ignore a flag externa
            if Path("build/main.app").exists():
                if app_path.exists():
                    import shutil
                    shutil.rmtree(app_path)
                os.rename("build/main.app", app_path)

            plist_path = app_path / "Contents" / "Info.plist"
            with plist_path.open("rb") as stream:
                plist = plistlib.load(stream)
            plist["CFBundleDocumentTypes"] = [{
                "CFBundleTypeName": "Modelo FORNAX Forge",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.leobelisario.fornax-template"],
            }]
            plist["UTExportedTypeDeclarations"] = [{
                "UTTypeIdentifier": "com.leobelisario.fornax-template",
                "UTTypeDescription": "Modelo FORNAX Forge",
                "UTTypeConformsTo": ["public.data", "public.archive"],
                "UTTypeTagSpecification": {
                    "public.filename-extension": ["fornax"],
                    "public.mime-type": "application/x-fornax-template",
                },
            }]
            with plist_path.open("wb") as stream:
                plistlib.dump(plist, stream)
            # O inventário deve refletir o bundle final, incluindo a associação.
            inventory(app_path, build_dir / 'release-inventory', build_dir / 'compilation-report.xml')
            
            try:
                subprocess.run([
                    "hdiutil", "create",
                    "-volname", "FORNAX Forge",
                    "-srcfolder", str(app_path),
                    "-ov", "-format", "UDZO",
                    dmg_output
                ], check=True)
                print(f"✅ DMG simplificado gerado com sucesso: {dmg_output}")
            except Exception as e:
                print(f"❌ Erro ao criar o DMG via hdiutil: {e}")
                raise

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erro durante a compilação: {e}")
        raise

if __name__ == "__main__":
    build_app()

# Assim que a instalação terminar, você pode retomar a sequência de compilação normalmente:
#    flatpak-builder --repo=repo --force-clean build-dir com.leobelisario.FornaxForge.yaml
#    flatpak build-bundle repo FORNAX_Forge.flatpak com.leobelisario.FornaxForge
#    flatpak install --reinstall FORNAX_Forge.flatpak
