import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.errors import conflict, not_found
from backend.app.core.security import safe_fingerprint
from backend.app.repositories import (
    ECONOMICS_SCOPES,
    count_farm_records,
    create_season,
    count_plots,
    create_farm_record,
    create_farm_task,
    create_plot,
    delete_farm_record,
    delete_farm_task,
    delete_plot_with_records,
    delete_season,
    get_farm_record,
    get_active_season,
    get_farm_task,
    get_plot,
    get_season,
    list_farm_records_page,
    list_farm_record_years,
    list_harvest_safety,
    list_open_farm_tasks,
    list_plots,
    list_recent_done_farm_tasks,
    list_seasons,
    summarize_farm_economics,
    update_farm_task,
    update_farm_record,
    update_plot,
    update_season,
)


logger = logging.getLogger("yunxun.backend.farm")


def require_plot_owner(plot_id: str, user_id: str) -> dict[str, Any]:
    """校验地块归属。

    地块不存在和地块属于别人都返回 404：不让调用方通过状态码探测别人是否
    存在某个地块。
    """
    plot = get_plot(plot_id)
    if not plot or plot["user_id"] != user_id:
        raise not_found("地块不存在或已被删除。")
    return plot


def _plot_by_id(user_id: str, plot_id: str) -> dict[str, Any]:
    """从地块列表里取回单块地，这样带出的茬次字段与列表完全一致。"""
    for item in list_plots(user_id):
        if item["id"] == plot_id:
            return item
    raise not_found("地块不存在或已被删除。")


def require_season_owner(season_id: str, user_id: str) -> dict[str, Any]:
    season = get_season(season_id)
    if not season or season["user_id"] != user_id:
        raise not_found("茬次不存在或已被删除。")
    return season


def list_user_seasons(user_id: str, *, plot_id: str | None = None) -> list[dict[str, Any]]:
    return list_seasons(user_id, plot_id=plot_id)


def create_user_season(
    user_id: str,
    client_host: str,
    plot_id: str,
    crop: str,
    started_on: str | None,
    notes: str,
) -> dict[str, Any]:
    require_plot_owner(plot_id, user_id)
    active = get_active_season(plot_id)
    if active:
        # 不静默改写上一茬的结束日：让农户自己决定那一茬什么时候结束。
        raise conflict(f"该地块还有进行中的茬次（{active['crop']}），请先结束它再开始新茬。")
    season = create_season(
        user_id=user_id,
        plot_id=plot_id,
        crop=crop.strip(),
        started_on=started_on or None,
        notes=notes.strip(),
    )
    log_event(
        logger,
        "season_create",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        season_id=season["id"],
        plot_id=plot_id,
        crop=season["crop"],
    )
    return season


def update_user_season(
    season_id: str,
    user_id: str,
    client_host: str,
    crop: str,
    started_on: str | None,
    ended_on: str | None,
    notes: str,
) -> dict[str, Any]:
    existing = require_season_owner(season_id, user_id)
    if started_on and ended_on and ended_on < started_on:
        raise HTTPException(status_code=422, detail="结束日期不能早于开始日期。")
    if ended_on is None:
        active = get_active_season(existing["plot_id"])
        if active and active["id"] != season_id:
            raise conflict("该地块已有进行中的茬次，请先结束它再重开旧茬。")
    season = update_season(
        season_id,
        crop=crop.strip(),
        started_on=started_on or None,
        ended_on=ended_on or None,
        notes=notes.strip(),
    )
    log_event(
        logger,
        "season_update",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        season_id=season_id,
        active=season["active"],
    )
    return season


def delete_user_season(season_id: str, user_id: str, client_host: str) -> None:
    require_season_owner(season_id, user_id)
    delete_season(season_id)
    log_event(
        logger,
        "season_delete",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        season_id=season_id,
    )


def list_user_plots(user_id: str, *, today: str | None = None) -> list[dict[str, Any]]:
    return list_plots(user_id, reference_date=today)


def create_user_plot(
    user_id: str,
    client_host: str,
    name: str,
    area_mu: float,
    soil_type: str,
    irrigation: str,
    crop: str,
    planted_on: str | None,
    notes: str,
) -> dict[str, Any]:
    plot = create_plot(
        user_id=user_id,
        name=name.strip(),
        area_mu=area_mu,
        soil_type=soil_type.strip(),
        irrigation=irrigation.strip(),
        notes=notes.strip(),
    )
    # 建地块时填的作物与日期就是第一茬，顺手建出来，省得再点一次「开始新茬」。
    create_season(
        user_id=user_id,
        plot_id=plot["id"],
        crop=crop.strip(),
        started_on=planted_on or None,
        notes="",
    )
    log_event(
        logger,
        "plot_create",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot["id"],
        crop=crop.strip(),
    )
    return _plot_by_id(user_id, plot["id"])


def update_user_plot(
    plot_id: str,
    user_id: str,
    client_host: str,
    name: str,
    area_mu: float,
    soil_type: str,
    irrigation: str,
    crop: str,
    planted_on: str | None,
    notes: str,
) -> dict[str, Any]:
    require_plot_owner(plot_id, user_id)
    update_plot(
        plot_id,
        name=name.strip(),
        area_mu=area_mu,
        soil_type=soil_type.strip(),
        irrigation=irrigation.strip(),
        notes=notes.strip(),
    )
    # 兼容旧界面：地块编辑里给了作物就改当前茬次的作物与开始日。
    if crop is not None and crop.strip():
        active = get_active_season(plot_id)
        if active:
            update_season(
                active["id"],
                crop=crop.strip(),
                started_on=planted_on or None,
                ended_on=None,
                notes=active["notes"],
            )
    plot = _plot_by_id(user_id, plot_id)
    log_event(
        logger,
        "plot_update",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot_id,
        crop=plot["crop"],
    )
    return plot


def delete_user_plot(plot_id: str, user_id: str, client_host: str, expected_revision: str | None = None) -> tuple[int, int]:
    """地块移入回收站，子项继承可见性；保留原响应计数字段。"""
    require_plot_owner(plot_id, user_id)
    removed_records, removed_tasks = delete_plot_with_records(plot_id, user_id, expected_revision)
    log_event(
        logger,
        "plot_delete",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot_id,
        removed_records=removed_records,
        removed_tasks=removed_tasks,
    )
    return removed_records, removed_tasks


def list_user_farm_records(
    user_id: str,
    *,
    plot_id: str | None,
    limit: int,
    cursor: tuple[str, str] | None,
    kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    season_id: str | None = None,
    economics_scope: str = "all",
    year: int | None = None,
    data_scope: str = "all",
) -> tuple[list[dict[str, Any]], bool]:
    validate_farm_record_filters(user_id, plot_id=plot_id, season_id=season_id, date_from=date_from,
                                 date_to=date_to, economics_scope=economics_scope, data_scope=data_scope)
    return list_farm_records_page(user_id, plot_id=plot_id, limit=limit, cursor=cursor,
                                  kind=kind, date_from=date_from, date_to=date_to, season_id=season_id,
                                  economics_scope=economics_scope, year=year, data_scope=data_scope)


def validate_farm_record_filters(
    user_id: str, *, plot_id: str | None = None, season_id: str | None = None,
    date_from: str | None = None, date_to: str | None = None,
    economics_scope: str = "all", data_scope: str = "all",
) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="筛选结束日期不能早于开始日期。")
    _validate_record_season_filter(user_id, plot_id, season_id)
    validate_data_scope(data_scope)
    if economics_scope not in ECONOMICS_SCOPES:
        raise HTTPException(status_code=422, detail="收支明细类型无效。")


def _validate_record_season_filter(user_id: str, plot_id: str | None, season_id: str | None) -> None:
    if season_id and season_id != "unassigned":
        season = require_season_owner(season_id, user_id)
        if plot_id and season["plot_id"] != plot_id:
            raise not_found("茬次不属于该地块。")


def _prepare_farm_record(
    user_id: str,
    plot_id: str,
    kind: str,
    happened_on: str,
    crop: str,
    detail: str,
    quantity: str,
    cost: float | None,
    material: str = "",
    safe_days: int | None = None,
    yield_kg: float | None = None,
    unit_price: float | None = None,
    season_id: str | None = None,
    auto_select_season: bool = True,
) -> dict[str, Any]:
    require_plot_owner(plot_id, user_id)
    season = None
    if season_id is not None:
        season = require_season_owner(season_id, user_id)
        if season["plot_id"] != plot_id:
            raise not_found("茬次不属于该地块。")
        if ((season["started_on"] and happened_on < season["started_on"])
                or (season["ended_on"] and happened_on > season["ended_on"])):
            raise HTTPException(status_code=422, detail="作业日期不在所选茬次的起止日期内。")
    elif auto_select_season:
        candidates = [
            item for item in list_seasons(user_id, plot_id=plot_id)
            if (not item["started_on"] or item["started_on"] <= happened_on)
            and (not item["ended_on"] or happened_on <= item["ended_on"])
        ]
        if len(candidates) > 1 or (candidates and not candidates[0]["started_on"]):
            raise HTTPException(status_code=422, detail="无法按日期唯一确定茬次，请选择具体茬次或明确选择未归茬。")
        if candidates:
            season = candidates[0]
    return dict(
        plot_id=plot_id,
        season_id=season["id"] if season else None,
        kind=kind,
        happened_on=happened_on,
        crop=crop.strip() or (season["crop"] if season else ""),
        detail=detail.strip(),
        quantity=quantity.strip(),
        cost=cost,
        material=material.strip() if kind in {"施肥", "打药"} else "",
        safe_days=safe_days if kind == "打药" else None,
        yield_kg=yield_kg if kind == "采收" else None,
        unit_price=unit_price if kind == "采收" else None,
    )


def create_user_farm_record(
    user_id: str,
    client_host: str,
    plot_id: str,
    kind: str,
    happened_on: str,
    crop: str,
    detail: str,
    quantity: str,
    cost: float | None,
    material: str = "",
    safe_days: int | None = None,
    yield_kg: float | None = None,
    unit_price: float | None = None,
    season_id: str | None = None,
    auto_select_season: bool = True,
    submission_id: str | None = None,
) -> dict[str, Any]:
    values = _prepare_farm_record(
        user_id, plot_id, kind, happened_on, crop, detail, quantity, cost,
        material, safe_days, yield_kg, unit_price, season_id, auto_select_season,
    )
    # 用户参与派生主键，其他用户即使使用相同提交标识也无法命中本人的记录。
    record_id = uuid.uuid5(uuid.NAMESPACE_URL, f"yunxun:{user_id}:{submission_id}").hex if submission_id else None
    record = create_farm_record(user_id=user_id, record_id=record_id, **values)
    log_event(
        logger,
        "farm_record_create",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        record_id=record["id"],
        plot_id=plot_id,
        kind=kind,
        happened_on=happened_on,
    )
    return record


def update_user_farm_record(
    record_id: str, user_id: str, client_host: str, **values: Any,
) -> dict[str, Any]:
    existing = get_farm_record(record_id)
    if not existing or existing["user_id"] != user_id:
        raise not_found("农事记录不存在或已被删除。")
    prepared = _prepare_farm_record(user_id=user_id, **values)
    record = update_farm_record(record_id, user_id, **prepared)
    log_event(logger, "farm_record_update", user_id=user_id,
              client_fingerprint=safe_fingerprint(client_host), record_id=record_id,
              plot_id=record["plot_id"], kind=record["kind"], happened_on=record["happened_on"])
    return record


def delete_user_farm_record(record_id: str, user_id: str, client_host: str) -> None:
    record = get_farm_record(record_id)
    if not record or record["user_id"] != user_id:
        raise not_found("农事记录不存在或已被删除。")
    delete_farm_record(record_id, user_id)
    log_event(
        logger,
        "farm_record_delete",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        record_id=record_id,
        plot_id=record["plot_id"],
    )


def summarize_user_farm_records(user_id: str) -> dict[str, int]:
    return {"plot_count": count_plots(user_id), "record_count": count_farm_records(user_id)}


def summarize_user_farm_economics(
    user_id: str, *, plot_id: str | None = None, season_id: str | None = None, year: int | None = None, data_scope: str = "all",
) -> dict[str, Any]:
    if plot_id:
        require_plot_owner(plot_id, user_id)
    _validate_record_season_filter(user_id, plot_id, season_id)
    validate_data_scope(data_scope)
    return {
        "plots": summarize_farm_economics(user_id, plot_id=plot_id, season_id=season_id, year=year, data_scope=data_scope),
        "available_years": list_farm_record_years(user_id, data_scope),
        "year_basis": "happened_on",
    }


def validate_data_scope(data_scope: str) -> None:
    if data_scope not in {"all", "real", "demo"}:
        raise HTTPException(status_code=422, detail="数据来源只能是全部、真实或演示。")


def require_task_owner(task_id: str, user_id: str) -> dict[str, Any]:
    task = get_farm_task(task_id)
    if not task or task["user_id"] != user_id:
        raise not_found("待办事项不存在或已被删除。")
    return task


def list_user_farm_tasks(user_id: str) -> dict[str, Any]:
    return {
        "tasks": list_open_farm_tasks(user_id),
        "recent_done": list_recent_done_farm_tasks(user_id),
    }


def create_user_farm_task(
    user_id: str,
    client_host: str,
    plot_id: str | None,
    title: str,
    due_on: str,
    notes: str,
) -> dict[str, Any]:
    if plot_id:
        require_plot_owner(plot_id, user_id)
    task = create_farm_task(
        user_id=user_id,
        plot_id=plot_id or None,
        title=title.strip(),
        due_on=due_on,
        notes=notes.strip(),
    )
    log_event(
        logger,
        "farm_task_create",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        task_id=task["id"],
        plot_id=plot_id or "",
        due_on=due_on,
    )
    return task


def update_user_farm_task(
    task_id: str,
    user_id: str,
    client_host: str,
    plot_id: str | None,
    title: str,
    due_on: str,
    notes: str,
    done: bool,
) -> dict[str, Any]:
    require_task_owner(task_id, user_id)
    if plot_id:
        require_plot_owner(plot_id, user_id)
    task = update_farm_task(
        task_id,
        plot_id=plot_id or None,
        title=title.strip(),
        due_on=due_on,
        notes=notes.strip(),
        done=done,
    )
    log_event(
        logger,
        "farm_task_update",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        task_id=task_id,
        done=done,
    )
    return task


def delete_user_farm_task(task_id: str, user_id: str, client_host: str) -> None:
    require_task_owner(task_id, user_id)
    delete_farm_task(task_id)
    log_event(
        logger,
        "farm_task_delete",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        task_id=task_id,
    )

