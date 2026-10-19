import io
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
from backend.app.core.database import SCHEMA_VERSION, get_connection, init_db
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import hash_recovery_code, verify_password
from backend.app.repositories import get_user_by_id
from backend.app.repositories_account import INVALID_RECOVERY, recover_password
from backend.app.services.auth import issue_auth_token, login_user
from scripts import account_admin


class PasswordManagementTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "password.db"
        environment = patch.dict(os.environ, {"YUNXUN_DB_PATH": str(self.database), "YUNXUN_ENV": "test",
            "YUNXUN_COOKIE_SECURE": "false", "YUNXUN_JWT_SECRET": "password-test-secret",
            "YUNXUN_AUTH_REQUESTS_PER_MINUTE": "2000"})
        environment.start()
        self.addCleanup(environment.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        for name in ("auth_rate_limiter", "credential_rate_limiter"):
            limiter = patch.object(auth, name, InMemoryRateLimiter())
            limiter.start()
            self.addCleanup(limiter.stop)
        from backend.app.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.username, self.password, self.new_password = "account_owner", "old-password", "new-password"
        result = self.client.post("/api/auth/register", json={"username": self.username, "password": self.password, "display_name": "农户"})
        self.assertEqual(result.status_code, 200)
        self.user = result.json()["user"]
        self.token = result.json()["token"]
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]

    def me(self, token):
        with TestClient(self.app, raise_server_exceptions=False) as client:
            return client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    def change(self, **overrides):
        return self.client.post("/api/auth/change-password", json={"current_password": self.password, "new_password": self.new_password, **overrides})

    def generate(self):
        response = self.client.post("/api/auth/recovery-code", json={"current_password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["recovery_code"]

    def recover(self, code, **overrides):
        return self.client.post("/api/auth/recover-password", json={"username": self.username, "recovery_code": code, "new_password": self.new_password, **overrides})

    def snapshot(self):
        with get_connection() as conn:
            return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE user_id=? ORDER BY id", (self.user["id"],))]
                    for table in ("plots", "plot_seasons", "farm_records", "farm_tasks", "tool_records")}

    def seed(self):
        response = self.client.post("/api/plots", json={"name": "保留的地", "crop": "玉米", "area_mu": 2, "soil_type": "壤土", "irrigation": "井灌", "planted_on": "2026-01-01"})
        self.assertEqual(response.status_code, 200)
        plot = response.json()["plot"]
        self.assertEqual(self.client.post("/api/farm-records", json={"plot_id": plot["id"], "kind": "施肥", "happened_on": "2026-10-19", "cost": 30}).status_code, 200)
        self.assertEqual(self.client.post("/api/farm-tasks", json={"plot_id": plot["id"], "title": "待办保留", "due_on": "2026-10-19"}).status_code, 200)
        self.assertEqual(self.client.post("/api/decision", json={"crop": "玉米", "stage": "快速生长期", "rain_prob": 55}).status_code, 200)

    def test_change_preserves_business_and_revokes_cookie_bearer_sessions_and_code(self):
        self.seed()
        code = self.generate()
        other_token = issue_auth_token(self.user["id"])
        before = self.snapshot()
        response = self.change()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("yunxun_session", self.client.cookies)
        self.assertNotIn("yunxun_csrf", self.client.cookies)
        self.assertEqual(self.me(self.token).status_code, 401)
        self.assertEqual(self.me(other_token).status_code, 401)
        self.assertEqual(self.change().status_code, 401)
        self.assertIsNone(get_user_by_id(self.user["id"])["recovery_code_hash"])
        self.assertEqual(self.recover(code).status_code, 400)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(HTTPException):
            login_user(self.username, self.password)
        self.assertEqual(login_user(self.username, self.new_password)["user"]["id"], self.user["id"])

    def test_wrong_old_password_invalid_input_and_same_password_do_not_mutate(self):
        before = get_user_by_id(self.user["id"])
        for override in ({"current_password": "wrong-password"}, {"new_password": self.password},
                         {"new_password": "short"}, {"new_password": " " * 8}, {"new_password": "p" * 65}, {"user_id": "someone_else"}):
            with self.subTest(fields=list(override)):
                self.assertIn(self.change(**override).status_code, (400, 422))
                self.assertEqual(get_user_by_id(self.user["id"]), before)
                self.assertEqual(self.me(self.token).status_code, 200)

    def test_high_entropy_digest_only_one_time_code_regeneration_and_recovery(self):
        self.seed()
        before = self.snapshot()
        first, code = self.generate(), self.generate()
        self.assertNotEqual(first, code)
        self.assertRegex(code, r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(get_user_by_id(self.user["id"])["recovery_code_hash"], hash_recovery_code(code))
        self.assertNotIn(code.encode(), self.database.read_bytes())
        self.assertNotIn("recovery_code", self.me(self.token).text)
        self.assertEqual(self.client.get("/api/auth/recovery-code").status_code, 405)
        self.assertEqual(self.recover(first).status_code, 400)
        second_token = issue_auth_token(self.user["id"])
        response = self.recover(" " + code + " ", username=" ACCOUNT_OWNER ")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.me(self.token).status_code, 401)
        self.assertEqual(self.me(second_token).status_code, 401)
        self.assertIsNone(get_user_by_id(self.user["id"])["recovery_code_hash"])
        self.assertEqual(self.recover(code).status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(login_user(self.username, self.new_password)["user"]["id"], self.user["id"])

    def test_recovery_errors_do_not_enumerate_accounts_or_echo_secrets(self):
        code = self.generate()
        errors = []
        with TestClient(self.app) as guest:
            guest_name = guest.post("/api/auth/guest").json()["user"]["username"]
        for name in (self.username, "unknown_account", guest_name):
            response = self.recover("bad-secret-value", username=name)
            self.assertEqual(response.status_code, 400)
            errors.append(response.json())
            self.assertNotIn(name, response.text)
            self.assertNotIn("bad-secret-value", response.text)
        self.assertEqual(errors, [{"success": False, "error": INVALID_RECOVERY}] * 3)
        # 仅公开用户名、显示名称不提供恢复权限，失败也不消费真实恢复码。
        self.assertEqual(self.recover(self.user["display_name"]).status_code, 400)
        self.assertEqual(get_user_by_id(self.user["id"])["recovery_code_hash"], hash_recovery_code(code))

    def test_recovery_per_account_limit_includes_unknown_accounts_and_expires(self):
        clock = [0.0]
        with patch.object(auth, "credential_rate_limiter", InMemoryRateLimiter(lambda: clock[0])):
            for name in (self.username, "unknown"):
                for _ in range(5):
                    self.assertEqual(self.recover("invalid", username=name).status_code, 400)
                response = self.recover("invalid", username=name)
                self.assertEqual(response.status_code, 429)
                self.assertGreater(int(response.headers["retry-after"]), 0)
            clock[0] = 601.0
            self.assertEqual(self.recover("invalid").status_code, 400)

    def test_ip_limit_cannot_be_bypassed_by_changing_usernames(self):
        for index in range(20):
            self.assertEqual(self.recover("invalid", username=f"unknown_{index}").status_code, 400)
        self.assertEqual(self.recover("invalid", username="another_unknown").status_code, 429)

    def test_password_proof_is_rate_limited(self):
        for _ in range(5):
            self.assertEqual(self.change(current_password="wrong").status_code, 400)
        self.assertEqual(self.change().status_code, 429)
        self.assertEqual(self.client.post("/api/auth/recovery-code", json={"current_password": self.password}).status_code, 429)

    def test_recovery_code_requires_correct_password_and_legacy_short_password_can_change(self):
        original = self.generate()
        self.assertEqual(self.client.post("/api/auth/recovery-code", json={"current_password": "wrong"}).status_code, 400)
        self.assertEqual(get_user_by_id(self.user["id"])["recovery_code_hash"], hash_recovery_code(original))
        with TestClient(self.app) as legacy:
            account = legacy.post("/api/auth/register", json={"username": "legacy_short", "password": "1234", "display_name": "历史农户"}).json()
            legacy.headers["X-CSRF-Token"] = legacy.cookies["yunxun_csrf"]
            response = legacy.post("/api/auth/change-password", json={"current_password": "1234", "new_password": self.new_password})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.me(account["token"]).status_code, 401)
            self.assertEqual(login_user("legacy_short", self.new_password)["user"]["id"], account["user"]["id"])

    def test_unauthorized_guest_cross_account_and_csrf_paths(self):
        code = self.generate()
        for path in ("change-password", "recovery-code"):
            data = {"current_password": self.password, **({"new_password": self.new_password} if path == "change-password" else {})}
            with TestClient(self.app) as anonymous:
                self.assertEqual(anonymous.post(f"/api/auth/{path}", json=data).status_code, 401)
            with TestClient(self.app) as guest:
                guest.post("/api/auth/guest")
                guest.headers["X-CSRF-Token"] = guest.cookies["yunxun_csrf"]
                self.assertEqual(guest.post(f"/api/auth/{path}", json=data).status_code, 403)
        with TestClient(self.app) as other:
            account = other.post("/api/auth/register", json={"username": "different", "password": "other-password", "display_name": "他人"}).json()
            other.headers["X-CSRF-Token"] = other.cookies["yunxun_csrf"]
            self.assertEqual(other.post("/api/auth/change-password", json={"user_id": self.user["id"], "current_password": self.password, "new_password": self.new_password}).status_code, 422)
            self.assertEqual(other.post("/api/auth/change-password", json={"current_password": self.password, "new_password": self.new_password}).status_code, 400)
            self.assertEqual(self.recover("wrong", username="different").status_code, 400)
            self.assertEqual(self.recover(code, username="different").status_code, 400)
            self.assertEqual(self.recover(code, user_id=account["user"]["id"]).status_code, 422)
            self.assertEqual(self.me(account["token"]).status_code, 200)
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.change().status_code, 403)
        self.assertEqual(self.recover("invalid").status_code, 403)
        self.assertTrue(verify_password(self.password, get_user_by_id(self.user["id"])["password_hash"]))

    def test_transaction_failures_roll_back_password_code_and_sessions(self):
        code = self.generate()
        before = get_user_by_id(self.user["id"])
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_revoke BEFORE DELETE ON auth_tokens BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
        self.assertEqual(self.change().status_code, 500)
        self.assertEqual(self.recover(code).status_code, 500)
        self.assertEqual(get_user_by_id(self.user["id"]), before)
        self.assertEqual(self.me(self.token).status_code, 200)
        with get_connection() as conn:
            conn.execute("DROP TRIGGER fail_revoke")
        self.assertEqual(self.recover(code).status_code, 200)

    def test_concurrent_recovery_consumes_code_once(self):
        code = self.generate()
        def attempt(index):
            try:
                return recover_password(self.username, code, f"concurrent-{index}")
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))
        self.assertEqual(results.count(self.user["id"]), 1)
        self.assertEqual(results.count(400), 1)
        self.assertEqual(self.me(self.token).status_code, 401)

    def test_login_verified_before_change_cannot_create_session_after_revocation(self):
        original_issue = issue_auth_token
        def change_before_issue(user_id, **kwargs):
            self.assertEqual(self.change().status_code, 200)
            return original_issue(user_id, **kwargs)
        with patch("backend.app.services.auth.issue_auth_token", side_effect=change_before_issue):
            with self.assertRaises(HTTPException) as failure:
                login_user(self.username, self.password)
        self.assertEqual(failure.exception.status_code, 401)
        with get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_tokens WHERE user_id=?", (self.user["id"],)).fetchone()[0], 0)

    def test_secrets_are_not_in_audit_request_logs_or_normal_errors(self):
        with self.assertLogs("yunxun.backend", level="INFO") as capture:
            code = self.generate()
            response = self.recover(code)
        logged = "\n".join(capture.output)
        for secret in (code, self.password, self.new_password, self.token):
            self.assertNotIn(secret, logged)
            self.assertNotIn(secret, response.text)

    def test_v10_migration_preserves_history_and_does_not_guess_guest_identity(self):
        self.seed()
        before = self.snapshot()
        with get_connection() as conn:
            conn.execute("ALTER TABLE users DROP COLUMN recovery_code_hash")
            conn.execute("UPDATE users SET username='guest_historical',is_guest=0 WHERE id=?", (self.user["id"],))
            conn.execute("PRAGMA user_version=10")
        init_db()
        init_db()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(get_user_by_id(self.user["id"])["is_guest"])
        self.assertEqual(self.me(self.token).status_code, 200)
        self.assertIsNone(get_user_by_id(self.user["id"])["recovery_code_hash"])
        self.generate()
        with get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def run_admin(self, **overrides):
        with patch.object(account_admin.sys.stdin, "isatty", return_value=overrides.get("interactive", True)), \
             patch.object(account_admin.sys.stderr, "isatty", return_value=True), \
             patch("builtins.input", return_value=overrides.get("confirm", self.username)), \
             patch.object(account_admin, "getpass", side_effect=overrides.get("passwords", [self.new_password, self.new_password])), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            result = account_admin.main(["--database", str(overrides.get("database", self.database)), "--username", overrides.get("username", self.username)])
            for secret in (self.password, self.new_password, self.token):
                self.assertNotIn(secret, output.getvalue())
            return result

    def test_local_admin_preserves_data_and_revokes_all_credentials(self):
        self.seed()
        before = self.snapshot()
        code = self.generate()
        self.assertEqual(self.run_admin(), 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.me(self.token).status_code, 401)
        self.assertEqual(self.recover(code).status_code, 400)
        self.assertEqual(login_user(self.username, self.new_password)["user"]["id"], self.user["id"])

    def test_local_admin_rejects_pipe_cancel_bad_password_and_nonexistent_database(self):
        before = get_user_by_id(self.user["id"])
        for options in ({"interactive": False}, {"confirm": "cancel"}, {"passwords": ["short"]},
                        {"passwords": [self.new_password, "mismatch"]}, {"passwords": [account_admin.GetPassWarning("cannot hide")]},
                        {"database": self.database.parent / "absent.db"}):
            self.assertEqual(self.run_admin(**options), 1)
            self.assertEqual(get_user_by_id(self.user["id"]), before)
        self.assertFalse((self.database.parent / "absent.db").exists())
        with TestClient(self.app) as guest:
            username = guest.post("/api/auth/guest").json()["user"]["username"]
        self.assertEqual(self.run_admin(username=username), 1)

    def test_local_admin_transaction_failure_keeps_password_and_code(self):
        self.generate()
        before = get_user_by_id(self.user["id"])
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_revoke BEFORE DELETE ON auth_tokens BEGIN SELECT RAISE(ABORT,'failure'); END")
        self.assertEqual(self.run_admin(), 1)
        self.assertEqual(get_user_by_id(self.user["id"]), before)
        self.assertEqual(self.me(self.token).status_code, 200)
