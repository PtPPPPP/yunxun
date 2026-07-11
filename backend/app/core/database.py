import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from backend.app.core.config import get_settings


logger = logging.getLogger("yunxun.backend.database")
SCHEMA_VERSION = 1


def get_db_path() -> Path:
    return Path(get_settings().db_path)


def ensure_parent_dir() -> None:
    get_db_path().parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_parent_dir()
    connection = sqlite3.connect(get_db_path(), check_same_thread=False, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _create_auth_tokens_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def _ensure_auth_tokens_schema(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "auth_tokens")
    if not columns:
        _create_auth_tokens_table(conn)
        return
    if "token_hash" not in columns:
        logger.warning("Invalidating legacy plaintext auth tokens during schema migration.")
        conn.execute("DROP TABLE auth_tokens")
        _create_auth_tokens_table(conn)


def _apply_schema_v1(conn: sqlite3.Connection) -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, display_name TEXT NOT NULL, preferred_model TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS chat_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
        title TEXT NOT NULL, feature TEXT NOT NULL DEFAULT 'chat', model_name TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""",
        """CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES chat_sessions(id))""",
        """CREATE TABLE IF NOT EXISTS idempotency_requests (owner_id TEXT NOT NULL, key_hash TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('in_flight','completed','failed')),
        lease_id TEXT NOT NULL, response_status INTEGER, response_body TEXT, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, expires_at TEXT NOT NULL, PRIMARY KEY(owner_id,key_hash))""",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_feature_updated ON chat_sessions(user_id,feature,updated_at DESC,id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id,created_at DESC,id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at ON idempotency_requests(expires_at)",
    ]
    for statement in statements:
        conn.execute(statement)
    _ensure_auth_tokens_schema(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires_at ON auth_tokens(expires_at)")


def migrate_schema(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current > SCHEMA_VERSION:
        raise sqlite3.DatabaseError(
            f"数据库 Schema 版本 {current} 高于当前代码支持的 {SCHEMA_VERSION}。"
        )
    applied: list[str] = []
    if current < 1:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v1(conn)
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("1_initial_secure_schema")
    return current, applied


def init_db() -> None:
    db_path = get_db_path()
    try:
        ensure_parent_dir()
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 10000")
            current, applied = migrate_schema(conn)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.commit()
        finally:
            conn.close()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"数据库路径不可写：{db_path}") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="数据库初始化失败，请检查 SQLite 文件权限。") from exc
    logger.info(
        "SQLite database initialized: %s schema_before=%s schema_target=%s migrations=%s",
        db_path, current, SCHEMA_VERSION, ",".join(applied) or "none",
    )
