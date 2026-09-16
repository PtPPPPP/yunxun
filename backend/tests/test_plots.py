import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import SCHEMA_VERSION, init_db, migrate_schema
from backend.app.core.errors import AppError, ErrorCode
from backend.app.core.exceptions import http_exception_handler
from backend.app.repositories import create_user, list_plots
from backend.app.services.farm import (
    create_user_plot,
    delete_user_plot,
    require_plot_owner,
    update_user_plot,
)
from backend.tests.helpers import make_settings


PLOT_FIELDS = {
    "name": "东坡三亩地",
    "area_mu": 3.5,
    "soil_type": "壤土",
    "irrigation": "井灌",
    "crop": "玉米",
    "planted_on": "2026-05-12",
    "notes": "去年种过小麦",
}


def insert_farm_record(db_path: Path, plot_id: str) -> None:
    """直接写一条台账记录，用于验证地块删除的连带行为。"""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO farm_records
                (id, user_id, plot_id, kind, happened_on, crop, detail, quantity, cost, created_at)
            VALUES ('r1', (SELECT user_id FROM plots WHERE id = ?), ?, '施肥', '2026-06-01',
                    '玉米', '追尿素', '15 公斤/亩', 120.0, '2026-06-01T08:00:00+00:00')
            """,
            (plot_id, plot_id),
        )
        conn.commit()


class PlotMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "plots.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fresh_database_creates_plot_tables(self) -> None:
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            plot_columns = {row[1] for row in conn.execute("PRAGMA table_info(plots)")}
            record_columns = {row[1] for row in conn.execute("PRAGMA table_info(farm_records)")}
        self.assertEqual(
            plot_columns,
            {
                "id", "user_id", "name", "area_mu", "soil_type", "irrigation",
                "crop", "planted_on", "notes", "created_at", "updated_at",
            },
        )
        self.assertEqual(
            record_columns,
            {
                "id", "user_id", "plot_id", "kind", "happened_on", "crop",
                "detail", "quantity", "cost", "material", "safe_days",
                "yield_kg", "unit_price", "created_at",
            },
        )

    def test_v7_database_gains_harvest_columns_and_task_table(self) -> None:
        # 先造一个 v7 形态的库：没有 v8 的四列，也没有 farm_tasks。
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            for column in ("material", "safe_days", "yield_kg", "unit_price"):
                conn.execute(f"ALTER TABLE farm_records DROP COLUMN {column}")
            conn.execute("DROP TABLE farm_tasks")
            conn.execute("PRAGMA user_version = 7")
            conn.commit()

            applied = migrate_schema(conn)[1]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            record_columns = {row[1] for row in conn.execute("PRAGMA table_info(farm_records)")}
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        self.assertEqual(applied, ["8_harvest_yield_and_tasks"])
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue({"material", "safe_days", "yield_kg", "unit_price"} <= record_columns)
        self.assertIn("farm_tasks", tables)


class PlotServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "plot-service.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_plot_crud_round_trip(self) -> None:
        plot = create_user_plot(user_id=self.user_id, client_host="127.0.0.1", **PLOT_FIELDS)
        self.assertEqual(plot["name"], "东坡三亩地")
        self.assertEqual(plot["area_mu"], 3.5)
        self.assertEqual(plot["record_count"], 0)

        updated = update_user_plot(
            plot_id=plot["id"],
            user_id=self.user_id,
            client_host="127.0.0.1",
            name="东坡四亩地",
            area_mu=4.0,
            soil_type="砂壤土",
            irrigation="滴灌",
            crop="大豆",
            planted_on=None,
            notes="",
        )
        self.assertEqual(updated["name"], "东坡四亩地")
        self.assertEqual(updated["area_mu"], 4.0)
        self.assertEqual(updated["crop"], "大豆")
        self.assertIsNone(updated["planted_on"])

        self.assertEqual(len(list_plots(self.user_id)), 1)

    def test_plots_are_isolated_by_user(self) -> None:
        create_user_plot(user_id=self.user_id, client_host="127.0.0.1", **PLOT_FIELDS)
        self.assertEqual(list_plots("user-other"), [])

    def test_require_plot_owner_rejects_foreign_plot(self) -> None:
        plot = create_user_plot(user_id=self.user_id, client_host="127.0.0.1", **PLOT_FIELDS)
        with self.assertRaises(AppError) as rejected:
            require_plot_owner(plot["id"], "user-other")
        self.assertEqual(rejected.exception.status_code, 404)
        self.assertEqual(rejected.exception.code, ErrorCode.NOT_FOUND)

        with self.assertRaises(AppError):
            require_plot_owner("missing-plot", self.user_id)

    def test_delete_plot_removes_its_records_and_reports_count(self) -> None:
        plot = create_user_plot(user_id=self.user_id, client_host="127.0.0.1", **PLOT_FIELDS)
        insert_farm_record(self.db_path, plot["id"])
        self.assertEqual(list_plots(self.user_id)[0]["record_count"], 1)

        removed = delete_user_plot(plot["id"], self.user_id, "127.0.0.1")
        self.assertEqual(removed, 1)
        self.assertEqual(list_plots(self.user_id), [])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM farm_records").fetchone()[0], 0)

    def test_delete_missing_plot_is_rejected(self) -> None:
        with self.assertRaises(AppError):
            delete_user_plot("missing-plot", self.user_id, "127.0.0.1")

    def test_service_trims_fields_and_blank_date(self) -> None:
        plot = create_user_plot(
            user_id=self.user_id,
            client_host="127.0.0.1",
            name="  西洼  ",
            area_mu=2.0,
            soil_type=" 砂土 ",
            irrigation=" 雨养 ",
            crop=" 小麦 ",
            planted_on="",
            notes=" ",
        )
        self.assertEqual(plot["name"], "西洼")
        self.assertEqual(plot["soil_type"], "砂土")
        self.assertEqual(plot["irrigation"], "雨养")
        self.assertEqual(plot["crop"], "小麦")
        self.assertEqual(plot["notes"], "")
        self.assertIsNone(plot["planted_on"])


class PlotRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "plot-routes.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.app = FastAPI()
        # create_app() 里注册的处理器，这里手动补上，才能验证 AppError 的 code 字段。
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.include_router(router)
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_list_plots(self) -> None:
        created = self.client.post("/api/plots", json=PLOT_FIELDS)
        self.assertEqual(created.status_code, 200)
        plot = created.json()["plot"]
        self.assertEqual(plot["name"], "东坡三亩地")
        self.assertEqual(plot["record_count"], 0)

        listed = self.client.get("/api/plots")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["plots"]), 1)

    def test_update_plot_returns_new_values(self) -> None:
        plot_id = self.client.post("/api/plots", json=PLOT_FIELDS).json()["plot"]["id"]
        response = self.client.patch(f"/api/plots/{plot_id}", json={**PLOT_FIELDS, "crop": "大豆", "area_mu": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plot"]["crop"], "大豆")
        self.assertEqual(response.json()["plot"]["area_mu"], 5)

    def test_create_plot_validates_input(self) -> None:
        cases = [
            {**PLOT_FIELDS, "name": ""},
            {**PLOT_FIELDS, "area_mu": 0},
            {**PLOT_FIELDS, "planted_on": "2026/05/12"},
            {**PLOT_FIELDS, "crop": ""},
        ]
        for payload in cases:
            self.assertEqual(self.client.post("/api/plots", json=payload).status_code, 422, payload)

    def test_delete_plot_reports_removed_records(self) -> None:
        plot_id = self.client.post("/api/plots", json=PLOT_FIELDS).json()["plot"]["id"]
        insert_farm_record(self.db_path, plot_id)

        listed = self.client.get("/api/plots").json()["plots"]
        self.assertEqual(listed[0]["record_count"], 1)

        deleted = self.client.delete(f"/api/plots/{plot_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_records"], 1)
        self.assertEqual(self.client.get("/api/plots").json()["plots"], [])

    def test_missing_plot_returns_not_found_with_code(self) -> None:
        response = self.client.delete("/api/plots/missing-plot")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], ErrorCode.NOT_FOUND)

    def test_other_users_cannot_touch_the_plot(self) -> None:
        plot_id = self.client.post("/api/plots", json=PLOT_FIELDS).json()["plot"]["id"]
        other_id = create_user("intruder", "hash", "陌生人")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": other_id}

        self.assertEqual(self.client.get("/api/plots").json()["plots"], [])
        self.assertEqual(self.client.patch(f"/api/plots/{plot_id}", json=PLOT_FIELDS).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/plots/{plot_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
