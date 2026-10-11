"""Títulos ao carregar modelos e recursos da marca nos pacotes de distribuição."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import plistlib
import struct
import importlib.metadata
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon, QImage
from core.branding import APP_DISPLAY_NAME
from core.i18n import initialize_i18n, tr
from core.resources import PROJECT_ROOT, app_icon_path
from script_nuitka import configure_macos_bundle
import script_nuitka
from scripts.release_tools import stage
from tools import install_linux_integration
import test_organogram as fixtures


class AppPresentationTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.OrganogramTest.setUpClass.__func__)
    setUp = fixtures.OrganogramTest.setUp
    editor = fixtures.OrganogramTest.editor

    def test_editor_title_updates_for_named_unnamed_and_starter_models(self):
        document = fixtures.card_document()
        window = self.editor(document)
        for locale in ('pt_BR', 'en_US', 'es_ES'):
            with self.subTest(locale=locale):
                settings = QSettings(str(self.root / 'language.ini'), QSettings.Format.IniFormat)
                settings.setValue('language/locale', locale)
                initialize_i18n(self.app, settings)
                window._load_document_into_scene(document)
                expected = tr('Editor de modelos — {modelo}').format(modelo=document['name'])
                self.assertEqual(window.windowTitle(), expected + ' — ' + APP_DISPLAY_NAME)
                unnamed = dict(document, name='')
                window._load_document_into_scene(unnamed)
                self.assertEqual(window.windowTitle(), tr('Editor de modelos') + ' — ' + APP_DISPLAY_NAME)
                window.load_starter_document(document)
                self.assertEqual(window.windowTitle(), tr('Editor de modelos') + ' — ' + APP_DISPLAY_NAME)
        settings.setValue('language/locale', 'pt_BR')
        initialize_i18n(self.app, settings)

    def test_release_stage_keeps_every_application_icon_unchanged(self):
        output = self.root / 'release-stage'
        stage(output)
        icons = list((PROJECT_ROOT / 'assets/icons').glob('fornax-forge*'))
        self.assertTrue(any(p.suffix == '.icns' for p in icons))
        self.assertTrue(any(p.suffix == '.svg' for p in icons))
        for source in icons:
            with self.subTest(file=source.name):
                target = output / source.relative_to(PROJECT_ROOT)
                self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertFalse((output / 'tests').exists())

    def test_runtime_icons_and_icns_variants_are_readable(self):
        self.assertFalse(QImage(str(app_icon_path())).isNull())
        for extension in ('ico', 'svg'):
            icon = QIcon(str(PROJECT_ROOT / f'assets/icons/fornax-forge.{extension}'))
            for size in (16, 32, 128, 256):
                self.assertFalse(icon.pixmap(size, size).isNull())
        # Os blocos ICNS maiores são PNGs: conferir contra as mesmas exportações.
        data = (PROJECT_ROOT / 'assets/icons/fornax-forge.icns').read_bytes()
        self.assertEqual(data[:4], b'icns')
        self.assertEqual(struct.unpack('>I', data[4:8])[0], len(data))
        offset, sizes = 8, set()
        while offset < len(data):
            length = struct.unpack('>I', data[offset + 4:offset + 8])[0]
            self.assertGreaterEqual(length, 8)
            self.assertLessEqual(offset + length, len(data))
            tag = data[offset:offset + 4]
            if tag in (b'ic07', b'ic08', b'ic09', b'ic10'):
                image = QImage.fromData(data[offset + 8:offset + length])
                self.assertFalse(image.isNull())
                self.assertEqual(image, QImage(str(app_icon_path(image.width()))))
                sizes.add(image.width())
            offset += length
        self.assertEqual(offset, len(data))
        self.assertTrue({128, 256, 512}.issubset(sizes))

    def test_mac_bundle_names_change_without_changing_identity_or_icon(self):
        bundle = self.root / 'FORNAX_Forge.app'
        contents = bundle / 'Contents'
        contents.mkdir(parents=True)
        path = contents / 'Info.plist'
        original = {'CFBundleIdentifier': 'FORNAX_Forge',
                    'CFBundleExecutable': 'FORNAX_Forge',
                    'CFBundleIconFile': 'fornax-forge.icns',
                    'CFBundleDisplayName': 'FORNAX_Forge',
                    'CFBundleName': 'FORNAX_Forge',
                    'CFBundleShortVersionString': '1.1.0'}
        path.write_bytes(plistlib.dumps(original))
        configure_macos_bundle(bundle)
        result = plistlib.loads(path.read_bytes())
        for key in ('CFBundleIdentifier', 'CFBundleExecutable', 'CFBundleIconFile',
                    'CFBundleShortVersionString'):
            self.assertEqual(result[key], original[key])
        self.assertEqual(result['CFBundleName'], APP_DISPLAY_NAME)
        self.assertEqual(result['CFBundleDisplayName'], APP_DISPLAY_NAME)
        self.assertEqual(result['CFBundleDocumentTypes'][0]['LSItemContentTypes'],
                         ['com.leobelisario.fornax-template'])
        self.assertEqual(result['UTExportedTypeDeclarations'][0]['UTTypeTagSpecification']
                         ['public.filename-extension'], ['fornax'])

    def test_linux_integration_installs_scalable_and_raster_icons(self):
        output = self.root / 'desktop-integration'
        with patch.object(install_linux_integration.sys, 'platform', 'linux'), \
                patch.object(install_linux_integration.shutil, 'which', return_value='/usr/bin/mock'), \
                patch.object(install_linux_integration.subprocess, 'run'):
            install_linux_integration.install(output, set_default=False)
        for context, name in (('apps', 'com.leobelisario.FornaxForge'),
                              ('mimetypes', 'application-x-fornax-template')):
            scalable = output / f'icons/hicolor/scalable/{context}/{name}.svg'
            self.assertEqual(scalable.read_bytes(),
                             (PROJECT_ROOT / 'assets/icons/fornax-forge.svg').read_bytes())
            self.assertTrue((output / f'icons/hicolor/256x256/{context}/{name}.png').is_file())

    def test_mac_build_uses_staged_icns_and_signs_final_bundle_before_dmg(self):
        build_root = self.root / 'simulated-build'
        build_root.mkdir()
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[0] == script_nuitka.sys.executable:
                icns = next(value.split('=', 1)[1] for value in command
                            if value.startswith('--macos-app-icon='))
                self.assertEqual(Path(icns).suffix, '.icns')
                self.assertEqual(Path(icns).read_bytes(),
                                 (PROJECT_ROOT / 'assets/icons/fornax-forge.icns').read_bytes())
                contents = build_root / 'build/main.app/Contents'
                contents.mkdir(parents=True)
                (contents / 'Info.plist').write_bytes(plistlib.dumps({
                    'CFBundleIdentifier': 'FORNAX_Forge',
                    'CFBundleIconFile': 'fornax-forge.icns',
                }))
            elif command[0] == '/usr/bin/codesign':
                metadata = plistlib.loads((Path(command[-1]) / 'Contents/Info.plist').read_bytes())
                self.assertEqual(metadata['CFBundleDisplayName'], APP_DISPLAY_NAME)
                self.assertEqual(metadata['CFBundleIdentifier'], 'FORNAX_Forge')
            self.assertTrue(kwargs['check'])

        previous_directory = Path.cwd()
        try:
            with patch.object(script_nuitka, '__file__', str(build_root / 'script_nuitka.py')), \
                    patch.object(script_nuitka.platform, 'system', return_value='Darwin'), \
                    patch('importlib.metadata.distribution', side_effect=importlib.metadata.PackageNotFoundError), \
                    patch.object(script_nuitka, 'collect_notices'), \
                    patch.object(script_nuitka, 'inventory'), \
                    patch.object(script_nuitka.subprocess, 'run', side_effect=run):
                script_nuitka.build_app()
        finally:
            os.chdir(previous_directory)
        self.assertEqual([call[0] for call in calls],
                         [script_nuitka.sys.executable, '/usr/bin/codesign', '/usr/bin/codesign', 'hdiutil'])
        self.assertIn('--sign', calls[1])
        self.assertIn('--verify', calls[2])


if __name__ == '__main__':
    unittest.main()
