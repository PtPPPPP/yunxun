import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import init_db
from backend.app.core.exceptions import http_exception_handler, validation_exception_handler
from backend.app.repositories import (
    create_farm_record, create_user, delete_farm_record, delete_plot_with_records,
    get_active_season, get_farm_record, list_harvest_safety, update_season, create_season,
)
from backend.app.services.farm import _prepare_farm_record
from backend.tests.helpers import make_plot, make_settings


class LedgerEditingTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = patch("backend.app.core.database.get_settings", return_value=make_settings(Path(temporary.name) / "ledger.db"))
        settings.start()
        self.addCleanup(settings.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.other_id = create_user("other", "hash", "另一农户")["id"]
        self.plot = make_plot(self.user_id, started_on="2026-04-01")
        self.season = get_active_season(self.plot["id"])
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.add_exception_handler(RequestValidationError, validation_exception_handler)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def payload(self, **overrides):
        return {"plot_id": self.plot["id"], "kind": "施肥", "happened_on": "2026-04-30",
                "cost": 30, **overrides}

    def create(self, **overrides):
        response = self.client.post("/api/farm-records", json=self.payload(**overrides))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["record"]

    def edit(self, record, **overrides):
        return self.client.patch(f"/api/farm-records/{record['id']}", json=self.payload(**overrides))

    def economics(self):
        return {row["season_id"]: row for row in self.client.get("/api/farm-records/economics").json()["plots"]}

    def test_edit_historical_cost_keeps_identity_and_recalculates_economics(self):
        update_season(self.season["id"], "玉米", "2026-04-01", "2026-05-31", "")
        second = create_season(self.user_id, self.plot["id"], "大豆", "2026-10-01", "")
        record = self.create(kind="采收", yield_kg=100, unit_price=2)
        self.assertEqual(record["season_id"], self.season["id"])
        self.assertEqual(self.economics()[self.season["id"]]["net_revenue"], 170)
        response = self.edit(record, kind="采收", season_id=self.season["id"], cost=80, yield_kg=100, unit_price=2)
        self.assertEqual(response.status_code, 200)
        edited = response.json()["record"]
        self.assertEqual((edited["id"], edited["created_at"]), (record["id"], record["created_at"]))
        self.assertEqual(edited["cost"], 80)
        rows = self.economics()
        self.assertEqual(rows[self.season["id"]]["net_revenue"], 120)
        self.assertEqual(rows[self.season["id"]]["record_count"], 1)
        self.assertEqual(rows[second["id"]]["record_count"], 0)

    def test_move_record_between_owned_plots_updates_counts_and_totals(self):
        target = make_plot(self.user_id, name="西田", crop="大豆", started_on="2026-01-01")
        season = get_active_season(target["id"])
        record = self.create()
        response = self.edit(record, plot_id=target["id"], season_id=season["id"], cost=75, happened_on="2026-06-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record"]["crop"], "大豆")
        by_plot = {plot["id"]: plot for plot in self.client.get("/api/plots").json()["plots"]}
        self.assertEqual(by_plot[self.plot["id"]]["record_count"], 0)
        self.assertEqual(by_plot[self.plot["id"]]["season_record_count"], 0)
        self.assertEqual(by_plot[target["id"]]["season_record_count"], 1)
        self.assertEqual(self.economics()[season["id"]]["total_cost"], 75)
        self.assertEqual(self.economics()[self.season["id"]]["total_cost"], 0)

    def test_update_checks_record_plot_and_season_ownership(self):
        record = self.create()
        foreign_plot = make_plot(self.other_id)
        own_plot = make_plot(self.user_id, name="另一块田")
        cases = [
            {"plot_id": foreign_plot["id"]},
            {"season_id": get_active_season(foreign_plot["id"])["id"]},
            {"season_id": get_active_season(own_plot["id"])["id"]},
            {"season_id": "missing"},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(self.edit(record, **values).status_code, 404)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.other_id}
        self.assertEqual(self.edit(record, plot_id=foreign_plot["id"]).status_code, 404)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        stored = get_farm_record(record["id"])
        self.assertEqual(stored["plot_id"], self.plot["id"])
        self.assertEqual(stored["cost"], 30)

    def test_selected_season_date_mismatch_rejects_create_and_update_without_changes(self):
        update_season(self.season["id"], "玉米", "2026-04-01", "2026-05-31", "")
        record = self.create()
        for day in ("2026-03-31", "2026-06-01"):
            values = self.payload(season_id=self.season["id"], happened_on=day, cost=999)
            for method, path in (("post", "/api/farm-records"), ("patch", f"/api/farm-records/{record['id']}")):
                with self.subTest(day=day, method=method):
                    response = self.client.request(method, path, json=values)
                    self.assertEqual(response.status_code, 422)
                    self.assertIn("起止日期", response.json()["error"])
        self.assertEqual(get_farm_record(record["id"])["cost"], 30)
        for day in ("2026-04-01", "2026-05-31"):
            self.assertEqual(self.edit(record, season_id=self.season["id"], happened_on=day).status_code, 200)

    def test_update_rejects_invalid_calendar_and_fields_and_accepts_leap_day(self):
        record = self.create()
        for changes in ({"happened_on": "2026-02-31"}, {"happened_on": "2026-02-29"},
                        {"cost": -1}, {"yield_kg": -1}, {"unit_price": -1}, {"safe_days": 366}):
            self.assertEqual(self.edit(record, **changes).status_code, 422)
        self.assertEqual(self.edit(record, kind="非法类型").status_code, 400)
        response = self.edit(record, happened_on="2024-02-29", season_id=None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record"]["happened_on"], "2024-02-29")

    def test_ambiguous_update_requires_choice_and_explicit_unassigned_is_preserved(self):
        record = self.create()
        update_season(self.season["id"], "玉米", "2026-04-01", "2026-05-31", "")
        second = create_season(self.user_id, self.plot["id"], "大豆", "2026-04-15", "")
        self.assertEqual(self.edit(record).status_code, 422)
        self.assertEqual(get_farm_record(record["id"])["season_id"], self.season["id"])
        response = self.edit(record, season_id=second["id"])
        self.assertEqual(response.json()["record"]["crop"], "大豆")
        self.assertIsNone(self.edit(record, season_id=None).json()["record"]["season_id"])
        self.assertEqual(self.economics()[None]["total_cost"], 30)

    def test_unmatched_dates_are_unassigned_instead_of_current_season(self):
        for day in ("2026-03-31",):
            self.assertIsNone(self.create(happened_on=day)["season_id"])
        update_season(self.season["id"], "玉米", "2026-04-01", "2026-05-31", "")
        create_season(self.user_id, self.plot["id"], "大豆", "2026-10-01", "")
        self.assertIsNone(self.create(happened_on="2026-08-01")["season_id"])

    def test_non_applicable_fields_are_cleared_on_both_create_and_edit(self):
        dirty_fields = {"material": "旧投入品", "safe_days": 30, "yield_kg": 100, "unit_price": 2}
        record = self.create(kind="采收", **dirty_fields)
        self.assertEqual(record["material"], "")
        self.assertIsNone(record["safe_days"])
        for kind in ("播种", "施肥", "打药", "灌溉", "除草", "其他"):
            with self.subTest(kind=kind):
                edited = self.edit(record, kind=kind, **dirty_fields).json()["record"]
                created = self.create(kind=kind, **dirty_fields)
                for item in (edited, created):
                    self.assertIsNone(item["yield_kg"])
                    self.assertIsNone(item["unit_price"])
                    self.assertEqual(item["material"], "旧投入品" if kind in {"施肥", "打药"} else "")
                    self.assertEqual(item["safe_days"], 30 if kind == "打药" else None)
                    self.assertEqual(item["earliest_harvest_on"], "2026-05-30" if kind == "打药" else None)
        self.assertEqual(self.economics()[self.season["id"]]["total_revenue"], 0)

    def test_legacy_non_harvest_income_is_not_counted_without_rewriting_history(self):
        record = create_farm_record(self.user_id, self.plot["id"], "施肥", "2026-04-30", "玉米", "", "", 10,
                                    yield_kg=100, unit_price=2, season_id=self.season["id"])
        rows = self.economics()
        self.assertEqual(rows[self.season["id"]]["total_revenue"], 0)
        self.assertEqual(rows[self.season["id"]]["total_yield_kg"], 0)
        self.assertEqual(get_farm_record(record["id"])["yield_kg"], 100)

    def test_spray_edit_recalculates_plot_harvest_reminder(self):
        record = self.create(kind="打药", happened_on="2026-10-01", safe_days=30)
        self.assertEqual(list_harvest_safety(self.user_id, reference_date="2026-10-19")[0]["days_remaining"], 12)
        self.edit(record, kind="打药", happened_on="2026-10-10", safe_days=3)
        item = list_harvest_safety(self.user_id, reference_date="2026-10-19")[0]
        self.assertEqual(item["earliest_harvest_on"], "2026-10-13")
        self.assertFalse(item["in_safe_window"])
        self.edit(record, kind="施肥")
        self.assertEqual(list_harvest_safety(self.user_id, reference_date="2026-10-19"), [])

    def test_date_plot_kind_filters_combine_with_cursor_and_same_day_ties(self):
        expected = []
        for day, kind in (("2026-04-01", "施肥"), ("2026-04-10", "施肥"), ("2026-04-10", "施肥"),
                          ("2026-04-15", "打药"), ("2026-04-20", "施肥"), ("2026-04-30", "施肥")):
            item = self.create(happened_on=day, kind=kind)
            if "2026-04-10" <= day <= "2026-04-20" and kind == "施肥":
                expected.append(item["id"])
        other = make_plot(self.user_id, name="其他田")
        self.create(plot_id=other["id"], happened_on="2026-06-01")
        foreign = make_plot(self.other_id)
        create_farm_record(self.other_id, foreign["id"], "施肥", "2026-04-10", "玉米", "", "", 1)
        params = {"plot_id": self.plot["id"], "kind": "施肥", "date_from": "2026-04-10",
                  "date_to": "2026-04-20", "limit": 1}
        ids = []
        while True:
            response = self.client.get("/api/farm-records", params=params)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            ids.extend(item["id"] for item in body["records"])
            if not body["pagination"]["has_more"]:
                self.assertIsNone(body["pagination"]["next_cursor"])
                break
            params["cursor"] = body["pagination"]["next_cursor"]
        self.assertCountEqual(ids, expected)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(self.client.get("/api/farm-records", params={"plot_id": foreign["id"]}).json()["records"], [])

    def test_filters_validate_real_dates_order_and_kind(self):
        for params in ({"date_from": "2026-02-31"}, {"date_to": "2026-02-29"},
                       {"date_from": "2026-04-30", "date_to": "2026-04-01"}):
            self.assertEqual(self.client.get("/api/farm-records", params=params).status_code, 422)
        self.assertEqual(self.client.get("/api/farm-records", params={"kind": "非法类型"}).status_code, 400)
        self.assertEqual(self.client.get("/api/farm-records", params={"date_from": "2024-02-29"}).status_code, 200)

    def test_concurrently_deleted_record_returns_not_found(self):
        record = self.create()
        stale = get_farm_record(record["id"])
        delete_farm_record(record["id"])
        with patch("backend.app.services.farm.get_farm_record", return_value=stale):
            self.assertEqual(self.edit(record).status_code, 404)

    def test_concurrently_deleted_target_returns_conflict_and_preserves_record(self):
        record = self.create()
        target = make_plot(self.user_id, name="目标地块", started_on="2026-01-01")

        def remove_after_validation(**values):
            prepared = _prepare_farm_record(**values)
            delete_plot_with_records(target["id"])
            return prepared

        with patch("backend.app.services.farm._prepare_farm_record", side_effect=remove_after_validation):
            response = self.edit(record, plot_id=target["id"], cost=999)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(get_farm_record(record["id"])["plot_id"], self.plot["id"])
        self.assertEqual(get_farm_record(record["id"])["cost"], 30)
