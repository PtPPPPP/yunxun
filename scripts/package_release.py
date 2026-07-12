from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
INCLUDE_ROOTS = ["backend", "frontend", "scripts", "docs"]
INCLUDE_FILES = [".env.example", ".gitignore", "README.md", "CHANGELOG.md", "LICENSE"]
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", "test-results", "playwright-report", ".venv", "backups"}
EXCLUDED_SUFFIXES = {".db", ".log", ".pyc", ".zip", ".png"}


def allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return not (EXCLUDED_PARTS & set(relative.parts)) and path.suffix.lower() not in EXCLUDED_SUFFIXES and path.name != ".env"


def main() -> None:
    output = ROOT / "dist" / "release"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"yunxun-{VERSION}.zip"
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory) / f"yunxun-{VERSION}"
        for root_name in INCLUDE_ROOTS:
            source_root = ROOT / root_name
            for source in source_root.rglob("*"):
                if source.is_file() and allowed(source):
                    destination = stage / source.relative_to(ROOT)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
        for name in INCLUDE_FILES:
            source = ROOT / name
            if source.is_file():
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        manifest = {
            "application_name": "云寻AI",
            "version": VERSION,
            "schema_version": 1,
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "working_tree_modified": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(),
            "node_version": subprocess.check_output(["node", "--version"], text=True).strip(),
            "frontend_lockfile_hash": hashlib.sha256((ROOT / "frontend/package-lock.json").read_bytes()).hexdigest(),
            "backend_dependency_hash": hashlib.sha256((ROOT / "backend/requirements.txt").read_bytes()).hexdigest(),
            "included_files_count": len(files) + 1,
        }
        (stage / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for source in sorted(stage.rglob("*")):
                if source.is_file():
                    bundle.write(source, source.relative_to(stage.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        names = bundle.namelist()
    if bad or any(any(part in name.split("/") for part in EXCLUDED_PARTS) or Path(name).suffix.lower() in EXCLUDED_SUFFIXES for name in names):
        raise SystemExit("发布包校验失败：包含损坏或禁止文件。")
    print(json.dumps({"archive": str(archive), "sha256": digest, "files": len(names)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
