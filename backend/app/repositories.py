import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.app.core.database import get_connection


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def add_days(iso_date: str | None, days: int | None) -> str | None:
    """在农事日期上加天数；任一参数缺失或日期格式异常时返回 None。"""
    if not iso_date or days is None:
        return None
    try:
        base = date.fromisoformat(iso_date)
    except ValueError:
        return None
    return (base + timedelta(days=days)).isoformat()


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
    """近 N 天按日计数与作物 Top K 汇总，供统计面板展示。

    按本机时区归日，而不是直接切 UTC 时间戳：created_at 存的是 UTC，在东八区
    早上 8 点前记的建议会被算到前一天。窗口只有十几天，取回来在 Python 里归日
    的代价可以忽略。窗口起点往前多取一天，覆盖时区偏移造成的边界。
    """
    local_today = datetime.now().date()
    since = (local_today - timedelta(days=days - 1)).isoformat()
    window_start = (local_today - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        stamp_rows = conn.execute(
            "SELECT created_at FROM tool_records WHERE user_id = ? AND created_at >= ?",
            (user_id, window_start),
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
    by_day: dict[str, int] = {}
    for row in stamp_rows:
        try:
            local_day = datetime.fromisoformat(row["created_at"]).astimezone().date().isoformat()
        except ValueError:
            continue
        if local_day >= since:
            by_day[local_day] = by_day.get(local_day, 0) + 1
    return {
        "since": since,
        "days": days,
        "by_day": by_day,
        "top_crops": [{"crop": str(row["crop"]), "total": int(row["total"])} for row in crop_rows],
    }


def public_plot(record: dict[str, Any]) -> dict[str, Any]:
    """地块投影。

    crop / planted_on 不再是地块自己的列，而是从茬次推导：优先进行中的那一茬，
    没有则退回最近一茬（「上次种的是玉米」对农户仍然有用）。这样台账的作物默认值、
    今日农活的地块带入都不用改。
    """
    season_id = record.get("season_id")
    season_ended_on = record.get("season_ended_on")
    is_active = season_id is not None and season_ended_on is None
    return {
        "id": record["id"],
        "name": record["name"],
        "area_mu": float(record["area_mu"]),
        "soil_type": record["soil_type"],
        "irrigation": record["irrigation"],
        "crop": record.get("season_crop") or "",
        "planted_on": record.get("season_started_on"),
        "notes": record["notes"],
        "record_count": int(record.get("record_count") or 0),
        "open_task_count": int(record.get("open_task_count") or 0),
        "active_season": (
            {
                "id": season_id,
                "crop": record.get("season_crop") or "",
                "started_on": record.get("season_started_on"),
            }
            if is_active
            else None
        ),
        "season_record_count": int(record.get("season_record_count") or 0) if is_active else 0,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def create_plot(
    user_id: str,
    name: str,
    area_mu: float,
    soil_type: str,
    irrigation: str,
    notes: str,
) -> dict[str, Any]:
    plot_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plots (id, user_id, name, area_mu, soil_type, irrigation, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (plot_id, user_id, name, area_mu, soil_type, irrigation, notes, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM plots WHERE id = ?", (plot_id,)).fetchone()
    return public_plot(dict(row))


def get_plot(plot_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM plots WHERE id = ?", (plot_id,))


def list_plots(user_id: str, *, reference_date: str | None = None) -> list[dict[str, Any]]:
    """地块列表，附带作业记录条数与最近一次打药的安全期状态。

    安全期状态并进地块列表而不是单开接口：地块页和台账页都要用它，
    合并后前端只需一次请求、一个数据来源，不必维护两份可能不同步的状态。
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                s.id AS season_id,
                s.crop AS season_crop,
                s.started_on AS season_started_on,
                s.ended_on AS season_ended_on,
                (
                    SELECT COUNT(*) FROM farm_records r WHERE r.plot_id = p.id
                ) AS record_count,
                (
                    SELECT COUNT(*) FROM farm_records r WHERE r.season_id = s.id
                ) AS season_record_count,
                (
                    SELECT COUNT(*) FROM farm_tasks t WHERE t.plot_id = p.id AND t.done_at IS NULL
                ) AS open_task_count
            FROM plots p
            LEFT JOIN plot_seasons s ON s.id = (
                SELECT s2.id FROM plot_seasons s2 WHERE s2.plot_id = p.id
                ORDER BY (s2.ended_on IS NULL) DESC, s2.started_on DESC, s2.id DESC LIMIT 1
            )
            WHERE p.user_id = ?
            ORDER BY p.updated_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()

    safety_by_plot = {
        item["plot_id"]: item
        for item in list_harvest_safety(
            user_id,
            reference_date=reference_date or datetime.now().date().isoformat(),
        )
    }
    plots = []
    for row in rows:
        plot = public_plot(dict(row))
        plot["harvest_safety"] = safety_by_plot.get(plot["id"])
        plots.append(plot)
    return plots


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
    notes: str,
) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE plots
            SET name = ?, area_mu = ?, soil_type = ?, irrigation = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, area_mu, soil_type, irrigation, notes, updated_at, plot_id),
        )
        row = conn.execute("SELECT * FROM plots WHERE id = ?", (plot_id,)).fetchone()
    return public_plot(dict(row))


def delete_plot_with_records(plot_id: str) -> tuple[int, int]:
    """删除地块并连带删除其作业记录与待办，返回 (记录条数, 待办条数)。"""
    with get_connection() as conn:
        record_row = conn.execute("SELECT COUNT(*) AS total FROM farm_records WHERE plot_id = ?", (plot_id,)).fetchone()
        task_row = conn.execute("SELECT COUNT(*) AS total FROM farm_tasks WHERE plot_id = ?", (plot_id,)).fetchone()
        removed_records = int(record_row["total"]) if record_row else 0
        removed_tasks = int(task_row["total"]) if task_row else 0
        conn.execute("DELETE FROM farm_records WHERE plot_id = ?", (plot_id,))
        conn.execute("DELETE FROM farm_tasks WHERE plot_id = ?", (plot_id,))
        conn.execute("DELETE FROM plots WHERE id = ?", (plot_id,))
    return removed_records, removed_tasks


# 待办查询统一带出地块名称，杂事可以不挂地块。
FARM_TASK_SELECT = """
    SELECT t.*, COALESCE(p.name, '') AS plot_name
    FROM farm_tasks t
    LEFT JOIN plots p ON p.id = t.plot_id
"""


def public_farm_task(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "plot_id": record["plot_id"],
        "plot_name": record["plot_name"],
        "title": record["title"],
        "due_on": record["due_on"],
        "done": record["done_at"] is not None,
        "done_at": record["done_at"],
        "notes": record["notes"],
        "created_at": record["created_at"],
    }


def create_farm_task(
    user_id: str,
    plot_id: str | None,
    title: str,
    due_on: str,
    notes: str,
) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO farm_tasks (id, user_id, plot_id, title, due_on, done_at, notes, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (task_id, user_id, plot_id, title, due_on, notes, created_at),
        )
        row = conn.execute(FARM_TASK_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()
    return public_farm_task(dict(row))


def get_farm_task(task_id: str) -> dict[str, Any] | None:
    return _fetchone(FARM_TASK_SELECT + " WHERE t.id = ?", (task_id,))


def list_open_farm_tasks(user_id: str) -> list[dict[str, Any]]:
    """未完成待办，按到期日升序；同一到期日再按创建时间保证顺序稳定。"""
    with get_connection() as conn:
        rows = conn.execute(
            FARM_TASK_SELECT + " WHERE t.user_id = ? AND t.done_at IS NULL ORDER BY t.due_on ASC, t.id ASC",
            (user_id,),
        ).fetchall()
    return [public_farm_task(dict(row)) for row in rows]


def list_recent_done_farm_tasks(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            FARM_TASK_SELECT + " WHERE t.user_id = ? AND t.done_at IS NOT NULL ORDER BY t.done_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [public_farm_task(dict(row)) for row in rows]


def update_farm_task(
    task_id: str,
    plot_id: str | None,
    title: str,
    due_on: str,
    notes: str,
    done: bool,
) -> dict[str, Any]:
    with get_connection() as conn:
        current = conn.execute("SELECT done_at FROM farm_tasks WHERE id = ?", (task_id,)).fetchone()
        if current is None:
            raise LookupError("farm task disappeared while updating")
        # 只在完成状态真正变化时改写完成时间，避免每次保存都刷新「完成于」。
        was_done = current["done_at"] is not None
        done_at = current["done_at"] if was_done == done else (now_iso() if done else None)
        conn.execute(
            """
            UPDATE farm_tasks
            SET plot_id = ?, title = ?, due_on = ?, notes = ?, done_at = ?
            WHERE id = ?
            """,
            (plot_id, title, due_on, notes, done_at, task_id),
        )
        row = conn.execute(FARM_TASK_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()
    return public_farm_task(dict(row))


def delete_farm_task(task_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM farm_tasks WHERE id = ?", (task_id,))


def public_season(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "plot_id": record["plot_id"],
        "crop": record["crop"],
        "started_on": record["started_on"],
        "ended_on": record["ended_on"],
        "active": record["ended_on"] is None,
        "notes": record["notes"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def create_season(
    user_id: str,
    plot_id: str,
    crop: str,
    started_on: str | None,
    notes: str,
) -> dict[str, Any]:
    season_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plot_seasons
                (id, user_id, plot_id, crop, started_on, ended_on, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (season_id, user_id, plot_id, crop, started_on, notes, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM plot_seasons WHERE id = ?", (season_id,)).fetchone()
    return public_season(dict(row))


def get_season(season_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM plot_seasons WHERE id = ?", (season_id,))


def get_active_season(plot_id: str) -> dict[str, Any] | None:
    """地块进行中的那一茬；部分唯一索引保证最多只有一条。"""
    return _fetchone(
        "SELECT * FROM plot_seasons WHERE plot_id = ? AND ended_on IS NULL",
        (plot_id,),
    )


def list_seasons(user_id: str, *, plot_id: str | None = None) -> list[dict[str, Any]]:
    conditions = ["user_id = ?"]
    params: list[Any] = [user_id]
    if plot_id:
        conditions.append("plot_id = ?")
        params.append(plot_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM plot_seasons WHERE " + " AND ".join(conditions)
            + " ORDER BY started_on DESC, id DESC",
            tuple(params),
        ).fetchall()
    return [public_season(dict(row)) for row in rows]


def update_season(
    season_id: str,
    crop: str,
    started_on: str | None,
    ended_on: str | None,
    notes: str,
) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE plot_seasons
            SET crop = ?, started_on = ?, ended_on = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (crop, started_on, ended_on, notes, updated_at, season_id),
        )
        row = conn.execute("SELECT * FROM plot_seasons WHERE id = ?", (season_id,)).fetchone()
    return public_season(dict(row))


def delete_season(season_id: str) -> None:
    """删掉一茬。它的作业记录变回「未归茬」，不连带删除。"""
    with get_connection() as conn:
        conn.execute("UPDATE farm_records SET season_id = NULL WHERE season_id = ?", (season_id,))
        conn.execute("DELETE FROM plot_seasons WHERE id = ?", (season_id,))


# 台账查询统一带出地块名称与茬次作物，接口因此自解释。
FARM_RECORD_SELECT = """
    SELECT r.*, COALESCE(p.name, '') AS plot_name, COALESCE(s.crop, '') AS season_crop
    FROM farm_records r
    LEFT JOIN plots p ON p.id = r.plot_id
    LEFT JOIN plot_seasons s ON s.id = r.season_id
"""


def public_farm_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_cost = record["cost"]
    raw_yield = record["yield_kg"]
    raw_price = record["unit_price"]
    raw_safe_days = record["safe_days"]
    return {
        "id": record["id"],
        "plot_id": record["plot_id"],
        "plot_name": record["plot_name"],
        "kind": record["kind"],
        "happened_on": record["happened_on"],
        "crop": record["crop"],
        "season_id": record["season_id"],
        "season_crop": record["season_crop"],
        "material": record["material"],
        "detail": record["detail"],
        "quantity": record["quantity"],
        "cost": None if raw_cost is None else float(raw_cost),
        "safe_days": None if raw_safe_days is None else int(raw_safe_days),
        # 最早安全采收日由施药日加安全间隔期推导，不冗余落库。
        "earliest_harvest_on": add_days(record["happened_on"], None if raw_safe_days is None else int(raw_safe_days)),
        "yield_kg": None if raw_yield is None else float(raw_yield),
        "unit_price": None if raw_price is None else float(raw_price),
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
    material: str = "",
    safe_days: int | None = None,
    yield_kg: float | None = None,
    unit_price: float | None = None,
    season_id: str | None = None,
) -> dict[str, Any]:
    record_id = uuid.uuid4().hex
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO farm_records
                (id, user_id, plot_id, kind, happened_on, crop, material, detail, quantity,
                 cost, safe_days, yield_kg, unit_price, season_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id, user_id, plot_id, kind, happened_on, crop, material, detail, quantity,
                cost, safe_days, yield_kg, unit_price, season_id, created_at,
            ),
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


def list_harvest_safety(user_id: str, *, reference_date: str) -> list[dict[str, Any]]:
    """每块地最近一次带安全间隔期的打药，以及距最早安全采收日的天数。

    「最近一次」用窗口函数取，避免每块地各发一条查询。
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT plot_id, plot_name, material, happened_on, safe_days FROM (
                SELECT
                    r.plot_id AS plot_id,
                    p.name AS plot_name,
                    r.material AS material,
                    r.happened_on AS happened_on,
                    r.safe_days AS safe_days,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.plot_id ORDER BY r.happened_on DESC, r.id DESC
                    ) AS row_number
                FROM farm_records r
                JOIN plots p ON p.id = r.plot_id
                WHERE r.user_id = ? AND r.kind = '打药' AND r.safe_days IS NOT NULL
            )
            WHERE row_number = 1
            ORDER BY happened_on DESC
            """,
            (user_id,),
        ).fetchall()

    try:
        today = date.fromisoformat(reference_date)
    except ValueError:
        return []

    safety: list[dict[str, Any]] = []
    for row in rows:
        safe_days = int(row["safe_days"])
        earliest = add_days(row["happened_on"], safe_days)
        days_remaining = None
        if earliest:
            days_remaining = (date.fromisoformat(earliest) - today).days
        safety.append(
            {
                "plot_id": row["plot_id"],
                "plot_name": row["plot_name"],
                "material": row["material"],
                "happened_on": row["happened_on"],
                "safe_days": safe_days,
                "earliest_harvest_on": earliest,
                "days_remaining": days_remaining,
                # 剩余天数 > 0 表示还在安全期内，此时采收不合规。
                "in_safe_window": days_remaining is not None and days_remaining > 0,
            }
        )
    return safety


def _economics_row(row: dict[str, Any]) -> dict[str, Any]:
    """把一条汇总行补齐亩均指标。面积异常时亩均给 None，而不是让查询报除零。"""
    area = float(row["area_mu"])
    total_cost = float(row["total_cost"])
    total_yield = float(row["total_yield_kg"])
    total_revenue = float(row["total_revenue"])
    return {
        "season_id": row["season_id"],
        "plot_id": row["plot_id"],
        "plot_name": row["plot_name"],
        "crop": row["crop"],
        "started_on": row["started_on"],
        "ended_on": row["ended_on"],
        "area_mu": area,
        "record_count": int(row["record_count"]),
        "total_cost": round(total_cost, 2),
        "total_yield_kg": round(total_yield, 2),
        "total_revenue": round(total_revenue, 2),
        "net_revenue": round(total_revenue - total_cost, 2),
        "cost_per_mu": round(total_cost / area, 2) if area > 0 else None,
        "yield_per_mu": round(total_yield / area, 2) if area > 0 else None,
        "revenue_per_mu": round(total_revenue / area, 2) if area > 0 else None,
        "net_per_mu": round((total_revenue - total_cost) / area, 2) if area > 0 else None,
    }


def summarize_farm_economics(user_id: str) -> list[dict[str, Any]]:
    """按茬次汇总投入与产出，未归茬的记录单独成行。

    升级前是按地块汇总的；有了茬次就按茬次算——否则种第二茬之后，上一茬的
    化肥钱会和这一茬的收成混在一起。season_id 为空的记录（建茬之前记的、
    或地块没有进行中茬次时记的）归到「未归茬」，不丢数据。
    """
    with get_connection() as conn:
        season_rows = conn.execute(
            """
            SELECT
                s.id AS season_id,
                s.crop AS crop,
                s.started_on AS started_on,
                s.ended_on AS ended_on,
                p.id AS plot_id,
                p.name AS plot_name,
                p.area_mu AS area_mu,
                COUNT(r.id) AS record_count,
                COALESCE(SUM(r.cost), 0) AS total_cost,
                COALESCE(SUM(r.yield_kg), 0) AS total_yield_kg,
                COALESCE(SUM(r.yield_kg * r.unit_price), 0) AS total_revenue
            FROM plot_seasons s
            JOIN plots p ON p.id = s.plot_id
            LEFT JOIN farm_records r ON r.season_id = s.id
            WHERE s.user_id = ?
            GROUP BY s.id, s.crop, s.started_on, s.ended_on, p.id, p.name, p.area_mu
            ORDER BY s.started_on DESC, s.id DESC
            """,
            (user_id,),
        ).fetchall()
        unassigned_rows = conn.execute(
            """
            SELECT
                NULL AS season_id,
                '' AS crop,
                NULL AS started_on,
                NULL AS ended_on,
                p.id AS plot_id,
                p.name AS plot_name,
                p.area_mu AS area_mu,
                COUNT(r.id) AS record_count,
                COALESCE(SUM(r.cost), 0) AS total_cost,
                COALESCE(SUM(r.yield_kg), 0) AS total_yield_kg,
                COALESCE(SUM(r.yield_kg * r.unit_price), 0) AS total_revenue
            FROM farm_records r
            JOIN plots p ON p.id = r.plot_id
            WHERE r.user_id = ? AND r.season_id IS NULL
            GROUP BY p.id, p.name, p.area_mu
            ORDER BY p.name ASC
            """,
            (user_id,),
        ).fetchall()

    return [_economics_row(dict(row)) for row in list(season_rows) + list(unassigned_rows)]


