from __future__ import annotations

import re
import uuid
from contextvars import ContextVar


_REQUEST_ID = ContextVar("request_id", default="")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def normalize_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if _SAFE_REQUEST_ID.fullmatch(candidate) else uuid.uuid4().hex


def set_request_id(value: str):
    return _REQUEST_ID.set(value)


def reset_request_id(token) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str:
    return _REQUEST_ID.get()
