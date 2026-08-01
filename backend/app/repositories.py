import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.core.database import get_connection


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def safe_text(value: str, fallback: str) -> str:
    text = value.strip()
    return text or fallback


def choose_model(model_name: str | None, available_models: list[str], fallback_endpoint: str) -> str:
    candidate = (model_name or "").strip()
    if candidate:
        return candidate
    if available_models:
        return available_models[0]
    return fallback_endpoint


def public_user(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "username": record["username"],
        "display_name": record["display_name"],
        "preferred_model": record["preferred_model"],
        "created_at": record["created_at"],
    }


def public_session(record: dict[str, Any], last_message: str = "") -> dict[str, Any]:
    return {
        "id": record["id"],
        "title": record["title"],
        "feature": record["feature"],
        "model_name": record["model_name"],
        "is_pinned": bool(record.get("is_pinned", 0)),
        "pinned_at": record.get("pinned_at"),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "last_message": last_message,
    }


def public_message(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "role": record["role"],
        "content": record["content"],
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


def create_user(username: str, password_hash: str, display_name: str, preferred_model: str) -> dict[str, Any]:
    user_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, display_name, preferred_model, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, display_name, preferred_model, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def update_user_profile(user_id: str, display_name: str, preferred_model: str) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET display_name = ?, preferred_model = ?, updated_at = ?
            WHERE id = ?
            """,
            (display_name, preferred_model, updated_at, user_id),
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


def create_session(
    user_id: str,
    title: str,
    feature: str,
    model_name: str,
) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_sessions
                (id, user_id, title, feature, model_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, title, feature, model_name, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row)


def get_session(session_id: str) -> dict[str, Any] | None:
    return _fetchone("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))


def list_sessions(user_id: str, feature: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.*,
                (
                    SELECT content
                    FROM chat_messages m
                    WHERE m.session_id = s.id
                    ORDER BY m.created_at DESC, m.id DESC
                    LIMIT 1
                ) AS last_message
            FROM chat_sessions s
            WHERE s.user_id = ? AND s.feature = ?
            ORDER BY s.is_pinned DESC, s.pinned_at DESC, s.updated_at DESC, s.id DESC
            """,
            (user_id, feature),
        ).fetchall()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        sessions.append(public_session(record, record.get("last_message") or ""))
    return sessions


def _session_list_query() -> str:
    return """
        SELECT
            s.*,
            (
                SELECT content
                FROM chat_messages m
                WHERE m.session_id = s.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) AS last_message
        FROM chat_sessions s
        WHERE s.user_id = ? AND s.feature = ?
        ORDER BY s.is_pinned DESC, s.pinned_at DESC, s.updated_at DESC, s.id DESC
    """


def list_sessions_page(user_id: str, feature: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
    """与 :func:`list_sessions` 相同的排序，但只取一页。"""
    with get_connection() as conn:
        rows = conn.execute(
            _session_list_query() + " LIMIT ? OFFSET ?",
            (user_id, feature, limit, offset),
        ).fetchall()
    return [public_session(dict(row), dict(row).get("last_message") or "") for row in rows]


def count_sessions(user_id: str, feature: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM chat_sessions WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        ).fetchone()
    return int(row["total"]) if row else 0


def count_all_sessions(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM chat_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row["total"]) if row else 0


def count_messages_for_user(user_id: str) -> int:
    """统计某用户的全部会话消息总数（跨功能）。"""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM chat_messages m
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE s.user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return int(row["total"]) if row else 0


def count_sessions_by_feature(user_id: str) -> dict[str, int]:
    """按功能维度统计该用户的会话数量。"""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT feature, COUNT(*) AS total
            FROM chat_sessions
            WHERE user_id = ?
            GROUP BY feature
            """,
            (user_id,),
        ).fetchall()
    return {str(row["feature"]): int(row["total"]) for row in rows}


def rename_session(session_id: str, title: str) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?", (title, updated_at, session_id))
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row)


def set_session_pinned(session_id: str, is_pinned: bool) -> dict[str, Any]:
    with get_connection() as conn:
        current = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if current is None:
            raise LookupError("chat session disappeared while changing pin state")
        if bool(current["is_pinned"]) == is_pinned:
            return dict(current)
        pinned_at = now_iso() if is_pinned else None
        updated_at = now_iso()
        conn.execute(
            "UPDATE chat_sessions SET is_pinned = ?, pinned_at = ?, updated_at = ? WHERE id = ?",
            (int(is_pinned), pinned_at, updated_at, session_id),
        )
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise LookupError("chat session disappeared while changing pin state")
    return dict(row)


def clear_session_messages(session_id: str) -> tuple[dict[str, Any], int]:
    updated_at = now_iso()
    with get_connection() as conn:
        session_row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if session_row is None:
            raise LookupError("chat session disappeared while clearing messages")
        count = int(
            conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,)).fetchone()[0]
        )
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (updated_at, session_id))
        updated_session = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(updated_session), count


def latest_session_exchange(session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT 2",
            (session_id,),
        ).fetchall()
    latest = dict(rows[0]) if rows else None
    previous = dict(rows[1]) if len(rows) > 1 else None
    return previous, latest


def replace_latest_assistant_message(
    session_id: str,
    assistant_message_id: str | None,
    content: str,
    model_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_at = now_utc().isoformat(timespec="microseconds")
    with get_connection() as conn:
        session_row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if session_row is None:
            raise LookupError("chat session disappeared while saving regenerated reply")
        if assistant_message_id:
            conn.execute(
                "UPDATE chat_messages SET content = ?, created_at = ? WHERE id = ? AND session_id = ? AND role = 'assistant'",
                (content, updated_at, assistant_message_id, session_id),
            )
            message_row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (assistant_message_id,)).fetchone()
        else:
            message_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES (?, ?, 'assistant', ?, ?)",
                (message_id, session_id, content, updated_at),
            )
            message_row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        conn.execute("UPDATE chat_sessions SET model_name = ?, updated_at = ? WHERE id = ?", (model_name, updated_at, session_id))
        updated_session = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return public_message(dict(message_row)), dict(updated_session)


def delete_session(session_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))


def save_chat_exchange(
    session_id: str,
    user_content: str,
    assistant_content: str,
    model_name: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """在一个事务中保存一轮完整对话并更新会话元数据。"""
    exchange_time = now_utc()
    user_created_at = exchange_time.isoformat(timespec="microseconds")
    assistant_created_at = (exchange_time + timedelta(microseconds=1)).isoformat(timespec="microseconds")
    user_message_id = uuid.uuid4().hex
    assistant_message_id = uuid.uuid4().hex

    with get_connection() as conn:
        session_row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if session_row is None:
            raise LookupError("chat session disappeared before message persistence")

        user_message_count = conn.execute(
            "SELECT COUNT(*) AS total FROM chat_messages WHERE session_id = ? AND role = 'user'",
            (session_id,),
        ).fetchone()["total"]
        next_title = session_row["title"]
        if next_title == "新会话" and int(user_message_count) == 0:
            next_title = safe_text(user_content.replace("\n", " ")[:24], "新会话")

        conn.executemany(
            """
            INSERT INTO chat_messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (user_message_id, session_id, "user", user_content, user_created_at),
                (assistant_message_id, session_id, "assistant", assistant_content, assistant_created_at),
            ],
        )
        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, model_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, model_name, assistant_created_at, session_id),
        )
        user_row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (user_message_id,)).fetchone()
        assistant_row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (assistant_message_id,)).fetchone()
        updated_session = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()

    return (
        public_message(dict(user_row)),
        public_message(dict(assistant_row)),
        dict(updated_session),
    )


def list_messages(session_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
    return [public_message(dict(row)) for row in rows]


def list_messages_page(
    session_id: str,
    *,
    limit: int,
    cursor: tuple[str, str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    cursor_sql = ""
    params: list[Any] = [session_id]
    if cursor:
        cursor_sql = " AND (created_at < ? OR (created_at = ? AND id < ?))"
        params.extend([cursor[0], cursor[0], cursor[1]])
    params.append(limit + 1)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ?" + cursor_sql
            + " ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    has_more = len(rows) > limit
    selected = rows[:limit]
    selected.reverse()
    return [public_message(dict(row)) for row in selected], has_more
