import logging
from typing import Any


SENSITIVE_FIELDS = {
    "password",
    "password_hash",
    "token",
    "authorization",
    "api_key",
    "image_base64",
}


def _format_value(key: str, value: Any) -> str:
    if key.casefold() in SENSITIVE_FIELDS:
        return "[redacted]"
    if value is None:
        return "none"
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:160]


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    ordered_fields = " ".join(f"{key}={_format_value(key, value)}" for key, value in sorted(fields.items()))
    if ordered_fields:
        logger.info("event=%s %s", event, ordered_fields)
    else:
        logger.info("event=%s", event)
