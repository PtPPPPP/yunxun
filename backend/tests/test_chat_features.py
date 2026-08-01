import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.app.core.database import init_db
from backend.app.core.errors import AppError
from backend.app.repositories import (
    create_session,
    create_user,
    list_messages,
    list_sessions,
    public_user,
    save_chat_exchange,
)
from backend.app.services import chat as chat_service
from backend.tests.test_chat_service import make_settings


class ChatFeaturesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "features.db"
        self.settings = make_settings(self.db_path)
        self.patches = [
            patch("backend.app.core.database.get_settings", return_value=self.settings),
            patch("backend.app.services.chat.get_settings", return_value=self.settings),
        ]
        for patcher in self.patches:
            patcher.start()
        init_db()
        chat_service.idempotency_store.reset()
        chat_service.rate_limiter.reset()
        record = create_user("feature-user", "hash", "Feature User", "doubao-test")
        self.user = public_user(record)
        self.session = create_session(self.user["id"], "session-title", "chat", "doubao-test")

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_pin_and_unpin_are_owned_and_sorted(self) -> None:
        other_user = public_user(create_user("feature-other", "hash", "Other User", "doubao-test"))
        create_session(other_user["id"], "other-session", "chat", "doubao-test")
        pinned = chat_service.pin_user_session(self.session["id"], self.user["id"], True)
        self.assertTrue(pinned["is_pinned"])
        repeated = chat_service.pin_user_session(self.session["id"], self.user["id"], True)
        self.assertEqual(repeated["pinned_at"], pinned["pinned_at"])
        sessions = list_sessions(self.user["id"], "chat")
        self.assertEqual(sessions[0]["id"], self.session["id"])
        chat_service.pin_user_session(self.session["id"], self.user["id"], False)
        self.assertFalse(list_sessions(self.user["id"], "chat")[0]["is_pinned"])
        with self.assertRaises(AppError):
            chat_service.pin_user_session(self.session["id"], other_user["id"], True)

    def test_clear_keeps_session_and_pin_but_removes_messages(self) -> None:
        chat_service.pin_user_session(self.session["id"], self.user["id"], True)
        save_chat_exchange(self.session["id"], "question", "answer", "doubao-test")
        result = chat_service.clear_user_session(self.session["id"], self.user["id"])
        self.assertEqual(result["cleared_count"], 2)
        self.assertEqual(list_messages(self.session["id"]), [])
        self.assertTrue(result["session"]["is_pinned"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0], 1)

    def test_regenerate_replaces_latest_assistant_without_duplicate_user(self) -> None:
        save_chat_exchange(self.session["id"], "question", "old answer", "doubao-test")
        result = asyncio.run(chat_service.regenerate_latest_reply(self.session["id"], self.user, "127.0.0.1"))
        messages = list_messages(self.session["id"])
        self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
        self.assertEqual(result["assistant_message"]["id"], messages[-1]["id"])
        self.assertNotEqual(messages[-1]["content"], "old answer")

    def test_regenerate_failure_preserves_old_reply(self) -> None:
        save_chat_exchange(self.session["id"], "question", "old answer", "doubao-test")
        live_settings = self.settings.__class__(**{**self.settings.__dict__, "api_key": "sk-real-example-value"})
        with patch("backend.app.services.chat.get_settings", return_value=live_settings), patch(
            "backend.app.services.chat.create_chat_reply", new=AsyncMock(side_effect=RuntimeError("provider failed"))
        ):
            with self.assertRaises(AppError):
                asyncio.run(chat_service.regenerate_latest_reply(self.session["id"], self.user, "127.0.0.1"))
        self.assertEqual(list_messages(self.session["id"])[-1]["content"], "old answer")


if __name__ == "__main__":
    unittest.main()
