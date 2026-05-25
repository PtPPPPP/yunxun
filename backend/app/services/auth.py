import logging
import re
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.core.security import create_token, hash_password, verify_password
from backend.app.repositories import (
    choose_model,
    cleanup_expired_tokens,
    create_auth_token,
    create_user,
    delete_auth_token,
    get_user_by_id,
    get_user_by_token,
    get_user_by_username,
    now_utc,
    public_user,
    update_user_profile,
)


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
logger = logging.getLogger("yunxun.backend.auth")


def register_user(username: str, password: str, display_name: str) -> dict[str, str | dict]:
    settings = get_settings()
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
        preferred_model=choose_model("", settings.available_models, settings.chat_endpoint),
    )
    log_event(logger, "auth_register_success", user_id=user_record["id"], username=normalized_username)
    token = issue_auth_token(user_record["id"])
    return {"user": public_user(user_record), "token": token}


def login_user(username: str, password: str) -> dict[str, str | dict]:
    user_record = get_user_by_username(username.strip().lower())
    if not user_record or not verify_password(password, user_record["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    log_event(logger, "auth_login_success", user_id=user_record["id"], username=user_record["username"])
    token = issue_auth_token(user_record["id"])
    return {"user": public_user(user_record), "token": token}


def guest_login() -> dict[str, str | dict]:
    suffix = uuid.uuid4().hex[:8]
    log_event(logger, "auth_guest_login", guest_suffix=suffix)
    return register_user(
        username=f"guest_{suffix}",
        password=secrets.token_urlsafe(16),
        display_name=f"访客 {suffix[:4]}",
    )


def issue_auth_token(user_id: str) -> str:
    settings = get_settings()
    token = create_token()
    expires_at = (now_utc() + timedelta(hours=settings.token_hours)).isoformat(timespec="seconds")
    create_auth_token(user_id, token, expires_at)
    return token


def get_current_user_from_header(authorization: str | None) -> dict[str, str]:
    cleanup_expired_tokens()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录。")

    token = authorization.split(" ", 1)[1].strip()
    user_record = get_user_by_token(token)
    if not user_record:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
    return user_record


def logout_user(authorization: str | None, user_id: str | None = None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        return

    token = authorization.split(" ", 1)[1].strip()
    delete_auth_token(token)
    log_event(logger, "auth_logout", user_id=user_id or "unknown")


def update_profile(user_id: str, display_name: str, preferred_model: str) -> dict[str, str]:
    settings = get_settings()
    user_record = get_user_by_id(user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="用户不存在。")
    if not display_name.strip():
        raise HTTPException(status_code=400, detail="显示名称不能为空。")

    normalized_model = choose_model(
        preferred_model or user_record["preferred_model"],
        settings.available_models,
        settings.chat_endpoint,
    )
    updated_record = update_user_profile(user_id, display_name.strip(), normalized_model)
    log_event(logger, "auth_profile_update", user_id=user_id, preferred_model=normalized_model)
    return public_user(updated_record)
