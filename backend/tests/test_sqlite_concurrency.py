import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend.app.core.database import init_db
from backend.app.repositories import create_session, create_user, list_messages, list_sessions, save_chat_exchange
from backend.tests.test_chat_service import make_settings


class SQLiteConcurrencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.temp_dir.name) / "concurrency.db")
        self.patcher = patch("backend.app.core.database.get_settings", return_value=self.settings)
        self.patcher.start()
        init_db()
        self.user = create_user("concurrent", "hash", "Concurrent", "model")

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_concurrent_session_creation_loses_no_records(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda index: create_session(self.user["id"], f"s{index}", "chat", "model")["id"], range(20)))
        self.assertEqual(len(set(ids)), 20)
        self.assertEqual(len(list_sessions(self.user["id"], "chat")), 20)

    def test_concurrent_exchanges_remain_atomic(self) -> None:
        session = create_session(self.user["id"], "session", "chat", "model")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda index: save_chat_exchange(session["id"], f"u{index}", f"a{index}", "model"), range(20)))
        messages = list_messages(session["id"])
        self.assertEqual(len(messages), 40)
        self.assertEqual(sum(item["role"] == "user" for item in messages), 20)
        self.assertEqual(sum(item["role"] == "assistant" for item in messages), 20)
