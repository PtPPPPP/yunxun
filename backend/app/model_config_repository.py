from __future__ import annotations

import uuid
from typing import Any

from backend.app.core.database import get_connection
from backend.app.repositories import now_iso


def public_model_config(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "provider": record["provider"],
        "display_name": record["display_name"],
        "model": record["model"],
        "base_url": record["base_url"],
        "masked_key": f"已配置 · {record['key_fingerprint'][:10]}",
        "is_default": bool(record["is_default"]),
        "is_enabled": bool(record["is_enabled"]),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "last_verified_at": record.get("last_verified_at"),
        "last_verify_status": record.get("last_verify_status"),
        "last_verify_error_code": record.get("last_verify_error_code"),
    }


def list_model_configs(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM user_model_credentials WHERE user_id = ? ORDER BY is_default DESC, updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_model_config(config_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_model_credentials WHERE id = ?", (config_id,)).fetchone()
    return dict(row) if row else None


def get_default_model_config(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM user_model_credentials WHERE user_id = ? AND is_default = 1 AND is_enabled = 1",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_model_config(
    *,
    user_id: str,
    provider: str,
    display_name: str,
    model: str,
    base_url: str,
    encrypted_api_key: bytes,
    key_fingerprint: str,
    is_default: bool,
) -> dict[str, Any]:
    config_id = uuid.uuid4().hex
    timestamp = now_iso()
    with get_connection() as conn:
        has_default = conn.execute(
            "SELECT 1 FROM user_model_credentials WHERE user_id = ? AND is_default = 1", (user_id,)
        ).fetchone()
        make_default = is_default or has_default is None
        if make_default:
            conn.execute("UPDATE user_model_credentials SET is_default = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO user_model_credentials
                (id, user_id, provider, display_name, model, base_url, encrypted_api_key,
                 key_fingerprint, is_default, is_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                config_id,
                user_id,
                provider,
                display_name,
                model,
                base_url,
                encrypted_api_key,
                key_fingerprint,
                int(make_default),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute("SELECT * FROM user_model_credentials WHERE id = ?", (config_id,)).fetchone()
    return dict(row)


def update_model_config(
    config_id: str,
    *,
    provider: str,
    display_name: str,
    model: str,
    base_url: str,
    is_enabled: bool,
    encrypted_api_key: bytes | None = None,
    key_fingerprint: str | None = None,
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as conn:
        if encrypted_api_key is None:
            conn.execute(
                """UPDATE user_model_credentials
                   SET provider = ?, display_name = ?, model = ?, base_url = ?, is_enabled = ?, updated_at = ?
                   WHERE id = ?""",
                (provider, display_name, model, base_url, int(is_enabled), timestamp, config_id),
            )
        else:
            conn.execute(
                """UPDATE user_model_credentials
                   SET provider = ?, display_name = ?, model = ?, base_url = ?, is_enabled = ?,
                       encrypted_api_key = ?, key_fingerprint = ?, updated_at = ?,
                       last_verified_at = NULL, last_verify_status = NULL, last_verify_error_code = NULL
                   WHERE id = ?""",
                (
                    provider,
                    display_name,
                    model,
                    base_url,
                    int(is_enabled),
                    encrypted_api_key,
                    key_fingerprint,
                    timestamp,
                    config_id,
                ),
            )
        row = conn.execute("SELECT * FROM user_model_credentials WHERE id = ?", (config_id,)).fetchone()
    return dict(row) if row else None


def set_default_model_config(user_id: str, config_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        target = conn.execute(
            "SELECT * FROM user_model_credentials WHERE id = ? AND user_id = ? AND is_enabled = 1",
            (config_id, user_id),
        ).fetchone()
        if target is None:
            return None
        conn.execute("UPDATE user_model_credentials SET is_default = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            "UPDATE user_model_credentials SET is_default = 1, updated_at = ? WHERE id = ?",
            (now_iso(), config_id),
        )
        row = conn.execute("SELECT * FROM user_model_credentials WHERE id = ?", (config_id,)).fetchone()
    return dict(row) if row else None


def delete_model_config(user_id: str, config_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_default FROM user_model_credentials WHERE id = ? AND user_id = ?", (config_id, user_id)
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM user_model_credentials WHERE id = ?", (config_id,))
        if row["is_default"]:
            replacement = conn.execute(
                """SELECT id FROM user_model_credentials
                   WHERE user_id = ? AND is_enabled = 1 ORDER BY updated_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if replacement:
                conn.execute(
                    "UPDATE user_model_credentials SET is_default = 1, updated_at = ? WHERE id = ?",
                    (now_iso(), replacement["id"]),
                )
    return True


def save_verification_result(config_id: str, status: str, error_code: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE user_model_credentials
               SET last_verified_at = ?, last_verify_status = ?, last_verify_error_code = ?, updated_at = ?
               WHERE id = ?""",
            (now_iso(), status, error_code, now_iso(), config_id),
        )
