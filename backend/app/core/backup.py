from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.database import SCHEMA_VERSION


CORE_TABLES = {"users", "chat_sessions", "chat_messages", "auth_tokens", "idempotency_requests"}


def validate_database(path: Path) -> int:
    if not path.is_file():
        raise ValueError(f"数据库文件不存在：{path.name}")
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("数据库完整性检查失败。")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as exc:
        raise ValueError("数据库文件无法打开或已经损坏。") from exc
    if version > SCHEMA_VERSION:
        raise ValueError(f"数据库 Schema 版本 {version} 高于当前支持版本 {SCHEMA_VERSION}。")
    if not CORE_TABLES.issubset(tables):
        raise ValueError("数据库缺少必要数据表。")
    return version


def create_backup(source: Path, backup_dir: Path, *, keep: int = 10) -> Path:
    validate_database(source)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"yunxun-{timestamp}.db"
    with closing(sqlite3.connect(source)) as source_conn, closing(sqlite3.connect(destination)) as destination_conn:
        source_conn.backup(destination_conn)
    validate_database(destination)
    backups = sorted(backup_dir.glob("yunxun-*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    for expired in backups[max(1, keep):]:
        expired.unlink()
    return destination


def restore_backup(current: Path, backup: Path, backup_dir: Path) -> Path:
    validate_database(backup)
    safety_backup = create_backup(current, backup_dir)
    temporary = current.with_suffix(current.suffix + ".restore.tmp")
    try:
        temporary.unlink(missing_ok=True)
        with closing(sqlite3.connect(backup)) as source_conn, closing(sqlite3.connect(temporary)) as destination_conn:
            source_conn.backup(destination_conn)
        validate_database(temporary)
        os.replace(temporary, current)
        current.with_name(current.name + "-wal").unlink(missing_ok=True)
        current.with_name(current.name + "-shm").unlink(missing_ok=True)
        validate_database(current)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return safety_backup
