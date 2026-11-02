"""Platform defaults must respect explicit Qt settings and be safe to repeat."""

import os
import unittest
from unittest.mock import patch

from core.qt_bootstrap import configure_qt_environment


class QtBootstrapTest(unittest.TestCase):
    def test_windows_defaults_to_freetype_and_can_be_initialized_twice(self):
        with patch('core.qt_bootstrap.sys.platform', 'win32'), patch.dict(os.environ, {}, clear=True):
            configure_qt_environment()
            configure_qt_environment()
            self.assertEqual(os.environ['QT_QPA_PLATFORM'], 'windows:fontengine=freetype')

    def test_explicit_platform_is_preserved(self):
        for platform in ('offscreen', 'windows', 'windows:fontengine=directwrite', ''):
            with self.subTest(platform=platform), \
                    patch('core.qt_bootstrap.sys.platform', 'win32'), \
                    patch.dict(os.environ, {'QT_QPA_PLATFORM': platform}, clear=True):
                configure_qt_environment()
                self.assertEqual(os.environ['QT_QPA_PLATFORM'], platform)

    def test_other_operating_systems_keep_their_platform_default(self):
        for platform in ('linux', 'darwin'):
            with self.subTest(platform=platform), \
                    patch('core.qt_bootstrap.sys.platform', platform), \
                    patch.dict(os.environ, {}, clear=True):
                configure_qt_environment()
                self.assertNotIn('QT_QPA_PLATFORM', os.environ)
