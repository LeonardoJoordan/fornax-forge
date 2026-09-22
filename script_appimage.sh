#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

echo "🔧 Montando AppDir e gerando AppImage..."

DIST_DIR="build/main.dist"
APP_DIR="FORNAX_Forge.AppDir"
USR_BIN="$APP_DIR/usr/bin"
# O standalone já contém as bibliotecas e plugins da mesma versão do Qt.
[[ -x "$DIST_DIR/FORNAX_Forge" ]] || { echo "Compile com script_nuitka.py primeiro." >&2; exit 1; }
APP_ICON="assets/icons/fornax-forge_512.png"
[[ -x ./appimagetool && -f "$APP_ICON" ]] || { echo "Faltam appimagetool ou $APP_ICON." >&2; exit 1; }

# Limpa e recria o AppDir
rm -rf "$APP_DIR"
mkdir -p "$USR_BIN"

# Copia tudo do main.dist para usr/bin
echo "📦 Copiando binário e libs do Nuitka..."
cp -r "$DIST_DIR"/. "$USR_BIN/"

# Cria o AppRun
cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/sh
SELF=$(dirname "$(readlink -f "$0")")
export PATH="$SELF/usr/bin:$PATH"
export LD_LIBRARY_PATH="$SELF/usr/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$SELF/usr/bin/PySide6/qt-plugins"
exec "$SELF/usr/bin/FORNAX_Forge" "$@"
EOF
chmod +x "$APP_DIR/AppRun"

# Cria o .desktop
cat > "$APP_DIR/app.desktop" << 'EOF'
[Desktop Entry]
Name=FORNAX Forge
Exec=FORNAX_Forge %F
Icon=app
Type=Application
Categories=Utility;
MimeType=application/x-fornax-template;
EOF

# Metadados MIME para integração no desktop (não instala no host automaticamente).
mkdir -p "$APP_DIR/usr/share/mime/packages"
cp assets/linux/com.leobelisario.FornaxForge.xml "$APP_DIR/usr/share/mime/packages/"

# Licença do aplicativo, autoria, marca e avisos de terceiros.
DOC_DIR="$APP_DIR/usr/share/doc/fornax-forge"
mkdir -p "$DOC_DIR"
cp -r "$USR_BIN/docs/." "$DOC_DIR/"
cp "$USR_BIN"/{LICENSE,NOTICE,AUTHORS.md,TRADEMARKS.md,SECURITY.md} "$DOC_DIR/"

# Ícone do aplicativo
cp "$APP_ICON" "$APP_DIR/app.png"

# Mostra tamanho antes de gerar
echo ""
echo "📊 Tamanho do AppDir: $(du -sh "$APP_DIR" | cut -f1)"

# Gera o AppImage
echo ""
echo "📦 Gerando AppImage..."
ARCH="${ARCH:-$(uname -m)}" ./appimagetool "$APP_DIR" FORNAX_Forge.AppImage

echo ""
echo "✅ FORNAX_Forge.AppImage gerado com sucesso!"
