from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.core.pagination import decode_cursor, encode_cursor
from backend.app.schemas import (
    FarmRecordCreateRequest,
    FarmTaskCreateRequest,
    FarmTaskUpdateRequest,
    PlotCreateRequest,
    PlotUpdateRequest,
)
from backend.app.services.farm import (
    create_user_farm_record,
    create_user_farm_task,
    create_user_plot,
    delete_user_farm_record,
    delete_user_farm_task,
    delete_user_plot,
    list_user_farm_records,
    list_user_farm_tasks,
    list_user_plots,
    summarize_user_farm_economics,
    summarize_user_farm_records,
    update_user_farm_task,
    update_user_plot,
)


router = APIRouter(prefix="/api", tags=["farm"])

# 允许值放在这里而不是数据库 CHECK 约束里：tool_records 的 CHECK 曾导致新增
# 取值只能整表重建，这里改一个集合即可扩展。
FARM_RECORD_KINDS = ("播种", "施肥", "打药", "灌溉", "除草", "采收", "其他")


@router.get("/plots")
async def list_plots_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return success_payload(plots=list_user_plots(user["id"]))


@router.post("/plots")
async def create_plot_api(
    request: PlotCreateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    plot = create_user_plot(
        user_id=user["id"],
        client_host=client_host,
        name=request.name,
        area_mu=request.area_mu,
        soil_type=request.soil_type,
        irrigation=request.irrigation,
        crop=request.crop,
        planted_on=request.planted_on,
        notes=request.notes,
    )
    return success_payload(plot=plot)


@router.patch("/plots/{plot_id}")
async def update_plot_api(
    plot_id: str,
    request: PlotUpdateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    plot = update_user_plot(
        plot_id=plot_id,
        user_id=user["id"],
        client_host=client_host,
        name=request.name,
        area_mu=request.area_mu,
        soil_type=request.soil_type,
        irrigation=request.irrigation,
        crop=request.crop,
        planted_on=request.planted_on,
        notes=request.notes,
    )
    return success_payload(plot=plot)


@router.delete("/plots/{plot_id}")
async def delete_plot_api(
    plot_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    removed_records, removed_tasks = delete_user_plot(plot_id, user["id"], client_host)
    return success_payload(
        message="地块已删除。",
        deleted_records=removed_records,
        deleted_tasks=removed_tasks,
    )


@router.get("/farm-records")
async def list_farm_records_api(
    plot_id: str | None = Query(default=None, max_length=64, description="按地块筛选。"),
    limit: int = Query(default=20, ge=1, le=100, description="每页数量。"),
    cursor: str | None = Query(default=None, max_length=512, description="分页游标。"),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    try:
        parsed_cursor = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    records, has_more = list_user_farm_records(
        user["id"],
        plot_id=plot_id,
        limit=limit,
        cursor=parsed_cursor,
    )
    next_cursor = None
    if has_more and records:
        next_cursor = encode_cursor(records[-1]["happened_on"], records[-1]["id"])
    return success_payload(records=records, pagination={"has_more": has_more, "next_cursor": next_cursor})


@router.post("/farm-records")
async def create_farm_record_api(
    request: FarmRecordCreateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    normalized_kind = request.kind.strip()
    if normalized_kind not in FARM_RECORD_KINDS:
        raise HTTPException(status_code=400, detail="作业类型只能是：" + "、".join(FARM_RECORD_KINDS) + "。")
    client_host = http_request.client.host if http_request.client else "local"
    record = create_user_farm_record(
        user_id=user["id"],
        client_host=client_host,
        plot_id=request.plot_id,
        kind=normalized_kind,
        happened_on=request.happened_on,
        crop=request.crop,
        detail=request.detail,
        quantity=request.quantity,
        cost=request.cost,
        material=request.material,
        safe_days=request.safe_days,
        yield_kg=request.yield_kg,
        unit_price=request.unit_price,
    )
    return success_payload(record=record)


@router.delete("/farm-records/{record_id}")
async def delete_farm_record_api(
    record_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    delete_user_farm_record(record_id, user["id"], client_host)
    return success_payload(message="农事记录已删除。")


@router.get("/farm-records/stats")
async def farm_records_stats_api(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**summarize_user_farm_records(user["id"]))


@router.get("/farm-records/economics")
async def farm_records_economics_api(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**summarize_user_farm_economics(user["id"]))



@router.get("/farm-tasks")
async def list_farm_tasks_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    """一次返回未完成待办与最近完成的若干条。

    待办量级很小（未完成通常几十条），所以不做游标分页；已完成的历史
    只回最近一批，避免为了一个计数把所有历史都传出来。
    """
    return success_payload(**list_user_farm_tasks(user["id"]))


@router.post("/farm-tasks")
async def create_farm_task_api(
    request: FarmTaskCreateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    task = create_user_farm_task(
        user_id=user["id"],
        client_host=client_host,
        plot_id=request.plot_id,
        title=request.title,
        due_on=request.due_on,
        notes=request.notes,
    )
    return success_payload(task=task)


@router.patch("/farm-tasks/{task_id}")
async def update_farm_task_api(
    task_id: str,
    request: FarmTaskUpdateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    task = update_user_farm_task(
        task_id=task_id,
        user_id=user["id"],
        client_host=client_host,
        plot_id=request.plot_id,
        title=request.title,
        due_on=request.due_on,
        notes=request.notes,
        done=request.done,
    )
    return success_payload(task=task)


@router.delete("/farm-tasks/{task_id}")
async def delete_farm_task_api(
    task_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    delete_user_farm_task(task_id, user["id"], client_host)
    return success_payload(message="待办事项已删除。")
