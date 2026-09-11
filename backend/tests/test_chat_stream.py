import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.chat import router
from backend.app.core.database import init_db
from backend.app.repositories import create_user, list_messages
from backend.app.services.chat import create_user_session
from backend.tests.test_chat_service import make_settings


def make_chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        kind = ""
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                kind = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        events.append((kind, json.loads(data)))
    return events


class ChatStreamTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "stream.db"
        self.settings = make_settings(self.db_path)
        self.current_settings = self.settings

        def get_test_settings():
            return self.current_settings

        for target in (
            "backend.app.core.database.get_settings",
            "backend.app.services.chat.get_settings",
            "backend.app.services.assistant.get_settings",
        ):
            patcher = patch(target, get_test_settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户", "doubao-test")["id"]
        self.session = create_user_session(self.user_id, "新会话", "chat", "doubao-test")

        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def _enable_ai(self) -> None:
        self.current_settings = replace(self.settings, api_key="test-key")

    def _mock_stream_client(self, chunks, *, fail_after: int | None = None):
        def create(**kwargs):
            def generator():
                for chunk in chunks:
                    yield chunk
                if fail_after is not None:
                    raise RuntimeError("stream interrupted")

            return generator()

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return patch("backend.app.services.assistant.get_client", return_value=client)

    def test_demo_mode_streams_deltas_then_done_and_persists(self) -> None:
        response = self.client.post(
            f"/api/chat/sessions/{self.session['id']}/messages/stream",
            json={"message": "玉米叶子有虫孔怎么办", "model_name": "doubao-test"},
            headers={"X-Idempotency-Key": "req-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = parse_sse(response.text)
        kinds = [kind for kind, _ in events]
        self.assertEqual(kinds[0], "delta")
        self.assertEqual(kinds[-1], "done")

        joined = "".join(data["text"] for kind, data in events if kind == "delta")
        done = events[-1][1]
        self.assertEqual(done["reply"], joined)
        self.assertEqual(done["assistant_message"]["content"], joined)
        messages = list_messages(self.session["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1]["content"], joined)

    def test_idempotent_replay_emits_single_done_event(self) -> None:
        first = self.client.post(
            f"/api/chat/sessions/{self.session['id']}/messages/stream",
            json={"message": "水稻发黄", "model_name": "doubao-test"},
            headers={"X-Idempotency-Key": "req-dup"},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/api/chat/sessions/{self.session['id']}/messages/stream",
            json={"message": "水稻发黄", "model_name": "doubao-test"},
            headers={"X-Idempotency-Key": "req-dup"},
        )
        self.assertEqual(second.status_code, 200)
        events = parse_sse(second.text)
        self.assertEqual([kind for kind, _ in events], ["done"])
        self.assertEqual(len(list_messages(self.session["id"])), 2)

    def test_prepare_phase_failure_returns_http_error(self) -> None:
        response = self.client.post(
            "/api/chat/sessions/missing-session/messages/stream",
            json={"message": "你好", "model_name": "doubao-test"},
        )
        self.assertEqual(response.status_code, 404)

    def test_live_mode_streams_model_deltas(self) -> None:
        self._enable_ai()
        chunks = [make_chunk("先看"), make_chunk("心叶"), make_chunk("和叶片。")]
        with self._mock_stream_client(chunks):
            response = self.client.post(
                f"/api/chat/sessions/{self.session['id']}/messages/stream",
                json={"message": "玉米虫害", "model_name": "doubao-test"},
                headers={"X-Idempotency-Key": "req-live"},
            )
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        joined = "".join(data["text"] for kind, data in events if kind == "delta")
        self.assertEqual(joined, "先看心叶和叶片。")
        self.assertEqual(events[-1][0], "done")
        messages = list_messages(self.session["id"])
        self.assertEqual(messages[-1]["content"], "先看心叶和叶片。")

    def test_mid_stream_error_emits_error_event(self) -> None:
        self._enable_ai()
        chunks = [make_chunk("开头")]
        with self._mock_stream_client(chunks, fail_after=1):
            response = self.client.post(
                f"/api/chat/sessions/{self.session['id']}/messages/stream",
                json={"message": "小麦发黄", "model_name": "doubao-test"},
                headers={"X-Idempotency-Key": "req-fail"},
            )
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        kinds = [kind for kind, _ in events]
        self.assertIn("delta", kinds)
        self.assertEqual(kinds[-1], "error")
        self.assertTrue(events[-1][1]["error"])
        # 中途失败的流不落库任何消息。
        self.assertEqual(list_messages(self.session["id"]), [])

    def test_regenerate_stream_replaces_latest_reply(self) -> None:
        self.client.post(
            f"/api/chat/sessions/{self.session['id']}/messages/stream",
            json={"message": "玉米虫害", "model_name": "doubao-test"},
            headers={"X-Idempotency-Key": "req-regen-1"},
        )
        response = self.client.post(
            f"/api/chat/sessions/{self.session['id']}/regenerate/stream",
            headers={"X-Idempotency-Key": "req-regen-2"},
        )
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        kinds = [kind for kind, _ in events]
        self.assertEqual(kinds[0], "delta")
        self.assertEqual(kinds[-1], "done")
        done = events[-1][1]
        self.assertIn("assistant_message", done)
        self.assertIn("session", done)
        messages = list_messages(self.session["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1]["id"], done["assistant_message"]["id"])

    def test_regenerate_stream_rejects_session_without_exchange(self) -> None:
        response = self.client.post(
            f"/api/chat/sessions/{self.session['id']}/regenerate/stream",
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
