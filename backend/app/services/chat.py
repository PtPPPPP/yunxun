import logging

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.repositories import (
    choose_model,
    create_session,
    delete_session,
    get_session,
    list_messages,
    list_sessions,
    maybe_update_session_title,
    public_session,
    rename_session,
    save_message,
    safe_text,
    update_session_model,
)
from backend.app.services.assistant import build_local_chat_reply, create_chat_reply


rate_limiter = InMemoryRateLimiter()
logger = logging.getLogger("yunxun.backend.chat")


def require_session_owner(session_id: str, user_id: str) -> dict[str, str]:
    session_record = get_session(session_id)
    if not session_record:
        raise HTTPException(status_code=404, detail="会话不存在。")
    if session_record["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="你无权访问这个会话。")
    return session_record


def create_user_session(user_id: str, title: str, feature: str, model_name: str) -> dict[str, str]:
    settings = get_settings()
    normalized_title = safe_text(title, "新会话")
    normalized_model = choose_model(model_name, settings.available_models, settings.chat_endpoint)
    session_record = create_session(user_id, normalized_title, feature.strip(), normalized_model)
    log_event(logger, "chat_session_create", user_id=user_id, session_id=session_record["id"], feature=feature.strip(), model_name=normalized_model)
    return public_session(session_record)


def list_user_sessions(user_id: str, feature: str) -> list[dict[str, str]]:
    return list_sessions(user_id, feature)


def get_session_detail(session_id: str, user_id: str) -> dict[str, object]:
    session_record = require_session_owner(session_id, user_id)
    return {"session": public_session(session_record), "messages": list_messages(session_id)}


def rename_user_session(session_id: str, user_id: str, title: str) -> dict[str, str]:
    require_session_owner(session_id, user_id)
    session_record = rename_session(session_id, safe_text(title, "新会话"))
    return public_session(session_record)


def delete_user_session(session_id: str, user_id: str) -> None:
    require_session_owner(session_id, user_id)
    delete_session(session_id)


def build_history(session_id: str) -> list[dict[str, str]]:
    history = list_messages(session_id)
    return [{"role": item["role"], "content": item["content"]} for item in history[-12:]]


def create_session_message(
    session_id: str,
    user: dict[str, str],
    message_text: str,
    model_name: str,
    client_host: str,
) -> dict[str, object]:
    settings = get_settings()
    session_record = require_session_owner(session_id, user["id"])
    rate_limiter.check(f"{user['id']}:{client_host}", settings.requests_per_minute)
    log_event(
        logger,
        "chat_message_request",
        user_id=user["id"],
        session_id=session_id,
        client_host=client_host,
        message_length=len(message_text.strip()),
        ai_configured=settings.ai_configured,
    )

    normalized_message = message_text.strip()
    if not normalized_message:
        raise HTTPException(status_code=400, detail="输入内容不能为空。")
    if len(normalized_message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail=f"输入内容不能超过 {settings.max_message_length} 个字符。")

    user_message = save_message(session_id, "user", normalized_message)
    maybe_update_session_title(session_id, normalized_message)

    selected_model = choose_model(model_name or session_record["model_name"] or user["preferred_model"], settings.available_models, settings.chat_endpoint)
    if settings.ai_configured:
        try:
            reply = create_chat_reply(build_history(session_id), selected_model)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="模型服务暂时不可用，请稍后重试。") from exc
    else:
        reply = build_local_chat_reply(normalized_message)

    assistant_message = save_message(session_id, "assistant", reply)
    log_event(
        logger,
        "chat_message_success",
        user_id=user["id"],
        session_id=session_id,
        model_name=selected_model,
        reply_length=len(reply),
    )
    updated_session = update_session_model(session_id, selected_model)

    return {
        "reply": reply,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "session": public_session(updated_session),
    }
