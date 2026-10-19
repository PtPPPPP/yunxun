"""凭据变更与会话撤销共用 SQLite 写事务；不修改用户 ID 或业务数据。"""
import secrets
import sqlite3

from fastapi import HTTPException

from backend.app.core.database import get_connection
from backend.app.core.security import hash_password, hash_recovery_code, verify_password
from backend.app.core.time import now_iso


INVALID_RECOVERY = "账号或恢复凭据无效，请核对后重试；无法恢复时请联系部署者。"


def replace_password_and_revoke_sessions(conn: sqlite3.Connection, user_id: str, password_hash: str) -> None:
    # 调用者必须持有 BEGIN IMMEDIATE；任一步失败会整体回滚。
    conn.execute("UPDATE users SET password_hash=?, recovery_code_hash=NULL, updated_at=? WHERE id=?",
                 (password_hash, now_iso(), user_id))
    conn.execute("DELETE FROM auth_tokens WHERE user_id=?", (user_id,))


def manage_credentials(user: dict, current_password: str, *, new_password: str | None = None) -> str | None:
    code = secrets.token_urlsafe(32) if new_password is None else None
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not current or current["is_guest"]:
            raise HTTPException(403, "请先将访客保存为正式账号，再管理密码。")
        # 拒绝认证后被其他请求改密的旧身份快照。
        if not secrets.compare_digest(current["password_hash"], user["password_hash"]) or not verify_password(current_password, current["password_hash"]):
            raise HTTPException(400, "原密码不正确，或登录状态已变化，请重新登录后重试。")
        if new_password is not None:
            if current_password == new_password:
                raise HTTPException(400, "新密码不能与原密码相同。")
            replace_password_and_revoke_sessions(conn, user["id"], hash_password(new_password))
        else:
            conn.execute("UPDATE users SET recovery_code_hash=?, updated_at=? WHERE id=?",
                         (hash_recovery_code(code), now_iso(), user["id"]))
    return code


def recover_password(username: str, recovery_code: str, new_password: str) -> str:
    digest = hash_recovery_code(recovery_code.strip())
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        expected = current["recovery_code_hash"] if current and current["recovery_code_hash"] else "0" * 64
        matches = secrets.compare_digest(digest, expected)
        if not matches or not current or current["is_guest"] or not current["recovery_code_hash"]:
            raise HTTPException(400, INVALID_RECOVERY)
        replace_password_and_revoke_sessions(conn, current["id"], hash_password(new_password))
        user_id = current["id"]
    return user_id
