import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.app.core.database import SCHEMA_VERSION, init_db, migrate_schema
from backend.tests.test_chat_service import make_settings


class DatabaseMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "migration.db"
        self.settings = make_settings(self.db_path)
        self.patcher = patch("backend.app.core.database.get_settings", return_value=self.settings)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_empty_database_reaches_current_version(self) -> None:
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"users", "chat_sessions", "chat_messages", "auth_tokens", "idempotency_requests"} <= tables)

    def test_repeated_startup_does_not_reapply_migration(self) -> None:
        init_db()
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(migrate_schema(conn)[1], [])

    def test_legacy_data_is_preserved_but_plain_tokens_are_invalidated(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript("""
            CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
              display_name TEXT NOT NULL, preferred_model TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE auth_tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
            INSERT INTO users VALUES ('u','name','hash','Name','model','now','now');
            INSERT INTO auth_tokens VALUES ('raw-token','u','later','now');
            """)
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_tokens").fetchone()[0], 0)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(auth_tokens)")}
        self.assertIn("token_hash", columns)

    def test_future_version_is_rejected(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            with self.assertRaises(sqlite3.DatabaseError):
                migrate_schema(conn)

    def test_failed_migration_does_not_advance_version(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, patch(
            "backend.app.core.database._apply_schema_v1", side_effect=sqlite3.OperationalError("forced")
        ):
            with self.assertRaises(sqlite3.OperationalError):
                migrate_schema(conn)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
