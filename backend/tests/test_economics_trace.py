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
from backend.app.repositories import create_season, create_user, get_active_season, update_season
from backend.tests.helpers import make_plot, make_settings


class EconomicsTraceTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = patch("backend.app.core.database.get_settings", return_value=make_settings(Path(temporary.name) / "economics.db"))
        database.start()
        self.addCleanup(database.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.other_id = create_user("other", "hash", "他人")["id"]
        self.plot = make_plot(self.user_id, started_on="2025-10-01")
        self.first = get_active_season(self.plot["id"])
        update_season(self.first["id"], "玉米", "2025-10-01", "2026-05-31", "")
        self.second = create_season(self.user_id, self.plot["id"], "大豆", "2026-10-01", "")
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.add_exception_handler(RequestValidationError, validation_exception_handler)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def record(self, **values):
        response = self.client.post("/api/farm-records", json={
            "plot_id": self.plot["id"], "season_id": self.first["id"],
            "kind": "施肥", "happened_on": "2025-12-01", **values,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["record"]

    def summary(self, **params):
        response = self.client.get("/api/farm-records/economics", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def row(self, **params):
        return self.summary(season_id=self.first["id"], **params)["plots"][0]

    def trace(self, **params):
        query = {"season_id": self.first["id"], "limit": 2, **params}
        records = []
        while True:
            response = self.client.get("/api/farm-records", params=query)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            records.extend(body["records"])
            if not body["pagination"]["has_more"]:
                self.assertIsNone(body["pagination"]["next_cursor"])
                return records
            query["cursor"] = body["pagination"]["next_cursor"]

    def seed_missing_and_zero(self):
        self.record(cost=None)
        self.record(cost=0)
        self.record(cost=10)
        self.record(kind="采收", cost=None)
        self.record(kind="采收", cost=0, yield_kg=100)
        self.record(kind="采收", cost=0, unit_price=2)
        self.record(kind="采收", cost=0, yield_kg=0, unit_price=2)
        self.record(kind="采收", cost=0, yield_kg=10, unit_price=0)
        self.record(kind="采收", cost=5, yield_kg=100, unit_price=2)

    def test_missing_values_are_counted_and_zero_is_complete(self):
        self.seed_missing_and_zero()
        row = self.row()
        self.assertEqual(row["record_count"], 9)
        self.assertEqual(row["recorded_cost_count"], 7)
        self.assertEqual(row["missing_cost_count"], 2)
        self.assertEqual(row["harvest_count"], 6)
        self.assertEqual(row["complete_harvest_count"], 3)
        self.assertEqual(row["incomplete_harvest_count"], 3)
        self.assertEqual(row["recorded_yield_count"], 4)
        self.assertEqual(row["total_cost"], 15)
        self.assertEqual(row["total_yield_kg"], 210)
        self.assertEqual(row["total_revenue"], 200)
        self.assertEqual(row["net_revenue"], 185)
        self.assertEqual(row["cost_per_mu"], round(15 / 3.5, 2))
        self.assertEqual(row["revenue_per_mu"], round(200 / 3.5, 2))
        self.assertEqual(row["net_per_mu"], round(185 / 3.5, 2))

    def test_each_summary_number_reconciles_to_paginated_trace(self):
        self.seed_missing_and_zero()
        row = self.row()
        costs = self.trace(economics_scope="cost")
        incomes = self.trace(economics_scope="revenue")
        self.assertEqual(len(costs), row["recorded_cost_count"])
        self.assertEqual(round(sum(item["cost"] for item in costs), 2), row["total_cost"])
        self.assertTrue(any(item["cost"] == 0 for item in costs))
        self.assertEqual(len(incomes), row["complete_harvest_count"])
        self.assertEqual(round(sum(item["yield_kg"] * item["unit_price"] for item in incomes), 2), row["total_revenue"])
        self.assertEqual(len(self.trace(economics_scope="missing_cost")), row["missing_cost_count"])
        self.assertEqual(len(self.trace(economics_scope="incomplete_harvest")), row["incomplete_harvest_count"])
        self.assertEqual(len(self.trace()), row["record_count"])
        self.assertEqual(len({item["id"] for item in costs}), len(costs))

    def test_entirely_missing_harvest_keeps_compatible_numeric_field_and_exposes_missing_count(self):
        self.record(kind="采收", yield_kg=100)
        row = self.row()
        self.assertEqual(row["total_revenue"], 0)
        self.assertEqual(row["complete_harvest_count"], 0)
        self.assertEqual(row["incomplete_harvest_count"], 1)
        self.assertEqual(row["missing_cost_count"], 1)
        self.assertEqual(self.trace(economics_scope="revenue"), [])
        self.assertEqual(len(self.trace(economics_scope="incomplete_harvest")), 1)

    def test_empty_season_has_no_phantom_missing_record(self):
        row = self.row()
        for field in ("record_count", "missing_cost_count", "incomplete_harvest_count", "recorded_cost_count", "complete_harvest_count"):
            self.assertEqual(row[field], 0)
        self.assertEqual(self.trace(economics_scope="missing_cost"), [])

    def test_year_is_operation_date_and_cross_year_season_is_not_duplicated(self):
        records = [
            self.record(happened_on="2025-10-01", cost=100),
            self.record(happened_on="2025-12-31", cost=0, kind="采收", yield_kg=50, unit_price=2),
            self.record(happened_on="2026-01-01", cost=20, kind="采收", yield_kg=100, unit_price=2),
            self.record(happened_on="2026-05-31", cost=5),
        ]
        self.record(season_id=self.second["id"], happened_on="2026-10-01", cost=300)
        all_years = self.row()
        first_year, second_year = self.row(year=2025), self.row(year=2026)
        self.assertEqual((first_year["total_cost"], first_year["total_revenue"]), (100, 100))
        self.assertEqual((second_year["total_cost"], second_year["total_revenue"]), (25, 200))
        self.assertEqual(first_year["total_cost"] + second_year["total_cost"], all_years["total_cost"])
        self.assertEqual(first_year["total_revenue"] + second_year["total_revenue"], all_years["total_revenue"])
        self.assertEqual(all_years["record_count"], 4)
        first_ids = {item["id"] for item in self.trace(year=2025)}
        second_ids = {item["id"] for item in self.trace(year=2026)}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(first_ids | second_ids, {item["id"] for item in records})
        self.assertEqual({row["season_id"] for row in self.summary(year=2025)["plots"]}, {self.first["id"]})
        self.assertEqual(self.summary()["year_basis"], "happened_on")

    def test_trace_date_range_matches_year_filter(self):
        self.record(happened_on="2025-12-31", cost=10)
        self.record(happened_on="2026-01-01", cost=20)
        by_year = self.trace(year=2026, economics_scope="cost")
        by_range = self.trace(date_from="2026-01-01", date_to="2026-12-31", economics_scope="cost")
        self.assertEqual(by_year, by_range)
        self.assertEqual(sum(item["cost"] for item in by_range), self.row(year=2026)["total_cost"])

    def test_unassigned_records_stay_separate_and_are_traceable(self):
        self.record(cost=10)
        self.record(season_id=None, cost=None)
        self.record(season_id=None, cost=0, happened_on="2026-01-01")
        body = self.summary(plot_id=self.plot["id"], season_id="unassigned")
        self.assertEqual(len(body["plots"]), 1)
        row = body["plots"][0]
        self.assertIsNone(row["season_id"])
        self.assertEqual(row["record_count"], 2)
        self.assertEqual(row["missing_cost_count"], 1)
        self.assertEqual(row["recorded_cost_count"], 1)
        self.assertTrue(all(item["season_id"] is None for item in self.trace(season_id="unassigned")))

    def test_plot_season_filters_check_owner_and_relationship(self):
        own_other = make_plot(self.user_id, name="另一块田")
        foreign = make_plot(self.other_id)
        foreign_season = get_active_season(foreign["id"])
        for path in ("/api/farm-records/economics", "/api/farm-records"):
            for params in ({"season_id": foreign_season["id"]},
                           {"plot_id": own_other["id"], "season_id": self.first["id"]},
                           {"season_id": "missing"}):
                self.assertEqual(self.client.get(path, params=params).status_code, 404)
        self.assertEqual(self.client.get("/api/farm-records/economics", params={"plot_id": foreign["id"]}).status_code, 404)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.other_id}
        self.assertEqual(self.client.get("/api/farm-records/economics", params={"season_id": self.first["id"]}).status_code, 404)
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/api/farm-records/economics").status_code, 401)

    def test_available_years_and_aggregates_do_not_leak_other_users(self):
        self.record(cost=10)
        foreign = make_plot(self.other_id, started_on="2020-01-01")
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.other_id}
        response = self.client.post("/api/farm-records", json={"plot_id": foreign["id"], "kind": "采收",
                                     "happened_on": "2020-01-01", "cost": 999, "yield_kg": 999, "unit_price": 999})
        self.assertEqual(response.status_code, 200)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        body = self.summary()
        self.assertEqual(body["available_years"], [2025])
        self.assertEqual(sum(row["total_cost"] for row in body["plots"]), 10)
        self.assertEqual(sum(row["total_revenue"] for row in body["plots"]), 0)
        self.assertTrue(all(item["plot_id"] == self.plot["id"] for item in self.trace(season_id="")))

    def test_year_and_trace_scope_are_validated(self):
        for path in ("/api/farm-records/economics", "/api/farm-records"):
            for year in (0, 10000, "unknown"):
                self.assertEqual(self.client.get(path, params={"year": year}).status_code, 422)
        self.assertEqual(self.client.get("/api/farm-records", params={"economics_scope": "unknown"}).status_code, 422)
        row = self.row(year=9999)
        self.assertEqual(row["record_count"], 0)

    def test_trace_edit_updates_missing_counts_and_actual_totals(self):
        record = self.record(kind="采收", yield_kg=100)
        pending = self.trace(economics_scope="incomplete_harvest")[0]
        response = self.client.patch(f"/api/farm-records/{pending['id']}", json={
            "plot_id": record["plot_id"], "season_id": record["season_id"], "kind": "采收",
            "happened_on": record["happened_on"], "yield_kg": 100, "unit_price": 2, "cost": 0,
        })
        self.assertEqual(response.status_code, 200)
        row = self.row()
        self.assertEqual(row["missing_cost_count"], 0)
        self.assertEqual(row["incomplete_harvest_count"], 0)
        self.assertEqual(row["total_cost"], 0)
        self.assertEqual(row["total_revenue"], 200)
        self.assertEqual(row["net_revenue"], 200)
