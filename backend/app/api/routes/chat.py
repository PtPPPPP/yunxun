from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.schemas import ChatMessageRequest, ChatSessionCreateRequest, ChatSessionRenameRequest
from backend.app.services.chat import (
    create_session_message,
    create_user_session,
    delete_user_session,
    get_session_detail,
    list_user_sessions,
    rename_user_session,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
async def list_chat_sessions_api(
    feature: str = "chat",
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(sessions=list_user_sessions(user["id"], feature))


@router.post("/sessions")
async def create_chat_session_api(
    request: ChatSessionCreateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    session = create_user_session(user["id"], request.title, request.feature, request.model_name)
    return success_payload(session=session)


@router.get("/sessions/{session_id}")
async def chat_session_detail_api(
    session_id: str,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**get_session_detail(session_id, user["id"]))


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
) -> dict[str, str]:
    delete_user_session(session_id, user["id"])
    return success_payload(message="会话已删除。")


@router.post("/sessions/{session_id}/messages")
async def create_chat_message_api(
    session_id: str,
    request: ChatMessageRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    payload = create_session_message(
        session_id=session_id,
        user=user,
        message_text=request.message,
        model_name=request.model_name,
        client_host=http_request.client.host if http_request.client else "local",
    )
    return success_payload(**payload)
