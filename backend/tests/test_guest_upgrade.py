import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.database import get_connection
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import hash_auth_token, verify_password
from backend.app.repositories import get_user_by_id, get_user_by_username
from backend.app.services.auth import issue_auth_token, upgrade_guest_user


class GuestUpgradeTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {"YUNXUN_DB_PATH": str(Path(temporary.name) / "upgrade.db"),
            "YUNXUN_ENV": "test", "YUNXUN_COOKIE_SECURE": "false", "YUNXUN_JWT_SECRET": "upgrade-test-secret",
            "YUNXUN_ALLOWED_ORIGINS": "http://127.0.0.1:5173"})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        limiter = patch.object(auth, "auth_rate_limiter", InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        # 模块级 app 的首次初始化也只能访问临时数据库。
        from backend.app.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        response = self.client.post("/api/auth/guest")
        self.assertEqual(response.status_code, 200)
        self.guest = response.json()["user"]
        self.old_token = response.json()["token"]
        self.old_csrf = self.client.cookies["yunxun_csrf"]
        self.client.headers["X-CSRF-Token"] = self.old_csrf
        self.payload = {"username": "saved_farmer", "password": "new-password", "display_name": "正式农户"}

    def upgrade(self, **values):
        return self.client.post("/api/auth/upgrade-guest", json={**self.payload, **values})

    def bearer_me(self, token):
        with TestClient(self.app) as client:
            return client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    def token_hashes(self):
        with get_connection() as conn:
            return [row[0] for row in conn.execute("SELECT token_hash FROM auth_tokens WHERE user_id=? ORDER BY token_hash", (self.guest["id"],))]

    def business_snapshot(self):
        with get_connection() as conn:
            return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE user_id=? ORDER BY id", (self.guest["id"],))]
                    for table in ("plots", "plot_seasons", "farm_records", "farm_tasks", "tool_records")}

    def seed(self):
        plot = self.client.post("/api/plots", json={"name": "保留的地块", "area_mu": 2, "soil_type": "壤土", "irrigation": "井灌", "crop": "玉米", "planted_on": "2026-01-01"}).json()["plot"]
        self.assertEqual(self.client.post("/api/farm-records", json={"plot_id": plot["id"], "kind": "施肥", "happened_on": "2026-10-19", "cost": 35}).status_code, 200)
        self.assertEqual(self.client.post("/api/farm-tasks", json={"plot_id": plot["id"], "title": "保留的待办", "due_on": "2026-10-19"}).status_code, 200)
        self.assertEqual(self.client.post("/api/decision", json={"crop": "玉米", "stage": "快速生长期", "rain_prob": 55, "soil_moisture": 42, "temperature": 25}).status_code, 200)
        return plot

    def test_upgrade_keeps_id_every_business_row_and_login_after_logout(self):
        self.seed()
        self.client.patch("/api/onboarding", json={"skipped": True})
        before = self.business_snapshot()
        created_at = get_user_by_id(self.guest["id"])["created_at"]
        response = self.upgrade()
        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()["user"]
        self.assertEqual(user["id"], self.guest["id"])
        self.assertEqual(user["created_at"], created_at)
        self.assertFalse(user["is_guest"])
        self.assertEqual(self.business_snapshot(), before)
        self.assertTrue(self.client.get("/api/onboarding").json()["onboarding"]["skipped"])
        stored = get_user_by_id(user["id"])
        self.assertNotEqual(stored["password_hash"], self.payload["password"])
        self.assertTrue(verify_password(self.payload["password"], stored["password_hash"]))
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        login = self.client.post("/api/auth/login", json={"username": self.payload["username"], "password": self.payload["password"]})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["id"], self.guest["id"])
        self.assertEqual(self.business_snapshot(), before)
        for path, key in (("/api/plots", "plots"), ("/api/seasons", "seasons"), ("/api/farm-records", "records"), ("/api/farm-tasks", "tasks"), ("/api/tool-records", "records")):
            self.assertEqual(len(self.client.get(path).json()[key]), 1, path)

    def test_session_tokens_and_csrf_rotate_and_other_sessions_are_revoked(self):
        extra = issue_auth_token(self.guest["id"])
        response = self.upgrade()
        self.assertEqual(response.status_code, 200)
        new_token = response.json()["token"]
        self.assertNotEqual(new_token, self.old_token)
        self.assertEqual(self.client.cookies["yunxun_session"], new_token)
        self.assertNotEqual(self.client.cookies["yunxun_csrf"], self.old_csrf)
        self.assertEqual(self.token_hashes(), [hash_auth_token(new_token)])
        self.assertEqual(self.bearer_me(self.old_token).status_code, 401)
        self.assertEqual(self.bearer_me(extra).status_code, 401)
        self.assertEqual(self.bearer_me(new_token).status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("HttpOnly", response.headers.get_list("set-cookie")[0])
        self.assertEqual(self.client.patch("/api/me/profile", json={"display_name": "旧 CSRF 应拒绝"}).status_code, 403)
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        self.assertEqual(self.client.patch("/api/me/profile", json={"display_name": "新 CSRF 可写"}).status_code, 200)

    def test_username_conflict_rolls_back_and_does_not_merge_accounts(self):
        with TestClient(self.app) as other:
            existing = other.post("/api/auth/register", json=self.payload).json()
        before = get_user_by_id(self.guest["id"])
        hashes = self.token_hashes()
        response = self.upgrade(username=" SAVED_FARMER ")
        self.assertEqual(response.status_code, 409)
        self.assertIn("用户名已存在", response.json()["error"])
        self.assertEqual(get_user_by_id(self.guest["id"]), before)
        self.assertEqual(self.token_hashes(), hashes)
        self.assertEqual(self.client.cookies["yunxun_session"], self.old_token)
        self.assertEqual(self.bearer_me(existing["token"]).json()["user"]["id"], existing["user"]["id"])
        self.assertEqual(self.upgrade(username="another_farmer").status_code, 200)

    def test_invalid_input_has_no_account_or_session_side_effects(self):
        before, hashes = get_user_by_id(self.guest["id"]), self.token_hashes()
        for values in ({"username": " a "}, {"username": "bad-name"}, {"username": "用户名"}, {"username": "a" * 33},
                       {"password": "123"}, {"password": " " * 5}, {"password": "p" * 65}, {"display_name": "   "},
                       {"display_name": "名" * 33}, {"user_id": "other"}, {"is_guest": False}):
            with self.subTest(values=list(values)):
                response = self.upgrade(**values)
                self.assertIn(response.status_code, (400, 422))
                self.assertEqual(get_user_by_id(self.guest["id"]), before)
                self.assertEqual(self.token_hashes(), hashes)

    def test_names_are_normalized_and_password_preserves_spaces(self):
        response = self.upgrade(username="  New_Farmer  ", display_name=" 新农户 ", password=" pass with spaces ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "new_farmer")
        self.assertEqual(response.json()["user"]["display_name"], "新农户")
        self.assertTrue(verify_password(" pass with spaces ", get_user_by_id(self.guest["id"])["password_hash"]))

    def test_registered_or_legacy_prefix_account_cannot_upgrade(self):
        with TestClient(self.app) as official:
            payload = official.post("/api/auth/register", json={**self.payload, "username": "guest_legacy"}).json()
            official.headers["X-CSRF-Token"] = official.cookies["yunxun_csrf"]
            response = official.post("/api/auth/upgrade-guest", json={**self.payload, "username": "cannot_change"})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(get_user_by_id(payload["user"]["id"])["is_guest"])
            self.assertEqual(get_user_by_id(payload["user"]["id"])["username"], "guest_legacy")
            self.assertTrue(get_user_by_id(self.guest["id"])["is_guest"])

    def test_unauthenticated_and_conflicting_identities_cannot_upgrade(self):
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.post("/api/auth/upgrade-guest", json=self.payload).status_code, 401)
        with TestClient(self.app) as other:
            other_token = other.post("/api/auth/guest").json()["token"]
        response = self.client.post("/api/auth/upgrade-guest", json=self.payload, headers={"Authorization": f"Bearer {other_token}"})
        self.assertEqual(response.status_code, 401)
        self.assertTrue(get_user_by_id(self.guest["id"])["is_guest"])

    def test_missing_or_wrong_csrf_rejects_upgrade_and_keeps_guest(self):
        for csrf in (None, "wrong"):
            if csrf is None:
                self.client.headers.pop("X-CSRF-Token")
            else:
                self.client.headers["X-CSRF-Token"] = csrf
            response = self.upgrade()
            self.assertEqual(response.status_code, 403)
            self.assertIn("x-request-id", response.headers)
            self.assertTrue(get_user_by_id(self.guest["id"])["is_guest"])
            self.assertEqual(self.bearer_me(self.old_token).status_code, 200)

    def test_duplicate_requests_cannot_change_saved_credentials(self):
        first = self.upgrade()
        self.assertEqual(first.status_code, 200)
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        self.assertEqual(self.upgrade(username="overwrite", password="other-password").status_code, 403)
        with TestClient(self.app) as stale:
            self.assertEqual(stale.post("/api/auth/upgrade-guest", json=self.payload, headers={"Authorization": f"Bearer {self.old_token}"}).status_code, 401)
        self.assertEqual(get_user_by_id(self.guest["id"])["username"], self.payload["username"])
        self.assertTrue(verify_password(self.payload["password"], get_user_by_id(self.guest["id"])["password_hash"]))

    def test_concurrent_authenticated_guest_snapshots_upgrade_only_once(self):
        user = get_user_by_id(self.guest["id"])
        def run(index):
            try:
                return upgrade_guest_user(user, f"winner_{index}", "password", "农户")
            except HTTPException as exc:
                return exc
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        success = [item for item in results if isinstance(item, dict)]
        failure = [item for item in results if isinstance(item, HTTPException)]
        self.assertEqual((len(success), len(failure)), (1, 1))
        self.assertEqual(failure[0].status_code, 409)
        self.assertEqual(failure[0].code, "GUEST_ALREADY_UPGRADED")
        self.assertEqual(self.token_hashes(), [hash_auth_token(success[0]["token"])])

    def test_session_insert_failure_rolls_back_credentials_role_and_all_tokens(self):
        self.seed()
        issue_auth_token(self.guest["id"])
        before, hashes, business = get_user_by_id(self.guest["id"]), self.token_hashes(), self.business_snapshot()
        with get_connection() as conn:
            conn.execute("""CREATE TRIGGER fail_session BEFORE INSERT ON auth_tokens
                BEGIN SELECT RAISE(ABORT, 'simulated session write failure'); END""")
        response = self.upgrade()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(get_user_by_id(self.guest["id"]), before)
        self.assertEqual(self.token_hashes(), hashes)
        self.assertEqual(self.business_snapshot(), business)
        self.assertEqual(self.bearer_me(self.old_token).status_code, 200)
        with get_connection() as conn:
            conn.execute("DROP TRIGGER fail_session")
        self.assertEqual(self.upgrade().status_code, 200)

    def test_upgrade_preserves_demo_origin_and_allows_clearing_afterward(self):
        self.seed()
        self.client.post("/api/demo-data")
        before = self.business_snapshot()
        self.assertEqual(self.upgrade().status_code, 200)
        self.assertEqual(self.business_snapshot(), before)
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        self.assertEqual(self.client.post("/api/demo-data").status_code, 403)
        self.assertEqual(self.client.delete("/api/demo-data").status_code, 200)
        records = self.client.get("/api/farm-records").json()["records"]
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["is_demo"])
