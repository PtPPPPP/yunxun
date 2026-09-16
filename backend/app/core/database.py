import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from backend.app.core.config import get_settings


logger = logging.getLogger("yunxun.backend.database")
SCHEMA_VERSION = 9


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
    # PRAGMA table_info 的输出顺序固定为 (cid, name, type, notnull, dflt_value, pk)；
    # 用下标取值，这样没有设置 row_factory 的连接也能安全调用。
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


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


def _apply_schema_v2(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_model_credentials (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            display_name TEXT NOT NULL,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL,
            encrypted_api_key BLOB NOT NULL,
            key_fingerprint TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0, 1)),
            is_enabled INTEGER NOT NULL DEFAULT 1 CHECK(is_enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified_at TEXT,
            last_verify_status TEXT,
            last_verify_error_code TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_credentials_user_updated "
        "ON user_model_credentials(user_id, updated_at DESC)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_model_credentials_one_default "
        "ON user_model_credentials(user_id) WHERE is_default = 1"
    )
    if "model_config_id" not in _table_columns(conn, "chat_sessions"):
        conn.execute(
            "ALTER TABLE chat_sessions ADD COLUMN model_config_id TEXT "
            "REFERENCES user_model_credentials(id) ON DELETE SET NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_model_config "
        "ON chat_sessions(model_config_id)"
    )


def _apply_schema_v3(conn: sqlite3.Connection) -> None:
    """Remove the user-managed model credential surface while preserving all user data."""
    if "user_model_credentials" in _table_names(conn):
        count = conn.execute("SELECT COUNT(*) FROM user_model_credentials").fetchone()[0]
        logger.info("Removing legacy user model credentials rows=%s", count)
    conn.execute("DROP INDEX IF EXISTS idx_chat_sessions_model_config")
    if "model_config_id" in _table_columns(conn, "chat_sessions"):
        conn.execute("ALTER TABLE chat_sessions DROP COLUMN model_config_id")
    conn.execute("DROP INDEX IF EXISTS idx_model_credentials_user_updated")
    conn.execute("DROP INDEX IF EXISTS idx_model_credentials_one_default")
    conn.execute("DROP TABLE IF EXISTS user_model_credentials")


def _apply_schema_v4(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "chat_sessions")
    if "is_pinned" not in columns:
        conn.execute(
            "ALTER TABLE chat_sessions ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0 "
            "CHECK(is_pinned IN (0, 1))"
        )
    if "pinned_at" not in columns:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN pinned_at TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_feature_pinned_updated "
        "ON chat_sessions(user_id, feature, is_pinned DESC, pinned_at DESC, updated_at DESC, id DESC)"
    )


def _apply_schema_v5(conn: sqlite3.Connection) -> None:
    """Persist image diagnosis and farm decision records for the user stats panel."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('vision','decision')),
            crop TEXT NOT NULL,
            payload TEXT,
            result TEXT NOT NULL,
            mode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_records_user_kind_created "
        "ON tool_records(user_id, kind, created_at DESC, id DESC)"
    )


def _apply_schema_v7(conn: sqlite3.Connection) -> None:
    """新增地块档案与农事台账：地块是业务主体，台账是挂在地块下的作业记录。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plots (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            area_mu REAL NOT NULL,
            soil_type TEXT NOT NULL,
            irrigation TEXT NOT NULL,
            crop TEXT NOT NULL,
            planted_on TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plots_user_updated "
        "ON plots(user_id, updated_at DESC, id DESC)"
    )
    # kind 刻意不加 CHECK 约束：tool_records 的 CHECK 让新增取值只能整表重建，
    # 这里改为在路由层用常量集合校验。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS farm_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plot_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            happened_on TEXT NOT NULL,
            crop TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            quantity TEXT NOT NULL DEFAULT '',
            cost REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(plot_id) REFERENCES plots(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_farm_records_user_plot_date "
        "ON farm_records(user_id, plot_id, happened_on DESC, id DESC)"
    )


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def _apply_schema_v9(conn: sqlite3.Connection) -> None:
    """新增茬次（种植季），并把地块上的当季作物与定植日期搬进茬次表。

    搬完就删掉 plots.crop / plots.planted_on：留着会和茬次表形成两个真相来源。
    该地块既有的作业记录一并归到这条茬次上，这样升级前后看到的投入产出口径一致
    （升级前本来就是按地块汇总的）。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plot_seasons (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plot_id TEXT NOT NULL,
            crop TEXT NOT NULL,
            started_on TEXT,
            ended_on TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(plot_id) REFERENCES plots(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plot_seasons_user_plot_started "
        "ON plot_seasons(user_id, plot_id, started_on DESC, id DESC)"
    )
    # 一块地同时只能有一茬进行中，用部分唯一索引把它变成数据库层面的约束。
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_plot_seasons_one_active "
        "ON plot_seasons(plot_id) WHERE ended_on IS NULL"
    )

    if "season_id" not in _table_columns(conn, "farm_records"):
        conn.execute("ALTER TABLE farm_records ADD COLUMN season_id TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_farm_records_season_created "
        "ON farm_records(season_id, happened_on DESC, id DESC)"
    )

    plot_columns = _table_columns(conn, "plots")
    if "crop" in plot_columns:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 用下标取值，迁移可能在没设置 row_factory 的连接上执行。
        rows = conn.execute("SELECT id, user_id, crop, planted_on FROM plots").fetchall()
        migrated = 0
        for row in rows:
            plot_id, user_id, crop, planted_on = row[0], row[1], row[2], row[3]
            if not (crop or "").strip():
                continue
            season_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO plot_seasons
                    (id, user_id, plot_id, crop, started_on, ended_on, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, '', ?, ?)
                """,
                (season_id, user_id, plot_id, crop.strip(), planted_on, timestamp, timestamp),
            )
            conn.execute("UPDATE farm_records SET season_id = ? WHERE plot_id = ?", (season_id, plot_id))
            migrated += 1
        if migrated:
            logger.info("Migrated %s plot crops into plot_seasons.", migrated)
        conn.execute("ALTER TABLE plots DROP COLUMN crop")
        conn.execute("ALTER TABLE plots DROP COLUMN planted_on")


def _apply_schema_v8(conn: sqlite3.Connection) -> None:
    """台账扩展投入品、安全间隔期与采收产量，并新增农事待办表。"""
    record_columns = _table_columns(conn, "farm_records")
    additions = (
        ("material", "material TEXT"),
        ("safe_days", "safe_days INTEGER"),
        ("yield_kg", "yield_kg REAL"),
        ("unit_price", "unit_price REAL"),
    )
    for column, ddl in additions:
        if column not in record_columns:
            conn.execute(f"ALTER TABLE farm_records ADD COLUMN {ddl}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS farm_tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plot_id TEXT,
            title TEXT NOT NULL,
            due_on TEXT NOT NULL,
            done_at TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(plot_id) REFERENCES plots(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_farm_tasks_user_due "
        "ON farm_tasks(user_id, done_at, due_on, id)"
    )


def _apply_schema_v6(conn: sqlite3.Connection) -> None:
    """移除 AI 能力：删除会话、消息与幂等表，并去掉用户模型偏好字段。"""
    # chat_messages 通过外键指向 chat_sessions 且没有级联，必须先删子表。
    conn.execute("DROP TABLE IF EXISTS chat_messages")
    conn.execute("DROP TABLE IF EXISTS chat_sessions")
    conn.execute("DROP TABLE IF EXISTS idempotency_requests")
    if "preferred_model" in _table_columns(conn, "users"):
        logger.info("Removing users.preferred_model during schema migration.")
        conn.execute("ALTER TABLE users DROP COLUMN preferred_model")


def migrate_schema(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    starting_version = current
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
        current = 1
    if current < 2:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v2(conn)
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("2_user_model_credentials")
        current = 2
    if current < 3:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v3(conn)
            conn.execute("PRAGMA user_version = 3")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("3_remove_user_model_credentials")
        current = 3
    if current < 4:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v4(conn)
            conn.execute("PRAGMA user_version = 4")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("4_session_pinning")
        current = 4
    if current < 5:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v5(conn)
            conn.execute("PRAGMA user_version = 5")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("5_tool_records")
        current = 5
    if current < 6:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v6(conn)
            conn.execute("PRAGMA user_version = 6")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("6_remove_ai_surface")
        current = 6
    if current < 7:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v7(conn)
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("7_farm_plots_and_records")
        current = 7
    if current < 8:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v8(conn)
            conn.execute("PRAGMA user_version = 8")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("8_harvest_yield_and_tasks")
        current = 8
    if current < 9:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _apply_schema_v9(conn)
            conn.execute("PRAGMA user_version = 9")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append("9_plot_seasons")
        current = 9
    return starting_version, applied


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
