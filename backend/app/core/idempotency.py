from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from backend.app.core.database import get_connection


IdempotencyState = Literal["acquired", "in_flight", "completed", "conflict"]
NowProvider = Callable[[], datetime]
MAX_RESPONSE_BYTES = 512 * 1024
CLEANUP_BATCH_SIZE = 500


def build_fingerprint(*parts: Any) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotencyClaim:
    state: IdempotencyState
    lease_id: str | None = None
    response_status: int | None = None
    response_body: dict[str, Any] | None = None


class DatabaseIdempotencyStore:
    def __init__(
        self,
        *,
        now_provider: NowProvider | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._now = now_provider or (lambda: datetime.now(timezone.utc))
        self._max_response_bytes = max_response_bytes

    def begin(
        self,
        *,
        owner_id: str,
        key_hash: str,
        request_fingerprint: str,
        ttl_seconds: float,
    ) -> IdempotencyClaim:
        self._validate_identity(owner_id, key_hash, request_fingerprint)
        now = self._now()
        now_text = self._format_time(now)
        expires_at = self._format_time(now + timedelta(seconds=ttl_seconds))
        lease_id = uuid.uuid4().hex

        with get_connection() as conn:
            self._cleanup_expired_with_connection(conn, now_text)
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO idempotency_requests (
                    owner_id, key_hash, request_fingerprint, status, lease_id,
                    response_status, response_body, created_at, updated_at, expires_at
                )
                VALUES (?, ?, ?, 'in_flight', ?, NULL, NULL, ?, ?, ?)
                """,
                (owner_id, key_hash, request_fingerprint, lease_id, now_text, now_text, expires_at),
            )
            if inserted.rowcount == 1:
                return IdempotencyClaim(state="acquired", lease_id=lease_id)

            row = conn.execute(
                """
                SELECT request_fingerprint, status, response_status, response_body
                FROM idempotency_requests
                WHERE owner_id = ? AND key_hash = ?
                """,
                (owner_id, key_hash),
            ).fetchone()
            if row is None:
                raise RuntimeError("idempotency row disappeared during claim")
            if row["request_fingerprint"] != request_fingerprint:
                return IdempotencyClaim(state="conflict")
            if row["status"] == "completed":
                response_body = json.loads(row["response_body"]) if row["response_body"] else None
                return IdempotencyClaim(
                    state="completed",
                    response_status=row["response_status"],
                    response_body=response_body,
                )
            if row["status"] == "in_flight":
                return IdempotencyClaim(state="in_flight")

            restarted = conn.execute(
                """
                UPDATE idempotency_requests
                SET status = 'in_flight', lease_id = ?, response_status = NULL,
                    response_body = NULL, updated_at = ?, expires_at = ?
                WHERE owner_id = ? AND key_hash = ? AND status = 'failed'
                """,
                (lease_id, now_text, expires_at, owner_id, key_hash),
            )
            if restarted.rowcount != 1:
                return IdempotencyClaim(state="in_flight")
            return IdempotencyClaim(state="acquired", lease_id=lease_id)

    def complete(
        self,
        *,
        owner_id: str,
        key_hash: str,
        lease_id: str,
        response_status: int,
        response_body: dict[str, Any],
        ttl_seconds: float,
    ) -> bool:
        serialized = json.dumps(response_body, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > self._max_response_bytes:
            raise ValueError("idempotency response exceeds configured storage limit")
        now = self._now()
        completed_at = self._format_time(now)
        expires_at = self._format_time(now + timedelta(seconds=ttl_seconds))
        with get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE idempotency_requests
                SET status = 'completed', response_status = ?, response_body = ?,
                    updated_at = ?, expires_at = ?
                WHERE owner_id = ? AND key_hash = ? AND status = 'in_flight' AND lease_id = ?
                """,
                (response_status, serialized, completed_at, expires_at, owner_id, key_hash, lease_id),
            )
        return updated.rowcount == 1

    def fail(self, *, owner_id: str, key_hash: str, lease_id: str) -> bool:
        updated_at = self._format_time(self._now())
        with get_connection() as conn:
            updated = conn.execute(
                """
                UPDATE idempotency_requests
                SET status = 'failed', response_status = NULL, response_body = NULL, updated_at = ?
                WHERE owner_id = ? AND key_hash = ? AND status = 'in_flight' AND lease_id = ?
                """,
                (updated_at, owner_id, key_hash, lease_id),
            )
        return updated.rowcount == 1

    def cleanup_expired(self) -> int:
        with get_connection() as conn:
            return self._cleanup_expired_with_connection(conn, self._format_time(self._now()))

    def reset(self) -> bool:
        with get_connection() as conn:
            result = conn.execute("DELETE FROM idempotency_requests")
        return result.rowcount > 0

    @staticmethod
    def _cleanup_expired_with_connection(conn: Any, now_text: str) -> int:
        result = conn.execute(
            """
            DELETE FROM idempotency_requests
            WHERE rowid IN (
                SELECT rowid FROM idempotency_requests
                WHERE expires_at < ?
                ORDER BY expires_at ASC
                LIMIT ?
            )
            """,
            (now_text, CLEANUP_BATCH_SIZE),
        )
        return result.rowcount

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def _validate_identity(owner_id: str, key_hash: str, request_fingerprint: str) -> None:
        if not owner_id.strip() or not key_hash.strip() or not request_fingerprint.strip():
            raise ValueError("idempotency identity cannot be empty")
