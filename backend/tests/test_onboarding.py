import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import get_connection, init_db, SCHEMA_VERSION
from backend.app.core.exceptions import http_exception_handler, validation_exception_handler
from backend.app.repositories import create_user, get_active_season, delete_season
from backend.app.repositories_onboarding import load_demo_data
from backend.app.repositories_onboarding import clear_demo_data
from backend.app import repositories
from backend.app.services.auth import register_user, guest_login
from backend.tests.helpers import make_settings


class OnboardingTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = patch("backend.app.core.database.get_settings", return_value=make_settings(Path(temporary.name) / "onboarding.db"))
        settings.start()
        self.addCleanup(settings.stop)
        init_db()
        self.guest = create_user("guest_test", "hash", "访客", is_guest=True)
        self.registered = create_user("registered", "hash", "农户")
        self.other = create_user("other_guest", "hash", "其他访客", is_guest=True)
        self.current_id = self.guest["id"]
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.add_exception_handler(RequestValidationError, validation_exception_handler)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.current_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def state(self):
        return self.client.get("/api/onboarding").json()["onboarding"]

    def load(self):
        response = self.client.post("/api/demo-data")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def clear(self):
        response = self.client.delete("/api/demo-data")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def plots(self):
        return self.client.get("/api/plots").json()["plots"]

    def records(self, **params):
        return self.client.get("/api/farm-records", params=params).json()["records"]

    def create_plot(self):
        response = self.client.post("/api/plots", json={"name": "我的田", "crop": "玉米", "planted_on": "2026-01-01", "area_mu": 2, "soil_type": "壤土", "irrigation": "井灌"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["plot"]

    def create_record(self, plot, **values):
        response = self.client.post("/api/farm-records", json={"plot_id": plot["id"], "kind": "施肥", "happened_on": "2026-10-19", "cost": 35, **values})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["record"]

    def test_real_progress_reuses_first_season_and_tracks_deletions(self):
        self.assertFalse(any(self.state()[field] for field in ("plot_done", "season_done", "record_done")))
        plot = self.create_plot()
        self.assertEqual(len(self.client.get("/api/seasons").json()["seasons"]), 1)
        self.assertTrue(self.state()["plot_done"])
        self.assertTrue(self.state()["season_done"])
        record = self.create_record(plot)
        self.assertTrue(self.state()["record_done"])
        self.client.delete(f"/api/farm-records/{record['id']}")
        self.assertFalse(self.state()["record_done"])
        with self.assertRaises(HTTPException) as blocked:
            delete_season(plot["active_season"]["id"])
        self.assertEqual(blocked.exception.status_code, 409)
        archived = self.client.get("/api/trash").json()["records"][0]
        self.assertEqual(self.client.delete(f"/api/trash/records/{record['id']}", params={"confirm": True, "expected_revision": archived["revision"]}).status_code, 200)
        delete_season(plot["active_season"]["id"])
        self.assertFalse(self.state()["season_done"])

    def test_skip_and_continue_are_persisted_without_faking_progress(self):
        self.assertEqual(self.client.patch("/api/onboarding", json={"skipped": True}).status_code, 200)
        self.assertTrue(self.state()["skipped"])
        self.assertFalse(self.state()["plot_done"])
        self.client.patch("/api/onboarding", json={"skipped": False})
        self.assertFalse(self.state()["skipped"])

    def test_demo_load_is_opt_in_repeatable_and_excluded_from_real_progress(self):
        self.assertEqual(self.plots(), [])
        self.assertFalse(self.load()["already_loaded"])
        self.assertTrue(self.load()["already_loaded"])
        self.assertEqual(len(self.plots()), 1)
        self.assertEqual(len(self.client.get("/api/seasons").json()["seasons"]), 1)
        self.assertEqual(len(self.records()), 3)
        self.assertTrue(all(record["is_demo"] for record in self.records()))
        self.assertFalse(self.state()["plot_done"])
        self.assertFalse(self.state()["season_done"])
        self.assertFalse(self.state()["record_done"])

    def test_concurrent_demo_loads_only_create_one_dataset(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: load_demo_data(self.current_id), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.plots()), 1)
        self.assertEqual(len(self.records()), 3)

    def test_partial_load_failure_rolls_back_every_entity_and_can_retry(self):
        with patch("backend.app.repositories_onboarding.uuid.uuid4", side_effect=[Mock(hex="plot"), Mock(hex="season"), RuntimeError("write failed")]):
            with self.assertRaises(RuntimeError):
                load_demo_data(self.current_id)
        self.assertEqual(self.plots(), [])
        self.assertFalse(self.state()["demo_loaded"])
        self.load()
        self.assertEqual(len(self.records()), 3)

    def test_clear_is_repeatable_and_can_reload_new_demo_dataset(self):
        self.load()
        old_id = self.plots()[0]["id"]
        self.clear()
        self.clear()
        self.assertEqual(self.plots(), [])
        self.assertEqual(self.records(), [])
        self.assertFalse(self.state()["demo_loaded"])
        self.load()
        self.assertNotEqual(self.plots()[0]["id"], old_id)

    def test_clear_preserves_independent_real_plot_record_and_task(self):
        plot = self.create_plot()
        record = self.create_record(plot)
        task = self.client.post("/api/farm-tasks", json={"title": "我的杂事", "due_on": "2026-10-19"}).json()["task"]
        self.load()
        self.clear()
        self.assertEqual([row["id"] for row in self.plots()], [plot["id"]])
        self.assertEqual([row["id"] for row in self.records()], [record["id"]])
        self.assertEqual(self.client.get("/api/farm-tasks").json()["tasks"][0]["id"], task["id"])

    def test_real_record_on_demo_season_retains_and_promotes_ancestors(self):
        self.load()
        plot = self.plots()[0]
        record = self.create_record(plot, happened_on=plot["active_season"]["started_on"], season_id=plot["active_season"]["id"])
        self.assertFalse(record["is_demo"])
        real_rows = self.client.get("/api/farm-records/economics", params={"data_scope": "real"}).json()["plots"]
        self.assertEqual(sum(row["total_cost"] for row in real_rows), 35)
        cleared = self.clear()
        self.assertEqual(cleared["retained"], {"plots": 1, "plot_seasons": 1})
        self.assertFalse(self.plots()[0]["is_demo"])
        self.assertFalse(get_active_season(plot["id"])["is_demo"])
        self.assertEqual(self.records(), [record])
        self.clear()
        self.load()
        self.assertEqual(len(self.plots()), 2)
        self.assertTrue(any(row["id"] == record["id"] for row in self.records()))

    def test_real_task_and_new_season_on_demo_plot_are_preserved(self):
        self.load()
        plot = self.plots()[0]
        task = self.client.post("/api/farm-tasks", json={"title": "自己加的待办", "plot_id": plot["id"], "due_on": "2026-10-19"}).json()["task"]
        delete_season(plot["active_season"]["id"])
        season = self.client.post("/api/seasons", json={"plot_id": plot["id"], "crop": "大豆", "started_on": "2026-01-01"}).json()["season"]
        self.clear()
        self.assertEqual(self.client.get("/api/seasons").json()["seasons"], [season])
        self.assertEqual(self.client.get("/api/farm-tasks").json()["tasks"], [task])
        self.assertEqual(self.plots()[0]["id"], plot["id"])

    def test_demo_origin_survives_edit_and_cannot_be_set_by_normal_clients(self):
        real_plot = self.create_plot()
        record = self.create_record(real_plot, is_demo=True)
        self.assertFalse(record["is_demo"])
        self.load()
        demo = next(item for item in self.records() if item["is_demo"])
        response = self.client.patch(f"/api/farm-records/{demo['id']}", json={"plot_id": real_plot["id"], "kind": "其他", "happened_on": "2026-10-19", "is_demo": False})
        self.assertTrue(response.json()["record"]["is_demo"])
        self.clear()
        self.assertEqual([item["id"] for item in self.records()], [record["id"]])

    def test_statistics_and_trace_filter_by_record_origin(self):
        real_plot = self.create_plot()
        self.create_record(real_plot)
        self.load()
        for scope, count, cost, revenue in (("real", 1, 35, 0), ("demo", 3, 200, 600), ("all", 4, 235, 600)):
            with self.subTest(scope=scope):
                rows = self.client.get("/api/farm-records/economics", params={"data_scope": scope}).json()["plots"]
                self.assertEqual(sum(row["record_count"] for row in rows), count)
                self.assertEqual(sum(row["total_cost"] for row in rows), cost)
                self.assertEqual(sum(row["total_revenue"] for row in rows), revenue)
                self.assertEqual(len(self.records(data_scope=scope)), count)
        self.assertEqual(self.client.get("/api/farm-records/economics?data_scope=invalid").status_code, 422)
        self.assertEqual(self.client.get("/api/farm-records?data_scope=invalid").status_code, 422)

    def test_ownership_and_registered_account_empty_defaults(self):
        self.load()
        self.current_id = self.registered["id"]
        self.assertFalse(self.state()["demo_loaded"])
        self.assertEqual(self.plots(), [])
        self.assertEqual(self.client.post("/api/demo-data").status_code, 403)
        self.clear()
        self.current_id = self.other["id"]
        self.client.patch("/api/onboarding", json={"skipped": True})
        self.load()
        self.clear()
        self.current_id = self.guest["id"]
        self.assertEqual(len(self.records()), 3)
        self.assertFalse(self.state()["skipped"])

    def test_source_filter_is_preserved_across_cursor_pages(self):
        self.create_record(self.create_plot())
        self.load()
        cursor, records = None, []
        while True:
            params = {"data_scope": "demo", "limit": 1}
            if cursor:
                params["cursor"] = cursor
            response = self.client.get("/api/farm-records", params=params).json()
            records.extend(response["records"])
            cursor = response["pagination"]["next_cursor"]
            if not cursor:
                break
        self.assertEqual(len(records), 3)
        self.assertEqual(len({row["id"] for row in records}), 3)
        self.assertTrue(all(row["is_demo"] for row in records))

    def test_clear_between_validation_and_create_returns_conflict_without_orphan(self):
        self.load()
        plot = self.plots()[0]
        self.client.post("/api/farm-tasks", json={"plot_id": plot["id"], "title": "保留地块的真实待办", "due_on": "2026-10-19"})
        def clear_then_create(**values):
            clear_demo_data(self.current_id)
            return repositories.create_farm_record(**values)
        with patch("backend.app.services.farm.create_farm_record", side_effect=clear_then_create):
            response = self.client.post("/api/farm-records", json={"plot_id": plot["id"], "season_id": plot["active_season"]["id"],
                "kind": "其他", "happened_on": plot["active_season"]["started_on"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.records(), [])
        self.assertEqual(len(self.plots()), 1)

    def test_clear_between_validation_and_edit_keeps_original_record(self):
        real_plot = self.create_plot()
        record = self.create_record(real_plot)
        self.load()
        demo = next(row for row in self.plots() if row["is_demo"])
        def clear_then_edit(*args, **values):
            clear_demo_data(self.current_id)
            return repositories.update_farm_record(*args, **values)
        with patch("backend.app.services.farm.update_farm_record", side_effect=clear_then_edit):
            response = self.client.patch(f"/api/farm-records/{record['id']}", json={"plot_id": demo["id"], "season_id": demo["active_season"]["id"],
                "kind": "其他", "happened_on": demo["active_season"]["started_on"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.records(), [record])

    def test_guest_flag_is_explicit_not_inferred_from_username(self):
        result = register_user("guest_12345678", "password", "注册农户")
        self.assertFalse(result["user"]["is_guest"])
        guest = guest_login()["user"]
        self.assertTrue(guest["is_guest"])
        self.current_id = guest["id"]
        self.assertEqual(self.plots(), [])

    def test_v9_migration_preserves_existing_data_and_defaults_to_real(self):
        plot = self.create_plot()
        record = self.create_record(plot)
        with get_connection() as conn:
            conn.execute("DROP TABLE demo_data_state")
            for table in ("plots", "plot_seasons", "farm_records", "farm_tasks"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN is_demo")
            conn.execute("ALTER TABLE users DROP COLUMN is_guest")
            conn.execute("ALTER TABLE users DROP COLUMN onboarding_skipped")
            conn.execute("PRAGMA user_version=9")
        init_db()
        init_db()
        with get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(self.records(), [record])
        self.assertEqual(self.plots()[0]["id"], plot["id"])
        self.assertFalse(self.plots()[0]["is_demo"])
