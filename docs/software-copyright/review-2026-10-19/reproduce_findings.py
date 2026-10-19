"""在临时数据库中复现检查发现，不访问现有业务数据库。

在仓库根目录使用已安装 backend/requirements.txt 的 Python 执行：
python docs/software-copyright/review-2026-10-19/reproduce_findings.py
输出为观察结果，不把当前错误行为当作期望行为或回归测试。
"""

import json
import logging
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="yunxun-review-") as directory:
        os.environ.update(
            YUNXUN_DB_PATH=str(Path(directory) / "review.db"),
            YUNXUN_ENV="test",
            YUNXUN_DEBUG="false",
            YUNXUN_JWT_SECRET="isolated-review-only-secret",
            YUNXUN_ALLOWED_ORIGINS="http://testserver",
        )
        from backend.app.main import app
        from backend.app.repositories import list_harvest_safety
        from fastapi.testclient import TestClient

        logging.disable(logging.CRITICAL)
        observations = {}
        with TestClient(app, raise_server_exceptions=False) as client:
            guest = client.post("/api/auth/guest")
            guest.raise_for_status()
            user_id = guest.json()["user"]["id"]
            client.headers["X-CSRF-Token"] = client.cookies.get("yunxun_csrf")
            created = client.post("/api/plots", json={
                "name": "review plot", "area_mu": 3, "soil_type": "loam",
                "irrigation": "well", "crop": "corn", "planted_on": "2026-04-01",
            })
            created.raise_for_status()
            plot = created.json()["plot"]
            plot_id = plot["id"]
            old_season_id = plot["active_season"]["id"]
            invalid = client.post("/api/farm-tasks", json={
                "title": "invalid calendar date", "due_on": "2026-02-31",
            })
            observations["invalid_calendar_date"] = {
                "status": invalid.status_code,
                "stored_date": invalid.json().get("task", {}).get("due_on"),
            }
            backwards = client.patch(f"/api/seasons/{old_season_id}", json={
                "crop": "corn", "started_on": "2026-04-01", "ended_on": "2026-03-01",
            })
            observations["season_end_before_start"] = {"status": backwards.status_code}
            # 修正为有效日期，独立验证补录历史台账的归茬问题。
            corrected = client.patch(f"/api/seasons/{old_season_id}", json={
                "crop": "corn", "started_on": "2026-04-01", "ended_on": "2026-05-31",
            })
            corrected.raise_for_status()
            new_season = client.post("/api/seasons", json={
                "plot_id": plot_id, "crop": "wheat", "started_on": "2026-10-01",
            })
            new_season.raise_for_status()
            new_season_id = new_season.json()["season"]["id"]
            historical = client.post("/api/farm-records", json={
                "plot_id": plot_id, "kind": "采收", "happened_on": "2026-04-30",
                "yield_kg": 100, "unit_price": 2,
            })
            observations["backdated_record"] = {
                "status": historical.status_code,
                "attached_to_october_season": historical.json().get("record", {}).get("season_id") == new_season_id,
            }
            reopened = client.patch(f"/api/seasons/{old_season_id}", json={
                "crop": "corn", "started_on": "2026-04-01", "ended_on": None,
            })
            observations["reopen_old_season_while_new_active"] = {"status": reopened.status_code}
            for happened_on, safe_days in [("2026-10-01", 30), ("2026-10-10", 3)]:
                spray = client.post("/api/farm-records", json={
                    "plot_id": plot_id, "kind": "打药", "happened_on": happened_on,
                    "material": "review input", "safe_days": safe_days,
                })
                spray.raise_for_status()
            safety = list_harvest_safety(user_id, reference_date="2026-10-19")[0]
            observations["overlapping_spray_intervals"] = {
                "reference_date": "2026-10-19",
                "reported_earliest_harvest_on": safety["earliest_harvest_on"],
                "reported_in_safe_window": safety["in_safe_window"],
                "longer_interval_ends_on": "2026-10-31",
            }
            client.headers.pop("X-CSRF-Token")
            csrf = client.post("/api/farm-tasks", json={
                "title": "missing csrf header", "due_on": "2026-10-19",
            })
            observations["cookie_write_without_csrf"] = {"status": csrf.status_code}
        print(json.dumps(observations, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
