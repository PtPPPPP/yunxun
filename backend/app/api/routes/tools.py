from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.core.pagination import decode_cursor, encode_cursor
from backend.app.repositories import (
    count_tool_records_by_kind,
    list_tool_records_page,
    summarize_tool_records,
)
from backend.app.schemas import DecisionRequest
from backend.app.services.tools import create_decision_advice


router = APIRouter(prefix="/api", tags=["tools"])

TOOL_RECORD_KINDS = {"decision"}


@router.post("/decision")
async def decision_api(
    request: DecisionRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    payload = create_decision_advice(
        user_id=user["id"],
        client_host=client_host,
        crop=request.crop,
        stage=request.stage,
        rain_prob=request.rain_prob,
        soil_moisture=request.soil_moisture,
        temperature=request.temperature,
    )
    return success_payload(**payload)


@router.get("/tool-records")
async def list_tool_records_api(
    kind: str | None = Query(default=None, description="记录类型：decision，不传则返回全部。"),
    limit: int = Query(default=20, ge=1, le=100, description="每页数量。"),
    cursor: str | None = Query(default=None, max_length=512, description="分页游标。"),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    normalized_kind = (kind or "").strip().lower() or None
    if normalized_kind and normalized_kind not in TOOL_RECORD_KINDS:
        raise HTTPException(status_code=400, detail="kind 只支持 decision。")
    try:
        parsed_cursor = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    records, has_more = list_tool_records_page(
        user["id"],
        kind=normalized_kind,
        limit=limit,
        cursor=parsed_cursor,
    )
    next_cursor = None
    if has_more and records:
        next_cursor = encode_cursor(records[-1]["created_at"], records[-1]["id"])
    return success_payload(records=records, pagination={"has_more": has_more, "next_cursor": next_cursor})


@router.get("/tool-records/stats")
async def tool_records_stats_api(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    summary = summarize_tool_records(user["id"])
    return success_payload(
        counts_by_kind=count_tool_records_by_kind(user["id"]),
        by_day=summary["by_day"],
        by_day_since=summary["since"],
        by_day_days=summary["days"],
        top_crops=summary["top_crops"],
    )
