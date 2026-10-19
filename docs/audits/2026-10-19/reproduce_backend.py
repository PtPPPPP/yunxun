"""Fault probes for the audited revision; only a new temporary database is used.

These assertions document current defects, not desired product behavior.
Run with a Python environment containing backend requirements and httpx.
"""
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
work = Path(tempfile.mkdtemp(prefix="yunxun-backend-audit-"))
os.environ.update(
    YUNXUN_DB_PATH=str(work / "audit.db"), YUNXUN_ENV="test",
    YUNXUN_JWT_SECRET="isolated-audit-secret-no-production-data",
    YUNXUN_ALLOWED_ORIGINS="http://127.0.0.1:5179",
    YUNXUN_AUTH_REQUESTS_PER_MINUTE="2000",
)
logging.disable(logging.CRITICAL)
from backend.app.main import app
from fastapi.testclient import TestClient

with TestClient(app, raise_server_exceptions=False) as client:
    auth = client.post("/api/auth/guest").json()
    client.headers["Authorization"] = "Bearer " + auth["token"]
    data = dict(name="audit", area_mu=3, soil_type="壤土", irrigation="井灌", crop="玉米", planted_on="2026-04-01")
    response = client.post("/api/plots", json=data)
    assert response.status_code == 200
    plot = response.json()["plot"]
    sid = plot["active_season"]["id"]
    record = dict(plot_id=plot["id"], season_id=sid, kind="施肥", happened_on="2026-04-30", cost=10)
    response = client.post("/api/farm-records", json=record)
    assert response.status_code == 200
    rid = response.json()["record"]["id"]
    changed = client.patch("/api/seasons/" + sid, json=dict(crop="玉米", started_on="2026-06-01", ended_on=None, notes=""))
    edited = client.patch("/api/farm-records/" + rid, json={**record, "cost": 20})
    assert changed.status_code == 200 and edited.status_code == 422
    before = len(client.get("/api/plots").json()["plots"])
    with patch("backend.app.services.farm.create_season", side_effect=sqlite3.OperationalError("injected second-write failure")):
        failed = client.post("/api/plots", json={**data, "name": "atomicity-probe"})
    after = client.get("/api/plots").json()["plots"]
    orphan = [p for p in after if p["name"] == "atomicity-probe"]
    assert failed.status_code == 500 and len(after) == before + 1 and orphan[0]["active_season"] is None
    results = {
        "season_dates": {"season_update_status": changed.status_code, "record_edit_status": edited.status_code, "record_edit_error": edited.json()},
        "atomicity": {"create_status": failed.status_code, "plots_before": before, "plots_after": len(after), "persisted_plot_has_season": orphan[0]["active_season"] is not None},
    }
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else work / "results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("RESULTS", output)
