"""F4/F5：临时 SQLite、真实故障注入与写事务交错，不使用业务数据库。"""
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app import repositories as repo
from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import get_connection, init_db
from backend.app.core.exceptions import http_exception_handler
from backend.app.services import farm
from backend.tests.helpers import make_settings


class FarmTransactionTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "farm-transactions.db"
        settings = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        settings.start()
        self.addCleanup(settings.stop)
        init_db()
        self.user_id = repo.create_user("farmer", "hash", "农户")["id"]
        self.other_id = repo.create_user("other", "hash", "其他农户")["id"]
        app = FastAPI()
        app.include_router(router)
        app.add_exception_handler(HTTPException, http_exception_handler)
        app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.plot_payload = dict(name="事务试验田", area_mu=2, soil_type="壤土", irrigation="井灌",
                                 notes="地块原备注", crop="玉米", planted_on="2026-04-01")

    def create_plot(self, **overrides):
        response = self.client.post("/api/plots", json={**self.plot_payload, **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["plot"]

    def record(self, plot, **overrides):
        response = self.client.post("/api/farm-records", json={"plot_id": plot["id"],
            "season_id": plot["active_season"]["id"], "kind": "施肥", "happened_on": "2026-04-30", "cost": 20, **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["record"]

    def season_patch(self, plot, **overrides):
        return self.client.patch(f"/api/seasons/{plot['active_season']['id']}", json={
            "crop": "玉米", "started_on": "2026-04-01", "ended_on": None, "notes": "茬次新备注", **overrides})

    def raw_rows(self, table):
        self.assertIn(table, ("plots", "plot_seasons", "farm_records"))
        with get_connection() as conn:
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]

    def snapshot(self):
        return {table: self.raw_rows(table) for table in ("plots", "plot_seasons", "farm_records")}

    def assert_invariants(self):
        with get_connection() as conn:
            invalid = conn.execute("""SELECT r.id FROM farm_records r LEFT JOIN plot_seasons s ON s.id=r.season_id
                WHERE r.season_id IS NOT NULL AND (s.id IS NULL OR s.user_id<>r.user_id OR s.plot_id<>r.plot_id
                  OR (s.started_on IS NOT NULL AND r.happened_on<s.started_on)
                  OR (s.ended_on IS NOT NULL AND r.happened_on>s.ended_on))""").fetchall()
            self.assertEqual(invalid, [])
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_first_and_second_insert_faults_leave_no_partial_plot_and_retry_succeeds(self):
        before = self.snapshot()
        for table in ("plots", "plot_seasons"):
            with self.subTest(table=table):
                with get_connection() as conn:
                    conn.execute(f"CREATE TRIGGER fail_insert BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected insert failure'); END")
                response = self.client.post("/api/plots", json=self.plot_payload)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(self.snapshot(), before)
                with get_connection() as conn:
                    conn.execute("DROP TRIGGER fail_insert")
        plot = self.create_plot()
        self.assertEqual(len(self.raw_rows("plots")), 1)
        self.assertEqual(len(self.raw_rows("plot_seasons")), 1)
        self.assertEqual(repo.get_season(plot["active_season"]["id"])["plot_id"], plot["id"])
        self.assert_invariants()

    def test_creation_uses_one_connection_and_never_publishes_half_a_plot(self):
        events = []
        @contextmanager
        def traced():
            with get_connection() as conn:
                conn.set_trace_callback(events.append)
                yield conn
        original = repo._insert_season
        def check_before_second_insert(conn, *args):
            self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM plots").fetchone()[0], 1)
            # 独立读连接看不到未提交的第一步。
            with get_connection() as observer:
                self.assertEqual(observer.execute("SELECT COUNT(*) FROM plots").fetchone()[0], 0)
                self.assertEqual(observer.execute("SELECT COUNT(*) FROM plot_seasons").fetchone()[0], 0)
            return original(conn, *args)
        with patch.object(repo, "get_connection", side_effect=traced) as connections, patch.object(repo, "_insert_season", side_effect=check_before_second_insert):
            repo.create_plot_with_first_season(self.user_id, "原子地块", 2, "壤土", "井灌", "", "玉米", None)
        self.assertEqual(connections.call_count, 1)
        statements = [sql.strip().upper() for sql in events]
        self.assertEqual(statements.count("BEGIN IMMEDIATE"), 1)
        self.assertEqual(statements.count("COMMIT"), 1)
        self.assert_invariants()

    def test_f5_rejects_start_end_and_combined_conflicts_without_any_row_change(self):
        plot = self.create_plot()
        self.record(plot, happened_on="2026-04-30")
        self.record(plot, happened_on="2026-06-15")
        before = self.snapshot()
        for dates, count in (({"started_on": "2026-05-01"}, 1),
                             ({"ended_on": "2026-05-31"}, 1),
                             ({"started_on": "2026-05-01", "ended_on": "2026-05-31"}, 2)):
            with self.subTest(dates=dates):
                response = self.season_patch(plot, **dates)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["code"], "CONFLICT")
                self.assertIn(f"{count} 条台账", response.json()["error"])
                self.assertEqual(self.snapshot(), before)
        self.assert_invariants()

    def test_conflict_counts_live_and_recycle_bin_records_and_preserves_restore(self):
        plot = self.create_plot()
        first = self.record(plot)
        second = self.record(plot, happened_on="2026-04-29")
        self.assertEqual(self.client.delete(f"/api/farm-records/{second['id']}").status_code, 200)
        before = self.snapshot()
        response = self.season_patch(plot, started_on="2026-05-01")
        self.assertEqual(response.status_code, 409)
        self.assertIn("2 条台账", response.json()["error"])
        self.assertIn("回收站 1 条", response.json()["error"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post(f"/api/trash/records/{second['id']}/restore").status_code, 200)
        self.assertEqual(repo.get_farm_record(first["id"])["season_id"], repo.get_farm_record(second["id"])["season_id"])
        self.assert_invariants()

    def test_only_recycle_bin_record_still_blocks_date_narrowing(self):
        plot = self.create_plot()
        record = self.record(plot)
        self.client.delete(f"/api/farm-records/{record['id']}")
        before = self.snapshot()
        response = self.season_patch(plot, ended_on="2026-04-29")
        self.assertEqual(response.status_code, 409)
        self.assertIn("回收站 1 条", response.json()["error"])
        self.assertEqual(self.snapshot(), before)

    def test_valid_inclusive_bounds_null_dates_and_metadata_changes_preserve_records(self):
        plot = self.create_plot(planted_on=None)
        self.record(plot, happened_on="2026-04-01")
        self.record(plot, happened_on="2026-05-31")
        before_records = self.raw_rows("farm_records")
        for start, end in (("2026-04-01", "2026-05-31"), (None, "2026-05-31"),
                           ("2026-04-01", None), (None, None), ("2026-03-01", "2026-06-30")):
            with self.subTest(start=start, end=end):
                response = self.season_patch(plot, crop="大豆", started_on=start, ended_on=end)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["season"]["started_on"], start)
                self.assertEqual(response.json()["season"]["ended_on"], end)
                self.assertEqual(self.raw_rows("farm_records"), before_records)
                self.assert_invariants()

    def test_unassigned_other_season_and_other_users_do_not_block_valid_update(self):
        plot = self.create_plot()
        unassigned = self.record(plot, season_id=None, happened_on="2025-01-01")
        old = plot["active_season"]["id"]
        self.assertEqual(self.season_patch(plot, ended_on="2026-05-31").status_code, 200)
        current = repo.create_season(self.user_id, plot["id"], "大豆", "2026-06-01", "")
        repo.create_farm_record(self.user_id, plot["id"], "其他", "2026-06-15", "大豆", "", "", 0, season_id=current["id"])
        other = repo.create_plot_with_first_season(self.other_id, "他人的田", 1, "壤土", "雨养", "", "玉米", "2026-01-01")
        foreign = repo.get_active_season(other["id"])
        repo.create_farm_record(self.other_id, other["id"], "其他", "2026-01-02", "玉米", "", "", 0, season_id=foreign["id"])
        before = self.raw_rows("farm_records")
        response = self.client.patch(f"/api/seasons/{old}", json={"crop": "玉米", "started_on": "2026-04-10", "ended_on": "2026-05-20"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.raw_rows("farm_records"), before)
        self.assertIsNone(repo.get_farm_record(unassigned["id"])["season_id"])
        self.assert_invariants()

    def test_legacy_plot_update_reuses_date_guard_and_rolls_back_plot_fields(self):
        plot = self.create_plot()
        record = self.record(plot)
        self.client.delete(f"/api/farm-records/{record['id']}")
        before = self.snapshot()
        response = self.client.patch(f"/api/plots/{plot['id']}", json={**self.plot_payload,
            "name": "不应保存的名称", "area_mu": 99, "notes": "不应保存的备注", "crop": "番茄", "planted_on": "2026-06-01"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("回收站 1 条", response.json()["error"])
        self.assertEqual(self.snapshot(), before)
        response = self.client.patch(f"/api/plots/{plot['id']}", json={**self.plot_payload,
            "name": "合法的新名称", "crop": "番茄", "planted_on": "2026-04-30"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plot"]["name"], "合法的新名称")
        self.assertEqual(response.json()["plot"]["crop"], "番茄")
        self.assertEqual(self.raw_rows("farm_records"), before["farm_records"])
        self.assert_invariants()

    def test_legacy_plot_and_season_update_sql_failure_roll_back_together(self):
        plot = self.create_plot()
        before = self.snapshot()
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON plot_seasons BEGIN SELECT RAISE(ABORT,'injected season update failure'); END")
        response = self.client.patch(f"/api/plots/{plot['id']}", json={**self.plot_payload, "name": "不应残留", "crop": "番茄"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.snapshot(), before)

    def test_record_create_and_edit_revalidate_after_service_preparation(self):
        for edit in (False, True):
            with self.subTest(edit=edit):
                plot = self.create_plot()
                record = self.record(plot, happened_on="2026-04-01") if edit else None
                original = farm._prepare_farm_record
                def change_dates_after_preparation(*args, **kwargs):
                    prepared = original(*args, **kwargs)
                    repo.update_season(plot["active_season"]["id"], "玉米", "2026-04-01", "2026-04-15", "")
                    return prepared
                before = self.raw_rows("farm_records")
                values = dict(plot_id=plot["id"], season_id=plot["active_season"]["id"], kind="施肥", happened_on="2026-04-30", cost=888)
                with patch.object(farm, "_prepare_farm_record", side_effect=change_dates_after_preparation):
                    response = self.client.patch(f"/api/farm-records/{record['id']}", json=values) if edit else self.client.post("/api/farm-records", json=values)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(self.raw_rows("farm_records"), before)
                self.assert_invariants()

    def test_auto_selection_and_crop_use_current_transaction_not_prepared_snapshot(self):
        plot = self.create_plot()
        original = farm._prepare_farm_record
        def change_seasons(*args, **kwargs):
            prepared = original(*args, **kwargs)
            repo.update_season(plot["active_season"]["id"], "玉米", "2026-04-01", "2026-04-15", "")
            repo.create_season(self.user_id, plot["id"], "大豆", "2026-04-16", "")
            return prepared
        with patch.object(farm, "_prepare_farm_record", side_effect=change_seasons):
            response = self.client.post("/api/farm-records", json={"plot_id": plot["id"], "kind": "其他", "happened_on": "2026-04-30"})
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()["record"]
        self.assertEqual(record["season_id"], repo.get_active_season(plot["id"])["id"])
        self.assertEqual(record["crop"], "大豆")
        self.assert_invariants()

    def test_auto_selection_detects_new_ambiguity_and_preserves_explicit_null(self):
        plot = self.create_plot()
        old = plot["active_season"]["id"]
        repo.update_season(old, "玉米", "2026-04-01", "2026-05-31", "")
        original = farm._prepare_farm_record
        def overlap_after_preparation(*args, **kwargs):
            prepared = original(*args, **kwargs)
            repo.create_season(self.user_id, plot["id"], "大豆", "2026-04-15", "")
            return prepared
        with patch.object(farm, "_prepare_farm_record", side_effect=overlap_after_preparation):
            response = self.client.post("/api/farm-records", json={"plot_id": plot["id"], "kind": "其他", "happened_on": "2026-04-30"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.raw_rows("farm_records"), [])
        response = self.client.post("/api/farm-records", json={"plot_id": plot["id"], "season_id": None, "kind": "其他", "happened_on": "2026-04-30"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["record"]["season_id"])
        self.assert_invariants()

    def test_repository_direct_writes_cannot_bypass_dates_and_keep_original_record(self):
        plot = self.create_plot()
        season_id = plot["active_season"]["id"]
        record = self.record(plot)
        values = {key: record[key] for key in ("plot_id", "season_id", "kind", "crop", "detail", "quantity", "cost", "material", "safe_days", "yield_kg", "unit_price")}
        before = self.snapshot()
        with self.assertRaises(HTTPException) as create_error:
            repo.create_farm_record(self.user_id, plot["id"], "其他", "2026-03-31", "", "", "", 1, season_id=season_id)
        self.assertEqual(create_error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as edit_error:
            repo.update_farm_record(record["id"], self.user_id, happened_on="2026-03-31", **values)
        self.assertEqual(edit_error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as season_error:
            repo.update_season(season_id, "番茄", "2026-05-01", None, "不应保存")
        self.assertEqual(season_error.exception.status_code, 409)
        with self.assertRaises(HTTPException) as reversed_dates:
            repo.update_season(season_id, "番茄", "2026-06-01", "2026-05-31", "不应保存")
        self.assertEqual(reversed_dates.exception.status_code, 422)
        self.assertEqual(self.snapshot(), before)

    def run_serialized_race(self, first_operation, second_operation, guard_name):
        """持锁后暂停第一写者，确认第二连接到达 BEGIN，再放行；不依赖 sleep。"""
        locked, release, attempted = threading.Event(), threading.Event(), threading.Event()
        original = getattr(repo, guard_name)
        first_thread_id = None
        def guarded(conn, *args):
            nonlocal first_thread_id
            if first_thread_id is None:
                first_thread_id = threading.get_ident()
                self.assertTrue(conn.in_transaction)
                locked.set()
                self.assertTrue(release.wait(5), "未释放测试事务")
            return original(conn, *args)
        @contextmanager
        def connection():
            with get_connection() as conn:
                def trace(sql):
                    if sql.strip().upper() == "BEGIN IMMEDIATE" and first_thread_id is not None and threading.get_ident() != first_thread_id:
                        attempted.set()
                conn.set_trace_callback(trace)
                yield conn
        def result(operation):
            try:
                operation()
                return 200
            except HTTPException as exc:
                return exc.status_code
        with patch.object(repo, guard_name, side_effect=guarded), patch.object(repo, "get_connection", side_effect=connection):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(result, first_operation)
                try:
                    self.assertTrue(locked.wait(5), "第一个写者未持锁")
                    second = pool.submit(result, second_operation)
                    self.assertTrue(attempted.wait(5), "第二个连接未尝试写事务")
                    self.assertFalse(second.done(), "第一写者未提交时第二写者不应完成")
                finally:
                    release.set()
                return first.result(timeout=5), second.result(timeout=5)

    def test_season_commits_first_then_record_create_or_edit_rejects_new_out_of_range_date(self):
        for edit in (False, True):
            with self.subTest(edit=edit):
                plot = self.create_plot()
                season_id = plot["active_season"]["id"]
                record = self.record(plot, happened_on="2026-04-01") if edit else None
                before = self.raw_rows("farm_records")
                values = dict(plot_id=plot["id"], season_id=season_id, kind="施肥", happened_on="2026-06-15", crop="", detail="", quantity="", cost=100)
                def write_record():
                    if edit:
                        farm.update_user_farm_record(record["id"], self.user_id, "test", **values)
                    else:
                        farm.create_user_farm_record(self.user_id, "test", **values)
                results = self.run_serialized_race(
                    lambda: repo.update_season(season_id, "玉米", "2026-04-01", "2026-05-31", ""),
                    write_record, "_validate_season_record_dates")
                self.assertEqual(results, (200, 422))
                self.assertEqual(self.raw_rows("farm_records"), before)
                self.assert_invariants()

    def test_record_commits_first_then_season_or_legacy_plot_update_rejects_conflict(self):
        for edit in (False, True):
            for legacy in (False, True):
                with self.subTest(edit=edit, legacy=legacy):
                    plot = self.create_plot()
                    season_id = plot["active_season"]["id"]
                    record = self.record(plot, happened_on="2026-04-30") if edit else None
                    before_plot = repo.get_plot(plot["id"])
                    before_season = repo.get_season(season_id)
                    values = dict(plot_id=plot["id"], season_id=season_id, kind="施肥", happened_on="2026-06-15", crop="", detail="", quantity="", cost=100)
                    def write_record():
                        if edit:
                            farm.update_user_farm_record(record["id"], self.user_id, "test", **values)
                        else:
                            farm.create_user_farm_record(self.user_id, "test", **values)
                    def write_season():
                        if legacy:
                            farm.update_user_plot(plot["id"], self.user_id, "test", "不应保存", 99, "壤土", "井灌", "番茄", "2026-07-01", "不应保存")
                        else:
                            repo.update_season(season_id, "番茄", "2026-04-01", "2026-05-31", "不应保存")
                    results = self.run_serialized_race(write_record, write_season, "_resolve_record_season")
                    self.assertEqual(results, (200, 409))
                    self.assertEqual(repo.get_plot(plot["id"]), before_plot)
                    self.assertEqual(repo.get_season(season_id), before_season)
                    records = [r for r in self.raw_rows("farm_records") if r["plot_id"] == plot["id"]]
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]["happened_on"], "2026-06-15")
                    self.assert_invariants()
