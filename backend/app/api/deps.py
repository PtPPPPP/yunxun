from fastapi import Header

from backend.app.services.auth import get_current_user_from_header


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    return get_current_user_from_header(authorization)
