import base64
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.app.core.database import init_db
from backend.app.core.errors import AppError, ErrorCode
from backend.app.model_config_repository import get_model_config, list_model_configs
from backend.app.repositories import create_user
from backend.app.repositories import get_session
from backend.app.services.chat import create_session_message, create_user_session
from backend.app.services.model_configs import (
    create_user_model_config,
    delete_user_model_config,
    resolve_runtime_model_config,
    set_user_default_model_config,
    test_unsaved_model_config,
    update_user_model_config,
    verify_rate_limiter,
)
from backend.tests.test_config_runtime import make_settings


TEST_MASTER_KEY = base64.urlsafe_b64encode(b"m" * 32).decode("ascii")


class ModelConfigsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "byok.db"
        self.settings = make_settings(
            db_path=str(self.db_path),
            byok_enabled=True,
            byok_allow_persistence=True,
            credential_encryption_key=TEST_MASTER_KEY,
            byok_allowed_providers_raw="openai,deepseek",
        )
        self.patchers = [
            patch("backend.app.core.database.get_settings", return_value=self.settings),
            patch("backend.app.services.model_configs.get_settings", return_value=self.settings),
            patch("backend.app.core.byok_security.get_settings", return_value=self.settings),
            patch("backend.app.services.chat.get_settings", return_value=self.settings),
            patch(
                "backend.app.services.model_configs.validate_provider_base_url",
                side_effect=lambda provider, url: url or ("https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com"),
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
        init_db()
        self.user = create_user("byok-user", "hash", "BYOK User", "system-model")
        self.other = create_user("other-user", "hash", "Other User", "system-model")

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def create_payload(name: str = "OpenAI", key: str = "sk-test-secret-value") -> SimpleNamespace:
        return SimpleNamespace(
            provider="openai",
            display_name=name,
            model="gpt-test",
            base_url="https://api.openai.com/v1",
            api_key=key,
            is_default=False,
        )

    def test_create_encrypts_key_and_response_is_redacted(self) -> None:
        raw_key = "sk-never-store-in-plaintext"
        public = create_user_model_config(self.user["id"], self.create_payload(key=raw_key))
        stored = get_model_config(public["id"])

        self.assertNotIn(raw_key, str(public))
        self.assertNotIn("encrypted_api_key", public)
        self.assertNotIn(raw_key.encode(), bytes(stored["encrypted_api_key"]))
        with closing(sqlite3.connect(self.db_path)) as conn:
            database_dump = "\n".join(conn.iterdump())
        self.assertNotIn(raw_key, database_dump)

    def test_user_isolation_default_and_delete_lifecycle(self) -> None:
        first = create_user_model_config(self.user["id"], self.create_payload("First"))
        second = create_user_model_config(self.user["id"], self.create_payload("Second", "sk-second-secret"))

        set_user_default_model_config(self.user["id"], second["id"])
        records = list_model_configs(self.user["id"])
        self.assertEqual(sum(bool(item["is_default"]) for item in records), 1)
        self.assertTrue(get_model_config(second["id"])["is_default"])
        with self.assertRaises(AppError) as rejected:
            delete_user_model_config(self.other["id"], first["id"])
        self.assertEqual(rejected.exception.code, ErrorCode.MODEL_CONFIG_NOT_FOUND)

        delete_user_model_config(self.user["id"], second["id"])
        self.assertIsNone(get_model_config(second["id"]))
        self.assertTrue(get_model_config(first["id"])["is_default"])

    def test_replace_key_requires_explicit_flag_and_invalidates_old_ciphertext(self) -> None:
        created = create_user_model_config(self.user["id"], self.create_payload())
        before = bytes(get_model_config(created["id"])["encrypted_api_key"])
        ambiguous = SimpleNamespace(
            provider="openai",
            display_name="Updated",
            model="gpt-test",
            base_url="https://api.openai.com/v1",
            api_key="sk-new-secret-value",
            replace_api_key=False,
            is_enabled=True,
        )
        with self.assertRaises(AppError):
            update_user_model_config(self.user["id"], created["id"], ambiguous)
        ambiguous.replace_api_key = True
        update_user_model_config(self.user["id"], created["id"], ambiguous)
        after = bytes(get_model_config(created["id"])["encrypted_api_key"])
        self.assertNotEqual(before, after)

    def test_runtime_resolution_prefers_explicit_then_default(self) -> None:
        first = create_user_model_config(self.user["id"], self.create_payload("Default"))
        second = create_user_model_config(self.user["id"], self.create_payload("Explicit", "sk-explicit-secret"))
        default_runtime = resolve_runtime_model_config(self.user["id"], None, None)
        explicit_runtime = resolve_runtime_model_config(self.user["id"], second["id"], first["id"])
        self.assertEqual(default_runtime["id"], first["id"])
        self.assertEqual(explicit_runtime["id"], second["id"])
        self.assertEqual(explicit_runtime["api_key"], "sk-explicit-secret")

    def test_connection_test_uses_fixed_prompt_without_persisting_key(self) -> None:
        provider_call = AsyncMock(return_value=("OK", 12))
        with patch("backend.app.services.model_configs.call_chat_completion", provider_call):
            result = __import__("asyncio").run(
                test_unsaved_model_config("user", "127.0.0.1", self.create_payload())
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(list_model_configs(self.user["id"]), [])
        self.assertEqual(provider_call.await_args.kwargs["history"], [{"role": "user", "content": "Reply with OK."}])

    def test_connection_test_has_independent_rate_limit(self) -> None:
        limited_settings = replace(self.settings, byok_test_requests_per_minute=1)
        provider_call = AsyncMock(return_value=("OK", 12))
        verify_rate_limiter.reset()
        with (
            patch("backend.app.services.model_configs.get_settings", return_value=limited_settings),
            patch("backend.app.services.model_configs.call_chat_completion", provider_call),
        ):
            __import__("asyncio").run(test_unsaved_model_config("limited-user", "127.0.0.1", self.create_payload()))
            with self.assertRaises(AppError) as rejected:
                __import__("asyncio").run(
                    test_unsaved_model_config("limited-user", "127.0.0.1", self.create_payload())
                )
        self.assertEqual(rejected.exception.code, ErrorCode.RATE_LIMITED)
        verify_rate_limiter.reset()

    def test_chat_uses_owned_config_and_delete_clears_session_binding(self) -> None:
        created = create_user_model_config(self.user["id"], self.create_payload())
        session = create_user_session(
            self.user["id"], "BYOK chat", "chat", "", created["id"]
        )
        provider_call = AsyncMock(return_value=("provider reply", 10))
        user = {**self.user, "preferred_model": "system-model"}
        with patch("backend.app.services.chat.call_chat_completion", provider_call):
            result = __import__("asyncio").run(
                create_session_message(
                    session["id"], user, "hello", "", "127.0.0.1", model_config_id=created["id"]
                )
            )
        self.assertEqual(result["reply"], "provider reply")
        self.assertEqual(provider_call.await_args.kwargs["api_key"], "sk-test-secret-value")
        self.assertEqual(result["session"]["model_config_id"], created["id"])

        delete_user_model_config(self.user["id"], created["id"])
        self.assertIsNone(get_session(session["id"])["model_config_id"])

    def test_explicit_system_model_can_bypass_user_default(self) -> None:
        create_user_model_config(self.user["id"], self.create_payload())
        session = create_user_session(self.user["id"], "System chat", "chat", "system-model", None)
        self.assertIsNone(session["model_config_id"])
        self.assertEqual(session["model_name"], "system-model")

    def test_user_delete_cascades_model_credentials(self) -> None:
        created = create_user_model_config(self.user["id"], self.create_payload())
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM users WHERE id = ?", (self.user["id"],))
            conn.commit()
        self.assertIsNone(get_model_config(created["id"]))


if __name__ == "__main__":
    unittest.main()
