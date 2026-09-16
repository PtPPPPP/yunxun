import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.core.database import get_connection


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def public_user(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "username": record["username"],
        "display_name": record["display_name"],
        "created_at": record["created_at"],
    }


def _fetchone(query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM users WHERE username = ?", (username,))


def create_user(username: str, password_hash: str, display_name: str) -> dict[str, Any]:
    user_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, display_name, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def update_user_profile(user_id: str, display_name: str) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET display_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (display_name, updated_at, user_id),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def create_auth_token(user_id: str, token_hash: str, expires_at: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_tokens (token_hash, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, expires_at, now_iso()),
        )


def delete_auth_token(token_hash: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))


def cleanup_expired_tokens() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (now_iso(),))


def get_user_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        token_row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token_hash = ? AND expires_at >= ?",
            (token_hash, now_iso()),
        ).fetchone()
        if not token_row:
            return None
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (token_row["user_id"],)).fetchone()
    return dict(user_row) if user_row else None


def public_tool_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "kind": record["kind"],
        "crop": record["crop"],
        "result": record["result"],
        "mode": record["mode"],
        "created_at": record["created_at"],
    }


def create_tool_record(
    user_id: str,
    kind: str,
    crop: str,
    payload: dict[str, Any] | None,
    result: str,
    mode: str,
) -> dict[str, Any]:
    record_id = uuid.uuid4().hex
    created_at = now_iso()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tool_records (id, user_id, kind, crop, payload, result, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                user_id,
                kind,
                crop,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                result,
                mode,
                created_at,
            ),
        )
        row = conn.execute("SELECT * FROM tool_records WHERE id = ?", (record_id,)).fetchone()
    return public_tool_record(dict(row))


def list_tool_records_page(
    user_id: str,
    *,
    kind: str | None = None,
    limit: int = 20,
    cursor: tuple[str, str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    conditions = ["user_id = ?"]
    params: list[Any] = [user_id]
    if kind:
        conditions.append("kind = ?")
        params.append(kind)
    if cursor:
        conditions.append("(created_at < ? OR (created_at = ? AND id < ?))")
        params.extend([cursor[0], cursor[0], cursor[1]])
    params.append(limit + 1)
    where_sql = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_records WHERE " + where_sql
            + " ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    has_more = len(rows) > limit
    return [public_tool_record(dict(row)) for row in rows[:limit]], has_more


def count_tool_records_by_kind(user_id: str) -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT kind, COUNT(*) AS total
            FROM tool_records
            WHERE user_id = ?
            GROUP BY kind
            """,
            (user_id,),
        ).fetchall()
    return {str(row["kind"]): int(row["total"]) for row in rows}


def summarize_tool_records(user_id: str, *, days: int = 14, top_crops: int = 5) -> dict[str, Any]:
    """近 N 天按日计数与作物 Top K 汇总，供统计面板展示。"""
    since = (now_utc() - timedelta(days=days - 1)).date().isoformat()
    with get_connection() as conn:
        day_rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
            FROM tool_records
            WHERE user_id = ? AND created_at >= ?
            GROUP BY day
            """,
            (user_id, since),
        ).fetchall()
        crop_rows = conn.execute(
            """
            SELECT crop, COUNT(*) AS total
            FROM tool_records
            WHERE user_id = ?
            GROUP BY crop
            ORDER BY total DESC, crop ASC
            LIMIT ?
            """,
            (user_id, top_crops),
        ).fetchall()
    by_day = {str(row["day"]): int(row["total"]) for row in day_rows}
    return {
        "since": since,
        "days": days,
        "by_day": by_day,
        "top_crops": [{"crop": str(row["crop"]), "total": int(row["total"])} for row in crop_rows],
    }
