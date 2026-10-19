import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.app.core.database import get_connection
from backend.app.core.errors import AppError, ErrorCode, conflict, not_found


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
        "is_guest": bool(record.get("is_guest", False)),
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


def create_user(username: str, password_hash: str, display_name: str, *, is_guest: bool = False) -> dict[str, Any]:
    user_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, display_name, created_at, updated_at, is_guest)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, display_name, timestamp, timestamp, int(is_guest)),
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


def upgrade_guest_account(
    user_id: str, username: str, password_hash: str, display_name: str,
    token_hash: str, expires_at: str,
) -> dict[str, Any]:
    """原地升级及会话替换必须一起提交；不复制或修改业务实体。"""
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT is_guest FROM users WHERE id=?", (user_id,)).fetchone()
        if not current:
            raise not_found("账号不存在。")
        if not current["is_guest"]:
            raise AppError(code=ErrorCode.GUEST_ALREADY_UPGRADED, message="账号已经保存，不能重复升级。请使用正式账号登录。", status_code=409)
        try:
            conn.execute("""UPDATE users SET username=?, password_hash=?, display_name=?, is_guest=0, updated_at=?
                WHERE id=? AND is_guest=1""", (username, password_hash, display_name, timestamp, user_id))
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and "users.username" in str(exc):
                raise conflict("用户名已存在，请换一个用户名。") from exc
            raise
        conn.execute("DELETE FROM auth_tokens WHERE user_id=?", (user_id,))
        conn.execute("INSERT INTO auth_tokens (token_hash,user_id,expires_at,created_at) VALUES (?,?,?,?)",
                     (token_hash, user_id, expires_at, timestamp))
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row)


def create_auth_token(user_id: str, token_hash: str, expires_at: str, *, expected_password_hash: str | None = None) -> None:
    with get_connection() as conn:
        if expected_password_hash is not None:
            # 登录校验与插入之间可能发生改密；写锁下复核，防止撤销后补发旧凭据会话。
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or row["password_hash"] != expected_password_hash:
                from fastapi import HTTPException
                raise HTTPException(401, "登录状态已变化，请使用最新密码重新登录。")
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
        "is_demo": bool(record.get("is_demo", False)),
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
    return _fetchone("SELECT * FROM plots WHERE id = ? AND deleted_at IS NULL", (plot_id,))


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
                    SELECT COUNT(*) FROM farm_records r WHERE r.plot_id = p.id AND r.user_id=p.user_id AND r.deleted_at IS NULL
                ) AS record_count,
                (
                    SELECT COUNT(*) FROM farm_records r WHERE r.season_id = s.id AND r.user_id=p.user_id AND r.deleted_at IS NULL
                ) AS season_record_count,
                (
                    SELECT COUNT(*) FROM farm_tasks t WHERE t.plot_id = p.id AND t.user_id=p.user_id AND t.done_at IS NULL
                ) AS open_task_count
            FROM plots p
            LEFT JOIN plot_seasons s ON s.id = (
                SELECT s2.id FROM plot_seasons s2 WHERE s2.plot_id = p.id AND s2.user_id=p.user_id
                ORDER BY (s2.ended_on IS NULL) DESC, s2.started_on DESC, s2.id DESC LIMIT 1
            )
            WHERE p.user_id = ? AND p.deleted_at IS NULL
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
        row = conn.execute("SELECT COUNT(*) AS total FROM plots WHERE user_id = ? AND deleted_at IS NULL", (user_id,)).fetchone()
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
            WHERE id = ? AND deleted_at IS NULL
            """,
            (name, area_mu, soil_type, irrigation, notes, updated_at, plot_id),
        )
        row = conn.execute("SELECT * FROM plots WHERE id = ? AND deleted_at IS NULL", (plot_id,)).fetchone()
    if row is None:
        raise not_found("地块不存在或已移入回收站。")
    return public_plot(dict(row))


def delete_plot_with_records(plot_id: str, user_id: str | None = None, expected_revision: str | None = None) -> tuple[int, int]:
    from backend.app.repositories_trash import trash_plot
    impact = trash_plot(plot_id, user_id, expected_revision)
    return impact["record_count"], impact["task_count"]


# 待办查询统一带出地块名称，杂事可以不挂地块。
FARM_TASK_SELECT = """
    SELECT t.*, COALESCE(p.name, '') AS plot_name
    FROM farm_tasks t
    LEFT JOIN plots p ON p.id = t.plot_id AND p.user_id=t.user_id
"""


def public_farm_task(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_demo": bool(record.get("is_demo", False)),
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
        conn.execute("BEGIN IMMEDIATE")
        _validate_farm_links(conn, user_id, plot_id)
        conn.execute(
            """
            INSERT INTO farm_tasks (id, user_id, plot_id, title, due_on, done_at, notes, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (task_id, user_id, plot_id, title, due_on, notes, created_at),
        )
        row = conn.execute(FARM_TASK_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()
    return public_farm_task(dict(row))


TASK_VISIBLE = "(t.plot_id IS NULL OR EXISTS (SELECT 1 FROM plots p WHERE p.id=t.plot_id AND p.user_id=t.user_id AND p.deleted_at IS NULL))"


def get_farm_task(task_id: str) -> dict[str, Any] | None:
    return _fetchone(FARM_TASK_SELECT + " WHERE t.id = ? AND " + TASK_VISIBLE, (task_id,))


def list_open_farm_tasks(user_id: str) -> list[dict[str, Any]]:
    """未完成待办，按到期日升序；同一到期日再按创建时间保证顺序稳定。"""
    with get_connection() as conn:
        rows = conn.execute(
            FARM_TASK_SELECT + " WHERE t.user_id = ? AND " + TASK_VISIBLE + " AND t.done_at IS NULL ORDER BY t.due_on ASC, t.id ASC",
            (user_id,),
        ).fetchall()
    return [public_farm_task(dict(row)) for row in rows]


def list_recent_done_farm_tasks(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            FARM_TASK_SELECT + " WHERE t.user_id = ? AND " + TASK_VISIBLE + " AND t.done_at IS NOT NULL ORDER BY t.done_at DESC LIMIT ?",
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
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(FARM_TASK_SELECT + " WHERE t.id = ? AND " + TASK_VISIBLE, (task_id,)).fetchone()
        if current is None:
            raise not_found("待办事项不存在或已被删除。")
        _validate_farm_links(conn, current["user_id"], plot_id)
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
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute(FARM_TASK_SELECT + " WHERE t.id=? AND " + TASK_VISIBLE, (task_id,)).fetchone():
            raise not_found("待办不存在或所属地块已移入回收站。")
        conn.execute("DELETE FROM farm_tasks WHERE id = ?", (task_id,))


def public_season(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_demo": bool(record.get("is_demo", False)),
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
        conn.execute("BEGIN IMMEDIATE")
        _validate_farm_links(conn, user_id, plot_id)
        try:
            conn.execute(
                """
                INSERT INTO plot_seasons
                    (id, user_id, plot_id, crop, started_on, ended_on, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (season_id, user_id, plot_id, crop, started_on, notes, timestamp, timestamp),
            )
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and "plot_seasons.plot_id" in str(exc):
                raise conflict("该地块已有进行中的茬次，请刷新后重试。") from exc
            raise
        row = conn.execute("SELECT * FROM plot_seasons WHERE id = ?", (season_id,)).fetchone()
    return public_season(dict(row))


def get_season(season_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM plot_seasons WHERE id = ? AND EXISTS (SELECT 1 FROM plots p WHERE p.id=plot_seasons.plot_id AND p.user_id=plot_seasons.user_id AND p.deleted_at IS NULL)", (season_id,))


def get_active_season(plot_id: str) -> dict[str, Any] | None:
    """地块进行中的那一茬；部分唯一索引保证最多只有一条。"""
    return _fetchone(
        "SELECT * FROM plot_seasons WHERE plot_id = ? AND ended_on IS NULL AND EXISTS (SELECT 1 FROM plots p WHERE p.id=plot_seasons.plot_id AND p.user_id=plot_seasons.user_id AND p.deleted_at IS NULL)",
        (plot_id,),
    )


def list_seasons(user_id: str, *, plot_id: str | None = None) -> list[dict[str, Any]]:
    conditions = ["user_id = ?", "EXISTS (SELECT 1 FROM plots p WHERE p.id=plot_seasons.plot_id AND p.user_id=plot_seasons.user_id AND p.deleted_at IS NULL)"]
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
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM plot_seasons WHERE id=?", (season_id,)).fetchone()
        if not current:
            raise not_found("茬次不存在。")
        _validate_farm_links(conn, current["user_id"], current["plot_id"])
        try:
            conn.execute(
                """
                UPDATE plot_seasons
                SET crop = ?, started_on = ?, ended_on = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (crop, started_on, ended_on, notes, updated_at, season_id),
            )
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and "plot_seasons.plot_id" in str(exc):
                raise conflict("该地块已有进行中的茬次，请刷新后重试。") from exc
            raise
        row = conn.execute("SELECT * FROM plot_seasons WHERE id = ?", (season_id,)).fetchone()
    return public_season(dict(row))


def delete_season(season_id: str) -> None:
    """删掉一茬。它的作业记录变回「未归茬」，不连带删除。"""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM plot_seasons WHERE id=?", (season_id,)).fetchone()
        if not current:
            raise not_found("茬次不存在。")
        _validate_farm_links(conn, current["user_id"], current["plot_id"])
        if conn.execute("SELECT 1 FROM farm_records WHERE season_id=? AND deleted_at IS NOT NULL LIMIT 1", (season_id,)).fetchone():
            raise conflict("该茬次关联回收站台账，请先恢复或最终删除这些台账。")
        conn.execute("UPDATE farm_records SET season_id = NULL WHERE season_id = ?", (season_id,))
        conn.execute("DELETE FROM plot_seasons WHERE id = ?", (season_id,))


# 台账查询统一带出地块名称与茬次作物，接口因此自解释。
FARM_RECORD_SELECT = """
    SELECT r.*, COALESCE(p.name, '') AS plot_name, COALESCE(s.crop, '') AS season_crop
    FROM farm_records r
    LEFT JOIN plots p ON p.id = r.plot_id AND p.user_id=r.user_id
    LEFT JOIN plot_seasons s ON s.id = r.season_id AND s.plot_id=r.plot_id AND s.user_id=r.user_id
"""


def public_farm_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_cost = record["cost"]
    raw_yield = record["yield_kg"]
    raw_price = record["unit_price"]
    raw_safe_days = record["safe_days"]
    return {
        "is_demo": bool(record.get("is_demo", False)),
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
        "earliest_harvest_on": add_days(record["happened_on"], int(raw_safe_days))
        if record["kind"] == "打药" and raw_safe_days is not None else None,
        "yield_kg": None if raw_yield is None else float(raw_yield),
        "unit_price": None if raw_price is None else float(raw_price),
        "created_at": record["created_at"],
    }


def _validate_farm_links(conn: sqlite3.Connection, user_id: str, plot_id: str | None, season_id: str | None = None) -> None:
    """持有写锁后再核对引用，防止清空演示与保存交错产生已失效的茬次引用。"""
    if plot_id and not conn.execute("SELECT 1 FROM plots WHERE id=? AND user_id=? AND deleted_at IS NULL", (plot_id, user_id)).fetchone():
        raise conflict("关联地块已变化，请刷新后重新选择。")
    if season_id and not conn.execute("SELECT 1 FROM plot_seasons WHERE id=? AND plot_id=? AND user_id=?", (season_id, plot_id, user_id)).fetchone():
        raise conflict("关联茬次已变化，请刷新后重新选择。")


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
    record_id: str | None = None,
) -> dict[str, Any]:
    record_id = record_id or uuid.uuid4().hex
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _validate_farm_links(conn, user_id, plot_id, season_id)
        conn.execute(
            """
            INSERT INTO farm_records
                (id, user_id, plot_id, kind, happened_on, crop, material, detail, quantity,
                 cost, safe_days, yield_kg, unit_price, season_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                record_id, user_id, plot_id, kind, happened_on, crop, material, detail, quantity,
                cost, safe_days, yield_kg, unit_price, season_id, created_at,
            ),
        )
        row = conn.execute(FARM_RECORD_SELECT + " WHERE r.id = ?", (record_id,)).fetchone()
        if row["deleted_at"] is not None:
            raise conflict("该次提交的台账已在回收站，请恢复已有台账，不要重复记账。")
        expected = dict(user_id=user_id, plot_id=plot_id, season_id=season_id, kind=kind,
                        happened_on=happened_on, crop=crop, detail=detail, quantity=quantity,
                        cost=cost, material=material, safe_days=safe_days, yield_kg=yield_kg, unit_price=unit_price)
        if any(row[key] != value for key, value in expected.items()):
            raise conflict("该次提交已保存且内容不同，请刷新台账后编辑已有记录。")
    return public_farm_record(dict(row))


RECORD_VISIBLE = "r.deleted_at IS NULL AND EXISTS (SELECT 1 FROM plots p WHERE p.id=r.plot_id AND p.user_id=r.user_id AND p.deleted_at IS NULL)"


def get_farm_record(record_id: str) -> dict[str, Any] | None:
    return _fetchone(FARM_RECORD_SELECT + " WHERE r.id = ? AND " + RECORD_VISIBLE, (record_id,))


def update_farm_record(record_id: str, user_id: str, **values: Any) -> dict[str, Any]:
    """一次更新全部业务字段，保留记录 ID、用户和创建时间。"""
    columns = ("plot_id", "season_id", "kind", "happened_on", "crop", "detail", "quantity",
               "cost", "material", "safe_days", "yield_kg", "unit_price")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _validate_farm_links(conn, user_id, values["plot_id"], values["season_id"])
        try:
            result = conn.execute(
                "UPDATE farm_records SET " + ", ".join(f"{column} = ?" for column in columns)
                + " WHERE id = ? AND user_id = ? AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM plots p WHERE p.id=farm_records.plot_id AND p.deleted_at IS NULL)",
                tuple(values[column] for column in columns) + (record_id, user_id),
            )
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY:
                raise conflict("关联地块或茬次已变化，请刷新后重新选择。") from exc
            raise
        if result.rowcount == 0:
            raise not_found("农事记录不存在或已被删除。")
        row = conn.execute(FARM_RECORD_SELECT + " WHERE r.id = ?", (record_id,)).fetchone()
    return public_farm_record(dict(row))


ECONOMICS_SCOPES = {
    "all": "",
    "cost": "r.cost IS NOT NULL",
    "revenue": "r.kind = '采收' AND r.yield_kg IS NOT NULL AND r.unit_price IS NOT NULL",
    "missing_cost": "r.cost IS NULL",
    "incomplete_harvest": "r.kind = '采收' AND (r.yield_kg IS NULL OR r.unit_price IS NULL)",
}


def _farm_record_conditions(
    user_id: str, *, plot_id: str | None = None, season_id: str | None = None,
    kind: str | None = None, date_from: str | None = None, date_to: str | None = None,
    year: int | None = None, economics_scope: str = "all", data_scope: str = "all",
) -> tuple[list[str], list[Any]]:
    """统计与追溯台账共用同一组筛选条件；年度按作业日期划分。"""
    conditions = ["r.user_id = ?", RECORD_VISIBLE]
    params: list[Any] = [user_id]
    if data_scope != "all":
        conditions.append("r.is_demo = ?")
        params.append(int(data_scope == "demo"))
    for column, operator, value in (("plot_id", "=", plot_id), ("kind", "=", kind),
                                    ("happened_on", ">=", date_from), ("happened_on", "<=", date_to)):
        if value:
            conditions.append(f"r.{column} {operator} ?")
            params.append(value)
    if season_id == "unassigned":
        conditions.append("r.season_id IS NULL")
    elif season_id:
        conditions.append("r.season_id = ?")
        params.append(season_id)
    if year is not None:
        conditions.append("r.happened_on BETWEEN ? AND ?")
        params.extend([f"{year:04d}-01-01", f"{year:04d}-12-31"])
    scope_condition = ECONOMICS_SCOPES[economics_scope]
    if scope_condition:
        conditions.append(f"({scope_condition})")
    return conditions, params


def list_farm_records_page(
    user_id: str,
    *,
    plot_id: str | None = None,
    limit: int = 20,
    cursor: tuple[str, str] | None = None,
    kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    season_id: str | None = None,
    economics_scope: str = "all",
    year: int | None = None,
    data_scope: str = "all",
) -> tuple[list[dict[str, Any]], bool]:
    """按作业日期倒序翻页；游标复用 (happened_on, id)。"""
    conditions, params = _farm_record_conditions(
        user_id, plot_id=plot_id, kind=kind, date_from=date_from, date_to=date_to,
        season_id=season_id, economics_scope=economics_scope, year=year, data_scope=data_scope,
    )
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


def delete_farm_record(record_id: str, user_id: str | None = None) -> None:
    from backend.app.repositories_trash import trash_record
    trash_record(record_id, user_id)


def export_farm_records(user_id: str, **filters: Any) -> list[dict[str, Any]]:
    """单次读取全部匹配数据，不带分页；关联信息也必须属于本人及该地块。"""
    conditions, params = _farm_record_conditions(user_id, **filters)
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.*, p.name AS plot_name, s.crop AS season_crop,
                   s.started_on AS season_started_on, s.ended_on AS season_ended_on
            FROM farm_records r
            JOIN plots p ON p.id=r.plot_id AND p.user_id=r.user_id
            LEFT JOIN plot_seasons s ON s.id=r.season_id AND s.plot_id=r.plot_id AND s.user_id=r.user_id
            WHERE """ + " AND ".join(conditions) + " ORDER BY r.happened_on DESC, r.id DESC", tuple(params)).fetchall()
    return [dict(row) for row in rows]


def count_farm_records(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM farm_records r WHERE r.user_id = ? AND " + RECORD_VISIBLE, (user_id,)).fetchone()
    return int(row["total"]) if row else 0


def list_harvest_safety(user_id: str, *, reference_date: str) -> list[dict[str, Any]]:
    """按地块汇总截至查询日已登记的间隔期，取约束最晚的一条。

    提醒保守覆盖同一地块的全部茬次和作物，换茬或改作物不会解除尚未到期的
    提醒；未归茬记录也参与。这里只计算用户填入的天数，不判断标签合规性。
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
                        PARTITION BY r.plot_id
                        ORDER BY date(r.happened_on, '+' || r.safe_days || ' days') DESC,
                                 r.happened_on DESC, r.id DESC
                    ) AS row_number
                FROM farm_records r
                JOIN plots p ON p.id = r.plot_id
                WHERE r.user_id = ? AND r.deleted_at IS NULL AND p.deleted_at IS NULL AND p.user_id=r.user_id AND r.kind = '打药' AND r.safe_days IS NOT NULL
                    AND r.happened_on <= ?
            )
            WHERE row_number = 1
            ORDER BY happened_on DESC
            """,
            (user_id, reference_date),
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
                # 剩余天数 > 0 表示用户登记的间隔期尚未结束。
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
        "is_demo": bool(row.get("is_demo", False)),
        "season_id": row["season_id"],
        "plot_id": row["plot_id"],
        "plot_name": row["plot_name"],
        "crop": row["crop"],
        "started_on": row["started_on"],
        "ended_on": row["ended_on"],
        "area_mu": area,
        "record_count": int(row["record_count"]),
        **{name: int(row[name]) for name in (
            "recorded_cost_count", "missing_cost_count", "harvest_count", "complete_harvest_count",
            "incomplete_harvest_count", "recorded_yield_count",
        )},
        "total_cost": round(total_cost, 2),
        "total_yield_kg": round(total_yield, 2),
        "total_revenue": round(total_revenue, 2),
        "net_revenue": round(total_revenue - total_cost, 2),
        "cost_per_mu": round(total_cost / area, 2) if area > 0 else None,
        "yield_per_mu": round(total_yield / area, 2) if area > 0 else None,
        "revenue_per_mu": round(total_revenue / area, 2) if area > 0 else None,
        "net_per_mu": round((total_revenue - total_cost) / area, 2) if area > 0 else None,
    }


def summarize_farm_economics(
    user_id: str, *, plot_id: str | None = None, season_id: str | None = None, year: int | None = None, data_scope: str = "all",
) -> list[dict[str, Any]]:
    """按茬次汇总投入与产出，未归茬的记录单独成行。

    升级前是按地块汇总的；有了茬次就按茬次算——否则种第二茬之后，上一茬的
    化肥钱会和这一茬的收成混在一起。明确未归茬或无法确定归属的记录单独
    分组，不丢数据。年度仅按作业日期过滤，金额字段保持数字并由完整度计数
    表达缺失，页面据此区分待补录与有效零值。
    """
    conditions, params = _farm_record_conditions(user_id, plot_id=plot_id, season_id=season_id, year=year, data_scope=data_scope)
    cte = "WITH filtered_records AS (SELECT r.* FROM farm_records r WHERE " + " AND ".join(conditions) + ") "
    season_conditions = ["s.user_id = ?", "p.deleted_at IS NULL"]
    season_params: list[Any] = [user_id]
    if plot_id:
        season_conditions.append("s.plot_id = ?")
        season_params.append(plot_id)
    if season_id == "unassigned":
        season_conditions.append("0 = 1")
    elif season_id:
        season_conditions.append("s.id = ?")
        season_params.append(season_id)
    if data_scope != "all":
        # 真实台账可能新增在演示茬次下；按记录来源筛金额，不能因此漏掉它。
        season_conditions.append("(s.is_demo = ? OR EXISTS (SELECT 1 FROM filtered_records f WHERE f.season_id = s.id AND f.plot_id = s.plot_id))")
        season_params.append(int(data_scope == "demo"))
    # LEFT JOIN 的空行不计入缺失数。0 是有效填写值，只有 NULL 才是未填。
    quality_columns = """
        COUNT(r.cost) AS recorded_cost_count,
        SUM(CASE WHEN r.id IS NOT NULL AND r.cost IS NULL THEN 1 ELSE 0 END) AS missing_cost_count,
        SUM(CASE WHEN r.kind = '采收' THEN 1 ELSE 0 END) AS harvest_count,
        SUM(CASE WHEN r.kind = '采收' AND r.yield_kg IS NOT NULL AND r.unit_price IS NOT NULL THEN 1 ELSE 0 END) AS complete_harvest_count,
        SUM(CASE WHEN r.kind = '采收' AND (r.yield_kg IS NULL OR r.unit_price IS NULL) THEN 1 ELSE 0 END) AS incomplete_harvest_count,
        SUM(CASE WHEN r.kind = '采收' AND r.yield_kg IS NOT NULL THEN 1 ELSE 0 END) AS recorded_yield_count,
    """
    with get_connection() as conn:
        conn.execute("BEGIN")
        season_rows = conn.execute(
            cte + """
            SELECT
                s.id AS season_id,
                s.is_demo AS is_demo,
                s.crop AS crop,
                s.started_on AS started_on,
                s.ended_on AS ended_on,
                p.id AS plot_id,
                p.name AS plot_name,
                p.area_mu AS area_mu,
                """ + quality_columns + """ COUNT(r.id) AS record_count,
                COALESCE(SUM(r.cost), 0) AS total_cost,
                COALESCE(SUM(CASE WHEN r.kind = '采收' THEN r.yield_kg END), 0) AS total_yield_kg,
                COALESCE(SUM(CASE WHEN r.kind = '采收' THEN r.yield_kg * r.unit_price END), 0) AS total_revenue
            FROM plot_seasons s
            JOIN plots p ON p.id = s.plot_id AND p.user_id = s.user_id
            LEFT JOIN filtered_records r ON r.season_id = s.id AND r.plot_id = p.id
            WHERE """ + " AND ".join(season_conditions) + """
            GROUP BY s.id, s.crop, s.started_on, s.ended_on, p.id, p.name, p.area_mu
            """ + (" HAVING COUNT(r.id) > 0 " if year is not None and not season_id else "")
            + " ORDER BY s.started_on DESC, s.id DESC",
            tuple(params + season_params),
        ).fetchall()
        unassigned_rows = conn.execute(
            cte + """
            SELECT
                NULL AS season_id,
                p.is_demo AS is_demo,
                '' AS crop,
                NULL AS started_on,
                NULL AS ended_on,
                p.id AS plot_id,
                p.name AS plot_name,
                p.area_mu AS area_mu,
                """ + quality_columns + """ COUNT(r.id) AS record_count,
                COALESCE(SUM(r.cost), 0) AS total_cost,
                COALESCE(SUM(CASE WHEN r.kind = '采收' THEN r.yield_kg END), 0) AS total_yield_kg,
                COALESCE(SUM(CASE WHEN r.kind = '采收' THEN r.yield_kg * r.unit_price END), 0) AS total_revenue
            FROM filtered_records r
            JOIN plots p ON p.id = r.plot_id AND p.user_id = r.user_id
            WHERE r.season_id IS NULL
            GROUP BY p.id, p.name, p.area_mu
            ORDER BY p.name ASC
            """,
            tuple(params),
        ).fetchall()

    return [_economics_row(dict(row)) for row in list(season_rows) + list(unassigned_rows)]


def list_farm_record_years(user_id: str, data_scope: str = "all") -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT CAST(substr(happened_on, 1, 4) AS INTEGER) AS year "
            "FROM farm_records r WHERE user_id = ? AND " + RECORD_VISIBLE + " "
            + ("AND is_demo = ? " if data_scope != "all" else "") + "ORDER BY year DESC",
            (user_id, int(data_scope == "demo")) if data_scope != "all" else (user_id,),
        ).fetchall()
    return [row["year"] for row in rows if 1 <= row["year"] <= 9999]


