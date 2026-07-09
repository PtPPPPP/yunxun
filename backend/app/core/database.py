import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from backend.app.core.config import get_settings


logger = logging.getLogger("yunxun.backend.database")


def get_db_path() -> Path:
    return Path(get_settings().db_path)


def ensure_parent_dir() -> None:
    get_db_path().parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_parent_dir()
    connection = sqlite3.connect(get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
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


def init_db() -> None:
    db_path = get_db_path()
    try:
        with get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    preferred_model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    feature TEXT NOT NULL DEFAULT 'chat',
                    model_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                );
                """
            )
            _ensure_auth_tokens_schema(conn)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"数据库路径不可写：{db_path}") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="数据库初始化失败，请检查 SQLite 文件权限。") from exc
    logger.info("SQLite database initialized: %s", db_path)
