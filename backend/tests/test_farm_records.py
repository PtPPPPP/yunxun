import tempfile
import unittest
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
    list_harvest_safety,
    list_plots,
    summarize_farm_economics,
)
from backend.app.services.farm import (
    create_user_farm_record,
    delete_user_farm_record,
    list_user_farm_records,
    summarize_user_farm_records,
)
from backend.tests.helpers import make_settings


def make_plot(user_id: str, name: str = "东坡三亩地", crop: str = "玉米") -> dict:
    return create_plot(
        user_id=user_id,
        name=name,
        area_mu=3.5,
        soil_type="壤土",
        irrigation="井灌",
        crop=crop,
        planted_on="2026-05-12",
        notes="",
    )


class FarmRecordServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "record-service.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.plot = make_plot(self.user_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_record_defaults_crop_to_plot_crop(self) -> None:
        record = create_user_farm_record(
            user_id=self.user_id,
            client_host="127.0.0.1",
            plot_id=self.plot["id"],
            kind="施肥",
            happened_on="2026-06-01",
            crop="",
            detail="追尿素",
            quantity="15 公斤/亩",
            cost=120.5,
        )
        self.assertEqual(record["crop"], "玉米")
        self.assertEqual(record["plot_name"], "东坡三亩地")
        self.assertEqual(record["quantity"], "15 公斤/亩")
        self.assertEqual(record["cost"], 120.5)

    def test_record_keeps_explicit_crop_and_null_cost(self) -> None:
        record = create_user_farm_record(
            user_id=self.user_id,
            client_host="127.0.0.1",
            plot_id=self.plot["id"],
            kind="采收",
            happened_on="2026-09-20",
            crop="大豆",
            detail="",
            quantity="",
            cost=None,
        )
        self.assertEqual(record["crop"], "大豆")
        self.assertIsNone(record["cost"])

    def test_records_paginate_by_operation_date(self) -> None:
        for day in ("2026-06-01", "2026-06-20", "2026-06-10"):
            create_user_farm_record(
                user_id=self.user_id,
                client_host="127.0.0.1",
                plot_id=self.plot["id"],
                kind="灌溉",
                happened_on=day,
                crop="",
                detail="",
                quantity="",
                cost=None,
            )

        first_page, has_more = list_user_farm_records(self.user_id, plot_id=None, limit=2, cursor=None)
        self.assertTrue(has_more)
        self.assertEqual([item["happened_on"] for item in first_page], ["2026-06-20", "2026-06-10"])

        cursor = (first_page[-1]["happened_on"], first_page[-1]["id"])
        second_page, has_more = list_user_farm_records(self.user_id, plot_id=None, limit=2, cursor=cursor)
        self.assertFalse(has_more)
        self.assertEqual([item["happened_on"] for item in second_page], ["2026-06-01"])

    def test_records_can_be_filtered_by_plot(self) -> None:
        other_plot = make_plot(self.user_id, name="西洼两亩地", crop="小麦")
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="施肥", happened_on="2026-06-01", crop="", detail="", quantity="", cost=None,
        )

        records, _ = list_user_farm_records(self.user_id, plot_id=other_plot["id"], limit=20, cursor=None)
        self.assertEqual(records, [])

    def test_records_are_isolated_by_user(self) -> None:
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="施肥", happened_on="2026-06-01", crop="", detail="", quantity="", cost=None,
        )
        self.assertEqual(list_user_farm_records("user-other", plot_id=None, limit=20, cursor=None)[0], [])

    def test_create_on_foreign_plot_is_rejected(self) -> None:
        with self.assertRaises(AppError) as rejected:
            create_user_farm_record(
                user_id="user-other", client_host="127.0.0.1", plot_id=self.plot["id"],
                kind="施肥", happened_on="2026-06-01", crop="", detail="", quantity="", cost=None,
            )
        self.assertEqual(rejected.exception.code, ErrorCode.NOT_FOUND)

    def test_summarize_counts_plots_and_records(self) -> None:
        make_plot(self.user_id, name="西洼两亩地")
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="施肥", happened_on="2026-06-01", crop="", detail="", quantity="", cost=None,
        )
        self.assertEqual(summarize_user_farm_records(self.user_id), {"plot_count": 2, "record_count": 1})

    def test_delete_record_is_scoped_to_owner(self) -> None:
        record = create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="施肥", happened_on="2026-06-01", crop="", detail="", quantity="", cost=None,
        )
        with self.assertRaises(AppError):
            delete_user_farm_record(record["id"], "user-other", "127.0.0.1")

        delete_user_farm_record(record["id"], self.user_id, "127.0.0.1")
        self.assertEqual(list_user_farm_records(self.user_id, plot_id=None, limit=20, cursor=None)[0], [])
        with self.assertRaises(AppError):
            delete_user_farm_record(record["id"], self.user_id, "127.0.0.1")

    def test_economics_aggregates_cost_yield_and_revenue(self) -> None:
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="播种", happened_on="2026-05-12", crop="", detail="", quantity="", cost=180.0,
        )
        # 两次采收单价不同，逐笔保留
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="采收", happened_on="2026-09-20", crop="", detail="", quantity="",
            cost=260.0, yield_kg=2100.0, unit_price=2.4,
        )
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="采收", happened_on="2026-09-28", crop="", detail="", quantity="",
            cost=80.0, yield_kg=600.0, unit_price=2.6,
        )

        economics = summarize_farm_economics(self.user_id)
        self.assertEqual(len(economics), 1)
        item = economics[0]
        self.assertEqual(item["plot_name"], "东坡三亩地")
        self.assertEqual(item["record_count"], 3)
        self.assertEqual(item["total_cost"], 520.0)
        self.assertEqual(item["total_yield_kg"], 2700.0)
        self.assertEqual(item["total_revenue"], 6600.0)
        self.assertEqual(item["net_revenue"], 6080.0)
        # 地块面积 3.5 亩
        self.assertEqual(item["cost_per_mu"], 148.57)
        self.assertEqual(item["yield_per_mu"], 771.43)
        self.assertEqual(item["revenue_per_mu"], 1885.71)
        self.assertEqual(item["net_per_mu"], 1737.14)

    def test_economics_needs_both_yield_and_price_for_revenue(self) -> None:
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="采收", happened_on="2026-09-20", crop="", detail="", quantity="",
            cost=100.0, yield_kg=500.0, unit_price=None,
        )
        item = summarize_farm_economics(self.user_id)[0]
        self.assertEqual(item["total_yield_kg"], 500.0)
        self.assertEqual(item["total_revenue"], 0.0)
        self.assertEqual(item["net_revenue"], -100.0)

    def test_economics_handles_plot_without_records(self) -> None:
        item = summarize_farm_economics(self.user_id)[0]
        self.assertEqual(item["record_count"], 0)
        self.assertEqual(item["total_cost"], 0.0)
        self.assertEqual(item["net_revenue"], 0.0)
        self.assertEqual(item["net_per_mu"], 0.0)

    def test_economics_is_isolated_by_user(self) -> None:
        self.assertEqual(summarize_farm_economics("user-other"), [])

    def spray(self, happened_on: str, material: str, safe_days: int | None) -> dict:
        return create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="打药", happened_on=happened_on, crop="", detail="", quantity="",
            cost=None, material=material, safe_days=safe_days,
        )

    def test_earliest_harvest_date_is_derived_from_interval(self) -> None:
        record = self.spray("2026-09-10", "吡虫啉", 7)
        self.assertEqual(record["material"], "吡虫啉")
        self.assertEqual(record["safe_days"], 7)
        self.assertEqual(record["earliest_harvest_on"], "2026-09-17")

    def test_spray_without_interval_has_no_earliest_date(self) -> None:
        self.assertIsNone(self.spray("2026-09-10", "代森锰锌", None)["earliest_harvest_on"])

    def test_harvest_safety_uses_only_the_latest_spray(self) -> None:
        self.spray("2026-08-01", "多菌灵", 15)
        self.spray("2026-09-10", "吡虫啉", 7)

        safety = list_harvest_safety(self.user_id, reference_date="2026-09-16")
        self.assertEqual(len(safety), 1)
        item = safety[0]
        self.assertEqual(item["material"], "吡虫啉")
        self.assertEqual(item["earliest_harvest_on"], "2026-09-17")
        self.assertEqual(item["days_remaining"], 1)
        self.assertTrue(item["in_safe_window"])

    def test_harvest_safety_window_closes_and_can_go_negative(self) -> None:
        self.spray("2026-09-10", "吡虫啉", 7)

        on_the_day = list_harvest_safety(self.user_id, reference_date="2026-09-17")[0]
        self.assertEqual(on_the_day["days_remaining"], 0)
        self.assertFalse(on_the_day["in_safe_window"])

        later = list_harvest_safety(self.user_id, reference_date="2026-09-25")[0]
        self.assertEqual(later["days_remaining"], -8)
        self.assertFalse(later["in_safe_window"])

    def test_only_sprays_with_interval_create_safety_state(self) -> None:
        self.spray("2026-09-10", "代森锰锌", None)
        create_user_farm_record(
            user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
            kind="施肥", happened_on="2026-09-12", crop="", detail="", quantity="",
            cost=None, material="尿素", safe_days=14,
        )
        self.assertEqual(list_harvest_safety(self.user_id, reference_date="2026-09-16"), [])

    def test_plot_list_carries_harvest_safety(self) -> None:
        self.assertIsNone(list_plots(self.user_id, reference_date="2026-09-16")[0]["harvest_safety"])

        self.spray("2026-09-10", "吡虫啉", 7)
        safety = list_plots(self.user_id, reference_date="2026-09-16")[0]["harvest_safety"]
        self.assertTrue(safety["in_safe_window"])
        self.assertEqual(safety["material"], "吡虫啉")

    def test_plot_delete_reports_removed_records(self) -> None:
        for day in ("2026-06-01", "2026-06-10"):
            create_user_farm_record(
                user_id=self.user_id, client_host="127.0.0.1", plot_id=self.plot["id"],
                kind="灌溉", happened_on=day, crop="", detail="", quantity="", cost=None,
            )
        self.assertEqual(list_plots(self.user_id)[0]["record_count"], 2)


class FarmRecordRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "record-routes.db"
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
        self.plot = make_plot(self.user_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def payload(self, **overrides: object) -> dict:
        base = {
            "plot_id": self.plot["id"],
            "kind": "施肥",
            "happened_on": "2026-06-01",
            "crop": "",
            "detail": "追尿素",
            "quantity": "15 公斤/亩",
            "cost": 120.5,
        }
        base.update(overrides)
        return base

    def test_create_and_list_records(self) -> None:
        created = self.client.post("/api/farm-records", json=self.payload())
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["record"]["crop"], "玉米")

        listed = self.client.get("/api/farm-records")
        self.assertEqual(listed.status_code, 200)
        body = listed.json()
        self.assertEqual(len(body["records"]), 1)
        self.assertEqual(body["records"][0]["plot_name"], "东坡三亩地")
        self.assertFalse(body["pagination"]["has_more"])

    def test_unknown_kind_is_rejected(self) -> None:
        response = self.client.post("/api/farm-records", json=self.payload(kind="浇水"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("播种", response.json()["error"])

    def test_invalid_payload_is_rejected(self) -> None:
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(happened_on="2026/06/01")).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(cost=-1)).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(plot_id="missing")).status_code, 404)

    def test_list_supports_cursor_and_plot_filter(self) -> None:
        other_plot = make_plot(self.user_id, name="西洼两亩地")
        for day in ("2026-06-01", "2026-06-10", "2026-06-20"):
            self.client.post("/api/farm-records", json=self.payload(happened_on=day))

        first = self.client.get("/api/farm-records", params={"limit": 2}).json()
        self.assertEqual(len(first["records"]), 2)
        self.assertTrue(first["pagination"]["has_more"])

        second = self.client.get(
            "/api/farm-records",
            params={"limit": 2, "cursor": first["pagination"]["next_cursor"]},
        ).json()
        self.assertEqual(len(second["records"]), 1)
        self.assertFalse(second["pagination"]["has_more"])

        filtered = self.client.get("/api/farm-records", params={"plot_id": other_plot["id"]}).json()
        self.assertEqual(filtered["records"], [])

    def test_list_rejects_invalid_cursor(self) -> None:
        response = self.client.get("/api/farm-records", params={"cursor": "not-a-cursor"})
        self.assertEqual(response.status_code, 400)

    def test_delete_record_and_stats(self) -> None:
        record_id = self.client.post("/api/farm-records", json=self.payload()).json()["record"]["id"]
        self.assertEqual(self.client.get("/api/farm-records/stats").json()["record_count"], 1)

        deleted = self.client.delete(f"/api/farm-records/{record_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/farm-records/{record_id}").status_code, 404)

        stats = self.client.get("/api/farm-records/stats").json()
        self.assertEqual(stats["plot_count"], 1)
        self.assertEqual(stats["record_count"], 0)

    def test_record_count_is_reflected_on_plot_list(self) -> None:
        self.client.post("/api/farm-records", json=self.payload())
        self.assertEqual(self.client.get("/api/plots").json()["plots"][0]["record_count"], 1)

    def test_harvest_record_keeps_yield_and_price(self) -> None:
        created = self.client.post(
            "/api/farm-records",
            json=self.payload(kind="采收", yield_kg=2100.0, unit_price=2.4),
        )
        self.assertEqual(created.status_code, 200)
        record = created.json()["record"]
        self.assertEqual(record["yield_kg"], 2100.0)
        self.assertEqual(record["unit_price"], 2.4)

    def test_negative_yield_is_rejected(self) -> None:
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(yield_kg=-1)).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(unit_price=-1)).status_code, 422)

    def test_spray_record_keeps_material_and_interval(self) -> None:
        created = self.client.post(
            "/api/farm-records",
            json=self.payload(kind="打药", material="吡虫啉", safe_days=7, happened_on="2026-09-10"),
        )
        self.assertEqual(created.status_code, 200)
        record = created.json()["record"]
        self.assertEqual(record["material"], "吡虫啉")
        self.assertEqual(record["safe_days"], 7)
        self.assertEqual(record["earliest_harvest_on"], "2026-09-17")

    def test_out_of_range_interval_is_rejected(self) -> None:
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(safe_days=-1)).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload(safe_days=999)).status_code, 422)

    def test_plot_list_exposes_harvest_safety(self) -> None:
        self.assertIsNone(self.client.get("/api/plots").json()["plots"][0]["harvest_safety"])
        self.client.post(
            "/api/farm-records",
            json=self.payload(kind="打药", material="吡虫啉", safe_days=7, happened_on="2026-09-10"),
        )
        safety = self.client.get("/api/plots").json()["plots"][0]["harvest_safety"]
        self.assertEqual(safety["material"], "吡虫啉")
        self.assertEqual(safety["earliest_harvest_on"], "2026-09-17")

    def test_economics_endpoint_returns_per_plot_totals(self) -> None:
        self.client.post("/api/farm-records", json=self.payload(kind="施肥", cost=320.5))
        self.client.post(
            "/api/farm-records",
            json=self.payload(kind="采收", happened_on="2026-09-20", yield_kg=2100.0, unit_price=2.4, cost=0),
        )
        response = self.client.get("/api/farm-records/economics")
        self.assertEqual(response.status_code, 200)
        plots = response.json()["plots"]
        self.assertEqual(len(plots), 1)
        self.assertEqual(plots[0]["plot_name"], "东坡三亩地")
        self.assertEqual(plots[0]["total_cost"], 320.5)
        self.assertEqual(plots[0]["total_revenue"], 5040.0)
        self.assertEqual(plots[0]["net_revenue"], 4719.5)

    def test_other_users_cannot_read_or_delete_records(self) -> None:
        record_id = self.client.post("/api/farm-records", json=self.payload()).json()["record"]["id"]
        other_id = create_user("intruder", "hash", "陌生人")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": other_id}

        self.assertEqual(self.client.get("/api/farm-records").json()["records"], [])
        self.assertEqual(self.client.delete(f"/api/farm-records/{record_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/farm-records/stats").json(), {"success": True, "plot_count": 0, "record_count": 0})
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload()).status_code, 404)


if __name__ == "__main__":
    unittest.main()
