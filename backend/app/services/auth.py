import logging
import re
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.core.time import now_utc
from backend.app.core.security import create_token, hash_auth_token, hash_password, verify_password, session_reference
from backend.app.repositories import (
    cleanup_expired_tokens,
    create_auth_token,
    create_user,
    delete_auth_token,
    get_user_by_id,
    get_user_by_token_hash,
    get_user_by_username,
    public_user,
    update_user_profile,
    upgrade_guest_account,
)


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
logger = logging.getLogger("yunxun.backend.auth")


def register_user(username: str, password: str, display_name: str, *, is_guest: bool = False) -> dict[str, str | dict]:
    normalized_username = username.strip().lower()
    normalized_display_name = display_name.strip()

    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise HTTPException(status_code=400, detail="用户名只能包含英文字母、数字或下划线。")
    if get_user_by_username(normalized_username):
        raise HTTPException(status_code=409, detail="用户名已存在。")
    if not normalized_display_name:
        raise HTTPException(status_code=400, detail="显示名称不能为空。")

    user_record = create_user(
        username=normalized_username,
        password_hash=hash_password(password),
        display_name=normalized_display_name,
        is_guest=is_guest,
    )
    log_event(logger, "auth_register_success", user_id=user_record["id"], username=normalized_username)
    token = issue_auth_token(user_record["id"], expected_password_hash=user_record["password_hash"])
    return {"user": public_user(user_record), "token": token, "session_id": session_reference(token)}


def login_user(username: str, password: str) -> dict[str, str | dict]:
    user_record = get_user_by_username(username.strip().lower())
    if not user_record or not verify_password(password, user_record["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    token = issue_auth_token(user_record["id"], expected_password_hash=user_record["password_hash"])
    log_event(logger, "auth_login_success", user_id=user_record["id"], username=user_record["username"])
    return {"user": public_user(user_record), "token": token, "session_id": session_reference(token)}


def guest_login() -> dict[str, str | dict]:
    suffix = uuid.uuid4().hex[:8]
    log_event(logger, "auth_guest_login", guest_suffix=suffix)
    return register_user(
        username=f"guest_{suffix}",
        password=secrets.token_urlsafe(16),
        display_name=f"访客 {suffix[:4]}",
        is_guest=True,
    )


def upgrade_guest_user(user: dict, username: str, password: str, display_name: str) -> dict:
    # is_guest 来自服务端认证查询，旧账号的用户名不是身份凭据。
    if not user.get("is_guest"):
        raise HTTPException(status_code=403, detail="当前账号不是可升级的访客账号，不能通过此入口修改账号。")
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="用户名只能包含英文字母、数字或下划线。")
    token = create_token()
    expires_at = (now_utc() + timedelta(hours=get_settings().token_hours)).isoformat(timespec="seconds")
    updated = upgrade_guest_account(user["id"], normalized, hash_password(password), display_name.strip(),
                                    hash_auth_token(token), expires_at)
    log_event(logger, "auth_guest_upgrade", user_id=updated["id"], username=normalized)
    return {"user": public_user(updated), "token": token, "session_id": session_reference(token)}


def issue_auth_token(user_id: str, *, expected_password_hash: str | None = None) -> str:
    settings = get_settings()
    token = create_token()
    expires_at = (now_utc() + timedelta(hours=settings.token_hours)).isoformat(timespec="seconds")
    cleanup_expired_tokens()
    if expected_password_hash is None:
        create_auth_token(user_id, hash_auth_token(token), expires_at)
    else:
        create_auth_token(user_id, hash_auth_token(token), expires_at, expected_password_hash=expected_password_hash)
    return token


def get_current_user_from_header(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录。")

    token = authorization.split(" ", 1)[1].strip()
    user_record = get_user_by_token_hash(hash_auth_token(token))
    if not user_record:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
    return user_record


def logout_user(authorization: str | None, user_id: str | None = None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        return

    token = authorization.split(" ", 1)[1].strip()
    delete_auth_token(hash_auth_token(token))
    log_event(logger, "auth_logout", user_id=user_id or "unknown")


def update_profile(user_id: str, display_name: str) -> dict[str, str]:
    user_record = get_user_by_id(user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="用户不存在。")
    if not display_name.strip():
        raise HTTPException(status_code=400, detail="显示名称不能为空。")

    updated_record = update_user_profile(user_id, display_name.strip())
    log_event(logger, "auth_profile_update", user_id=user_id)
    return public_user(updated_record)
