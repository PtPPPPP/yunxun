"""两类业务对象的回收站；地块子项继承父项可见性，不复制历史快照。"""
import hashlib
import json
import sqlite3

from backend.app.core.database import get_connection
from backend.app.core.errors import conflict, not_found
from backend.app.repositories import now_utc


def _owned(conn, table, entity_id, user_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (entity_id,)).fetchone()
    if not row or (user_id is not None and row["user_id"] != user_id):
        raise not_found("资料不存在或已最终删除。")
    return row


def _impact(conn, plot):
    rows = {}
    for table, fields in (("plot_seasons", "id,updated_at"), ("farm_records", "id,deleted_at"), ("farm_tasks", "id,done_at")):
        rows[table] = conn.execute(f"SELECT {fields} FROM {table} WHERE plot_id=? AND user_id=? ORDER BY id", (plot["id"], plot["user_id"])).fetchall()
    revision = hashlib.sha256(json.dumps([plot["id"], plot["deleted_at"], plot["updated_at"],
        *[[tuple(row) for row in rows[table]] for table in rows]], ensure_ascii=True).encode()).hexdigest()
    return {"season_count": len(rows["plot_seasons"]), "record_count": len(rows["farm_records"]),
        "trashed_record_count": sum(row["deleted_at"] is not None for row in rows["farm_records"]),
        "task_count": len(rows["farm_tasks"]), "open_task_count": sum(row["done_at"] is None for row in rows["farm_tasks"]),
        "revision": revision}


def _check_revision(expected, actual):
    if expected != actual:
        raise conflict("资料或关联数量已变化，请刷新后重新核对删除范围。")


def _record_revision(record):
    return hashlib.sha256(f"{record['id']}:{record['deleted_at']}".encode()).hexdigest()


def _check_plot_links(conn, plot):
    for table in ("plot_seasons", "farm_records", "farm_tasks"):
        if conn.execute(f"SELECT 1 FROM {table} WHERE plot_id=? AND user_id<>? LIMIT 1", (plot["id"], plot["user_id"])).fetchone():
            raise conflict("地块关联资料的归属异常，未修改数据，请联系部署者核对。")
    if conn.execute("""SELECT 1 FROM farm_records r JOIN plot_seasons s ON s.id=r.season_id
        WHERE s.plot_id=? AND (r.plot_id<>s.plot_id OR r.user_id<>s.user_id) LIMIT 1""", (plot["id"],)).fetchone():
        raise conflict("茬次存在范围外的台账关联，未修改数据，请联系部署者核对。")


def plot_delete_impact(plot_id: str, user_id: str) -> dict:
    with get_connection() as conn:
        conn.execute("BEGIN")
        plot = _owned(conn, "plots", plot_id, user_id)
        if plot["deleted_at"] is not None:
            raise not_found("地块已在回收站，请到回收站查看。")
        return _impact(conn, plot)


def trash_plot(plot_id: str, user_id: str | None, expected_revision: str | None = None) -> dict:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        plot = _owned(conn, "plots", plot_id, user_id)
        if plot["deleted_at"] is not None:
            raise not_found("地块已移入回收站。")
        _check_plot_links(conn, plot)
        impact = _impact(conn, plot)
        if expected_revision is not None:
            _check_revision(expected_revision, impact["revision"])
        conn.execute("UPDATE plots SET deleted_at=? WHERE id=?", (now_utc().isoformat(timespec="microseconds"), plot_id))
    return impact


def trash_record(record_id: str, user_id: str | None) -> None:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        record = _owned(conn, "farm_records", record_id, user_id)
        plot = _owned(conn, "plots", record["plot_id"], record["user_id"])
        if record["deleted_at"] is not None or plot["deleted_at"] is not None:
            raise not_found("台账或所属地块已移入回收站。")
        conn.execute("UPDATE farm_records SET deleted_at=? WHERE id=?", (now_utc().isoformat(timespec="microseconds"), record_id))


def list_trash(user_id: str) -> dict:
    with get_connection() as conn:
        conn.execute("BEGIN")
        plots = conn.execute("SELECT * FROM plots WHERE user_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC,id DESC", (user_id,)).fetchall()
        records = conn.execute("""SELECT r.*,p.name AS plot_name,p.deleted_at AS parent_deleted_at
            FROM farm_records r JOIN plots p ON p.id=r.plot_id AND p.user_id=r.user_id
            WHERE r.user_id=? AND r.deleted_at IS NOT NULL ORDER BY r.deleted_at DESC,r.id DESC""", (user_id,)).fetchall()
        return {"plots": [{"id": row["id"], "name": row["name"], "is_demo": bool(row["is_demo"]), "deleted_at": row["deleted_at"], **_impact(conn, row)} for row in plots],
            "records": [{key: row[key] for key in ("id", "plot_id", "plot_name", "kind", "happened_on", "deleted_at", "parent_deleted_at")}
                        | {"is_demo": bool(row["is_demo"]), "revision": _record_revision(row)} for row in records],
            "retention": "保留至你主动最终删除；当前没有自动清理。"}


def restore_plot(plot_id: str, user_id: str) -> bool:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        plot = _owned(conn, "plots", plot_id, user_id)
        if plot["deleted_at"] is None:
            return False
        _check_plot_links(conn, plot)
        if conn.execute("""SELECT 1 FROM farm_records r WHERE r.plot_id=? AND r.deleted_at IS NULL AND r.season_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM plot_seasons s WHERE s.id=r.season_id AND s.plot_id=r.plot_id AND s.user_id=r.user_id) LIMIT 1""", (plot_id,)).fetchone():
            raise conflict("台账茬次关联异常，未恢复数据，请联系部署者核对。")
        active = conn.execute("SELECT COUNT(*) FROM plot_seasons WHERE plot_id=? AND ended_on IS NULL", (plot_id,)).fetchone()[0]
        if active > 1:
            raise conflict("检测到多个进行中茬次，未恢复或覆盖数据；请联系部署者核对后再试。")
        try:
            conn.execute("UPDATE plots SET deleted_at=NULL WHERE id=?", (plot_id,))
        except sqlite3.IntegrityError as exc:
            raise conflict("恢复遇到数据约束冲突，未覆盖现有资料，请核对后重试。") from exc
    return True


def restore_record(record_id: str, user_id: str) -> bool:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        record = _owned(conn, "farm_records", record_id, user_id)
        plot = _owned(conn, "plots", record["plot_id"], user_id)
        if plot["deleted_at"] is not None:
            raise conflict("请先恢复所属地块，再恢复这条单独删除的台账。")
        if record["deleted_at"] is None:
            return False
        if record["season_id"]:
            season = conn.execute("SELECT * FROM plot_seasons WHERE id=? AND plot_id=? AND user_id=?", (record["season_id"], record["plot_id"], user_id)).fetchone()
            if not season:
                raise conflict("所属茬次关联已变化，未恢复台账，请先核对茬次资料。")
            if ((season["started_on"] and record["happened_on"] < season["started_on"])
                    or (season["ended_on"] and record["happened_on"] > season["ended_on"])):
                raise conflict("作业日期与茬次当前起止日期不符，未恢复；请先核对茬次日期。")
        conn.execute("UPDATE farm_records SET deleted_at=NULL WHERE id=?", (record_id,))
    return True


def purge_plot(plot_id: str, user_id: str, expected_revision: str) -> dict:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        plot = _owned(conn, "plots", plot_id, user_id)
        if plot["deleted_at"] is None:
            raise conflict("只能最终删除回收站中的地块，请刷新后核对。")
        _check_plot_links(conn, plot)
        impact = _impact(conn, plot)
        _check_revision(expected_revision, impact["revision"])
        for table in ("farm_records", "farm_tasks", "plot_seasons"):
            conn.execute(f"DELETE FROM {table} WHERE plot_id=? AND user_id=?", (plot_id, user_id))
        conn.execute("DELETE FROM plots WHERE id=? AND user_id=?", (plot_id, user_id))
    return impact


def purge_record(record_id: str, user_id: str, expected_revision: str) -> None:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        record = _owned(conn, "farm_records", record_id, user_id)
        if record["deleted_at"] is None:
            raise conflict("只能最终删除单独移入回收站的台账。")
        _check_revision(expected_revision, _record_revision(record))
        conn.execute("DELETE FROM farm_records WHERE id=? AND user_id=?", (record_id, user_id))
