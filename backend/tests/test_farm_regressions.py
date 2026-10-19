"""完整 create_app 回归：Cookie/CSRF、中间件、日期和茬次归属。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.repositories import get_active_season, get_season


class FarmApplicationRegressionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {
            "YUNXUN_DB_PATH": str(Path(temporary.name) / "regression.db"),
            "YUNXUN_ENV": "test", "YUNXUN_COOKIE_SECURE": "false",
            "YUNXUN_JWT_SECRET": "regression-test-secret",
            "YUNXUN_ALLOWED_ORIGINS": "http://127.0.0.1:5173",
        })
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        limiter = patch.object(auth, "auth_rate_limiter", InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        # 首次导入也在临时数据库配置内，避免模块级 app 初始化正式数据库。
        from backend.app.main import create_app

        self.app = create_app()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        login = self.client.post("/api/auth/guest")
        self.assertEqual(login.status_code, 200)
        self.token = login.json()["token"]
        self.csrf = self.client.cookies["yunxun_csrf"]
        self.client.headers["X-CSRF-Token"] = self.csrf
        self.plot = self.client.post("/api/plots", json={
            "name": "测试田", "area_mu": 3, "soil_type": "壤土", "irrigation": "井灌",
            "crop": "玉米", "planted_on": "2026-04-01",
        }).json()["plot"]
        self.first_id = self.plot["active_season"]["id"]

    def second_season(self, started_on="2026-10-01") -> dict:
        ended = self.client.patch(f"/api/seasons/{self.first_id}", json={
            "crop": "玉米", "started_on": "2026-04-01", "ended_on": "2026-05-31",
        })
        self.assertEqual(ended.status_code, 200)
        response = self.client.post("/api/seasons", json={
            "plot_id": self.plot["id"], "crop": "大豆", "started_on": started_on,
        })
        self.assertEqual(response.status_code, 200)
        return response.json()["season"]

    def record(self, happened_on="2026-04-30", **overrides):
        return self.client.post("/api/farm-records", json={
            "plot_id": self.plot["id"], "kind": "采收", "happened_on": happened_on,
            "yield_kg": 100, "unit_price": 2, "cost": 30, **overrides,
        })

    def test_csrf_rejection_keeps_error_headers_request_id_and_log(self) -> None:
        for token in (None, "incorrect"):
            with self.subTest(token=token):
                if token is None:
                    del self.client.headers["X-CSRF-Token"]
                else:
                    self.client.headers["X-CSRF-Token"] = token
                with self.assertLogs("yunxun.backend", level="INFO") as logs:
                    response = self.client.post("/api/farm-tasks", json={
                        "title": "查苗", "due_on": "2026-10-19",
                    }, headers={"X-Request-ID": "csrf-regression-123", "Origin": "http://127.0.0.1:5173"})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {
                    "success": False, "error": "CSRF 验证失败，请刷新页面后重试。",
                })
                self.assertEqual(response.headers["X-Request-ID"], "csrf-regression-123")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")
                self.assertEqual(response.headers["Access-Control-Allow-Credentials"], "true")
                self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
                self.assertIn("status_code=403", " ".join(logs.output))
                self.assertIn("request_id=csrf-regression-123", " ".join(logs.output))
        self.assertEqual(self.client.get("/api/farm-tasks").json()["tasks"], [])

    def test_cookie_csrf_pair_is_required_and_valid_pair_allows_write(self) -> None:
        self.client.cookies.delete("yunxun_csrf")
        payload = {"title": "查苗", "due_on": "2026-10-19"}
        self.assertEqual(self.client.post("/api/farm-tasks", json=payload).status_code, 403)
        self.client.cookies.set("yunxun_csrf", self.csrf)
        self.assertEqual(self.client.post("/api/farm-tasks", json=payload).status_code, 200)

    def test_bearer_client_can_write_without_csrf(self) -> None:
        with TestClient(self.app) as client:
            response = client.post("/api/farm-tasks", json={
                "title": "查苗", "due_on": "2026-10-19",
            }, headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(response.status_code, 200)

    def test_invalid_calendar_dates_are_rejected_on_all_date_fields(self) -> None:
        cases = [
            ("post", "/api/plots", {"name": "新田", "area_mu": 1, "soil_type": "壤土",
                                     "irrigation": "井灌", "crop": "玉米"}, "planted_on"),
            ("patch", f"/api/plots/{self.plot['id']}", {"name": "测试田", "area_mu": 3,
                       "soil_type": "壤土", "irrigation": "井灌", "crop": "玉米"}, "planted_on"),
            ("post", "/api/seasons", {"plot_id": self.plot["id"], "crop": "大豆"}, "started_on"),
            ("patch", f"/api/seasons/{self.first_id}", {"crop": "玉米"}, "started_on"),
            ("patch", f"/api/seasons/{self.first_id}", {"crop": "玉米"}, "ended_on"),
            ("post", "/api/farm-records", {"plot_id": self.plot["id"], "kind": "采收"}, "happened_on"),
            ("post", "/api/farm-tasks", {"title": "查苗"}, "due_on"),
        ]
        for method, path, payload, field in cases:
            for invalid in ("2026-02-31", "2026-02-29", "1900-02-29", "2026-13-01", "2026-1-01"):
                with self.subTest(method=method, path=path, field=field, value=invalid):
                    response = self.client.request(method, path, json={**payload, field: invalid})
                    self.assertEqual(response.status_code, 422)
                    self.assertFalse(response.json()["success"])
        task = self.client.post("/api/farm-tasks", json={"title": "查苗", "due_on": "2026-10-19"}).json()["task"]
        self.assertEqual(self.client.patch(f"/api/farm-tasks/{task['id']}", json={
            "title": "查苗", "due_on": "2026-02-31",
        }).status_code, 422)
        self.assertEqual(get_season(self.first_id)["started_on"], "2026-04-01")

    def test_valid_leap_dates_keep_iso_string_contract(self) -> None:
        for valid in ("2024-02-29", "2000-02-29", "2026-02-28"):
            with self.subTest(valid=valid):
                response = self.client.post("/api/farm-tasks", json={"title": "查苗", "due_on": valid})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["task"]["due_on"], valid)

    def test_season_end_before_start_is_rejected_but_equal_is_allowed(self) -> None:
        payload = {"crop": "玉米", "started_on": "2026-04-01", "ended_on": "2026-03-01"}
        self.assertEqual(self.client.patch(f"/api/seasons/{self.first_id}", json=payload).status_code, 422)
        self.assertIsNone(get_season(self.first_id)["ended_on"])
        payload["ended_on"] = "2026-04-01"
        self.assertEqual(self.client.patch(f"/api/seasons/{self.first_id}", json=payload).status_code, 200)

    def test_backfilled_record_and_economics_belong_to_historical_season(self) -> None:
        second = self.second_season()
        response = self.record()
        self.assertEqual(response.status_code, 200)
        record = response.json()["record"]
        self.assertEqual(record["season_id"], self.first_id)
        self.assertEqual(record["crop"], "玉米")
        rows = self.client.get("/api/farm-records/economics").json()["plots"]
        by_id = {row["season_id"]: row for row in rows}
        self.assertEqual(by_id[self.first_id]["total_yield_kg"], 100)
        self.assertEqual(by_id[self.first_id]["total_revenue"], 200)
        self.assertEqual(by_id[self.first_id]["net_revenue"], 170)
        self.assertEqual(by_id[second["id"]]["record_count"], 0)

    def test_gap_before_first_and_unknown_start_stay_unassigned(self) -> None:
        second = self.second_season(started_on=None)
        for day in ("2026-03-31", "2026-04-30", "2026-06-01", "2026-10-19"):
            self.assertIsNone(self.record(day).json()["record"]["season_id"])
        # 日期未知时可明确指定；null 可明确保留未归茬。
        self.assertEqual(self.record("2026-10-19", season_id=second["id"]).json()["record"]["season_id"], second["id"])
        self.assertIsNone(self.record(season_id=None).json()["record"]["season_id"])

    def test_overlapping_seasons_require_explicit_choice(self) -> None:
        second = self.second_season(started_on="2026-05-01")
        self.assertIsNone(self.record("2026-05-15").json()["record"]["season_id"])
        self.assertEqual(self.record("2026-05-15", season_id=self.first_id).json()["record"]["season_id"], self.first_id)
        self.assertEqual(self.record("2026-05-15", season_id=second["id"]).json()["record"]["season_id"], second["id"])

    def test_explicit_season_checks_owner_plot_and_dates(self) -> None:
        second = self.second_season()
        self.assertEqual(self.record(season_id=second["id"]).status_code, 422)
        self.assertEqual(self.record(season_id="missing").status_code, 404)
        other_plot = self.client.post("/api/plots", json={
            "name": "另一块田", "area_mu": 1, "soil_type": "壤土", "irrigation": "井灌", "crop": "玉米",
        }).json()["plot"]
        self.assertEqual(self.record(season_id=other_plot["active_season"]["id"]).status_code, 404)
        with TestClient(self.app) as other:
            other.post("/api/auth/guest")
            other_id = other.post("/api/plots", json={
                "name": "他人的田", "area_mu": 1, "soil_type": "壤土", "irrigation": "井灌", "crop": "玉米",
            }, headers={"X-CSRF-Token": other.cookies["yunxun_csrf"]}).json()["plot"]["active_season"]["id"]
        self.assertEqual(self.record(season_id=other_id).status_code, 404)

    def test_reopening_old_season_returns_conflict_and_keeps_database_state(self) -> None:
        second = self.second_season()
        for race in (False, True):
            with self.subTest(race=race):
                # 模拟前置检查后出现竞争：实际写库仍由唯一索引保护。
                with patch("backend.app.services.farm.get_active_season", return_value=None) if race else patch(
                    "backend.app.services.farm.get_active_season", wraps=get_active_season
                ):
                    response = self.client.patch(f"/api/seasons/{self.first_id}", json={
                        "crop": "玉米", "started_on": "2026-04-01", "ended_on": None,
                    })
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "CONFLICT")
                self.assertEqual(get_active_season(self.plot["id"])["id"], second["id"])
                self.assertEqual(get_season(self.first_id)["ended_on"], "2026-05-31")

    def test_create_season_race_returns_conflict(self) -> None:
        with patch("backend.app.services.farm.get_active_season", return_value=None):
            response = self.client.post("/api/seasons", json={
                "plot_id": self.plot["id"], "crop": "大豆", "started_on": "2026-10-01",
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "CONFLICT")
        self.assertEqual(get_active_season(self.plot["id"])["id"], self.first_id)
