import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.app.core.backup import create_backup, restore_backup, validate_database
from backend.app.core.database import init_db
from backend.app.repositories import create_session, create_user
from backend.tests.test_chat_service import make_settings


class BackupRestoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "main.db"
        self.settings = make_settings(self.database)
        self.patcher = patch("backend.app.core.database.get_settings", return_value=self.settings)
        self.patcher.start()
        init_db()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp.cleanup()

    def test_backup_restore_preserves_data_and_version(self) -> None:
        user = create_user("backup-user", "hash", "Backup", "model")
        create_session(user["id"], "kept", "chat", "model")
        backup = create_backup(self.database, self.root / "backups", keep=2)
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute("DELETE FROM chat_sessions")
            conn.commit()
        safety = restore_backup(self.database, backup, self.root / "backups")
        self.assertTrue(safety.exists())
        self.assertEqual(validate_database(self.database), validate_database(backup))
        with closing(sqlite3.connect(self.database)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0], 1)

    def test_corrupt_and_future_backup_are_rejected_without_changing_current(self) -> None:
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"not sqlite")
        before = self.database.read_bytes()
        with self.assertRaises(ValueError):
            restore_backup(self.database, corrupt, self.root / "backups")
        self.assertEqual(self.database.read_bytes(), before)
        future = create_backup(self.database, self.root / "backups")
        with closing(sqlite3.connect(future)) as conn:
            conn.execute("PRAGMA user_version = 999")
            conn.commit()
        with self.assertRaises(ValueError):
            restore_backup(self.database, future, self.root / "backups")

    def test_retention_never_removes_all_backups(self) -> None:
        directory = self.root / "backups"
        for _ in range(3):
            create_backup(self.database, directory, keep=1)
        self.assertEqual(len(list(directory.glob("yunxun-*.db"))), 1)
