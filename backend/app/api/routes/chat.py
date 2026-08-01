from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from backend.app.api.deps import get_current_user
from backend.app.core.config import get_settings
from backend.app.core.exceptions import success_payload
from backend.app.core.pagination import build_page, decode_cursor, parse_page_params
from backend.app.schemas import ChatMessageRequest, ChatSessionCreateRequest, ChatSessionRenameRequest
from backend.app.services.chat import (
    build_session_stats,
    create_session_message,
    create_user_session,
    delete_user_session,
    get_session_detail,
    list_user_sessions,
    list_user_sessions_page,
    rename_user_session,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
async def list_chat_sessions_api(
    feature: str = "chat",
    page: str | None = Query(default=None, description="页码，从 1 开始；不传则一次返回全部。"),
    page_size: str | None = Query(default=None, description="每页数量；不传则使用默认值。"),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    # 未传分页参数时保持历史行为：一次返回全部会话，载荷结构与旧版一致。
    settings = get_settings()
    try:
        params = parse_page_params(
            page,
            page_size,
            default_page_size=settings.default_page_size,
            max_page_size=settings.max_page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if params is None:
        return success_payload(sessions=list_user_sessions(user["id"], feature))

    sessions, total = list_user_sessions_page(user["id"], feature, params)
    page_obj = build_page(sessions, total, params)
    return success_payload(sessions=page_obj.items, pagination=page_obj.to_payload())


@router.get("/stats")
async def chat_stats_api(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**build_session_stats(user["id"]))


@router.post("/sessions")
async def create_chat_session_api(
    request: ChatSessionCreateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    session = create_user_session(
        user["id"], request.title, request.feature, request.model_name, request.model_config_id
    )
    return success_payload(session=session)


@router.get("/sessions/{session_id}")
async def chat_session_detail_api(
    session_id: str,
    message_limit: int | None = Query(default=None, ge=1, le=200),
    message_cursor: str | None = Query(default=None, max_length=512),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    try:
        cursor = decode_cursor(message_cursor) if message_cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_payload(
        **get_session_detail(session_id, user["id"], message_limit=message_limit, message_cursor=cursor)
    )


@router.patch("/sessions/{session_id}")
async def rename_chat_session_api(
    session_id: str,
    request: ChatSessionRenameRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    session = rename_user_session(session_id, user["id"], request.title)
    return success_payload(session=session)


@router.delete("/sessions/{session_id}")
async def delete_chat_session_api(
    session_id: str,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    delete_user_session(session_id, user["id"])
    return success_payload(message="会话已删除。")


@router.post("/sessions/{session_id}/messages")
async def create_chat_message_api(
    session_id: str,
    request: ChatMessageRequest,
    http_request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    payload = await create_session_message(
        session_id=session_id,
        user=user,
        message_text=request.message,
        model_name=request.model_name,
        model_config_id=request.model_config_id,
        client_host=http_request.client.host if http_request.client else "local",
        idempotency_key=idempotency_key,
    )
    return success_payload(**payload)
