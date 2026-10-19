from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.core.pagination import decode_cursor, encode_cursor
from backend.app.schemas import (
    FarmRecordCreateRequest,
    FarmRecordSubmissionRequest,
    OnboardingUpdateRequest,
    IsoDate,
    FarmTaskCreateRequest,
    FarmTaskUpdateRequest,
    PlotCreateRequest,
    PlotUpdateRequest,
    SeasonCreateRequest,
    SeasonUpdateRequest,
)
from backend.app.services.farm import (
    create_user_farm_record,
    create_user_farm_task,
    create_user_plot,
    create_user_season,
    delete_user_farm_record,
    delete_user_farm_task,
    delete_user_plot,
    delete_user_season,
    list_user_farm_records,
    list_user_farm_tasks,
    list_user_plots,
    list_user_seasons,
    summarize_user_farm_economics,
    summarize_user_farm_records,
    update_user_farm_task,
    update_user_farm_record,
    update_user_plot,
    update_user_season,
)
from backend.app.repositories_onboarding import (
    onboarding_status, set_onboarding_skipped, load_demo_data, clear_demo_data,
)
from backend.app.services.exports import export_user_economics, export_user_records
from backend.app import repositories_trash as trash
from backend.app.core.audit import log_event
from backend.app.services.farm import logger as farm_logger


router = APIRouter(prefix="/api", tags=["farm"])


@router.get("/onboarding")
def onboarding_api(user: dict = Depends(get_current_user)) -> dict:
    return success_payload(onboarding=onboarding_status(user["id"]))


@router.patch("/onboarding")
def update_onboarding_api(request: OnboardingUpdateRequest, user: dict = Depends(get_current_user)) -> dict:
    set_onboarding_skipped(user["id"], request.skipped)
    return success_payload(onboarding=onboarding_status(user["id"]))


@router.post("/demo-data")
def load_demo_api(user: dict = Depends(get_current_user)) -> dict:
    already_loaded = load_demo_data(user["id"])
    return success_payload(already_loaded=already_loaded, onboarding=onboarding_status(user["id"]))


@router.delete("/demo-data")
def clear_demo_api(user: dict = Depends(get_current_user)) -> dict:
    result = clear_demo_data(user["id"])
    return success_payload(**result, onboarding=onboarding_status(user["id"]))

# 允许值放在这里而不是数据库 CHECK 约束里：tool_records 的 CHECK 曾导致新增
# 取值只能整表重建，这里改一个集合即可扩展。
FARM_RECORD_KINDS = ("播种", "施肥", "打药", "灌溉", "除草", "采收", "其他")


def normalize_record_kind(kind: str) -> str:
    normalized = kind.strip()
    if normalized not in FARM_RECORD_KINDS:
        raise HTTPException(status_code=400, detail="作业类型只能是：" + "、".join(FARM_RECORD_KINDS) + "。")
    return normalized


def record_write_values(request: FarmRecordCreateRequest) -> dict:
    return {**request.model_dump(exclude={"submission_id"}), "kind": normalize_record_kind(request.kind),
            "auto_select_season": "season_id" not in request.model_fields_set}


@router.get("/plots")
def list_plots_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return success_payload(plots=list_user_plots(user["id"]))


@router.post("/plots")
def create_plot_api(
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
def update_plot_api(
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
def delete_plot_api(
    plot_id: str,
    http_request: Request,
    expected_revision: str | None = Query(default=None, max_length=128),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    removed_records, removed_tasks = delete_user_plot(plot_id, user["id"], client_host, expected_revision)
    return success_payload(
        message="地块已移入回收站，关联资料保留，可在回收站恢复。",
        deleted_records=removed_records,
        deleted_tasks=removed_tasks,
    )


@router.get("/plots/{plot_id}/delete-impact")
def plot_delete_impact_api(plot_id: str, response: Response, user: dict = Depends(get_current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return success_payload(impact=trash.plot_delete_impact(plot_id, user["id"]))


@router.get("/trash")
def trash_list_api(response: Response, user: dict = Depends(get_current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return success_payload(**trash.list_trash(user["id"]))


@router.post("/trash/{kind}/{entity_id}/restore")
def trash_restore_api(kind: str, entity_id: str, user: dict = Depends(get_current_user)) -> dict:
    if kind not in {"plots", "records"}:
        raise HTTPException(404, "回收站类型不存在。")
    changed = (trash.restore_plot if kind == "plots" else trash.restore_record)(entity_id, user["id"])
    log_event(farm_logger, "trash_restore", user_id=user["id"], kind=kind, entity_id=entity_id, changed=changed)
    return success_payload(changed=changed, message="资料已恢复。" if changed else "资料已经恢复，无需重复操作。")


@router.delete("/trash/{kind}/{entity_id}")
def trash_purge_api(kind: str, entity_id: str, confirm: bool = False,
    expected_revision: str = Query(..., min_length=1, max_length=128), user: dict = Depends(get_current_user)) -> dict:
    if kind not in {"plots", "records"}:
        raise HTTPException(404, "回收站类型不存在。")
    if not confirm:
        raise HTTPException(422, "请明确确认最终删除，此操作无法从回收站恢复。")
    (trash.purge_plot if kind == "plots" else trash.purge_record)(entity_id, user["id"], expected_revision)
    log_event(farm_logger, "trash_purge", user_id=user["id"], kind=kind, entity_id=entity_id)
    return success_payload(message="已最终删除，无法再从回收站恢复。")


@router.get("/farm-records")
def list_farm_records_api(
    plot_id: str | None = Query(default=None, max_length=64, description="按地块筛选。"),
    kind: str | None = Query(default=None, max_length=16, description="按作业类型筛选。"),
    date_from: IsoDate | None = None,
    date_to: IsoDate | None = None,
    season_id: str | None = Query(default=None, max_length=64, description="茬次 ID；unassigned 表示未归茬。"),
    economics_scope: str = Query(default="all", max_length=32, description="收支或待补录明细类型。"),
    data_scope: str = Query(default="all", max_length=16, description="all、real 或 demo，按记录来源筛选。"),
    year: int | None = Query(default=None, ge=1, le=9999, description="按作业日期所属年份筛选。"),
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
        kind=normalize_record_kind(kind) if kind is not None else None,
        date_from=date_from,
        date_to=date_to,
        season_id=season_id,
        economics_scope=economics_scope,
        data_scope=data_scope,
        year=year,
    )
    next_cursor = None
    if has_more and records:
        next_cursor = encode_cursor(records[-1]["happened_on"], records[-1]["id"])
    return success_payload(records=records, pagination={"has_more": has_more, "next_cursor": next_cursor})


@router.post("/farm-records")
def create_farm_record_api(
    request: FarmRecordSubmissionRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    record = create_user_farm_record(
        user_id=user["id"],
        client_host=client_host,
        submission_id=str(request.submission_id) if request.submission_id else None,
        **record_write_values(request),
    )
    return success_payload(record=record)


@router.get("/farm-records/export.csv")
def farm_records_csv_api(
    plot_id: str | None = Query(default=None, max_length=64),
    kind: str | None = Query(default=None, max_length=16),
    date_from: IsoDate | None = None, date_to: IsoDate | None = None,
    season_id: str | None = Query(default=None, max_length=64),
    economics_scope: str = Query(default="all", max_length=32),
    data_scope: str = Query(default="all", max_length=16),
    year: int | None = Query(default=None, ge=1, le=9999),
    user: dict = Depends(get_current_user),
) -> Response:
    return export_user_records(user["id"], plot_id=plot_id,
        kind=normalize_record_kind(kind) if kind is not None else None, date_from=date_from, date_to=date_to,
        season_id=season_id, economics_scope=economics_scope, data_scope=data_scope, year=year)


@router.get("/farm-records/economics/export.csv")
def farm_economics_csv_api(
    plot_id: str | None = Query(default=None, max_length=64),
    season_id: str | None = Query(default=None, max_length=64),
    year: int | None = Query(default=None, ge=1, le=9999),
    data_scope: str = Query(default="all", max_length=16),
    user: dict = Depends(get_current_user),
) -> Response:
    return export_user_economics(user["id"], plot_id=plot_id, season_id=season_id, year=year, data_scope=data_scope)


@router.patch("/farm-records/{record_id}")
def update_farm_record_api(
    record_id: str,
    request: FarmRecordCreateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    """与新增共用完整表单，整体替换业务字段；省略 season_id 时重新按日期匹配。"""
    client_host = http_request.client.host if http_request.client else "local"
    record = update_user_farm_record(record_id, user["id"], client_host, **record_write_values(request))
    return success_payload(record=record)


@router.delete("/farm-records/{record_id}")
def delete_farm_record_api(
    record_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    delete_user_farm_record(record_id, user["id"], client_host)
    return success_payload(message="农事记录已移入回收站，可在回收站恢复。")


@router.get("/farm-records/stats")
def farm_records_stats_api(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**summarize_user_farm_records(user["id"]))


@router.get("/farm-records/economics")
def farm_records_economics_api(
    plot_id: str | None = Query(default=None, max_length=64),
    season_id: str | None = Query(default=None, max_length=64),
    year: int | None = Query(default=None, ge=1, le=9999, description="按作业日期所属年份筛选；不筛选茬次开始年份。"),
    data_scope: str = Query(default="all", max_length=16),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(**summarize_user_farm_economics(user["id"], plot_id=plot_id, season_id=season_id, year=year, data_scope=data_scope))



@router.get("/farm-tasks")
def list_farm_tasks_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    """一次返回未完成待办与最近完成的若干条。

    待办量级很小（未完成通常几十条），所以不做游标分页；已完成的历史
    只回最近一批，避免为了一个计数把所有历史都传出来。
    """
    return success_payload(**list_user_farm_tasks(user["id"]))


@router.post("/farm-tasks")
def create_farm_task_api(
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
def update_farm_task_api(
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
def delete_farm_task_api(
    task_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    delete_user_farm_task(task_id, user["id"], client_host)
    return success_payload(message="待办事项已删除。")


@router.get("/seasons")
def list_seasons_api(
    plot_id: str | None = Query(default=None, max_length=64, description="按地块筛选。"),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(seasons=list_user_seasons(user["id"], plot_id=plot_id))


@router.post("/seasons")
def create_season_api(
    request: SeasonCreateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    season = create_user_season(
        user_id=user["id"],
        client_host=client_host,
        plot_id=request.plot_id,
        crop=request.crop,
        started_on=request.started_on,
        notes=request.notes,
    )
    return success_payload(season=season)


@router.patch("/seasons/{season_id}")
def update_season_api(
    season_id: str,
    request: SeasonUpdateRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    season = update_user_season(
        season_id=season_id,
        user_id=user["id"],
        client_host=client_host,
        crop=request.crop,
        started_on=request.started_on,
        ended_on=request.ended_on,
        notes=request.notes,
    )
    return success_payload(season=season)


@router.delete("/seasons/{season_id}")
def delete_season_api(
    season_id: str,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    delete_user_season(season_id, user["id"], client_host)
    return success_payload(message="茬次已删除，它的作业记录已变为未归茬。")
