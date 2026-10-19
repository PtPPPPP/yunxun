from fastapi import Header, Request

from backend.app.services.auth import get_current_user_from_header
from backend.app.core.security import session_reference


def get_session_reference(request: Request, authorization: str | None = Header(default=None)) -> str:
    token = request.cookies.get("yunxun_session")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    return session_reference(token) if token else ""


def get_current_user(request: Request, authorization: str | None = Header(default=None)) -> dict[str, str]:
    cookie_token = request.cookies.get("yunxun_session")
    if cookie_token and authorization:
        cookie_user = get_current_user_from_header(f"Bearer {cookie_token}")
        bearer_user = get_current_user_from_header(authorization)
        if cookie_user["id"] != bearer_user["id"]:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="认证身份冲突。")
        return cookie_user
    if cookie_token:
        return get_current_user_from_header(f"Bearer {cookie_token}")
    return get_current_user_from_header(authorization)
