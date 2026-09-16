from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8031
BASE = f"http://127.0.0.1:{PORT}"


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def api(path: str, *, method: str = "GET", token: str = "", data: dict | None = None) -> tuple[int, dict, dict]:
    headers = {"Content-Type": "application/json", "X-Request-ID": "rehearsal-request"}
    if token: headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, json.dumps(data).encode() if data is not None else None, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read()), {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def wait_ready() -> None:
    for _ in range(150):
        try:
            status, payload, _ = api("/health/ready")
            if status == 200 and payload.get("status") == "ready": return
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError("后端未在限定时间内就绪。")


def start_backend(python: Path, project: Path, env: dict[str, str]) -> subprocess.Popen:
    process = subprocess.Popen([str(python), "backend/main.py"], cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    wait_ready()
    return process


def stop_backend(process: subprocess.Popen) -> None:
    process.terminate()
    process.wait(timeout=15)


@contextmanager
def running_backend(python: Path, project: Path, env: dict[str, str]):
    process = start_backend(python, project, env)
    try:
        yield process
    finally:
        if process.poll() is None:
            stop_backend(process)


def main() -> None:
    run([sys.executable, "scripts/package_release.py"], ROOT)
    archive = ROOT / "dist/release/yunxun-1.0.0.zip"
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        with zipfile.ZipFile(archive) as bundle: bundle.extractall(workspace)
        project = workspace / "yunxun-1.0.0"
        venv = workspace / "venv"
        run([sys.executable, "-m", "venv", str(venv)], workspace)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "pip", "install", "-r", "backend/requirements.txt"], project)
        run([str(python), "-m", "compileall", "backend"], project)
        run([str(python), "-m", "unittest"], project)
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run([npm, "ci"], project / "frontend")
        run([npm, "run", "test"], project / "frontend")
        run([npm, "run", "lint"], project / "frontend")
        run([npm, "run", "build"], project / "frontend")
        database = workspace / "rehearsal.db"
        env = os.environ.copy()
        env.update({"YUNXUN_ENV": "production", "YUNXUN_DEBUG": "false", "YUNXUN_COOKIE_SECURE": "true", "YUNXUN_PORT": str(PORT),
            "YUNXUN_HOST": "127.0.0.1", "YUNXUN_DB_PATH": str(database),
            "YUNXUN_JWT_SECRET": "release-rehearsal-secret-1234567890", "YUNXUN_ALLOWED_ORIGINS": "https://example.com"})
        run([str(python), "scripts/check_release.py"], project, env)
        with running_backend(python, project, env):
            status, live, headers = api("/health/live")
            assert status == 200 and live["version"] == "1.0.0" and headers.get("x-request-id") == "rehearsal-request"
            _, guest, _ = api("/api/auth/guest", method="POST")
            token = guest["token"]
            status, advice, _ = api(
                "/api/decision",
                method="POST",
                token=token,
                data={"crop": "玉米", "stage": "快速生长期", "rain_prob": 55, "soil_moisture": 42, "temperature": 24.5},
            )
            assert status == 200 and "今日建议" in advice["reply"]
        with running_backend(python, project, env):
            _, records, _ = api("/api/tool-records?limit=10", token=token)
            assert len(records["records"]) == 1
            assert records["records"][0]["crop"] == "玉米"
        backup_dir = workspace / "backups"
        run([str(python), "scripts/database_admin.py", "backup", "--dir", str(backup_dir)], project, env)
        backup = next(backup_dir.glob("yunxun-*.db"))
        run([str(python), "scripts/database_admin.py", "rehearse-restore", str(backup)], project, env)
        with running_backend(python, project, env):
            _, records, _ = api("/api/tool-records?limit=10", token=token)
            assert len(records["records"]) == 1
            _, stats, _ = api("/api/tool-records/stats", token=token)
            assert stats["counts_by_kind"] == {"decision": 1}
    print("发布演练通过：干净安装、构建、启动、重启、数据持久化和备份恢复均正常。")


if __name__ == "__main__":
    main()
