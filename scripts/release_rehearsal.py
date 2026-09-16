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


def start_backend(python: Path, project: Path, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    """启动后端并把输出写进日志文件。

    这里刻意不用 subprocess.PIPE：管道缓冲区只有几 KB，没人读就会写满，
    后端进程会阻塞在写日志上，后续请求全部超时。写文件既不会阻塞，
    失败时也还能把日志尾巴打出来定位问题。
    """
    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [str(python), "backend/main.py"],
            cwd=project,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    wait_ready()
    return process


def stop_backend(process: subprocess.Popen) -> None:
    process.terminate()
    process.wait(timeout=15)


@contextmanager
def running_backend(python: Path, project: Path, env: dict[str, str], log_path: Path):
    process = start_backend(python, project, env, log_path)
    try:
        yield process
    finally:
        if process.poll() is None:
            stop_backend(process)


def main() -> None:
    run([sys.executable, "scripts/package_release.py"], ROOT)
    archive = ROOT / "dist/release/yunxun-1.0.0.zip"
    # 日志留在 dist 下（已 gitignore）而不是临时目录：演练失败时还能翻。
    backend_log = ROOT / "dist" / "rehearsal-backend.log"
    backend_log.parent.mkdir(parents=True, exist_ok=True)
    backend_log.write_text("", encoding="utf-8")
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
        with running_backend(python, project, env, backend_log):
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

            status, created_plot, _ = api(
                "/api/plots",
                method="POST",
                token=token,
                data={
                    "name": "演练地块",
                    "area_mu": 3.5,
                    "soil_type": "壤土",
                    "irrigation": "井灌",
                    "crop": "玉米",
                    "planted_on": "2026-05-12",
                    "notes": "发布演练",
                },
            )
            assert status == 200 and created_plot["plot"]["record_count"] == 0
            status, created_record, _ = api(
                "/api/farm-records",
                method="POST",
                token=token,
                data={
                    "plot_id": created_plot["plot"]["id"],
                    "kind": "施肥",
                    "happened_on": "2026-06-01",
                    "quantity": "15 公斤/亩",
                    "cost": 120.5,
                    "detail": "发布演练",
                },
            )
            assert status == 200 and created_record["record"]["plot_name"] == "演练地块"
            status, created_harvest, _ = api(
                "/api/farm-records",
                method="POST",
                token=token,
                data={
                    "plot_id": created_plot["plot"]["id"],
                    "kind": "采收",
                    "happened_on": "2026-09-20",
                    "yield_kg": 2100.0,
                    "unit_price": 2.4,
                },
            )
            assert status == 200 and created_harvest["record"]["earliest_harvest_on"] is None
            status, created_task, _ = api(
                "/api/farm-tasks",
                method="POST",
                token=token,
                data={
                    "plot_id": created_plot["plot"]["id"],
                    "title": "演练待办：复查长势",
                    "due_on": "2026-09-25",
                    "notes": "",
                },
            )
            assert status == 200 and created_task["task"]["done"] is False
        with running_backend(python, project, env, backend_log):
            _, records, _ = api("/api/tool-records?limit=10", token=token)
            assert len(records["records"]) == 1
            assert records["records"][0]["crop"] == "玉米"

            _, plots, _ = api("/api/plots", token=token)
            assert len(plots["plots"]) == 1
            # 一条施肥 + 一条采收
            assert plots["plots"][0]["record_count"] == 2
            assert plots["plots"][0]["open_task_count"] == 1
            _, ledger, _ = api("/api/farm-records?limit=10", token=token)
            assert len(ledger["records"]) == 2
            assert sum(item["cost"] or 0 for item in ledger["records"]) == 120.5
            assert sum(item["yield_kg"] or 0 for item in ledger["records"]) == 2100.0

            _, economics, _ = api("/api/farm-records/economics", token=token)
            assert len(economics["plots"]) == 1
            assert economics["plots"][0]["total_revenue"] == 5040.0
            assert economics["plots"][0]["net_revenue"] == 4919.5

            _, tasks, _ = api("/api/farm-tasks", token=token)
            assert len(tasks["tasks"]) == 1
            assert tasks["tasks"][0]["title"] == "演练待办：复查长势"
        backup_dir = workspace / "backups"
        run([str(python), "scripts/database_admin.py", "backup", "--dir", str(backup_dir)], project, env)
        backup = next(backup_dir.glob("yunxun-*.db"))
        run([str(python), "scripts/database_admin.py", "rehearse-restore", str(backup)], project, env)
        with running_backend(python, project, env, backend_log):
            _, records, _ = api("/api/tool-records?limit=10", token=token)
            assert len(records["records"]) == 1
            _, stats, _ = api("/api/tool-records/stats", token=token)
            assert stats["counts_by_kind"] == {"decision": 1}

            _, plots, _ = api("/api/plots", token=token)
            assert len(plots["plots"]) == 1
            assert plots["plots"][0]["record_count"] == 2
            assert plots["plots"][0]["open_task_count"] == 1
            _, farm_stats, _ = api("/api/farm-records/stats", token=token)
            assert farm_stats["plot_count"] == 1 and farm_stats["record_count"] == 2

            _, economics, _ = api("/api/farm-records/economics", token=token)
            assert economics["plots"][0]["total_revenue"] == 5040.0
            _, tasks, _ = api("/api/farm-tasks", token=token)
            assert len(tasks["tasks"]) == 1
    print("发布演练通过：干净安装、构建、启动、重启、数据持久化和备份恢复均正常。")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_path = ROOT / "dist" / "rehearsal-backend.log"
        if log_path.is_file():
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
            print(f"发布演练失败，后端日志最后 30 行（{log_path}）：", file=sys.stderr)
            for log_line in tail:
                print(log_line, file=sys.stderr)
        raise
