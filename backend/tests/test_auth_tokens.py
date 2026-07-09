import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.core.config import Settings
from backend.app.core.database import init_db
from backend.app.core.security import hash_auth_token
from backend.app.repositories import create_auth_token, now_utc
from backend.app.services.auth import get_current_user_from_header, login_user, logout_user, register_user


def make_settings(db_path: Path) -> Settings:
    return Settings(
        app_name="yunxun-test",
        app_version="test",
        environment="test",
        debug=False,
        host="127.0.0.1",
        port=8001,
        backend_url="http://127.0.0.1:8001",
        jwt_secret="test-token-hash-secret",
        api_key="",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        chat_endpoint="doubao-test",
        vision_endpoint="doubao-test",
        available_models_raw="doubao-test",
        database_url=f"sqlite:///{db_path}",
        db_path=str(db_path),
        allowed_origins_raw="http://127.0.0.1:5173",
        cors_methods_raw="GET,POST,PATCH,DELETE,OPTIONS",
        cors_headers_raw="Authorization,Content-Type",
        max_message_length=3000,
        requests_per_minute=20,
        token_hours=168,
    )


class AuthTokenHashingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "yunxun-test.db"
        self.settings = make_settings(self.db_path)
        self.patches = [
            patch("backend.app.core.database.get_settings", return_value=self.settings),
            patch("backend.app.core.security.get_settings", return_value=self.settings),
            patch("backend.app.services.auth.get_settings", return_value=self.settings),
        ]
        for patcher in self.patches:
            patcher.start()
        init_db()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def _stored_token_hashes(self) -> list[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT token_hash FROM auth_tokens ORDER BY created_at ASC").fetchall()
        finally:
            conn.close()
        return [row[0] for row in rows]

    def test_raw_token_is_returned_but_only_hash_is_stored(self) -> None:
        payload = register_user("demo_user", "pass1234", "Demo User")
        raw_token = str(payload["token"])
        stored_hashes = self._stored_token_hashes()

        self.assertEqual(len(stored_hashes), 1)
        self.assertNotEqual(stored_hashes[0], raw_token)
        self.assertEqual(stored_hashes[0], hash_auth_token(raw_token))
        self.assertEqual(len(stored_hashes[0]), 64)

        user = get_current_user_from_header(f"Bearer {raw_token}")
        self.assertEqual(user["username"], "demo_user")

    def test_wrong_expired_and_logged_out_tokens_fail(self) -> None:
        payload = register_user("logout_user", "pass1234", "Logout User")
        raw_token = str(payload["token"])
        user_id = payload["user"]["id"]  # type: ignore[index]

        with self.assertRaises(HTTPException):
            get_current_user_from_header("Bearer wrong-token")

        expired_token = "expired-token-value"
        expired_at = (now_utc() - timedelta(hours=1)).isoformat(timespec="seconds")
        create_auth_token(str(user_id), hash_auth_token(expired_token), expired_at)
        with self.assertRaises(HTTPException):
            get_current_user_from_header(f"Bearer {expired_token}")

        logout_user(f"Bearer {raw_token}", user_id=str(user_id))
        with self.assertRaises(HTTPException):
            get_current_user_from_header(f"Bearer {raw_token}")

    def test_auth_hot_path_does_not_run_global_expired_token_cleanup(self) -> None:
        payload = register_user("hot_path_user", "pass1234", "Hot Path")
        raw_token = str(payload["token"])

        with patch("backend.app.services.auth.cleanup_expired_tokens", side_effect=AssertionError("unexpected cleanup")):
            user = get_current_user_from_header(f"Bearer {raw_token}")

        self.assertEqual(user["username"], "hot_path_user")

    def test_login_runs_expired_token_cleanup_on_session_creation_path(self) -> None:
        register_user("login_user", "pass1234", "Login User")

        with patch("backend.app.services.auth.cleanup_expired_tokens") as cleanup:
            login_user("login_user", "pass1234")

        cleanup.assert_called_once()

    def test_legacy_plaintext_token_schema_is_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy.db"
            settings = make_settings(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        preferred_model TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE auth_tokens (
                        token TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO auth_tokens (token, user_id, expires_at, created_at)
                    VALUES ('legacy-plaintext-token', 'missing-user', '2999-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
                    """
                )
            finally:
                conn.close()

            with patch("backend.app.core.database.get_settings", return_value=settings):
                init_db()

            conn = sqlite3.connect(db_path)
            try:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(auth_tokens)").fetchall()]
                count = conn.execute("SELECT COUNT(*) FROM auth_tokens").fetchone()[0]
            finally:
                conn.close()

            self.assertIn("token_hash", columns)
            self.assertNotIn("token", columns)
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
