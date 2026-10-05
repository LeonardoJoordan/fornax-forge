"""A migração preserva o histórico ComSoc sem misturá-lo aos logs do FORNAX."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.paths import MIGRATION_FILE, _migrate_data


class LogMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "comsoc"
        self.destination = self.root / "fornax"
        self.destination.mkdir()
        self.archive = self.destination / "legacy_logs" / "ProjetoComSoc"

    def write(self, root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def old_migration(self, *, complete=True, pending=None):
        state = {"complete": complete, "pending": pending or []}
        (self.destination / MIGRATION_FILE).write_text(json.dumps(state), encoding="utf-8")

    def read_state(self):
        return json.loads((self.destination / MIGRATION_FILE).read_text(encoding="utf-8"))

    def test_new_migration_archives_logs_and_still_copies_models(self):
        old_crash = b"[2026-04-10 00:22:47] CRASH OCORRIDO:\nTraceback ComSoc\n"
        self.write(self.source, "logs/crash_log.txt", old_crash)
        self.write(self.source, "models/example/model.json", b'{"name": "Example"}')
        self.write(self.source, "themes/custom.json", b'{"name": "Custom"}')

        _migrate_data(self.source, self.destination)

        self.assertEqual((self.archive / "crash_log.txt").read_bytes(), old_crash)
        self.assertFalse((self.destination / "logs").exists())
        self.assertEqual((self.destination / "models/example/model.json").read_bytes(), b'{"name": "Example"}')
        self.assertTrue((self.destination / "themes/custom.json").is_file())
        self.assertEqual((self.source / "logs/crash_log.txt").read_bytes(), old_crash)
        self.assertTrue(self.read_state()["legacy_logs_separated"])

    def test_completed_migration_separates_exact_copies_and_mixed_logs(self):
        old_crash = b"[2026-04-10] CRASH OCORRIDO:\nTraceback antigo\n"
        old_app = b"[2026-04-10] Evento ComSoc\n"
        new_app = b"[2026-10-05] Evento FORNAX\n"
        for relative, content in (("crash_log.txt", old_crash), ("app.log", old_app), ("app.log.1", old_app)):
            self.write(self.source, f"logs/{relative}", content)
            self.write(self.destination, f"logs/{relative}", content)
        self.write(self.destination, "logs/app.log", old_app + new_app)
        self.old_migration()

        _migrate_data(self.source, self.destination)

        self.assertFalse((self.destination / "logs/crash_log.txt").exists())
        self.assertFalse((self.destination / "logs/app.log.1").exists())
        self.assertEqual((self.destination / "logs/app.log").read_bytes(), new_app)
        self.assertEqual((self.archive / "crash_log.txt").read_bytes(), old_crash)
        self.assertEqual((self.archive / "app.log").read_bytes(), old_app)
        self.assertTrue(self.read_state()["legacy_logs_separated"])

    def test_resumes_old_pending_migration_with_logs_already_copied(self):
        old = b"Historico antigo\n"
        self.write(self.source, "logs/app.log", old)
        self.write(self.destination, "logs/app.log", old)
        self.write(self.source, "models/example/model.json", b"modelo")
        self.old_migration(complete=False, pending=["logs", "models/example"])

        _migrate_data(self.source, self.destination)

        self.assertFalse((self.destination / "logs/app.log").exists())
        self.assertEqual((self.archive / "app.log").read_bytes(), old)
        self.assertEqual((self.destination / "models/example/model.json").read_bytes(), b"modelo")
        self.assertTrue(self.read_state()["complete"])

    def test_unproven_current_logs_are_preserved(self):
        self.write(self.source, "logs/crash_log.txt", b"Historico ComSoc\n")
        current = b"Erro novo do FORNAX\n"
        self.write(self.destination, "logs/crash_log.txt", current)
        self.old_migration()

        _migrate_data(self.source, self.destination)

        self.assertEqual((self.destination / "logs/crash_log.txt").read_bytes(), current)
        self.assertEqual((self.archive / "crash_log.txt").read_bytes(), b"Historico ComSoc\n")

    def test_repeated_calls_do_not_change_archive_or_new_logs(self):
        old = b"Historico ComSoc\n"
        new = b"Registro novo\n"
        self.write(self.source, "logs/app.log", old)
        self.write(self.destination, "logs/app.log", old + new)
        self.old_migration()
        _migrate_data(self.source, self.destination)
        self.write(self.source, "logs/app.log", old + b"Outro registro ComSoc\n")

        _migrate_data(self.source, self.destination)

        self.assertEqual((self.archive / "app.log").read_bytes(), old)
        self.assertEqual((self.destination / "logs/app.log").read_bytes(), new)

    def test_failed_archive_copy_preserves_active_logs_and_can_retry(self):
        old = b"Historico ComSoc\n"
        self.write(self.source, "logs/app.log", old)
        self.write(self.destination, "logs/app.log", old)
        self.old_migration()
        with patch("core.paths._verified_copy", side_effect=OSError("falha de copia")):
            with self.assertRaises(OSError):
                _migrate_data(self.source, self.destination)
        self.assertEqual((self.destination / "logs/app.log").read_bytes(), old)
        self.assertFalse(self.archive.exists())

        _migrate_data(self.source, self.destination)

        self.assertEqual((self.archive / "app.log").read_bytes(), old)
        self.assertFalse((self.destination / "logs/app.log").exists())

    def test_failed_log_rewrite_preserves_all_records_and_can_retry(self):
        old = b"Historico ComSoc\n"
        new = b"Registro FORNAX\n"
        self.write(self.source, "logs/app.log", old)
        active = self.write(self.destination, "logs/app.log", old + new)
        self.old_migration()
        original_replace = Path.replace

        def fail_active_replace(path, target):
            if Path(target) == active:
                raise OSError("falha de publicacao")
            return original_replace(path, target)

        with patch.object(Path, "replace", fail_active_replace):
            with self.assertRaises(OSError):
                _migrate_data(self.source, self.destination)
        self.assertEqual(active.read_bytes(), old + new)
        self.assertEqual((self.archive / "app.log").read_bytes(), old)

        _migrate_data(self.source, self.destination)

        self.assertEqual(active.read_bytes(), new)


if __name__ == "__main__":
    unittest.main()
