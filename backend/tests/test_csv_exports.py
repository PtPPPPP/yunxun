import codecs
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

from fastapi.testclient import TestClient

from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.database import get_connection
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.repositories import create_farm_record, create_season, get_active_season, get_user_by_id, update_season
from backend.app.services.auth import register_user
from backend.tests.helpers import make_plot


class CsvExportsTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "exports.db"
        environment = patch.dict(os.environ, {"YUNXUN_DB_PATH": str(self.database), "YUNXUN_ENV": "test",
            "YUNXUN_COOKIE_SECURE": "false", "YUNXUN_JWT_SECRET": "export-test-secret",
            "YUNXUN_AUTH_REQUESTS_PER_MINUTE": "2000", "YUNXUN_REQUESTS_PER_MINUTE": "600",
            "YUNXUN_ALLOWED_ORIGINS": "http://127.0.0.1:5173"})
        environment.start()
        self.addCleanup(environment.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        limiter = patch.object(auth, "auth_rate_limiter", InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        from backend.app.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        identity = register_user("export_farmer", "export-password", "农户")
        self.user, self.token = identity["user"], identity["token"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"
        self.plot = make_plot(self.user["id"], name='东田,"温室"\n甲区', started_on="2025-10-01")
        self.first = get_active_season(self.plot["id"])
        update_season(self.first["id"], "玉米", "2025-10-01", "2026-05-31", "")
        self.second = create_season(self.user["id"], self.plot["id"], "大豆", "2026-10-01", "")
        self.other = register_user("other_farmer", "other-password", "其他用户")
        self.foreign = make_plot(self.other["user"]["id"], name="他人的地块", crop="私有作物")

    def record(self, **overrides):
        return create_farm_record(**{"user_id": self.user["id"], "plot_id": self.plot["id"], "season_id": self.first["id"],
            "kind": "施肥", "happened_on": "2025-12-31", "crop": "玉米", "detail": "", "quantity": "", "cost": None, **overrides})

    def export(self, summary=False, **params):
        endpoint = "/api/farm-records/economics/export.csv" if summary else "/api/farm-records/export.csv"
        response = self.client.get(endpoint, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.content.startswith(codecs.BOM_UTF8))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))
        self.assertEqual(int(response.headers["x-export-row-count"]), len(rows))
        return response, rows

    def filename(self, response):
        return unquote(response.headers["content-disposition"].split("filename*=UTF-8''", 1)[1])

    def test_all_filtered_records_exported_across_pages_without_cursor_or_limit(self):
        for index in range(137):
            self.record(detail=f"匹配-{index}", cost=index)
        self.record(happened_on="2025-11-30", detail="日期前")
        self.record(happened_on="2026-01-01", detail="日期后")
        self.record(kind="采收", detail="其他类型")
        self.record(season_id=self.second["id"], happened_on="2026-10-01", detail="其他茬")
        another = make_plot(self.user["id"], name="本人另一地块")
        self.record(plot_id=another["id"], season_id=get_active_season(another["id"])["id"], detail="其他地块")
        self.record(user_id=self.other["user"]["id"], plot_id=self.foreign["id"], season_id=get_active_season(self.foreign["id"])["id"], detail="他人记录")
        filters = {"plot_id": self.plot["id"], "season_id": self.first["id"], "kind": "施肥",
                   "date_from": "2025-12-01", "date_to": "2025-12-31", "data_scope": "real"}
        seen, cursor = [], None
        while True:
            page = self.client.get("/api/farm-records", params={**filters, "limit": 19, **({"cursor": cursor} if cursor else {})}).json()
            seen.extend(row["detail"] for row in page["records"])
            if not page["pagination"]["has_more"]:
                break
            cursor = page["pagination"]["next_cursor"]
        response, exported = self.export(**filters, limit=1, cursor="not-a-pagination-token")
        self.assertEqual(len(exported), 137)
        self.assertEqual([row["说明"] for row in exported], seen)
        name = self.filename(response)
        for fragment in ("农事台账", "真实记录", "玉米", "施肥", "2025-12-01至2025-12-31"):
            self.assertIn(fragment, name)

    def test_chinese_quotes_commas_newlines_and_units_round_trip(self):
        detail = '检查叶片,"注意"\r\n第二行：正常\n第三行'
        self.record(material='复合肥,"甲"', quantity="2 袋，每袋 50 公斤", cost=12.5, detail=detail)
        _, rows = self.export(season_id=self.first["id"])
        self.assertEqual(rows[0]["地块"], self.plot["name"])
        self.assertEqual(rows[0]["说明"], detail)
        self.assertEqual(rows[0]["投入品"], '复合肥,"甲"')
        self.assertEqual(rows[0]["用量（原填写内容及单位）"], "2 袋，每袋 50 公斤")
        self.assertEqual(rows[0]["茬次开始日期"], "2025-10-01")
        self.assertEqual(rows[0]["茬次结束日期"], "2026-05-31")
        self.assertEqual(float(rows[0]["费用（元）"]), 12.5)

    def test_missing_and_inapplicable_fields_stay_empty_and_zero_stays_numeric(self):
        self.record(detail="未填")
        self.record(kind="采收", yield_kg=0, unit_price=2, cost=0, detail="零值")
        self.record(kind="采收", yield_kg=10, cost=0, detail="缺单价")
        # 旧数据中隐藏的类型字段不能随导出混入适用业务列。
        self.record(cost=0, yield_kg=99, unit_price=10, safe_days=9, detail="不适用")
        _, rows = self.export()
        by_note = {row["说明"]: row for row in rows}
        for column in ("费用（元）", "采收产量（公斤）", "采收单价（元/公斤）", "已记录收入（元）", "登记间隔期（天）"):
            self.assertEqual(by_note["未填"][column], "")
        self.assertEqual(by_note["零值"]["费用（元）"], "0.0")
        self.assertEqual(by_note["零值"]["已记录收入（元）"], "0.0")
        self.assertEqual(by_note["缺单价"]["采收单价（元/公斤）"], "")
        self.assertEqual(by_note["缺单价"]["已记录收入（元）"], "")
        for column in ("采收产量（公斤）", "采收单价（元/公斤）", "已记录收入（元）", "登记间隔期（天）"):
            self.assertEqual(by_note["不适用"][column], "")

    def test_formula_injection_neutralized_in_every_untrusted_text_column(self):
        attacks = ["=1+2", "+SUM(1,2)", "-2+3", "@SUM(1,2)", "\t=1", "\r=1", "\n=1", "\x00=1",
                   "  =1", "\u00a0\ufeff=1", "\u200b=1", "＝1+1", "＋SUM(1)", "－1+1", "＠SUM(1)", '="a,b"\n=2']
        for index, attack in enumerate(attacks):
            self.record(detail=attack, quantity=attack, material=attack, crop=attack, cost=index)
        with get_connection() as conn:
            conn.execute("UPDATE plots SET name='=1+1' WHERE id=?", (self.plot["id"],))
            conn.execute("UPDATE plot_seasons SET crop='@SUM(1)' WHERE id=?", (self.first["id"],))
        _, rows = self.export()
        for row in rows:
            for column in ("地块", "作业作物", "茬次作物", "投入品", "用量（原填写内容及单位）", "说明"):
                self.assertTrue(row[column].startswith("\t'"), column)
            self.assertFalse(row["费用（元）"].startswith(("'", "\t")))
        self.assertEqual({row["说明"][2:] for row in rows}, set(attacks))

    def test_summary_missing_values_zero_values_and_numeric_negative_difference(self):
        self.record(kind="采收", yield_kg=12)
        self.record()
        _, rows = self.export(summary=True, season_id=self.first["id"])
        row = rows[0]
        self.assertEqual(row["已记录支出（元）"], "")
        self.assertEqual(row["已记录收入（元）"], "")
        self.assertEqual(row["亩均收入（元/亩）"], "")
        self.assertEqual(float(row["已记录产量（公斤）"]), 12)
        self.assertEqual(row["费用未填（条）"], "2")
        self.assertEqual(row["采收待补录（条）"], "1")
        self.record(cost=30)
        self.record(kind="采收", cost=0, yield_kg=0, unit_price=3)
        _, rows = self.export(summary=True, season_id=self.first["id"])
        self.assertEqual(float(rows[0]["已记录收入（元）"]), 0)
        self.assertEqual(float(rows[0]["已记录收支差额（元）"]), -30)
        self.assertEqual(rows[0]["已记录收支差额（元）"], "-30.0")
        self.assertIn("未记录的人工、地租", rows[0]["核算说明"])

    def test_historical_cross_year_summary_and_detail_match_api(self):
        self.record(cost=30)
        self.record(kind="采收", yield_kg=100, unit_price=2, cost=0, happened_on="2026-01-01")
        self.record(season_id=self.second["id"], happened_on="2026-10-01", cost=999)
        for year, count in ((2025, 1), (2026, 1), (None, 2)):
            filters = {"season_id": self.first["id"], "data_scope": "real", **({"year": year} if year else {})}
            _, rows = self.export(summary=True, **filters)
            _, details = self.export(**filters)
            summary = self.client.get("/api/farm-records/economics", params=filters).json()["plots"][0]
            for column, field in (("已记录支出（元）", "total_cost"), ("已记录收入（元）", "total_revenue"), ("已记录收支差额（元）", "net_revenue"), ("亩均收支差额（元/亩）", "net_per_mu")):
                self.assertEqual(float(rows[0][column]), summary[field])
            self.assertEqual(len(details), count)
            self.assertEqual(int(rows[0]["记录次数"]), count)
            self.assertEqual(rows[0]["年度口径"], "按作业日期")
            self.assertEqual(rows[0]["作业年份"], str(year) if year else "全部年份")

    def test_unassigned_and_quality_scopes_preserve_filter_semantics(self):
        self.record(season_id=None, cost=0)
        self.record(kind="采收", yield_kg=3)
        self.record(kind="采收", yield_kg=4, unit_price=2, cost=5)
        for scope in ("cost", "revenue", "missing_cost", "incomplete_harvest"):
            _, rows = self.export(economics_scope=scope)
            page = self.client.get("/api/farm-records", params={"economics_scope": scope}).json()["records"]
            self.assertEqual(len(rows), len(page))
        _, rows = self.export(season_id="unassigned")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["归茬情况"], "未归茬")
        self.assertEqual(rows[0]["茬次开始日期"], "")
        _, rows = self.export(summary=True, season_id="unassigned")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["归茬情况"], "未归茬")

    def test_real_and_demo_sources_are_separate_and_labeled(self):
        self.record(detail="真实")
        demo = self.record(detail="演示")
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET is_demo=1 WHERE id=?", (demo["id"],))
        for scope, expected in (("real", ["真实"]), ("demo", ["演示"]), ("all", ["真实", "演示"])):
            _, rows = self.export(data_scope=scope)
            self.assertCountEqual([row["说明"] for row in rows], expected)
            _, summaries = self.export(summary=True, season_id=self.first["id"], data_scope=scope)
            self.assertEqual(int(summaries[0]["记录次数"]), len(expected))
        _, rows = self.export(data_scope="demo")
        self.assertEqual(rows[0]["记录来源"], "演示记录")

    def test_empty_results_have_headers_and_do_not_create_files_or_change_data(self):
        before_files = set(self.database.parent.iterdir())
        with get_connection() as conn:
            before = conn.execute("SELECT COUNT(*) FROM farm_records").fetchone()[0]
        for summary, params in ((False, {}), (True, {"data_scope": "demo"})):
            response, rows = self.export(summary=summary, **params)
            self.assertEqual(rows, [])
            self.assertEqual(len(list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))), 1)
        self.assertEqual(set(self.database.parent.iterdir()), before_files)
        with get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM farm_records").fetchone()[0], before)

    def test_unauthenticated_and_foreign_plot_season_and_cross_plot_are_rejected(self):
        foreign_season = get_active_season(self.foreign["id"])
        another = make_plot(self.user["id"])
        for endpoint in ("/api/farm-records/export.csv", "/api/farm-records/economics/export.csv"):
            for params in ({"plot_id": self.foreign["id"]}, {"season_id": foreign_season["id"]},
                           {"plot_id": another["id"], "season_id": self.first["id"]}, {"plot_id": "absent"}):
                response = self.client.get(endpoint, params=params)
                self.assertEqual(response.status_code, 404, response.text)
                self.assertNotIn("他人的地块", response.text)
                self.assertNotIn("content-disposition", response.headers)
        self.client.headers.pop("Authorization")
        self.assertEqual(self.client.get("/api/farm-records/export.csv").status_code, 401)
        self.assertEqual(self.client.get("/api/farm-records/economics/export.csv").status_code, 401)

    def test_export_whitelist_excludes_credentials_config_and_other_user_data(self):
        self.record(detail="本人记录")
        self.record(user_id=self.other["user"]["id"], plot_id=self.foreign["id"], season_id=get_active_season(self.foreign["id"])["id"], detail="他人秘密记录")
        stored = get_user_by_id(self.user["id"])
        for summary in (False, True):
            response, _ = self.export(summary=summary)
            for value in (self.token, stored["password_hash"], self.user["id"], "他人秘密记录", "他人的地块", "私有作物", str(self.database), "password_hash", "token_hash", "recovery_code_hash"):
                self.assertNotIn(value, response.text)
        response, rows = self.export(user_id=self.other["user"]["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["说明"], "本人记录")
        self.assertNotIn("他人秘密记录", response.text)

    def test_corrupt_legacy_links_cannot_leak_foreign_related_entities(self):
        row = self.record()
        foreign_season = get_active_season(self.foreign["id"])
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET season_id=? WHERE id=?", (foreign_season["id"], row["id"]))
        response, rows = self.export()
        self.assertEqual(rows[0]["归茬情况"], "茬次关联不可用")
        self.assertNotIn("私有作物", response.text)
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET plot_id=?,season_id=NULL WHERE id=?", (self.foreign["id"], row["id"]))
            conn.execute("UPDATE plot_seasons SET plot_id=? WHERE id=?", (self.foreign["id"], self.first["id"]))
        for summary in (False, True):
            response, _ = self.export(summary=summary)
            self.assertNotIn("他人的地块", response.text)

    def test_invalid_filter_dates_kinds_and_scopes_fail_like_list_api(self):
        for params in ({"date_from": "2026-02-31"}, {"date_from": "2026-02-01", "date_to": "2026-01-01"},
                       {"kind": "unknown"}, {"economics_scope": "unknown"}, {"data_scope": "unknown"}, {"year": 0}):
            response = self.client.get("/api/farm-records/export.csv", params=params)
            original = self.client.get("/api/farm-records", params=params)
            self.assertEqual(response.status_code, original.status_code)
            self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/farm-records/economics/export.csv", params={"year": "invalid"}).status_code, 422)

    def test_filename_and_cors_download_headers_are_safe_and_readable(self):
        with get_connection() as conn:
            conn.execute("UPDATE plots SET name=? WHERE id=?", ('地块../\\"\r\nX-Bad: value', self.plot["id"]))
        response = self.client.get("/api/farm-records/export.csv", params={"plot_id": self.plot["id"]}, headers={"Origin": "http://127.0.0.1:5173"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("content-disposition", response.headers["access-control-expose-headers"].lower())
        self.assertIn("x-export-row-count", response.headers["access-control-expose-headers"].lower())
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5173")
        self.assertIn("x-request-id", response.headers)
        filename = self.filename(response)
        for character in '\r\n"/\\:*?<>|':
            self.assertNotIn(character, filename)
        self.assertNotIn("x-bad", response.headers)
