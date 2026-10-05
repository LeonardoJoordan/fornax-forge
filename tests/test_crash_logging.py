"""Persistência de crashes e confirmação fiel do destino mostrado no diálogo."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.diagnostic_logs import CrashLogWriteError, append_diagnostic_log, save_crash_report
from core.paths import APP_ID, get_fallback_logs_dir
from features.workspace.main import global_exception_handler


class CrashLoggingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.primary = self.root / "primary"
        self.fallback = self.root / "persistent-fallback"
        self.primary.mkdir()
        self.fallback.mkdir()
        self.primary_lookup = self.enterContext(patch(
            "core.diagnostic_logs.get_logs_dir", return_value=self.primary,
        ))
        self.fallback_lookup = self.enterContext(patch(
            "core.diagnostic_logs.get_fallback_logs_dir", return_value=self.fallback,
        ))

    def exception(self, exception_type=RuntimeError):
        try:
            raise exception_type("conteudo operacional confidencial")
        except exception_type:
            return sys.exc_info()

    def test_two_crashes_append_without_losing_the_first_report(self):
        for exception_type in (RuntimeError, AttributeError):
            kind, _, trace = self.exception(exception_type)
            path = save_crash_report(kind, trace)
        self.assertEqual(path, self.primary / "crash_log.txt")
        content = path.read_text(encoding="utf-8")
        self.assertIn("Exceção não tratada: RuntimeError", content)
        self.assertIn("Exceção não tratada: AttributeError", content)
        self.assertIn("test_crash_logging.py", content)
        self.assertNotIn("conteudo operacional confidencial", content)
        self.assertNotIn(str(Path(__file__).resolve()), content)
        self.fallback_lookup.assert_not_called()

    def test_read_only_primary_file_uses_persistent_fallback(self):
        original_open = Path.open

        def read_only_primary(path, *args, **kwargs):
            if path == self.primary / "crash_log.txt":
                raise PermissionError("arquivo sem permissao de escrita")
            return original_open(path, *args, **kwargs)

        kind, _, trace = self.exception()
        with patch.object(Path, "open", read_only_primary):
            path = save_crash_report(kind, trace)
        self.assertEqual(path, self.fallback / "crash_log.txt")
        self.assertIn("RuntimeError", path.read_text(encoding="utf-8"))

    def test_failure_resolving_primary_directory_uses_fallback(self):
        self.primary_lookup.side_effect = OSError("falha na pasta ou migracao")
        kind, _, trace = self.exception()
        path = save_crash_report(kind, trace)
        self.assertEqual(path, self.fallback / "crash_log.txt")
        self.assertTrue(path.is_file())

    def test_unexpected_primary_logging_error_uses_fallback(self):
        self.primary_lookup.side_effect = ValueError("marcador de migracao invalido")
        kind, _, trace = self.exception()
        self.assertEqual(save_crash_report(kind, trace), self.fallback / "crash_log.txt")

    def test_failure_flushing_primary_to_disk_uses_fallback(self):
        kind, _, trace = self.exception()
        with patch("core.diagnostic_logs.os.fsync", side_effect=[OSError("falha no disco"), None]) as sync:
            self.assertEqual(save_crash_report(kind, trace), self.fallback / "crash_log.txt")
            self.assertEqual(sync.call_count, 2)
        self.assertTrue((self.fallback / "crash_log.txt").is_file())

    def test_failure_in_both_destinations_is_not_suppressed(self):
        self.primary_lookup.side_effect = PermissionError("principal bloqueado")
        self.fallback_lookup.side_effect = OSError("alternativo indisponivel")
        kind, _, trace = self.exception()
        with self.assertRaises(CrashLogWriteError) as failure:
            save_crash_report(kind, trace)
        self.assertIsInstance(failure.exception.primary_error, PermissionError)
        self.assertIsInstance(failure.exception.fallback_error, OSError)

    def test_report_survives_immediate_process_exit(self):
        script = """
import os
from pathlib import Path
import sys
import core.paths
from core.diagnostic_logs import save_crash_report
core.paths._data_home = lambda: Path(sys.argv[1])
try:
    raise RuntimeError('valor que nao deve aparecer no arquivo')
except RuntimeError:
    kind, _, trace = sys.exc_info()
    save_crash_report(kind, trace)
os._exit(1)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.root / "child-data")], capture_output=True)
        self.assertEqual(result.returncode, 1, result.stderr.decode(errors="replace"))
        paths = list((self.root / "child-data").glob("*/logs/crash_log.txt"))
        self.assertEqual(len(paths), 1)
        content = paths[0].read_text(encoding="utf-8")
        self.assertIn("Exceção não tratada: RuntimeError", content)
        self.assertNotIn("valor que nao deve aparecer no arquivo", content)

    def test_emergency_directory_is_outside_temporary_cleanup(self):
        with patch("core.paths.platform.system", return_value="Linux"), patch.dict(
            os.environ, {"XDG_STATE_HOME": str(self.root / "state")},
        ):
            path = get_fallback_logs_dir()
        self.assertEqual(path, self.root / "state" / APP_ID / "logs")
        self.assertTrue(path.is_dir())

    def test_operational_log_sanitization_and_rotation_still_work(self):
        first = append_diagnostic_log("app.log", "Operacao /home/usuario/arquivo.png\nDados da linha", max_bytes=1)
        append_diagnostic_log("app.log", "Segunda operacao", max_bytes=1)
        backup = first.with_name("app.log.1").read_text(encoding="utf-8")
        self.assertIn("[caminho omitido]", backup)
        self.assertNotIn("Dados da linha", backup)
        self.assertIn("Segunda operacao", first.read_text(encoding="utf-8"))

    def test_dialog_confirms_a_file_saved_before_being_displayed(self):
        kind, value, trace = self.exception()
        with patch("features.workspace.main.QMessageBox") as box:
            message = box.return_value

            def check_saved_before_dialog():
                self.assertIn("RuntimeError", (self.primary / "crash_log.txt").read_text(encoding="utf-8"))

            message.exec.side_effect = check_saved_before_dialog
            global_exception_handler(kind, value, trace)
            information = message.setInformativeText.call_args.args[0]
            self.assertIn(str(self.primary / "crash_log.txt"), information)
            message.exec.assert_called_once()

    def test_dialog_shows_the_actual_fallback_path(self):
        self.primary_lookup.side_effect = PermissionError("sem permissao")
        kind, value, trace = self.exception()
        with patch("features.workspace.main.QMessageBox") as box:
            global_exception_handler(kind, value, trace)
            information = box.return_value.setInformativeText.call_args.args[0]
            self.assertIn(str(self.fallback / "crash_log.txt"), information)
            self.assertNotIn(str(self.primary / "crash_log.txt"), information)

    def test_dialog_reports_unsaved_crash_and_keeps_original_details(self):
        self.primary_lookup.side_effect = PermissionError("principal bloqueado")
        self.fallback_lookup.side_effect = OSError("alternativo indisponivel")
        kind, value, trace = self.exception()
        with patch("features.workspace.main.QMessageBox") as box:
            global_exception_handler(kind, value, trace)
            message = box.return_value
            information = message.setInformativeText.call_args.args[0]
            details = message.setDetailedText.call_args.args[0]
            self.assertIn("Não foi possível salvar", information)
            self.assertNotIn("foram salvos", information)
            self.assertIn("RuntimeError: conteudo operacional confidencial", details)
            self.assertIn("principal bloqueado", details)
            self.assertIn("alternativo indisponivel", details)
            message.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
