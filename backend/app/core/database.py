import logging
import sqlite3
from pathlib import Path

from fastapi import HTTPException

from backend.app.core.config import get_settings


logger = logging.getLogger("yunxun.backend.database")


def get_db_path() -> Path:
    return Path(get_settings().db_path)


def ensure_parent_dir() -> None:
    get_db_path().parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_parent_dir()
    connection = sqlite3.connect(get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


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

                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
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
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"数据库路径不可写：{db_path}") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="数据库初始化失败，请检查 SQLite 文件权限。") from exc
    logger.info("SQLite database initialized: %s", db_path)
