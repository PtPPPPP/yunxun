"""单 worker Uvicorn + 真实 TCP；以同步信号验证阻塞业务与事件循环隔离。"""

import logging
import os
import socket
import sqlite3
import tempfile
import threading
import unittest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import uvicorn

from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.request_context import get_request_id
from backend.app.services import auth as auth_service


WAIT_SECONDS = 5
PASSWORD = "Concurrency123!"


class ServiceConcurrencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "concurrency.db"
        environment = patch.dict(os.environ, {
            "YUNXUN_DB_PATH": str(self.db_path), "YUNXUN_ENV": "test",
            "YUNXUN_JWT_SECRET": "service-concurrency-test-secret",
            "YUNXUN_COOKIE_SECURE": "false",
            "YUNXUN_ALLOWED_ORIGINS": "http://127.0.0.1:5173",
        })
        environment.start()
        self.addCleanup(environment.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        self.limiter = InMemoryRateLimiter()
        limiter_patch = patch.object(auth, "auth_rate_limiter", self.limiter)
        limiter_patch.start()
        self.addCleanup(limiter_patch.stop)
        # 模块级 app 的首次初始化也必须使用临时库。
        from backend.app.main import create_app

        started = threading.Event()

        class SignaledServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                started.set()

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        self.addCleanup(listener.close)
        self.base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        self.server = SignaledServer(uvicorn.Config(
            create_app(), host="127.0.0.1", lifespan="off", workers=1,
            access_log=False, log_config=None,
        ))
        errors = []

        def serve():
            try:
                self.server.run(sockets=[listener])
            except BaseException as exc:
                errors.append(exc)
            finally:
                started.set()

        self.server_thread = threading.Thread(target=serve, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)
        self.assertTrue(started.wait(WAIT_SECONDS), "Uvicorn 未完成启动")
        self.assertEqual(errors, [])
        self.assertTrue(self.server.started)
        self.client = httpx.Client(base_url=self.base_url, timeout=WAIT_SECONDS, trust_env=False)
        self.addCleanup(self.client.close)
        login = self.client.post("/api/auth/guest")
        self.assertEqual(login.status_code, 200, login.text)
        self.token = login.json()["token"]
        self.user_id = login.json()["user"]["id"]
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]

    def stop_server(self):
        self.server.should_exit = True
        self.server_thread.join(WAIT_SECONDS * 2)
        self.assertFalse(self.server_thread.is_alive(), "Uvicorn 未正常停止")

    def request(self, method, path, *, request_id, **kwargs):
        # 并发请求不共享可变的 Cookie jar 或 httpx.Client。
        headers = {"Authorization": f"Bearer {self.token}", "X-Request-ID": request_id}
        headers.update(kwargs.pop("headers", {}))
        with httpx.Client(base_url=self.base_url, timeout=WAIT_SECONDS, trust_env=False) as client:
            return client.request(method, path, headers=headers, **kwargs)

    def assert_live(self, request_id):
        response = self.request("GET", "/health/live", request_id=request_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["request_id"], request_id)
        self.assertEqual(response.headers["X-Request-ID"], request_id)

    def locked_write(self, *, fail_second_insert=False):
        writer_started = threading.Event()
        events = []
        events_lock = threading.Lock()
        writer_id = "locked-plot-writer"
        original_connect = sqlite3.connect

        class ObservedConnection(sqlite3.Connection):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.owner = threading.get_ident()
                self.identifier = object()
                self.request_id = get_request_id()
                self.record("open")
                self.set_trace_callback(self.trace)

            def record(self, operation):
                if threading.get_ident() != self.owner:
                    raise AssertionError("事务连接跨执行线程使用")
                with events_lock:
                    events.append((self.identifier, self.request_id, self.owner, operation))

            def trace(self, statement):
                if self.request_id == writer_id and statement.strip().upper() == "BEGIN IMMEDIATE":
                    # SQLite 已收到 BEGIN，尚不能取得测试线程持有的写锁。
                    writer_started.set()

            def execute(self, *args, **kwargs):
                self.record("execute")
                return super().execute(*args, **kwargs)

            def commit(self):
                self.record("commit")
                return super().commit()

            def rollback(self):
                self.record("rollback")
                return super().rollback()

            def close(self):
                self.record("close")
                return super().close()

        def connect(*args, **kwargs):
            kwargs["factory"] = ObservedConnection
            return original_connect(*args, **kwargs)

        with closing(original_connect(self.db_path)) as blocker:
            if fail_second_insert:
                blocker.execute("""CREATE TRIGGER fail_first_season BEFORE INSERT ON plot_seasons
                    BEGIN SELECT RAISE(ABORT, 'injected second insert failure'); END""")
            blocker.execute("BEGIN IMMEDIATE")
            try:
                with patch("backend.app.core.database.sqlite3.connect", side_effect=connect):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        writer = pool.submit(self.request, "POST", "/api/plots", request_id=writer_id, json={
                            "name": "锁等待测试田", "area_mu": 2, "soil_type": "壤土",
                            "irrigation": "井灌", "crop": "玉米", "planted_on": "2026-04-01",
                        })
                        try:
                            self.assertTrue(writer_started.wait(WAIT_SECONDS), "写请求未进入 SQLite 写事务")
                            self.assertFalse(writer.done())
                            self.assertTrue(blocker.in_transaction)
                            self.assert_live("live-while-write-locked")
                            # 成功必须发生在释放写锁之前，且写请求还没完成。
                            self.assertTrue(blocker.in_transaction)
                            self.assertFalse(writer.done())
                        finally:
                            blocker.rollback()
                        response = writer.result(timeout=WAIT_SECONDS)
            finally:
                blocker.rollback()
        self.assertEqual(response.status_code, 500 if fail_second_insert else 200, response.text)
        by_connection = defaultdict(list)
        for identifier, request_id, owner, operation in events:
            if request_id == writer_id:
                self.assertNotEqual(owner, self.server_thread.ident)
                by_connection[identifier].append(operation)
        self.assertTrue(by_connection, "数据库操作未保留业务 request_id")
        for operations in by_connection.values():
            self.assertEqual(operations[0], "open")
            self.assertEqual(operations[-1], "close")
            self.assertEqual(operations.count("close"), 1)
        self.assertTrue(any(("rollback" if fail_second_insert else "commit") in operations
                            for operations in by_connection.values()))
        with closing(original_connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM plots WHERE user_id=?", (self.user_id,)).fetchone()[0],
                             0 if fail_second_insert else 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM plot_seasons WHERE user_id=?", (self.user_id,)).fetchone()[0],
                             0 if fail_second_insert else 1)

    def test_health_completes_while_write_still_waits_for_lock(self):
        self.locked_write()

    def test_waiting_write_failure_rolls_back_on_its_worker_thread(self):
        self.locked_write(fail_second_insert=True)

    def test_health_completes_while_password_work_is_in_progress(self):
        entered = threading.Event()
        release = threading.Event()
        original_hash = auth_service.hash_password
        execution = []

        def gated_hash(password):
            execution.append((threading.get_ident(), get_request_id()))
            entered.set()
            if not release.wait(WAIT_SECONDS * 2):
                raise AssertionError("未释放密码计算同步信号")
            return original_hash(password)

        with patch.object(auth_service, "hash_password", side_effect=gated_hash):
            with ThreadPoolExecutor(max_workers=1) as pool:
                registration = pool.submit(self.request, "POST", "/api/auth/register", request_id="password-worker",
                    json={"username": "password_worker", "password": PASSWORD, "display_name": "测试用户"})
                try:
                    self.assertTrue(entered.wait(WAIT_SECONDS))
                    self.assert_live("live-during-password-work")
                    self.assertFalse(registration.done())
                finally:
                    release.set()
                response = registration.result(timeout=WAIT_SECONDS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(execution), 1)
        self.assertNotEqual(execution[0][0], self.server_thread.ident)
        self.assertEqual(execution[0][1], "password-worker")

    def test_concurrent_registration_of_same_username_returns_conflict(self):
        both_prechecks_passed = threading.Barrier(2)
        original_hash = auth_service.hash_password

        def gated_hash(password):
            both_prechecks_passed.wait(timeout=WAIT_SECONDS)
            return original_hash(password)

        with patch.object(auth_service, "hash_password", side_effect=gated_hash):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.request, "POST", "/api/auth/register", request_id=f"same-name-{index}",
                    json={"username": "same_name", "password": PASSWORD, "display_name": f"用户{index}"}) for index in range(2)]
                responses = [future.result(timeout=WAIT_SECONDS * 2) for future in futures]
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE username='same_name'").fetchone()[0], 1)
            self.assertEqual(conn.execute("""SELECT COUNT(*) FROM auth_tokens t JOIN users u ON u.id=t.user_id
                WHERE u.username='same_name'""").fetchone()[0], 1)

    def test_concurrent_auth_attempts_preserve_rate_limit_and_error_context(self):
        self.limiter.reset()
        settings = replace(get_settings(), auth_requests_per_minute=3, auth_window_seconds=600)
        start = threading.Barrier(8)

        def attempt(index):
            start.wait(timeout=WAIT_SECONDS)
            return self.request("POST", "/api/auth/login", request_id=f"limited-login-{index}",
                                json={"username": "absent_user", "password": PASSWORD})

        with patch.object(auth, "get_settings", return_value=settings):
            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(attempt, range(8)))
        self.assertEqual(sorted(response.status_code for response in responses), [401] * 3 + [429] * 5)
        for index, response in enumerate(responses):
            self.assertFalse(response.json()["success"])
            self.assertEqual(response.headers["X-Request-ID"], f"limited-login-{index}")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            if response.status_code == 429:
                self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.assertEqual(sum(map(len, self.limiter.snapshot().values())), 3)

    def test_parallel_writes_keep_audit_context_permissions_and_csrf(self):
        start = threading.Barrier(6)

        def create(index):
            start.wait(timeout=WAIT_SECONDS)
            return self.request("POST", "/api/plots", request_id=f"parallel-plot-{index}", json={
                "name": f"并发测试田{index}", "area_mu": 1, "soil_type": "壤土", "irrigation": "井灌", "crop": "玉米",
            })

        with self.assertLogs("yunxun.backend", level=logging.INFO) as captured:
            with ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(create, range(6)))
        business_logs = [line for line in captured.output if "event=plot_create " in line]
        self.assertEqual(len(business_logs), 6)
        ids = []
        for index, response in enumerate(responses):
            self.assertEqual(response.status_code, 200, response.text)
            request_id = f"parallel-plot-{index}"
            self.assertEqual(response.headers["X-Request-ID"], request_id)
            plot = response.json()["plot"]
            ids.append(plot["id"])
            self.assertIsNotNone(plot["active_season"])
            matching = [line for line in business_logs if f"plot_id={plot['id']} " in line]
            self.assertEqual(len(matching), 1)
            self.assertIn(f"request_id={request_id} ", matching[0])
            self.assertIn(f"user_id={self.user_id}", matching[0])
        self.assertEqual(len(set(ids)), 6)
        # 同一个真实服务继续校验 Cookie 写请求的 CSRF 与另一账号的对象权限。
        task_payload = {"title": "查苗", "due_on": "2026-10-19"}
        forbidden = self.client.post("/api/farm-tasks", json=task_payload, headers={
            "X-CSRF-Token": "incorrect", "X-Request-ID": "real-service-csrf", "Origin": "http://127.0.0.1:5173",
        })
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.headers["X-Request-ID"], "real-service-csrf")
        self.assertEqual(forbidden.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")
        allowed = self.client.post("/api/farm-tasks", json=task_payload)
        self.assertEqual(allowed.status_code, 200, allowed.text)
        with httpx.Client(base_url=self.base_url, timeout=WAIT_SECONDS, trust_env=False) as other:
            self.assertEqual(other.post("/api/auth/guest").status_code, 200)
            denied = other.post("/api/seasons", headers={"X-CSRF-Token": other.cookies["yunxun_csrf"]},
                                json={"plot_id": ids[0], "crop": "大豆"})
            self.assertEqual(denied.status_code, 404, denied.text)


if __name__ == "__main__":
    unittest.main()
