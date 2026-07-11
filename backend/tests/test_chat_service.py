import asyncio
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Awaitable, TypeVar
from unittest.mock import patch

from backend.app.core.config import Settings
from backend.app.core.database import init_db
from backend.app.core.errors import AppError, ErrorCode, forbidden, session_not_found
from backend.app.core.idempotency import build_fingerprint
from backend.app.repositories import (
    create_session,
    create_user,
    list_messages,
    public_user,
)
from backend.app.services import chat as chat_service

T = TypeVar("T")


def _run(coro: Awaitable[T]) -> T:
    """在测试中同步执行协程，复用 asyncio 的事件循环生命周期管理。"""
    return asyncio.run(coro)


def make_settings(db_path: Path) -> Settings:
    return Settings(
        app_name="yunxun-test",
        app_version="test",
        environment="test",
        debug=False,
        host="127.0.0.1",
        port=8001,
        backend_url="http://127.0.0.1:8001",
        jwt_secret="test-secret",
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
        requests_per_minute=200,
        token_hours=168,
        idempotency_window_seconds=10.0,
    )


class ChatServiceIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "chat-test.db"
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

        self.user_record = create_user("chat_user", "hash", "Chat User", "doubao-test")
        self.user = public_user(self.user_record)
        self.session = create_session(self.user["id"], "新会话", "chat", "doubao-test")

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def _message_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        finally:
            conn.close()

    def test_duplicate_message_within_window_returns_cache_and_does_not_persist_twice(self) -> None:
        first = _run(
            chat_service.create_session_message(
                self.session["id"], self.user, "玉米叶子发黄怎么办", "", "127.0.0.1"
            )
        )
        second = _run(
            chat_service.create_session_message(
                self.session["id"], self.user, "玉米叶子发黄怎么办", "", "127.0.0.1"
            )
        )

        # 两次返回的是同一份缓存结果（user_message id 一致）
        self.assertEqual(first["user_message"]["id"], second["user_message"]["id"])
        # 只落库了一对 user + assistant，共 2 条
        self.assertEqual(self._message_count(), 2)
        self.assertEqual([item["role"] for item in list_messages(self.session["id"])], ["user", "assistant"])

    def test_different_message_bypasses_idempotency(self) -> None:
        _run(chat_service.create_session_message(self.session["id"], self.user, "第一个问题", "", "127.0.0.1"))
        _run(chat_service.create_session_message(self.session["id"], self.user, "第二个问题", "", "127.0.0.1"))

        self.assertEqual(self._message_count(), 4)

    def test_explicit_idempotency_keys_allow_intentional_repeat(self) -> None:
        _run(
            chat_service.create_session_message(
                self.session["id"], self.user, "重复问题", "", "127.0.0.1", "request-key-0001"
            )
        )
        _run(
            chat_service.create_session_message(
                self.session["id"], self.user, "重复问题", "", "127.0.0.1", "request-key-0002"
            )
        )

        self.assertEqual(self._message_count(), 4)

    def test_reusing_key_for_different_content_is_rejected(self) -> None:
        _run(
            chat_service.create_session_message(
                self.session["id"], self.user, "第一条", "", "127.0.0.1", "request-key-shared"
            )
        )

        with self.assertRaises(AppError) as rejected:
            _run(
                chat_service.create_session_message(
                    self.session["id"], self.user, "第二条", "", "127.0.0.1", "request-key-shared"
                )
            )

        self.assertEqual(rejected.exception.code, ErrorCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self._message_count(), 2)

    def test_model_failure_does_not_leave_partial_user_message(self) -> None:
        live_settings = replace(self.settings, api_key="sk-real-example-value")
        with (
            patch("backend.app.services.chat.get_settings", return_value=live_settings),
            patch("backend.app.services.chat.create_chat_reply", side_effect=RuntimeError("provider failed")),
        ):
            with self.assertRaises(AppError):
                _run(
                    chat_service.create_session_message(
                        self.session["id"], self.user, "不会残留", "", "127.0.0.1", "request-key-failure"
                    )
                )

        self.assertEqual(self._message_count(), 0)
        retry_claim = chat_service.idempotency_store.begin(
            owner_id=self.user["id"],
            key_hash=build_fingerprint("chat", self.user["id"], self.session["id"], "request-key-failure"),
            request_fingerprint=build_fingerprint("不会残留", "doubao-test"),
            ttl_seconds=60,
        )
        self.assertEqual(retry_claim.state, "acquired")

    def test_require_session_owner_raises_typed_errors(self) -> None:
        with self.assertRaises(session_not_found("x").__class__) as ctx:
            chat_service.require_session_owner("nonexistent", self.user["id"])
        self.assertEqual(ctx.exception.code, ErrorCode.SESSION_NOT_FOUND)

        other_user = public_user(create_user("other_user", "hash", "Other", "doubao-test"))
        with self.assertRaises(forbidden().__class__) as ctx2:
            chat_service.require_session_owner(self.session["id"], other_user["id"])
        self.assertEqual(ctx2.exception.code, ErrorCode.FORBIDDEN)

    def test_session_stats_aggregates_counts(self) -> None:
        _run(chat_service.create_session_message(self.session["id"], self.user, "统计问题", "", "127.0.0.1"))

        stats = chat_service.build_session_stats(self.user["id"])
        self.assertEqual(stats["total_sessions"], 1)
        self.assertEqual(stats["total_messages"], 2)
        self.assertEqual(stats["sessions_by_feature"], {"chat": 1})

    def test_paginated_session_list_returns_slice_and_total(self) -> None:
        from backend.app.core.pagination import PageParams

        for index in range(3):
            create_session(self.user["id"], f"会话{index}", "chat", "doubao-test")

        sessions, total = chat_service.list_user_sessions_page(self.user["id"], "chat", PageParams(page=1, page_size=2))
        self.assertEqual(total, 4)  # setUp 里的 1 + 3
        self.assertEqual(len(sessions), 2)

    def test_full_session_list_still_works_for_legacy_callers(self) -> None:
        create_session(self.user["id"], "额外会话", "chat", "doubao-test")
        sessions = chat_service.list_user_sessions(self.user["id"], "chat")
        self.assertEqual(len(sessions), 2)


if __name__ == "__main__":
    unittest.main()
