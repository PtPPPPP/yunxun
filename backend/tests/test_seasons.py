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
from backend.app.core.database import init_db
from backend.app.core.errors import AppError, ErrorCode
from backend.app.core.exceptions import http_exception_handler
from backend.app.repositories import (
    create_plot,
    create_user,
    get_active_season,
    list_plots,
    list_seasons,
    summarize_farm_economics,
)
from backend.app.services.farm import (
    create_user_farm_record,
    create_user_plot,
    create_user_season,
    delete_user_season,
    update_user_plot,
    update_user_season,
)
from backend.tests.helpers import make_plot, make_settings


class SeasonServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "season-service.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def start_season(self, plot_id: str, crop: str, started_on: str | None = "2026-05-12") -> dict:
        return create_user_season(
            user_id=self.user_id,
            client_host="127.0.0.1",
            plot_id=plot_id,
            crop=crop,
            started_on=started_on,
            notes="",
        )

    def add_record(self, plot_id: str, **overrides: object) -> dict:
        params = {
            "kind": "施肥",
            "happened_on": "2026-06-01",
            "crop": "",
            "detail": "",
            "quantity": "",
            "cost": None,
        }
        params.update(overrides)
        return create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=plot_id, **params
        )

    def test_creating_a_plot_also_opens_its_first_season(self) -> None:
        plot = create_user_plot(
            user_id=self.user_id,
            client_host="127.0.0.1",
            name="东坡三亩地",
            area_mu=3.0,
            soil_type="壤土",
            irrigation="井灌",
            crop="玉米",
            planted_on="2026-05-12",
            notes="",
        )
        self.assertEqual(plot["crop"], "玉米")
        self.assertEqual(plot["planted_on"], "2026-05-12")
        self.assertEqual(plot["active_season"]["crop"], "玉米")
        self.assertEqual(len(list_seasons(self.user_id)), 1)

    def test_second_active_season_is_refused(self) -> None:
        plot = make_plot(self.user_id)
        with self.assertRaises(AppError) as refused:
            self.start_season(plot["id"], "大豆", "2026-09-25")
        self.assertEqual(refused.exception.status_code, 409)
        self.assertEqual(refused.exception.code, ErrorCode.CONFLICT)
        self.assertIn("玉米", refused.exception.message)

    def test_new_season_allowed_after_ending_the_previous(self) -> None:
        plot = make_plot(self.user_id)
        active = get_active_season(plot["id"])
        update_user_season(
            active["id"], self.user_id, "127.0.0.1",
            crop=active["crop"], started_on=active["started_on"], ended_on="2026-09-20", notes="",
        )
        self.assertIsNone(get_active_season(plot["id"]))

        second = self.start_season(plot["id"], "大豆", "2026-09-25")
        self.assertTrue(second["active"])
        # 最后一茬仍是最近开始的这一茬
        listed = list_plots(self.user_id)[0]
        self.assertEqual(listed["crop"], "大豆")
        self.assertEqual(listed["active_season"]["id"], second["id"])

    def test_plot_keeps_last_crop_after_all_seasons_end(self) -> None:
        plot = make_plot(self.user_id)
        active = get_active_season(plot["id"])
        update_user_season(
            active["id"], self.user_id, "127.0.0.1",
            crop="玉米", started_on="2026-05-12", ended_on="2026-09-20", notes="",
        )
        listed = list_plots(self.user_id)[0]
        self.assertEqual(listed["crop"], "玉米")
        self.assertIsNone(listed["active_season"])
        self.assertEqual(listed["season_record_count"], 0)

    def test_records_attach_to_the_active_season(self) -> None:
        plot = make_plot(self.user_id)
        record = self.add_record(plot["id"], cost=300.0)
        self.assertIsNotNone(record["season_id"])
        self.assertEqual(record["season_crop"], "玉米")
        self.assertEqual(record["crop"], "玉米")
        self.assertEqual(list_plots(self.user_id)[0]["season_record_count"], 1)

    def test_records_without_active_season_are_unassigned(self) -> None:
        plot = create_plot(user_id=self.user_id, name="空地块", area_mu=1.0, soil_type="砂土", irrigation="雨养", notes="")
        record = self.add_record(plot["id"])
        self.assertIsNone(record["season_id"])
        self.assertEqual(record["crop"], "")
        self.assertEqual(list_plots(self.user_id)[0]["season_record_count"], 0)

    def test_economics_splits_by_season(self) -> None:
        plot = make_plot(self.user_id)
        self.add_record(plot["id"], kind="播种", happened_on="2026-05-12", cost=180.0)
        self.add_record(plot["id"], kind="采收", happened_on="2026-09-15", yield_kg=2100.0, unit_price=2.4)

        first = get_active_season(plot["id"])
        update_user_season(
            first["id"], self.user_id, "127.0.0.1",
            crop="玉米", started_on="2026-05-12", ended_on="2026-09-20", notes="",
        )
        self.start_season(plot["id"], "大豆", "2026-09-25")
        self.add_record(plot["id"], kind="播种", happened_on="2026-09-26", cost=150.0)

        rows = summarize_farm_economics(self.user_id)
        self.assertEqual(len(rows), 2)
        by_crop = {row["crop"]: row for row in rows}
        # 上一茬的投入不再和这一茬混在一起
        self.assertEqual(by_crop["玉米"]["total_cost"], 180.0)
        self.assertEqual(by_crop["玉米"]["total_revenue"], 5040.0)
        self.assertEqual(by_crop["大豆"]["total_cost"], 150.0)
        self.assertEqual(by_crop["大豆"]["total_revenue"], 0.0)
        self.assertEqual(by_crop["大豆"]["record_count"], 1)

    def test_economics_keeps_unassigned_records(self) -> None:
        plot = make_plot(self.user_id)
        self.add_record(plot["id"], kind="播种", cost=180.0)

        active = get_active_season(plot["id"])
        delete_user_season(active["id"], self.user_id, "127.0.0.1")

        rows = summarize_farm_economics(self.user_id)
        unassigned = [row for row in rows if row["season_id"] is None]
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]["total_cost"], 180.0)
        self.assertEqual(unassigned[0]["record_count"], 1)

    def test_editing_plot_crop_updates_the_active_season(self) -> None:
        plot = make_plot(self.user_id)
        updated = update_user_plot(
            plot_id=plot["id"],
            user_id=self.user_id,
            client_host="127.0.0.1",
            name="东坡三亩地",
            area_mu=3.5,
            soil_type="壤土",
            irrigation="井灌",
            crop="大豆",
            planted_on=None,
            notes="",
        )
        self.assertEqual(updated["crop"], "大豆")
        self.assertIsNone(updated["planted_on"])

    def test_seasons_are_isolated_by_user(self) -> None:
        plot = make_plot(self.user_id)
        with self.assertRaises(AppError):
            update_user_season(
                get_active_season(plot["id"])["id"], "user-other", "127.0.0.1",
                crop="大豆", started_on=None, ended_on=None, notes="",
            )
        with self.assertRaises(AppError):
            create_user_season(
                user_id="user-other", client_host="127.0.0.1",
                plot_id=plot["id"], crop="大豆", started_on=None, notes="",
            )

    def test_one_active_season_per_plot_is_enforced_by_the_database(self) -> None:
        plot = make_plot(self.user_id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO plot_seasons
                        (id, user_id, plot_id, crop, started_on, ended_on, notes, created_at, updated_at)
                    VALUES ('dup', ?, ?, '大豆', NULL, NULL, '', 'now', 'now')
                    """,
                    (self.user_id, plot["id"]),
                )


class SeasonRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "season-routes.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.app = FastAPI()
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.include_router(router)
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_start_and_end_a_season(self) -> None:
        plot = self.client.post("/api/plots", json={
            "name": "东坡三亩地", "area_mu": 3.0, "soil_type": "壤土", "irrigation": "井灌",
            "crop": "玉米", "planted_on": "2026-05-12", "notes": "",
        }).json()["plot"]
        self.assertEqual(plot["active_season"]["crop"], "玉米")

        conflict = self.client.post("/api/seasons", json={
            "plot_id": plot["id"], "crop": "大豆", "started_on": "2026-09-25",
        })
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], ErrorCode.CONFLICT)

        ended = self.client.patch(f"/api/seasons/{plot['active_season']['id']}", json={
            "crop": "玉米", "started_on": "2026-05-12", "ended_on": "2026-09-20", "notes": "",
        })
        self.assertEqual(ended.status_code, 200)
        self.assertFalse(ended.json()["season"]["active"])

        second = self.client.post("/api/seasons", json={
            "plot_id": plot["id"], "crop": "大豆", "started_on": "2026-09-25",
        })
        self.assertEqual(second.status_code, 200)

        seasons = self.client.get("/api/seasons", params={"plot_id": plot["id"]}).json()["seasons"]
        self.assertEqual([item["crop"] for item in seasons], ["大豆", "玉米"])

    def test_season_payload_is_validated(self) -> None:
        plot = make_plot(self.user_id)
        self.assertEqual(self.client.post("/api/seasons", json={
            "plot_id": plot["id"], "crop": "", "started_on": None,
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/seasons", json={
            "plot_id": plot["id"], "crop": "大豆", "started_on": "2026/09/25",
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/seasons", json={
            "plot_id": "missing", "crop": "大豆", "started_on": None,
        }).status_code, 404)

    def test_delete_season_keeps_its_records_as_unassigned(self) -> None:
        plot = make_plot(self.user_id)
        self.client.post("/api/farm-records", json={
            "plot_id": plot["id"], "kind": "施肥", "happened_on": "2026-06-01", "cost": 300.0,
        })
        season_id = self.client.get("/api/plots").json()["plots"][0]["active_season"]["id"]

        deleted = self.client.delete(f"/api/seasons/{season_id}")
        self.assertEqual(deleted.status_code, 200)

        records = self.client.get("/api/farm-records").json()["records"]
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["season_id"])
        self.assertEqual(self.client.delete(f"/api/seasons/{season_id}").status_code, 404)

    def test_other_users_cannot_touch_seasons(self) -> None:
        plot = make_plot(self.user_id)
        season_id = get_active_season(plot["id"])["id"]
        other_id = create_user("intruder", "hash", "陌生人")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": other_id}

        self.assertEqual(self.client.get("/api/seasons").json()["seasons"], [])
        self.assertEqual(self.client.patch(f"/api/seasons/{season_id}", json={
            "crop": "大豆", "started_on": None, "ended_on": None, "notes": "",
        }).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/seasons/{season_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
