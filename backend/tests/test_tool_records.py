import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.tools import router
from backend.app.core.database import SCHEMA_VERSION, init_db, migrate_schema
from backend.app.repositories import (
    count_tool_records_by_kind,
    create_user,
    list_tool_records_page,
    summarize_tool_records,
)
from backend.app.services.tools import create_decision_advice
from backend.tests.helpers import make_settings


class ToolRecordMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "tool-records.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fresh_database_creates_tool_records_table(self) -> None:
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tool_records)")}
        self.assertEqual(
            columns,
            {"id", "user_id", "kind", "crop", "payload", "result", "mode", "created_at"},
        )

    def test_schema_v4_database_is_upgraded_to_current_version(self) -> None:
        init_db()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DROP TABLE tool_records")
            conn.execute("PRAGMA user_version = 4")
            conn.commit()
            applied = migrate_schema(conn)[1]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(
            applied,
            ["5_tool_records", "6_remove_ai_surface", "7_farm_plots_and_records", "8_harvest_yield_and_tasks"],
        )
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertIn("tool_records", tables)


class ToolRecordServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "service.db"
        settings = make_settings(self.db_path)
        for target in (
            "backend.app.core.database.get_settings",
            "backend.app.services.tools.get_settings",
        ):
            patcher = patch(target, return_value=settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_decision_advice_is_persisted_with_payload(self) -> None:
        create_decision_advice(
            user_id=self.user_id,
            client_host="127.0.0.1",
            crop="水稻",
            stage="苗期",
            rain_prob=60,
            soil_moisture=45,
            temperature=25.0,
        )
        records, _ = list_tool_records_page(self.user_id, kind="decision")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "decision")
        self.assertEqual(record["mode"], "local")

        with closing(sqlite3.connect(self.db_path)) as conn:
            payload_raw = conn.execute("SELECT payload FROM tool_records").fetchone()[0]
        payload = json.loads(payload_raw)
        self.assertEqual(payload["stage"], "苗期")
        self.assertEqual(payload["rain_prob"], 60)

    def test_records_are_isolated_by_user(self) -> None:
        create_decision_advice(
            user_id=self.user_id,
            client_host="127.0.0.1",
            crop="玉米",
            stage="苗期",
            rain_prob=10,
            soil_moisture=30,
            temperature=20.0,
        )
        self.assertEqual(list_tool_records_page("user-other")[0], [])
        self.assertEqual(count_tool_records_by_kind("user-other"), {})
        self.assertEqual(count_tool_records_by_kind(self.user_id), {"decision": 1})

    def test_summarize_counts_by_day_and_top_crops(self) -> None:
        for crop in ("玉米", "玉米", "水稻"):
            create_decision_advice(
                user_id=self.user_id,
                client_host="127.0.0.1",
                crop=crop,
                stage="苗期",
                rain_prob=10,
                soil_moisture=30,
                temperature=20.0,
            )
        summary = summarize_tool_records(user_id=self.user_id)
        self.assertEqual(summary["days"], 14)
        self.assertEqual(sum(summary["by_day"].values()), 3)
        self.assertEqual(summary["top_crops"][0], {"crop": "玉米", "total": 2})


class ToolRecordRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "routes.db"
        settings = make_settings(self.db_path)
        for target in (
            "backend.app.core.database.get_settings",
            "backend.app.services.tools.get_settings",
        ):
            patcher = patch(target, return_value=settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()
        self.app = FastAPI()
        self.app.include_router(router)
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_records_supports_kind_filter_and_pagination(self) -> None:
        for crop in ("玉米", "水稻", "小麦"):
            create_decision_advice(
                user_id=self.user_id,
                client_host="127.0.0.1",
                crop=crop,
                stage="苗期",
                rain_prob=10,
                soil_moisture=30,
                temperature=20.0,
            )
        response = self.client.get("/api/tool-records", params={"limit": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["records"]), 2)
        self.assertTrue(body["pagination"]["has_more"])
        self.assertIsNotNone(body["pagination"]["next_cursor"])

        follow_up = self.client.get(
            "/api/tool-records",
            params={"limit": 2, "cursor": body["pagination"]["next_cursor"]},
        )
        self.assertEqual(len(follow_up.json()["records"]), 1)
        self.assertFalse(follow_up.json()["pagination"]["has_more"])

        filtered = self.client.get("/api/tool-records", params={"kind": "decision", "limit": 10})
        self.assertEqual(len(filtered.json()["records"]), 3)

    def test_list_records_rejects_kinds_that_no_longer_exist(self) -> None:
        for kind in ("unknown", "vision"):
            response = self.client.get("/api/tool-records", params={"kind": kind})
            self.assertEqual(response.status_code, 400)

    def test_list_records_rejects_invalid_cursor(self) -> None:
        response = self.client.get("/api/tool-records", params={"cursor": "not-a-cursor"})
        self.assertEqual(response.status_code, 400)

    def test_vision_endpoint_is_gone(self) -> None:
        response = self.client.post("/api/vision", json={"image_base64": "x" * 64})
        self.assertEqual(response.status_code, 404)

    def test_stats_endpoint_aggregates_counts(self) -> None:
        create_decision_advice(
            user_id=self.user_id,
            client_host="127.0.0.1",
            crop="玉米",
            stage="苗期",
            rain_prob=10,
            soil_moisture=30,
            temperature=20.0,
        )
        response = self.client.get("/api/tool-records/stats")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["counts_by_kind"], {"decision": 1})
        self.assertEqual(body["top_crops"], [{"crop": "玉米", "total": 1}])
        self.assertNotIn("total_sessions", body)
        self.assertNotIn("total_messages", body)


if __name__ == "__main__":
    unittest.main()
