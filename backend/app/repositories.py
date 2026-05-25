import sqlite3
import uuid
from datetime import datetime, timezone
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


def create_auth_token(user_id: str, token: str, expires_at: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_tokens (token, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, expires_at, now_iso()),
        )


def delete_auth_token(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))


def cleanup_expired_tokens() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (now_iso(),))


def get_user_by_token(token: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        token_row = conn.execute("SELECT * FROM auth_tokens WHERE token = ?", (token,)).fetchone()
        if not token_row:
            return None
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (token_row["user_id"],)).fetchone()
    return dict(user_row) if user_row else None


def create_session(user_id: str, title: str, feature: str, model_name: str) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_sessions (id, user_id, title, feature, model_name, created_at, updated_at)
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
            ORDER BY s.updated_at DESC, s.id DESC
            """,
            (user_id, feature),
        ).fetchall()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        sessions.append(public_session(record, record.get("last_message") or ""))
    return sessions


def rename_session(session_id: str, title: str) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?", (title, updated_at, session_id))
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row)


def update_session_model(session_id: str, model_name: str) -> dict[str, Any]:
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_sessions SET model_name = ?, updated_at = ? WHERE id = ?",
            (model_name, updated_at, session_id),
        )
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row)


def delete_session(session_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))


def save_message(session_id: str, role: str, content: str) -> dict[str, Any]:
    message_id = uuid.uuid4().hex
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, created_at),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (created_at, session_id))
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    return public_message(dict(row))


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


def count_user_messages(session_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM chat_messages WHERE session_id = ? AND role = 'user'",
            (session_id,),
        ).fetchone()
    return int(row["total"]) if row else 0


def maybe_update_session_title(session_id: str, content: str) -> None:
    session_record = get_session(session_id)
    if not session_record or session_record["title"] != "新会话":
        return
    if count_user_messages(session_id) > 1:
        return
    title = safe_text(content.replace("\n", " ")[:24], "新会话")
    rename_session(session_id, title)
