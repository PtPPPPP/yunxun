import csv
import io
import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import repositories, repositories_trash as trash
from backend.app.api.routes import auth
from backend.app.core.config import get_settings
from backend.app.core.database import SCHEMA_VERSION, get_connection, init_db
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.services.auth import register_user


class TrashTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "trash.db"
        env = patch.dict(os.environ, {"YUNXUN_DB_PATH": str(self.database), "YUNXUN_ENV": "test",
            "YUNXUN_JWT_SECRET": "trash-test-secret", "YUNXUN_COOKIE_SECURE": "false",
            "YUNXUN_AUTH_REQUESTS_PER_MINUTE": "2000", "YUNXUN_REQUESTS_PER_MINUTE": "600"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        limiter = patch.object(auth, "auth_rate_limiter", InMemoryRateLimiter())
        limiter.start(); self.addCleanup(limiter.stop)
        from backend.app.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        identity = self.client.post("/api/auth/register", json={"username": "trash_owner", "password": "owner-password", "display_name": "农户"}).json()
        self.user = identity["user"]
        self.client.headers["X-CSRF-Token"] = self.client.cookies["yunxun_csrf"]
        self.plot = self.post("/api/plots", {"name": "保留关联的田", "crop": "玉米", "area_mu": 2,
            "soil_type": "壤土", "irrigation": "井灌", "planted_on": "2026-04-01"})["plot"]
        self.first = self.plot["active_season"]
        self.client.patch(f"/api/seasons/{self.first['id']}", json={"crop": "玉米", "started_on": "2026-04-01", "ended_on": "2026-05-31"})
        self.second = self.post("/api/seasons", {"plot_id": self.plot["id"], "crop": "大豆", "started_on": "2026-10-01"})["season"]

    def post(self, path, data=None):
        response = self.client.post(path, json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def record(self, **overrides):
        return self.post("/api/farm-records", {"plot_id": self.plot["id"], "season_id": self.first["id"],
            "kind": "施肥", "happened_on": "2026-04-30", "cost": 30, **overrides})["record"]

    def seed(self):
        first = self.record()
        self.record(kind="采收", happened_on="2026-05-31", cost=0, yield_kg=100, unit_price=2)
        self.record(kind="打药", cost=10, material="按登记填写", safe_days=365)
        for done in (False, True):
            task = self.post("/api/farm-tasks", {"plot_id": self.plot["id"], "title": "已完成" if done else "未完成", "due_on": "2026-10-19"})["task"]
            if done:
                response = self.client.patch(f"/api/farm-tasks/{task['id']}", json={"plot_id": self.plot["id"], "title": task["title"], "due_on": task["due_on"], "done": True})
                self.assertEqual(response.status_code, 200)
        return first

    def snapshot(self):
        with get_connection() as conn:
            return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE user_id=? ORDER BY id", (self.user["id"],))]
                for table in ("plots", "plot_seasons", "farm_records", "farm_tasks")}

    def impact(self):
        response = self.client.get(f"/api/plots/{self.plot['id']}/delete-impact")
        self.assertEqual(response.status_code, 200)
        return response.json()["impact"]

    def delete_plot(self, revision=None):
        return self.client.delete(f"/api/plots/{self.plot['id']}", params={"expected_revision": revision} if revision else {})

    def contents(self):
        response = self.client.get("/api/trash")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def restore(self, kind, entity_id):
        return self.client.post(f"/api/trash/{kind}/{entity_id}/restore")

    def purge(self, kind, entity_id, revision, confirm=True):
        return self.client.delete(f"/api/trash/{kind}/{entity_id}", params={"expected_revision": revision, "confirm": confirm})

    def test_impact_counts_all_seasons_records_and_done_tasks(self):
        record = self.seed()
        self.client.delete(f"/api/farm-records/{record['id']}")
        impact = self.impact()
        self.assertEqual((impact["season_count"], impact["record_count"], impact["task_count"], impact["open_task_count"], impact["trashed_record_count"]), (2, 3, 2, 1, 1))
        response = self.delete_plot(impact["revision"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_records"], 3)
        self.assertEqual(response.json()["deleted_tasks"], 2)

    def test_stale_impact_rejected_without_deleting_new_related_data(self):
        revision = self.impact()["revision"]
        self.record()
        self.assertEqual(self.delete_plot(revision).status_code, 409)
        self.assertEqual(len(self.client.get("/api/plots").json()["plots"]), 1)
        self.assertEqual(self.contents()["plots"], [])
        self.assertEqual(self.delete_plot(self.impact()["revision"]).status_code, 200)

    def test_plot_hidden_consistently_and_restored_with_all_original_relationships(self):
        self.seed()
        original = self.snapshot()
        misc = self.post("/api/farm-tasks", {"title": "杂事不受影响", "due_on": "2026-10-19"})["task"]
        stats = self.client.get("/api/farm-records/economics").json()
        self.assertEqual(self.delete_plot().status_code, 200)
        for path, key in (("/api/plots", "plots"), ("/api/seasons", "seasons"), ("/api/farm-records", "records"), ("/api/farm-records/economics", "plots")):
            self.assertEqual(self.client.get(path).json()[key], [], path)
        self.assertEqual(self.client.get("/api/farm-records/stats").json()["record_count"], 0)
        self.assertEqual(self.client.get("/api/farm-records/stats").json()["plot_count"], 0)
        self.assertEqual(self.client.get("/api/farm-records/economics").json()["available_years"], [])
        tasks = self.client.get("/api/farm-tasks").json()
        self.assertEqual(tasks["tasks"], [misc]); self.assertEqual(tasks["recent_done"], [])
        for endpoint in ("/api/farm-records/export.csv", "/api/farm-records/economics/export.csv"):
            data = self.client.get(endpoint).content.decode("utf-8-sig")
            self.assertEqual(list(csv.DictReader(io.StringIO(data))), [])
        onboarding = self.client.get("/api/onboarding").json()["onboarding"]
        self.assertFalse(onboarding["plot_done"]); self.assertFalse(onboarding["season_done"]); self.assertFalse(onboarding["record_done"])
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 200)
        after = self.snapshot()
        after["farm_tasks"] = [row for row in after["farm_tasks"] if row["id"] != misc["id"]]
        self.assertEqual(after, original)
        self.assertEqual(self.client.get("/api/farm-records/economics").json(), stats)
        plot = self.client.get("/api/plots").json()["plots"][0]
        self.assertEqual(plot["record_count"], 3)
        self.assertIsNotNone(plot["harvest_safety"])

    def test_record_deletion_changes_counts_economics_safety_export_and_restoration(self):
        record = self.record(kind="打药", safe_days=365, material="登记记录")
        before = self.client.get("/api/farm-records/economics").json()
        self.assertEqual(self.client.delete(f"/api/farm-records/{record['id']}").status_code, 200)
        plot = self.client.get("/api/plots").json()["plots"][0]
        self.assertEqual(plot["record_count"], 0); self.assertIsNone(plot["harvest_safety"])
        self.assertEqual(self.client.get("/api/farm-records/stats").json()["record_count"], 0)
        self.assertEqual(self.client.get("/api/farm-records/economics").json()["available_years"], [])
        self.assertEqual(self.client.get("/api/farm-records/export.csv").headers["x-export-row-count"], "0")
        self.assertFalse(self.client.get("/api/onboarding").json()["onboarding"]["record_done"])
        self.assertEqual(self.restore("records", record["id"]).status_code, 200)
        self.assertEqual(self.client.get("/api/farm-records/economics").json(), before)
        self.assertEqual(repositories.get_farm_record(record["id"])["id"], record["id"])

    def test_plot_restore_leaves_independently_deleted_record_in_trash(self):
        record = self.seed()
        self.client.delete(f"/api/farm-records/{record['id']}")
        timestamp = self.contents()["records"][0]["deleted_at"]
        self.delete_plot()
        self.assertEqual(self.restore("records", record["id"]).status_code, 409)
        self.restore("plots", self.plot["id"])
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 2)
        self.assertEqual(self.contents()["records"][0]["deleted_at"], timestamp)
        self.assertEqual(self.restore("records", record["id"]).status_code, 200)
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 3)

    def test_repeated_delete_restore_and_purge_results_are_stable(self):
        record = self.record()
        for kind, entity_id, delete in (("records", record["id"], lambda: self.client.delete(f"/api/farm-records/{record['id']}")),
                                       ("plots", self.plot["id"], self.delete_plot)):
            self.assertEqual(delete().status_code, 200)
            first = self.contents()[kind][0]
            self.assertEqual(delete().status_code, 404)
            self.assertEqual(self.contents()[kind][0]["deleted_at"], first["deleted_at"])
            self.assertTrue(self.restore(kind, entity_id).json()["changed"])
            self.assertFalse(self.restore(kind, entity_id).json()["changed"])
        self.delete_plot()
        item = self.contents()["plots"][0]
        self.assertEqual(self.purge("plots", self.plot["id"], item["revision"]).status_code, 200)
        self.assertEqual(self.purge("plots", self.plot["id"], item["revision"]).status_code, 404)
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 404)

    def test_purge_requires_confirmation_and_fresh_revision_and_refuses_active(self):
        record = self.record()
        self.assertEqual(self.purge("plots", self.plot["id"], "bad").status_code, 409)
        self.assertEqual(self.purge("records", record["id"], "bad").status_code, 409)
        self.delete_plot()
        item = self.contents()["plots"][0]
        self.assertEqual(self.purge("plots", self.plot["id"], item["revision"], confirm=False).status_code, 422)
        self.assertEqual(self.purge("plots", self.plot["id"], "bad").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/trash/plots/{self.plot['id']}", params={"confirm": True}).status_code, 422)
        self.assertEqual(len(self.contents()["plots"]), 1)

    def test_permanent_plot_cleanup_removes_all_children_including_separately_trashed(self):
        record = self.seed()
        self.client.delete(f"/api/farm-records/{record['id']}")
        self.delete_plot()
        item = self.contents()["plots"][0]
        self.assertEqual(self.purge("plots", self.plot["id"], item["revision"]).status_code, 200)
        self.assertEqual(self.contents()["plots"], []); self.assertEqual(self.contents()["records"], [])
        with get_connection() as conn:
            for table in ("plots", "plot_seasons", "farm_records", "farm_tasks"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (self.user["id"],)).fetchone()[0], 0)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_record_purge_does_not_delete_plot_or_other_records(self):
        record, kept = self.record(), self.record(cost=7)
        self.client.delete(f"/api/farm-records/{record['id']}")
        item = self.contents()["records"][0]
        self.assertEqual(self.purge("records", record["id"], item["revision"]).status_code, 200)
        self.assertEqual(self.restore("records", record["id"]).status_code, 404)
        self.assertEqual(len(self.client.get("/api/plots").json()["plots"]), 1)
        self.assertEqual(self.client.get("/api/farm-records").json()["records"], [kept])

    def test_cross_user_cannot_view_restore_delete_or_purge_other_accounts(self):
        record = self.record()
        self.client.delete(f"/api/farm-records/{record['id']}")
        self.delete_plot()
        own = self.contents()
        other = register_user("other_farmer", "other-password", "他人")
        with TestClient(self.app) as client:
            client.headers["Authorization"] = f"Bearer {other['token']}"
            empty = client.get("/api/trash").json()
            self.assertEqual(empty["plots"], []); self.assertEqual(empty["records"], [])
            for kind, entity_id in (("plots", self.plot["id"]), ("records", record["id"])):
                self.assertEqual(client.post(f"/api/trash/{kind}/{entity_id}/restore").status_code, 404)
                self.assertEqual(client.delete(f"/api/trash/{kind}/{entity_id}", params={"confirm": True, "expected_revision": own[kind][0]["revision"]}).status_code, 404)
            self.assertEqual(client.get(f"/api/plots/{self.plot['id']}/delete-impact").status_code, 404)
        self.assertEqual(self.contents(), own)

    def test_authentication_and_csrf_protect_recovery_and_purge(self):
        self.delete_plot()
        revision = self.contents()["plots"][0]["revision"]
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 403)
        self.assertEqual(self.purge("plots", self.plot["id"], revision).status_code, 403)
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/trash").status_code, 401)
            self.assertEqual(client.post(f"/api/trash/plots/{self.plot['id']}/restore").status_code, 401)
            self.assertEqual(client.delete(f"/api/trash/plots/{self.plot['id']}", params={"confirm": True, "expected_revision": revision}).status_code, 401)

    def test_deleted_parent_cannot_be_used_for_new_records_seasons_or_tasks(self):
        record = self.seed()
        tasks = self.client.get("/api/farm-tasks").json()["tasks"]
        self.delete_plot()
        for path, data in (("/api/farm-records", {"plot_id": self.plot["id"], "kind": "其他", "happened_on": "2026-10-19"}),
                           ("/api/seasons", {"plot_id": self.plot["id"], "crop": "水稻"}),
                           ("/api/farm-tasks", {"plot_id": self.plot["id"], "title": "不能写", "due_on": "2026-10-19"})):
            self.assertEqual(self.client.post(path, json=data).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/farm-records/{record['id']}", json={"plot_id": self.plot["id"], "kind": "其他", "happened_on": "2026-10-19"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/farm-tasks/{tasks[0]['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/seasons/{self.second['id']}").status_code, 404)

    def test_writer_guards_stop_stale_edit_from_moving_hidden_data(self):
        record = self.record()
        task = self.post("/api/farm-tasks", {"plot_id": self.plot["id"], "title": "旧快照", "due_on": "2026-10-19"})["task"]
        target = self.post("/api/plots", {"name": "目标地", "crop": "玉米", "area_mu": 1, "soil_type": "壤土", "irrigation": "井灌"})["plot"]
        self.delete_plot()
        values = {key: record[key] for key in ("kind", "happened_on", "crop", "detail", "quantity", "cost", "material", "safe_days", "yield_kg", "unit_price")}
        with self.assertRaises(HTTPException):
            repositories.update_farm_record(record["id"], self.user["id"], plot_id=target["id"], season_id=None, **values)
        with self.assertRaises(HTTPException):
            repositories.update_farm_task(task["id"], target["id"], "不能移动", "2026-10-19", "", True)
        with self.assertRaises(HTTPException):
            repositories.update_season(self.second["id"], "水稻", "2026-10-01", None, "")
        self.restore("plots", self.plot["id"])
        self.assertEqual(repositories.get_farm_record(record["id"])["plot_id"], self.plot["id"])

    def test_restore_detects_active_season_conflict_without_overwriting(self):
        self.delete_plot()
        with get_connection() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_plot_seasons_one_active'").fetchone())
            # 模拟历史/外部损坏；正常 API 与保留的唯一索引不允许产生这个状态。
            conn.execute("DROP INDEX idx_plot_seasons_one_active")
            conn.execute("INSERT INTO plot_seasons (id,user_id,plot_id,crop,started_on,created_at,updated_at) VALUES ('conflict',?,?, '冲突', '2026-10-01','now','now')", (self.user["id"], self.plot["id"]))
        before = self.snapshot()
        response = self.restore("plots", self.plot["id"])
        self.assertEqual(response.status_code, 409)
        self.assertIn("多个进行中茬次", response.json()["error"])
        self.assertEqual(self.snapshot(), before)
        with get_connection() as conn:
            conn.execute("DELETE FROM plot_seasons WHERE id='conflict'")
            conn.execute("CREATE UNIQUE INDEX idx_plot_seasons_one_active ON plot_seasons(plot_id) WHERE ended_on IS NULL")
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 200)

    def test_record_date_conflict_and_season_deletion_preserve_archived_association(self):
        record = self.record()
        self.client.delete(f"/api/farm-records/{record['id']}")
        self.assertEqual(self.client.delete(f"/api/seasons/{self.first['id']}").status_code, 409)
        self.assertEqual(self.client.patch(f"/api/seasons/{self.first['id']}", json={"crop": "玉米", "started_on": "2026-05-01", "ended_on": "2026-05-31"}).status_code, 409)
        self.assertEqual(repositories.get_season(self.first["id"])["started_on"], "2026-04-01")
        # 模拟历史/外部损坏，继续验证恢复入口的独立防线；正常编辑已拒绝此状态。
        with get_connection() as conn:
            conn.execute("UPDATE plot_seasons SET started_on='2026-05-01' WHERE id=?", (self.first["id"],))
        self.assertEqual(self.restore("records", record["id"]).status_code, 409)
        self.client.patch(f"/api/seasons/{self.first['id']}", json={"crop": "玉米", "started_on": "2026-04-01", "ended_on": "2026-05-31"})
        self.assertEqual(self.restore("records", record["id"]).status_code, 200)
        self.assertEqual(repositories.get_farm_record(record["id"])["season_id"], self.first["id"])

    def test_fault_during_final_cleanup_rolls_back_entire_branch(self):
        self.seed(); self.delete_plot()
        before = self.snapshot()
        revision = self.contents()["plots"][0]["revision"]
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_cleanup BEFORE DELETE ON farm_tasks BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
        self.assertEqual(self.purge("plots", self.plot["id"], revision).status_code, 500)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 200)

    def test_concurrent_delete_restore_and_restore_purge_are_serialized(self):
        self.seed()
        def remove(_):
            try: trash.trash_plot(self.plot["id"], self.user["id"]); return 200
            except HTTPException as exc: return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(remove, range(2))), [200, 404])
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(lambda _: trash.restore_plot(self.plot["id"], self.user["id"]), range(2))), [True, False])
        self.delete_plot(); revision = self.contents()["plots"][0]["revision"]
        def race(kind):
            try:
                (lambda: trash.restore_plot(self.plot["id"], self.user["id"]))() if kind == "restore" else trash.purge_plot(self.plot["id"], self.user["id"], revision)
                return 200
            except HTTPException as exc: return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(race, ("restore", "purge")))
        self.assertIn(results, ([200, 409], [404, 200]))
        with get_connection() as conn:
            parent = conn.execute("SELECT deleted_at FROM plots WHERE id=?", (self.plot["id"],)).fetchone()
            children = conn.execute("SELECT COUNT(*) FROM farm_records WHERE plot_id=?", (self.plot["id"],)).fetchone()[0]
            self.assertEqual(children, 3 if parent else 0)

    def test_demo_clear_cannot_silently_purge_recycle_bin(self):
        with TestClient(self.app) as guest:
            guest.post("/api/auth/guest")
            guest.headers["X-CSRF-Token"] = guest.cookies["yunxun_csrf"]
            self.assertEqual(guest.post("/api/demo-data").status_code, 200)
            plot = guest.get("/api/plots").json()["plots"][0]
            guest.delete(f"/api/plots/{plot['id']}")
            self.assertEqual(guest.delete("/api/demo-data").status_code, 409)
            self.assertEqual(len(guest.get("/api/trash").json()["plots"]), 1)
            self.assertEqual(guest.post(f"/api/trash/plots/{plot['id']}/restore").status_code, 200)
            self.assertEqual(guest.delete("/api/demo-data").status_code, 200)

    def test_v11_migration_keeps_all_existing_rows_visible_and_unique_index(self):
        self.seed()
        before = self.snapshot()
        with get_connection() as conn:
            for table in ("plots", "farm_records"):
                conn.execute(f"DROP INDEX idx_{table}_user_deleted")
                conn.execute(f"ALTER TABLE {table} DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version=11")
        init_db(); init_db()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.contents()["plots"], [])
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 3)
        with get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_plot_seasons_one_active'").fetchone())

    def test_record_replay_does_not_revive_or_duplicate_a_deleted_submission(self):
        payload = {"submission_id": str(uuid.uuid4()), "plot_id": self.plot["id"], "season_id": self.first["id"],
            "kind": "施肥", "happened_on": "2026-04-30", "cost": 30}
        original = self.post("/api/farm-records", payload)["record"]
        self.client.delete(f"/api/farm-records/{original['id']}")
        self.assertEqual(self.client.post("/api/farm-records", json=payload).status_code, 409)
        self.assertEqual(self.client.get("/api/farm-records").json()["records"], [])
        self.assertEqual(len(self.contents()["records"]), 1)
        self.restore("records", original["id"])
        self.assertEqual(self.post("/api/farm-records", payload)["record"]["id"], original["id"])

    def test_stale_record_purge_cannot_delete_a_new_trash_cycle(self):
        record = self.record()
        self.client.delete(f"/api/farm-records/{record['id']}")
        old_revision = self.contents()["records"][0]["revision"]
        self.restore("records", record["id"])
        self.client.delete(f"/api/farm-records/{record['id']}")
        new_revision = self.contents()["records"][0]["revision"]
        self.assertNotEqual(new_revision, old_revision)
        self.assertEqual(self.purge("records", record["id"], old_revision).status_code, 409)
        self.assertEqual(len(self.contents()["records"]), 1)
        self.assertEqual(self.purge("records", record["id"], new_revision).status_code, 200)

    def test_malformed_associations_block_restore_or_cleanup_without_touching_other_data(self):
        record = self.record(); self.delete_plot()
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET season_id='missing' WHERE id=?", (record["id"],))
        before = self.snapshot()
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 409)
        self.assertEqual(self.snapshot(), before)
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET season_id=? WHERE id=?", (self.first["id"], record["id"]))
        other = register_user("other_links", "other-password", "他人")
        from backend.tests.helpers import make_plot
        foreign = make_plot(other["user"]["id"])
        foreign_record = repositories.create_farm_record(other["user"]["id"], foreign["id"], "其他", "2026-10-19", "玉米", "", "", 0)
        with get_connection() as conn:
            conn.execute("UPDATE farm_records SET season_id=? WHERE id=?", (self.first["id"], foreign_record["id"]))
        revision = self.contents()["plots"][0]["revision"]
        self.assertEqual(self.restore("plots", self.plot["id"]).status_code, 409)
        self.assertEqual(self.purge("plots", self.plot["id"], revision).status_code, 409)
        with get_connection() as conn:
            self.assertEqual(conn.execute("SELECT season_id FROM farm_records WHERE id=?", (foreign_record["id"],)).fetchone()[0], self.first["id"])
