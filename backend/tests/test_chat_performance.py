import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.core.database import init_db
from backend.app.repositories import delete_session, list_messages_page
from backend.tests.test_chat_service import make_settings


class ChatDataScaleTestCase(unittest.TestCase):
    def test_ten_thousand_messages_use_bounded_stable_page_and_indexed_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "scale.db"
            settings = make_settings(db_path)
            with patch("backend.app.core.database.get_settings", return_value=settings):
                init_db()
                conn = sqlite3.connect(db_path)
                sessions = [(f"s{i:03}", "u1", "title", "chat", "model", f"2026-01-01T00:{i // 60:02}:{i % 60:02}+00:00", f"2026-01-01T00:{i // 60:02}:{i % 60:02}+00:00") for i in range(100)]
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", ("u1", "user", "hash", "User", "model", "2026", "2026"))
                conn.executemany("INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?, ?)", sessions)
                messages = []
                for session_index in range(100):
                    for message_index in range(100):
                        stamp = f"2026-01-02T00:{message_index // 60:02}:{message_index % 60:02}.{session_index:03}+00:00"
                        messages.append((f"m{session_index:03}-{message_index:03}", f"s{session_index:03}", "user", "content", stamp))
                conn.executemany("INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", messages)
                conn.commit()
                conn.close()

                with patch("backend.app.core.database.get_settings", return_value=settings):
                    first, has_more = list_messages_page("s000", limit=25)
                    cursor = (first[0]["created_at"], first[0]["id"])
                    second, _ = list_messages_page("s000", limit=25, cursor=cursor)
                    self.assertTrue(has_more)
                    self.assertEqual(len(first), 25)
                    self.assertFalse({item["id"] for item in first} & {item["id"] for item in second})
                    delete_session("s000")
                conn = sqlite3.connect(db_path)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id='s000'").fetchone()[0], 0)
                indexes = {row[1] for row in conn.execute("PRAGMA index_list('chat_messages')")}
                self.assertIn("idx_chat_messages_session_created", indexes)
                conn.close()
