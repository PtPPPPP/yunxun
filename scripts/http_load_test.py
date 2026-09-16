from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8021"


def request(path: str, *, method: str = "GET", token: str = "", data: dict | None = None) -> tuple[int, float]:
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE_URL + path, body, headers, method=method), timeout=10) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, (time.perf_counter() - started) * 1000


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env = os.environ.copy()
        env.update({
            "YUNXUN_PORT": "8021", "YUNXUN_HOST": "127.0.0.1", "YUNXUN_ENV": "test",
            "YUNXUN_DB_PATH": str(Path(directory) / "load.db"),
            "YUNXUN_JWT_SECRET": "load-test-secret-not-for-production",
            "YUNXUN_REQUESTS_PER_MINUTE": "600",
        })
        process = subprocess.Popen([sys.executable, "backend/main.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    if request("/health/ready")[0] == 200:
                        break
                except OSError:
                    time.sleep(0.05)
            guest = urllib.request.Request(BASE_URL + "/api/auth/guest", b"", {"Content-Type": "application/json"}, method="POST")
            token = json.loads(urllib.request.urlopen(guest, timeout=10).read())["token"]
            tasks = []
            with ThreadPoolExecutor(max_workers=8) as pool:
                for index in range(120):
                    if index % 4 == 0:
                        tasks.append(pool.submit(request, "/health/live"))
                    elif index % 4 == 1:
                        tasks.append(pool.submit(request, "/api/tool-records?limit=20", token=token))
                    elif index % 4 == 2:
                        tasks.append(pool.submit(request, "/api/decision", method="POST", token=token,
                            data={"crop": "玉米", "stage": "快速生长期", "rain_prob": 55, "soil_moisture": 42, "temperature": 24.5}))
                    else:
                        tasks.append(pool.submit(request, "/api/tool-records/stats", token=token))
                results = [future.result() for future in as_completed(tasks)]
            durations = sorted(item[1] for item in results)
            counts = {code: sum(status == code for status, _ in results) for code in sorted({item[0] for item in results})}
            print(json.dumps({"concurrency": 8, "total": len(results), "status_counts": counts,
                "average_ms": round(statistics.mean(durations), 2), "p95_ms": round(durations[int(len(durations) * 0.95) - 1], 2)}, ensure_ascii=False))
            failed = [status for status, _ in results if not 200 <= status < 300]
            if failed:
                print(f"压测失败：出现非 2xx 响应 {sorted(set(failed))}", file=sys.stderr)
                raise SystemExit(1)
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
