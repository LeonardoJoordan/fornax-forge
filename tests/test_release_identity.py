"""A versão pode mudar sem criar outra instalação ou biblioteca de modelos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from core.paths import APP_ID, WINDOWS_APP_DIR, get_models_dir
from core.settings import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from core.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class ReleaseIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_installer_version_matches_runtime(self):
        installer = (ROOT / 'instalador.iss').read_text(encoding='utf-8')
        version = re.search(r'^#define AppVersion "([^"]+)"$', installer, re.M)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), APP_VERSION)

    def test_upgrade_keeps_published_windows_identity_and_directory(self):
        # Identidade publicada no instalador 1.0.1, independente da nova versão.
        installer = (ROOT / 'instalador.iss').read_text(encoding='utf-8')
        for line in (
            'AppId={{F0599521-F254-4070-91F0-A13FF6F788DA}',
            '#define AppName "FORNAX Forge"',
            '#define AppExeName "FORNAX_Forge.exe"',
            'DefaultDirName={autopf}\\FORNAX Forge',
            'UsePreviousAppDir=yes',
            'PrivilegesRequired=admin',
            'ArchitecturesInstallIn64BitMode=x64compatible',
        ):
            self.assertIn(line, installer.splitlines())

    def test_data_and_settings_keep_published_names(self):
        self.assertEqual(APP_ID, 'com.leobelisario.FornaxForge')
        self.assertEqual(WINDOWS_APP_DIR, 'FornaxForge')
        self.assertEqual((SETTINGS_ORGANIZATION, SETTINGS_APPLICATION),
                         ('FORNAX Forge', 'MainApp'))
        manifest = (ROOT / 'com.leobelisario.FornaxForge.yaml').read_text()
        self.assertIn(f'app-id: {APP_ID}', manifest.splitlines())

    def test_version_change_reuses_existing_models_and_assets(self):
        previous_version = self.app.applicationVersion()
        self.addCleanup(self.app.setApplicationVersion, previous_version)
        with TemporaryDirectory() as temporary:
            for system, directory in (('Windows', WINDOWS_APP_DIR), ('Linux', APP_ID)):
                with self.subTest(system=system), \
                        patch('core.paths.platform.system', return_value=system), \
                        patch('core.paths._data_home', return_value=Path(temporary) / system):
                    self.app.setApplicationVersion('1.0.1')
                    models = get_models_dir()
                    model = models / 'Meu modelo'
                    model.mkdir()
                    saved = {'model.json': b'{"name":"Meu modelo"}',
                             'background.png': b'asset preservado'}
                    for name, content in saved.items():
                        (model / name).write_bytes(content)
                    self.app.setApplicationVersion(APP_VERSION)
                    reopened = get_models_dir()
                    self.assertEqual(reopened, Path(temporary) / system / directory / 'models')
                    self.assertEqual(reopened, models)
                    for name, content in saved.items():
                        self.assertEqual((reopened / model.name / name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
