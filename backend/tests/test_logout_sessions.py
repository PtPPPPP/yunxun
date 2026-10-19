"""退出绑定会话、响应丢失重试与迟到响应的回归。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import hash_auth_token


class LogoutSessionsTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {
            "YUNXUN_DB_PATH": str(Path(temporary.name) / "logout.db"),
            "YUNXUN_ENV": "test", "YUNXUN_COOKIE_SECURE": "false",
            "YUNXUN_JWT_SECRET": "logout-regression-secret",
            "YUNXUN_REQUESTS_PER_MINUTE": "600",
            "YUNXUN_AUTH_REQUESTS_PER_MINUTE": "2000",
        })
        environment.start()
        self.addCleanup(environment.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        limiter = patch.object(auth, "auth_rate_limiter", InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        from backend.app.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.original = self.register("original")

    def register(self, username):
        result = self.client.post("/api/auth/register", json={
            "username": username, "password": "test-password", "display_name": username,
        })
        self.assertEqual(result.status_code, 200, result.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        return result.json()

    def logout(self, session_id):
        return self.client.post("/api/auth/logout", json={"session_id": session_id})

    def test_logout_revokes_cookie_and_bearer_and_can_repeat_after_lost_response(self):
        reference = self.original["session_id"]
        self.assertNotEqual(reference, self.original["token"])
        self.assertNotEqual(reference, hash_auth_token(self.original["token"]))
        for path in ("/api/me", "/api/auth/me"):
            self.assertEqual(self.client.get(path).json()["session_id"], reference)
        response = self.logout(reference)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(self.logout(reference).status_code, 200)
        with TestClient(self.app) as other:
            self.assertEqual(other.get("/api/me", headers={"Authorization": f"Bearer {self.original['token']}"}).status_code, 401)
            self.assertEqual(other.post("/api/auth/logout", json={"session_id": reference}).status_code, 200)

    def test_old_retry_cannot_revoke_different_or_same_account_new_login(self):
        for same_account in (False, True):
            with self.subTest(same_account=same_account):
                old_reference = self.client.get("/api/me").json()["session_id"]
                if same_account:
                    result = self.client.post("/api/auth/login", json={"username": "second", "password": "test-password"})
                    self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
                    next_session = result.json()
                else:
                    next_session = self.register("second")
                self.assertNotEqual(next_session["session_id"], old_reference)
                response = self.logout(old_reference)
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("set-cookie", response.headers)
                current = self.client.get("/api/me").json()
                self.assertEqual(current["session_id"], next_session["session_id"])
                self.assertEqual(current["user"], next_session["user"])

    def test_late_logout_response_has_no_cookie_instruction_to_erase_new_login(self):
        response = self.logout(self.original["session_id"])
        self.assertEqual(response.status_code, 200)
        next_session = self.register("second")
        # 模拟浏览器在新登录后收到旧响应：必须完全没有 Cookie 写入。
        self.assertEqual(response.headers.get_list("set-cookie"), [])
        self.assertEqual(self.client.get("/api/me").json()["session_id"], next_session["session_id"])

    def test_old_request_delivered_after_new_login_only_revokes_original_cookie(self):
        original_cookies = dict(self.client.cookies)
        next_session = self.register("second")
        with TestClient(self.app) as delayed_client:
            delayed_client.cookies.update(original_cookies)
            response = delayed_client.post("/api/auth/logout", json={"session_id": self.original["session_id"]},
                headers={"X-CSRF-Token": original_cookies["yunxun_csrf"]})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("set-cookie", response.headers)
            self.assertEqual(delayed_client.get("/api/me").status_code, 401)
        self.assertEqual(self.client.get("/api/me").json()["session_id"], next_session["session_id"])

    def test_wrong_reference_and_csrf_do_not_revoke_session(self):
        self.assertEqual(self.logout("0" * 64).status_code, 409)
        del self.client.headers["X-CSRF-Token"]
        self.assertEqual(self.logout(self.original["session_id"]).status_code, 403)
        self.assertEqual(self.client.get("/api/me").status_code, 200)

    def test_session_reference_cannot_authenticate(self):
        with TestClient(self.app) as other:
            response = other.get("/api/me", headers={"Authorization": f"Bearer {self.original['session_id']}"})
            self.assertEqual(response.status_code, 401)

    def test_legacy_bearer_logout_is_still_supported(self):
        with TestClient(self.app) as other:
            response = other.post("/api/auth/logout", headers={"Authorization": f"Bearer {self.original['token']}"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
