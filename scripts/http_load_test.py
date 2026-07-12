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


def request(path: str, *, method: str = "GET", token: str = "", data: dict | None = None, extra_headers: dict[str, str] | None = None) -> tuple[int, float]:
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
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
            "YUNXUN_REQUESTS_PER_MINUTE": "600", "DOUBAO_API_KEY": "",
        })
        process = subprocess.Popen([sys.executable, "backend/main.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    if request("/health/ready")[0] == 200:
                        break
                except OSError:
                    time.sleep(0.05)
            payload = urllib.request.urlopen(urllib.request.Request(BASE_URL + "/api/auth/guest", b"", {"Content-Type": "application/json"}, method="POST"), timeout=10).read()
            token = json.loads(payload)["token"]
            create_request = urllib.request.Request(BASE_URL + "/api/chat/sessions", json.dumps({"title": "load-chat", "feature": "chat", "model_name": "doubao-seed-1-6-250615"}).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
            session_id = json.loads(urllib.request.urlopen(create_request, timeout=10).read())["session"]["id"]
            tasks = []
            with ThreadPoolExecutor(max_workers=8) as pool:
                for index in range(120):
                    if index % 4 == 0:
                        tasks.append(pool.submit(request, "/health/live"))
                    elif index % 4 == 1:
                        tasks.append(pool.submit(request, "/api/chat/sessions?feature=chat&page=1&page_size=20", token=token))
                    elif index % 4 == 2:
                        tasks.append(pool.submit(request, "/api/chat/sessions", method="POST", token=token, data={"title": f"load-{index}", "feature": "chat", "model_name": "doubao-seed-1-6-250615"}))
                    else:
                        tasks.append(pool.submit(request, f"/api/chat/sessions/{session_id}/messages", method="POST", token=token,
                            data={"message": f"load message {index}", "model_name": "doubao-seed-1-6-250615"},
                            extra_headers={"X-Idempotency-Key": f"load-{index}"}))
                results = [future.result() for future in as_completed(tasks)]
            durations = sorted(item[1] for item in results)
            counts = {code: sum(status == code for status, _ in results) for code in sorted({item[0] for item in results})}
            print(json.dumps({"concurrency": 8, "total": len(results), "status_counts": counts,
                "average_ms": round(statistics.mean(durations), 2), "p95_ms": round(durations[int(len(durations) * 0.95) - 1], 2)}, ensure_ascii=False))
            if any(status >= 500 for status, _ in results):
                raise SystemExit(1)
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
