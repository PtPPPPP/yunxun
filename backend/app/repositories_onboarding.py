"""首次使用状态与演示数据；来源标识不可经普通业务写接口修改。"""
import uuid
from datetime import date, timedelta

from backend.app.core.database import get_connection
from fastapi import HTTPException

from backend.app.core.errors import conflict, not_found
from backend.app.repositories import now_iso


def onboarding_status(user_id: str) -> dict:
    with get_connection() as conn:
        conn.execute("BEGIN")
        user = conn.execute("SELECT onboarding_skipped FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise not_found("用户不存在。")
        plot = conn.execute("SELECT id FROM plots WHERE user_id = ? AND is_demo = 0 AND deleted_at IS NULL ORDER BY created_at, id LIMIT 1", (user_id,)).fetchone()
        season = conn.execute("""SELECT s.id FROM plot_seasons s JOIN plots p ON p.id = s.plot_id
            WHERE s.user_id = ? AND p.user_id = ? AND p.deleted_at IS NULL AND s.is_demo = 0 AND p.is_demo = 0 LIMIT 1""", (user_id, user_id)).fetchone()
        record = conn.execute("""SELECT r.id FROM farm_records r JOIN plots p ON p.id = r.plot_id
            WHERE r.user_id = ? AND p.user_id = ? AND p.deleted_at IS NULL AND r.deleted_at IS NULL AND r.is_demo = 0 AND p.is_demo = 0 LIMIT 1""", (user_id, user_id)).fetchone()
        state = conn.execute("SELECT loaded FROM demo_data_state WHERE user_id = ?", (user_id,)).fetchone()
        demo_count = conn.execute("SELECT COUNT(*) FROM plots WHERE user_id=? AND is_demo=1 AND deleted_at IS NULL", (user_id,)).fetchone()[0]
        for table in ("plot_seasons", "farm_records", "farm_tasks"):
            join = "LEFT JOIN" if table == "farm_tasks" else "JOIN"
            visible = "(x.plot_id IS NULL OR (p.id IS NOT NULL AND p.deleted_at IS NULL))" if table == "farm_tasks" else "p.deleted_at IS NULL"
            demo_count += conn.execute(f"SELECT COUNT(*) FROM {table} x {join} plots p ON p.id=x.plot_id AND p.user_id=x.user_id WHERE x.user_id=? AND x.is_demo=1 AND {visible}"
                + (" AND x.deleted_at IS NULL" if table == "farm_records" else ""), (user_id,)).fetchone()[0]
    return {"plot_done": plot is not None, "season_done": season is not None, "record_done": record is not None,
            "first_plot_id": plot["id"] if plot else None, "skipped": bool(user["onboarding_skipped"]),
            "demo_loaded": bool(state and state["loaded"]), "demo_count": demo_count}


def set_onboarding_skipped(user_id: str, skipped: bool) -> None:
    with get_connection() as conn:
        if conn.execute("UPDATE users SET onboarding_skipped = ? WHERE id = ?", (int(skipped), user_id)).rowcount == 0:
            raise not_found("用户不存在。")


def load_demo_data(user_id: str) -> bool:
    """返回是否已加载。写锁覆盖状态判断、种子创建与标记，失败全部回滚。"""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT is_guest FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or not user["is_guest"]:
            raise HTTPException(status_code=403, detail="仅访客可加载演示数据。")
        state = conn.execute("SELECT loaded FROM demo_data_state WHERE user_id = ?", (user_id,)).fetchone()
        if state and state["loaded"]:
            return True
        timestamp = now_iso()
        today = date.today()
        day = lambda offset: (today + timedelta(days=offset)).isoformat()
        plot_id, season_id = uuid.uuid4().hex, uuid.uuid4().hex
        note = "演示数据，仅用于了解功能，不代表实际经营成果。"
        conn.execute("""INSERT INTO plots
            (id,user_id,name,area_mu,soil_type,irrigation,notes,created_at,updated_at,is_demo)
            VALUES (?,?,?,2,'壤土','滴灌',?,?,?,1)""", (plot_id, user_id, "演示菜地", note, timestamp, timestamp))
        conn.execute("""INSERT INTO plot_seasons
            (id,user_id,plot_id,crop,started_on,notes,created_at,updated_at,is_demo)
            VALUES (?,?,?,'番茄',?,?,?,?,1)""", (season_id, user_id, plot_id, day(-100), note, timestamp, timestamp))
        for kind, offset, cost, quantity, yield_kg, price in (
            ("播种", -95, 120, "示例苗款", None, None),
            ("施肥", -60, 80, "示例肥料", None, None),
            ("采收", -1, 0, "", 300, 2),
        ):
            conn.execute("""INSERT INTO farm_records
                (id,user_id,plot_id,season_id,kind,happened_on,crop,detail,quantity,cost,yield_kg,unit_price,created_at,is_demo)
                VALUES (?,?,?,?,?,?,'番茄',?,?,?,?,?,?,1)""",
                (uuid.uuid4().hex, user_id, plot_id, season_id, kind, day(offset), note, quantity, cost, yield_kg, price, timestamp))
        for title, offset in (("演示·复查墒情", -1), ("演示·整理采收账目", 0)):
            conn.execute("""INSERT INTO farm_tasks (id,user_id,plot_id,title,due_on,notes,created_at,is_demo)
                VALUES (?,?,?,?,?,?,?,1)""", (uuid.uuid4().hex, user_id, plot_id, title, day(offset), note, timestamp))
        conn.execute("INSERT INTO demo_data_state (user_id,loaded) VALUES (?,1) ON CONFLICT(user_id) DO UPDATE SET loaded=1", (user_id,))
    return False


def clear_demo_data(user_id: str) -> dict:
    """先删演示叶子，保留并转普通所有被用户新增数据引用的演示祖先。"""
    removed, retained = {}, {}
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # 演示清理不能绕过回收站的恢复与最终删除确认。
        if conn.execute("SELECT 1 FROM farm_records WHERE user_id=? AND is_demo=1 AND deleted_at IS NOT NULL LIMIT 1", (user_id,)).fetchone():
            raise conflict("演示资料仍在回收站，请先恢复或最终删除，再清空演示数据。")
        if conn.execute("SELECT 1 FROM plots WHERE user_id=? AND is_demo=1 AND deleted_at IS NOT NULL LIMIT 1", (user_id,)).fetchone():
            raise conflict("演示地块仍在回收站，请先恢复或最终删除，再清空演示数据。")
        for table in ("plot_seasons", "farm_records", "farm_tasks"):
            if conn.execute(f"SELECT 1 FROM {table} x JOIN plots p ON p.id=x.plot_id WHERE x.user_id=? AND x.is_demo=1 AND p.deleted_at IS NOT NULL LIMIT 1", (user_id,)).fetchone():
                raise conflict("演示关联资料仍在回收站，请先处理回收站，再清空演示数据。")
        for table in ("farm_records", "farm_tasks"):
            removed[table] = conn.execute(f"DELETE FROM {table} WHERE user_id = ? AND is_demo = 1", (user_id,)).rowcount
        removed["plot_seasons"] = conn.execute("""DELETE FROM plot_seasons WHERE user_id = ? AND is_demo = 1
            AND NOT EXISTS (SELECT 1 FROM farm_records r WHERE r.season_id = plot_seasons.id)""", (user_id,)).rowcount
        retained["plot_seasons"] = conn.execute("UPDATE plot_seasons SET is_demo=0 WHERE user_id=? AND is_demo=1", (user_id,)).rowcount
        removed["plots"] = conn.execute("""DELETE FROM plots WHERE user_id = ? AND is_demo = 1
            AND NOT EXISTS (SELECT 1 FROM farm_records r WHERE r.plot_id = plots.id)
            AND NOT EXISTS (SELECT 1 FROM farm_tasks t WHERE t.plot_id = plots.id)
            AND NOT EXISTS (SELECT 1 FROM plot_seasons s WHERE s.plot_id = plots.id)""", (user_id,)).rowcount
        retained["plots"] = conn.execute("UPDATE plots SET is_demo=0 WHERE user_id=? AND is_demo=1", (user_id,)).rowcount
        conn.execute("UPDATE demo_data_state SET loaded=0 WHERE user_id=?", (user_id,))
    return {"removed": removed, "retained": retained}
