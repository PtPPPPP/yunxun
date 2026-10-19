import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import init_db
from backend.app.core.exceptions import http_exception_handler, validation_exception_handler
from backend.app.repositories import create_user
from backend.app.services.farm import create_user_farm_record
from backend.tests.helpers import make_plot, make_settings


class RecordSubmissionTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = patch("backend.app.core.database.get_settings", return_value=make_settings(Path(temporary.name) / "submission.db"))
        settings.start()
        self.addCleanup(settings.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.other_id = create_user("other", "hash", "另一农户")["id"]
        self.plot = make_plot(self.user_id, started_on="2026-01-01")
        self.payload = {"plot_id": self.plot["id"], "kind": "施肥", "happened_on": "2026-10-19",
                        "cost": 35, "submission_id": str(uuid.uuid4())}
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.add_exception_handler(RequestValidationError, validation_exception_handler)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_retry_returns_same_record_and_counts_once(self):
        first = self.client.post("/api/farm-records", json=self.payload)
        retry = self.client.post("/api/farm-records", json=self.payload)
        self.assertEqual((first.status_code, retry.status_code), (200, 200))
        self.assertEqual(first.json()["record"], retry.json()["record"])
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 1)
        self.assertEqual(self.client.get("/api/plots").json()["plots"][0]["record_count"], 1)
        self.assertEqual(self.client.get("/api/farm-records/economics").json()["plots"][0]["total_cost"], 35)

    def test_same_submission_with_changed_values_conflicts_without_overwrite(self):
        self.client.post("/api/farm-records", json=self.payload)
        response = self.client.post("/api/farm-records", json={**self.payload, "cost": 40})
        self.assertEqual(response.status_code, 409)
        records = self.client.get("/api/farm-records").json()["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["cost"], 35)

    def test_submission_ids_are_scoped_to_owner_and_still_check_plot_ownership(self):
        first = self.client.post("/api/farm-records", json=self.payload).json()["record"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.other_id}
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload).status_code, 404)
        other_plot = make_plot(self.other_id, started_on="2026-01-01")
        response = self.client.post("/api/farm-records", json={**self.payload, "plot_id": other_plot["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(first["id"], response.json()["record"]["id"])
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 1)

    def test_validation_failure_can_retry_same_submission(self):
        self.assertEqual(self.client.post("/api/farm-records", json={**self.payload, "happened_on": "2026-02-31"}).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-records", json=self.payload).status_code, 200)
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 1)

    def test_invalid_submission_uuid_is_rejected(self):
        self.assertEqual(self.client.post("/api/farm-records", json={**self.payload, "submission_id": "invalid"}).status_code, 422)
        self.assertEqual(self.client.get("/api/farm-records").json()["records"], [])

    def test_legacy_clients_can_create_separate_records_without_submission_id(self):
        payload = {key: value for key, value in self.payload.items() if key != "submission_id"}
        self.assertEqual(self.client.post("/api/farm-records", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/farm-records", json=payload).status_code, 200)
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 2)

    def test_concurrent_retries_create_one_row(self):
        values = dict(self.payload, user_id=self.user_id, client_host="test", crop="", detail="", quantity="")
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(lambda _: create_user_farm_record(**values), range(2)))
        self.assertEqual(records[0]["id"], records[1]["id"])
        self.assertEqual(len(self.client.get("/api/farm-records").json()["records"]), 1)
