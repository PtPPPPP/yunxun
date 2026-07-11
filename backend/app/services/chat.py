import logging

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    duplicate_request,
    forbidden,
    idempotency_conflict,
    message_empty,
    message_too_long,
    model_unavailable,
    session_not_found,
)
from backend.app.core.idempotency import DatabaseIdempotencyStore, MAX_RESPONSE_BYTES, build_fingerprint
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.repositories import (
    choose_model,
    count_all_sessions,
    count_messages_for_user,
    count_sessions,
    count_sessions_by_feature,
    create_session,
    delete_session,
    get_session,
    list_messages,
    list_messages_page,
    list_sessions,
    list_sessions_page,
    public_session,
    rename_session,
    save_chat_exchange,
    safe_text,
)
from backend.app.services.assistant import build_local_chat_reply, create_chat_reply


rate_limiter = InMemoryRateLimiter()
idempotency_store = DatabaseIdempotencyStore()
logger = logging.getLogger("yunxun.backend.chat")


def require_session_owner(session_id: str, user_id: str) -> dict[str, str]:
    session_record = get_session(session_id)
    if not session_record:
        raise session_not_found(session_id)
    if session_record["user_id"] != user_id:
        raise forbidden()
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


def list_user_sessions_page(user_id: str, feature: str, params) -> tuple[list[dict[str, str]], int]:
    """分页查询会话列表，返回 (当前页, 总数)。"""
    sessions = list_sessions_page(user_id, feature, limit=params.limit, offset=params.offset)
    return sessions, count_sessions(user_id, feature)


def build_session_stats(user_id: str) -> dict[str, object]:
    """面向工作台的会话统计：总会话数、总消息数、各功能会话数。"""
    return {
        "total_sessions": count_all_sessions(user_id),
        "total_messages": count_messages_for_user(user_id),
        "sessions_by_feature": count_sessions_by_feature(user_id),
    }


def get_session_detail(
    session_id: str,
    user_id: str,
    *,
    message_limit: int | None = None,
    message_cursor: tuple[str, str] | None = None,
) -> dict[str, object]:
    session_record = require_session_owner(session_id, user_id)
    if message_limit is None:
        return {"session": public_session(session_record), "messages": list_messages(session_id)}
    messages, has_more = list_messages_page(session_id, limit=message_limit, cursor=message_cursor)
    from backend.app.core.pagination import encode_cursor

    next_cursor = None
    if has_more and messages:
        next_cursor = encode_cursor(messages[0]["created_at"], messages[0]["id"])
    return {
        "session": public_session(session_record),
        "messages": messages,
        "message_pagination": {"has_more": has_more, "next_cursor": next_cursor},
    }


def rename_user_session(session_id: str, user_id: str, title: str) -> dict[str, str]:
    require_session_owner(session_id, user_id)
    session_record = rename_session(session_id, safe_text(title, "新会话"))
    log_event(logger, "chat_session_rename", user_id=user_id, session_id=session_id)
    return public_session(session_record)


def delete_user_session(session_id: str, user_id: str) -> None:
    require_session_owner(session_id, user_id)
    delete_session(session_id)
    log_event(logger, "chat_session_delete", user_id=user_id, session_id=session_id)


def build_history(session_id: str) -> list[dict[str, str]]:
    history = list_messages(session_id)
    return [{"role": item["role"], "content": item["content"]} for item in history[-12:]]


async def create_session_message(
    session_id: str,
    user: dict[str, str],
    message_text: str,
    model_name: str,
    client_host: str,
    idempotency_key: str | None = None,
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
        raise message_empty()
    if len(normalized_message) > settings.max_message_length:
        raise message_too_long(settings.max_message_length)

    # 显式请求标识用于网络重试；旧客户端没有标识时仍按消息内容防双击。
    explicit_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
    selected_model = choose_model(
        model_name or session_record["model_name"] or user["preferred_model"],
        settings.available_models,
        settings.chat_endpoint,
    )
    request_identity = explicit_key or normalized_message
    key_hash = build_fingerprint("chat", user["id"], session_id, request_identity)
    request_hash = build_fingerprint(normalized_message, selected_model)
    lease_id: str | None = None
    if settings.idempotency_enabled:
        claim = idempotency_store.begin(
            owner_id=user["id"],
            key_hash=key_hash,
            request_fingerprint=request_hash,
            ttl_seconds=max(settings.idempotency_window_seconds, settings.ai_timeout_seconds + 5),
        )
        if claim.state == "completed":
            log_event(logger, "chat_message_duplicate", user_id=user["id"], session_id=session_id)
            if claim.response_body is None:
                raise duplicate_request()
            return claim.response_body
        if claim.state == "in_flight":
            raise duplicate_request()
        if claim.state == "conflict":
            raise idempotency_conflict()
        lease_id = claim.lease_id
    try:
        if settings.ai_configured:
            history = build_history(session_id)
            history.append({"role": "user", "content": normalized_message})
            reply = await create_chat_reply(history, selected_model)
        else:
            reply = build_local_chat_reply(normalized_message)
        if len(reply.encode("utf-8")) > MAX_RESPONSE_BYTES // 2:
            raise model_unavailable("模型回复过长，未保存本次结果，请缩小问题范围后重试。")

        user_message, assistant_message, updated_session = save_chat_exchange(
            session_id,
            normalized_message,
            reply,
            selected_model,
        )
    except HTTPException:
        if lease_id:
            idempotency_store.fail(owner_id=user["id"], key_hash=key_hash, lease_id=lease_id)
        raise
    except Exception as exc:
        if lease_id:
            idempotency_store.fail(owner_id=user["id"], key_hash=key_hash, lease_id=lease_id)
        raise model_unavailable() from exc
    log_event(
        logger,
        "chat_message_success",
        user_id=user["id"],
        session_id=session_id,
        model_name=selected_model,
        reply_length=len(reply),
    )
    payload = {
        "reply": reply,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "session": public_session(updated_session),
    }
    if lease_id:
        idempotency_store.complete(
            owner_id=user["id"],
            key_hash=key_hash,
            lease_id=lease_id,
            response_status=200,
            response_body=payload,
            ttl_seconds=settings.idempotency_window_seconds,
        )
    return payload
