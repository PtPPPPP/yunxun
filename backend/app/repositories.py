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


def public_plot(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "name": record["name"],
        "area_mu": float(record["area_mu"]),
        "soil_type": record["soil_type"],
        "irrigation": record["irrigation"],
        "crop": record["crop"],
        "planted_on": record["planted_on"],
        "notes": record["notes"],
        "record_count": int(record.get("record_count") or 0),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def create_plot(
    user_id: str,
    name: str,
    area_mu: float,
    soil_type: str,
    irrigation: str,
    crop: str,
    planted_on: str | None,
    notes: str,
) -> dict[str, Any]:
    plot_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plots
                (id, user_id, name, area_mu, soil_type, irrigation, crop, planted_on, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (plot_id, user_id, name, area_mu, soil_type, irrigation, crop, planted_on, notes, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM plots WHERE id = ?", (plot_id,)).fetchone()
    return public_plot(dict(row))


def get_plot(plot_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM plots WHERE id = ?", (plot_id,))


def list_plots(user_id: str) -> list[dict[str, Any]]:
    """地块列表附带各自的作业记录条数，供卡片展示与删除确认使用。"""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, (
                SELECT COUNT(*) FROM farm_records r WHERE r.plot_id = p.id
            ) AS record_count
            FROM plots p
            WHERE p.user_id = ?
            ORDER BY p.updated_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [public_plot(dict(row)) for row in rows]


def count_plots(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM plots WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["total"]) if row else 0


def update_plot(
    plot_id: str,
    name: str,
    area_mu: float,
    soil_type: str,
    irrigation: str,
    crop: str,
    planted_on: str | None,
    notes: str,
) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE plots
            SET name = ?, area_mu = ?, soil_type = ?, irrigation = ?, crop = ?,
                planted_on = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, area_mu, soil_type, irrigation, crop, planted_on, notes, updated_at, plot_id),
        )
        row = conn.execute("SELECT * FROM plots WHERE id = ?", (plot_id,)).fetchone()
    return public_plot(dict(row))


def delete_plot_with_records(plot_id: str) -> int:
    """删除地块并连带删除其作业记录，返回被删除的记录条数。"""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM farm_records WHERE plot_id = ?", (plot_id,)).fetchone()
        removed = int(row["total"]) if row else 0
        conn.execute("DELETE FROM farm_records WHERE plot_id = ?", (plot_id,))
        conn.execute("DELETE FROM plots WHERE id = ?", (plot_id,))
    return removed


# 台账查询统一带出地块名称，接口因此自解释，前端不必再按 plot_id 映射。
FARM_RECORD_SELECT = """
    SELECT r.*, COALESCE(p.name, '') AS plot_name
    FROM farm_records r
    LEFT JOIN plots p ON p.id = r.plot_id
"""


def public_farm_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_cost = record["cost"]
    return {
        "id": record["id"],
        "plot_id": record["plot_id"],
        "plot_name": record["plot_name"],
        "kind": record["kind"],
        "happened_on": record["happened_on"],
        "crop": record["crop"],
        "detail": record["detail"],
        "quantity": record["quantity"],
        "cost": None if raw_cost is None else float(raw_cost),
        "created_at": record["created_at"],
    }


def create_farm_record(
    user_id: str,
    plot_id: str,
    kind: str,
    happened_on: str,
    crop: str,
    detail: str,
    quantity: str,
    cost: float | None,
) -> dict[str, Any]:
    record_id = uuid.uuid4().hex
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO farm_records
                (id, user_id, plot_id, kind, happened_on, crop, detail, quantity, cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, user_id, plot_id, kind, happened_on, crop, detail, quantity, cost, created_at),
        )
        row = conn.execute(FARM_RECORD_SELECT + " WHERE r.id = ?", (record_id,)).fetchone()
    return public_farm_record(dict(row))


def get_farm_record(record_id: str) -> dict[str, Any] | None:
    return _fetchone(FARM_RECORD_SELECT + " WHERE r.id = ?", (record_id,))


def list_farm_records_page(
    user_id: str,
    *,
    plot_id: str | None = None,
    limit: int = 20,
    cursor: tuple[str, str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """按作业日期倒序翻页；游标复用 (happened_on, id)。"""
    conditions = ["r.user_id = ?"]
    params: list[Any] = [user_id]
    if plot_id:
        conditions.append("r.plot_id = ?")
        params.append(plot_id)
    if cursor:
        conditions.append("(r.happened_on < ? OR (r.happened_on = ? AND r.id < ?))")
        params.extend([cursor[0], cursor[0], cursor[1]])
    params.append(limit + 1)
    with get_connection() as conn:
        rows = conn.execute(
            FARM_RECORD_SELECT + " WHERE " + " AND ".join(conditions)
            + " ORDER BY r.happened_on DESC, r.id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    has_more = len(rows) > limit
    return [public_farm_record(dict(row)) for row in rows[:limit]], has_more


def delete_farm_record(record_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM farm_records WHERE id = ?", (record_id,))


def count_farm_records(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM farm_records WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["total"]) if row else 0
