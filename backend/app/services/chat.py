import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

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
from backend.app.core.security import safe_fingerprint
from backend.app.repositories import (
    choose_model,
    count_all_sessions,
    count_messages_for_user,
    count_sessions,
    count_sessions_by_feature,
    clear_session_messages,
    create_session,
    delete_session,
    get_session,
    list_messages,
    list_messages_page,
    list_sessions,
    list_sessions_page,
    latest_session_exchange,
    public_session,
    rename_session,
    replace_latest_assistant_message,
    save_chat_exchange,
    set_session_pinned,
    safe_text,
)
from backend.app.services.assistant import build_local_chat_reply, create_chat_reply, create_chat_reply_stream


rate_limiter = InMemoryRateLimiter()
idempotency_store = DatabaseIdempotencyStore()
logger = logging.getLogger("yunxun.backend.chat")


@dataclass
class ChatStreamContext:
    """流式聊天两阶段上下文：prepare 完成校验与幂等领取，iter 负责产出事件。"""

    session_record: dict[str, Any]
    selected_model: str
    key_hash: str
    lease_id: str | None
    history: list[dict[str, str]] | None = None
    assistant_id: str | None = None
    cached_payload: dict[str, object] | None = None


def require_session_owner(session_id: str, user_id: str) -> dict[str, str]:
    session_record = get_session(session_id)
    if not session_record:
        raise session_not_found(session_id)
    if session_record["user_id"] != user_id:
        raise forbidden()
    return session_record


def create_user_session(
    user_id: str,
    title: str,
    feature: str,
    model_name: str,
) -> dict[str, str]:
    settings = get_settings()
    normalized_title = safe_text(title, "新会话")
    normalized_model = choose_model(model_name, settings.available_models, settings.chat_endpoint)
    session_record = create_session(
        user_id,
        normalized_title,
        feature.strip(),
        normalized_model,
    )
    log_event(
        logger,
        "chat_session_create",
        user_id=user_id,
        session_id=session_record["id"],
        feature=feature.strip(),
        model_name=normalized_model,
    )
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


def pin_user_session(session_id: str, user_id: str, is_pinned: bool) -> dict[str, str]:
    require_session_owner(session_id, user_id)
    session_record = set_session_pinned(session_id, is_pinned)
    log_event(logger, "chat_session_pin", user_id=user_id, session_id=session_id, is_pinned=is_pinned)
    return public_session(session_record)


def clear_user_session(session_id: str, user_id: str) -> dict[str, object]:
    require_session_owner(session_id, user_id)
    session_record, cleared_count = clear_session_messages(session_id)
    log_event(logger, "chat_session_clear", user_id=user_id, session_id=session_id, cleared_count=cleared_count)
    return {"session": public_session(session_record), "cleared_count": cleared_count}


def build_history(session_id: str) -> list[dict[str, str]]:
    history = list_messages(session_id)
    return [{"role": item["role"], "content": item["content"]} for item in history[-12:]]


async def regenerate_latest_reply(
    session_id: str,
    user: dict[str, str],
    client_host: str,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    session_record = require_session_owner(session_id, user["id"])
    rate_limiter.check(f"{user['id']}:{client_host}", settings.requests_per_minute)
    previous, latest = latest_session_exchange(session_id)
    if latest is None or latest["role"] != "user":
        if latest is None or latest["role"] != "assistant" or previous is None or previous["role"] != "user":
            raise HTTPException(status_code=400, detail="当前会话没有可重新生成的 AI 回复。")
        user_message = previous
        assistant_id = latest["id"]
    else:
        user_message = latest
        assistant_id = None
    selected_model = choose_model(
        session_record["model_name"] or user["preferred_model"],
        settings.available_models,
        settings.chat_endpoint,
    )
    key_hash = build_fingerprint("regenerate", user["id"], session_id, user_message["id"])
    request_hash = build_fingerprint(user_message["id"], user_message["content"], selected_model)
    lease_id: str | None = None
    if settings.idempotency_enabled:
        claim = idempotency_store.begin(
            owner_id=user["id"],
            key_hash=key_hash if not idempotency_key else build_fingerprint("regenerate", user["id"], session_id, idempotency_key),
            request_fingerprint=request_hash,
            ttl_seconds=max(settings.idempotency_window_seconds, settings.ai_timeout_seconds + 5),
        )
        if claim.state == "completed":
            if claim.response_body is None:
                raise duplicate_request()
            return claim.response_body
        if claim.state in {"in_flight", "conflict"}:
            raise duplicate_request() if claim.state == "in_flight" else idempotency_conflict()
        lease_id = claim.lease_id
        key_hash = key_hash if not idempotency_key else build_fingerprint("regenerate", user["id"], session_id, idempotency_key)
    try:
        history = build_history(session_id)
        if assistant_id and history and history[-1]["role"] == "assistant":
            history.pop()
        if not history or history[-1]["role"] != "user":
            history.append({"role": "user", "content": user_message["content"]})
        reply = await create_chat_reply(history, selected_model) if settings.ai_configured else build_local_chat_reply(user_message["content"])
        assistant_message, updated_session = replace_latest_assistant_message(
            session_id, assistant_id, reply, selected_model
        )
    except HTTPException:
        if lease_id:
            idempotency_store.fail(owner_id=user["id"], key_hash=key_hash, lease_id=lease_id)
        raise
    except Exception as exc:
        if lease_id:
            idempotency_store.fail(owner_id=user["id"], key_hash=key_hash, lease_id=lease_id)
        raise model_unavailable() from exc
    payload = {"assistant_message": assistant_message, "session": public_session(updated_session)}
    if lease_id:
        idempotency_store.complete(
            owner_id=user["id"], key_hash=key_hash, lease_id=lease_id,
            response_status=200, response_body=payload, ttl_seconds=settings.idempotency_window_seconds,
        )
    log_event(logger, "chat_message_regenerate", user_id=user["id"], session_id=session_id, model_name=selected_model)
    return payload


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
        client_fingerprint=safe_fingerprint(client_host),
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


def _claim_idempotency_lease(
    user: dict[str, str],
    key_hash: str,
    request_hash: str,
    *,
    settings,
) -> tuple[Any, str | None]:
    """领取幂等租约；已完成则返回缓存响应，冲突则直接抛错。"""
    if not settings.idempotency_enabled:
        return None, None
    claim = idempotency_store.begin(
        owner_id=user["id"],
        key_hash=key_hash,
        request_fingerprint=request_hash,
        ttl_seconds=max(settings.idempotency_window_seconds, settings.ai_timeout_seconds + 5),
    )
    if claim.state == "completed":
        if claim.response_body is None:
            raise duplicate_request()
        return claim, None
    if claim.state == "in_flight":
        raise duplicate_request()
    if claim.state == "conflict":
        raise idempotency_conflict()
    return claim, claim.lease_id


def prepare_session_message_stream(
    session_id: str,
    user: dict[str, str],
    message_text: str,
    model_name: str,
    client_host: str,
    idempotency_key: str | None = None,
) -> ChatStreamContext:
    """流式发消息的第一阶段：校验、限流、幂等领取；此时还未产出任何增量。"""
    settings = get_settings()
    session_record = require_session_owner(session_id, user["id"])
    rate_limiter.check(f"{user['id']}:{client_host}", settings.requests_per_minute)
    log_event(
        logger,
        "chat_message_request",
        user_id=user["id"],
        session_id=session_id,
        client_fingerprint=safe_fingerprint(client_host),
        message_length=len(message_text.strip()),
        ai_configured=settings.ai_configured,
        stream=True,
    )

    normalized_message = message_text.strip()
    if not normalized_message:
        raise message_empty()
    if len(normalized_message) > settings.max_message_length:
        raise message_too_long(settings.max_message_length)

    explicit_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
    selected_model = choose_model(
        model_name or session_record["model_name"] or user["preferred_model"],
        settings.available_models,
        settings.chat_endpoint,
    )
    request_identity = explicit_key or normalized_message
    key_hash = build_fingerprint("chat", user["id"], session_id, request_identity)
    request_hash = build_fingerprint(normalized_message, selected_model)
    claim, lease_id = _claim_idempotency_lease(user, key_hash, request_hash, settings=settings)
    if claim is not None and lease_id is None:
        log_event(logger, "chat_message_duplicate", user_id=user["id"], session_id=session_id, stream=True)
        return ChatStreamContext(
            session_record=session_record,
            selected_model=selected_model,
            key_hash=key_hash,
            lease_id=None,
            cached_payload=claim.response_body,
        )

    history = build_history(session_id)
    history.append({"role": "user", "content": normalized_message})
    return ChatStreamContext(
        session_record=session_record,
        selected_model=selected_model,
        key_hash=key_hash,
        lease_id=lease_id,
        history=history,
    )


async def iter_session_message_stream(context: ChatStreamContext) -> AsyncIterator[tuple[str, dict[str, object]]]:
    """流式发消息的第二阶段：产出 delta 事件并负责落库与幂等收尾。"""
    if context.cached_payload is not None:
        yield "done", context.cached_payload
        return

    reply_parts: list[str] = []
    try:
        async for delta in create_chat_reply_stream(context.history, context.selected_model):
            reply_parts.append(delta)
            yield "delta", {"text": delta}
        reply = "".join(reply_parts)
        if len(reply.encode("utf-8")) > MAX_RESPONSE_BYTES // 2:
            raise model_unavailable("模型回复过长，未保存本次结果，请缩小问题范围后重试。")
        user_message, assistant_message, updated_session = save_chat_exchange(
            context.session_record["id"],
            context.history[-1]["content"],
            reply,
            context.selected_model,
        )
    except HTTPException as exc:
        if context.lease_id:
            idempotency_store.fail(owner_id=context.session_record["user_id"], key_hash=context.key_hash, lease_id=context.lease_id)
        yield "error", {"error": str(exc.detail), "status": exc.status_code}
        return
    except Exception:
        if context.lease_id:
            idempotency_store.fail(owner_id=context.session_record["user_id"], key_hash=context.key_hash, lease_id=context.lease_id)
        logger.exception("Streaming chat message failed session_id=%s", context.session_record["id"])
        yield "error", {"error": "模型服务暂时不可用，请稍后重试。", "status": 502}
        return

    settings = get_settings()
    payload = {
        "reply": reply,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "session": public_session(updated_session),
    }
    if context.lease_id:
        idempotency_store.complete(
            owner_id=context.session_record["user_id"],
            key_hash=context.key_hash,
            lease_id=context.lease_id,
            response_status=200,
            response_body=payload,
            ttl_seconds=settings.idempotency_window_seconds,
        )
    log_event(
        logger,
        "chat_message_success",
        user_id=context.session_record["user_id"],
        session_id=context.session_record["id"],
        model_name=context.selected_model,
        reply_length=len(reply),
        stream=True,
    )
    yield "done", payload


def prepare_regenerate_stream(
    session_id: str,
    user: dict[str, str],
    client_host: str,
    idempotency_key: str | None = None,
) -> ChatStreamContext:
    """流式重新生成的第一阶段：与同步版同一套校验与幂等领取。"""
    settings = get_settings()
    session_record = require_session_owner(session_id, user["id"])
    rate_limiter.check(f"{user['id']}:{client_host}", settings.requests_per_minute)
    previous, latest = latest_session_exchange(session_id)
    if latest is None or latest["role"] != "user":
        if latest is None or latest["role"] != "assistant" or previous is None or previous["role"] != "user":
            raise HTTPException(status_code=400, detail="当前会话没有可重新生成的 AI 回复。")
        user_message = previous
        assistant_id: str | None = latest["id"]
    else:
        user_message = latest
        assistant_id = None
    selected_model = choose_model(
        session_record["model_name"] or user["preferred_model"],
        settings.available_models,
        settings.chat_endpoint,
    )
    key_hash = build_fingerprint("regenerate", user["id"], session_id, user_message["id"])
    if idempotency_key and idempotency_key.strip():
        key_hash = build_fingerprint("regenerate", user["id"], session_id, idempotency_key.strip())
    request_hash = build_fingerprint(user_message["id"], user_message["content"], selected_model)
    claim, lease_id = _claim_idempotency_lease(user, key_hash, request_hash, settings=settings)
    if claim is not None and lease_id is None:
        return ChatStreamContext(
            session_record=session_record,
            selected_model=selected_model,
            key_hash=key_hash,
            lease_id=None,
            cached_payload=claim.response_body,
        )

    history = build_history(session_id)
    if assistant_id and history and history[-1]["role"] == "assistant":
        history.pop()
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": user_message["content"]})
    return ChatStreamContext(
        session_record=session_record,
        selected_model=selected_model,
        key_hash=key_hash,
        lease_id=lease_id,
        history=history,
        assistant_id=assistant_id,
    )


async def iter_regenerate_stream(context: ChatStreamContext) -> AsyncIterator[tuple[str, dict[str, object]]]:
    """流式重新生成的第二阶段：产出增量并替换最近一条 AI 回复。"""
    if context.cached_payload is not None:
        yield "done", context.cached_payload
        return

    reply_parts: list[str] = []
    try:
        async for delta in create_chat_reply_stream(context.history, context.selected_model):
            reply_parts.append(delta)
            yield "delta", {"text": delta}
        reply = "".join(reply_parts)
        assistant_message, updated_session = replace_latest_assistant_message(
            context.session_record["id"], context.assistant_id, reply, context.selected_model
        )
    except HTTPException as exc:
        if context.lease_id:
            idempotency_store.fail(owner_id=context.session_record["user_id"], key_hash=context.key_hash, lease_id=context.lease_id)
        yield "error", {"error": str(exc.detail), "status": exc.status_code}
        return
    except Exception:
        if context.lease_id:
            idempotency_store.fail(owner_id=context.session_record["user_id"], key_hash=context.key_hash, lease_id=context.lease_id)
        logger.exception("Streaming regenerate failed session_id=%s", context.session_record["id"])
        yield "error", {"error": "模型服务暂时不可用，请稍后重试。", "status": 502}
        return

    settings = get_settings()
    payload = {"assistant_message": assistant_message, "session": public_session(updated_session)}
    if context.lease_id:
        idempotency_store.complete(
            owner_id=context.session_record["user_id"],
            key_hash=context.key_hash,
            lease_id=context.lease_id,
            response_status=200,
            response_body=payload,
            ttl_seconds=settings.idempotency_window_seconds,
        )
    log_event(
        logger,
        "chat_message_regenerate",
        user_id=context.session_record["user_id"],
        session_id=context.session_record["id"],
        model_name=context.selected_model,
        stream=True,
    )
    yield "done", payload
