import logging
from datetime import datetime
from typing import Any

from backend.app.core.audit import log_event
from backend.app.core.errors import not_found
from backend.app.core.security import safe_fingerprint
from backend.app.repositories import (
    count_farm_records,
    count_plots,
    create_farm_record,
    create_plot,
    delete_farm_record,
    delete_plot_with_records,
    get_farm_record,
    get_plot,
    list_farm_records_page,
    list_harvest_safety,
    list_plots,
    summarize_farm_economics,
    update_plot,
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
        crop=crop.strip(),
        planted_on=planted_on or None,
        notes=notes.strip(),
    )
    log_event(
        logger,
        "plot_create",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot["id"],
        crop=plot["crop"],
    )
    return plot


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
    plot = update_plot(
        plot_id,
        name=name.strip(),
        area_mu=area_mu,
        soil_type=soil_type.strip(),
        irrigation=irrigation.strip(),
        crop=crop.strip(),
        planted_on=planted_on or None,
        notes=notes.strip(),
    )
    log_event(
        logger,
        "plot_update",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot_id,
        crop=plot["crop"],
    )
    return plot


def delete_user_plot(plot_id: str, user_id: str, client_host: str) -> int:
    """删除地块，连带删除其作业记录，返回被删除的记录条数。"""
    require_plot_owner(plot_id, user_id)
    removed_records = delete_plot_with_records(plot_id)
    log_event(
        logger,
        "plot_delete",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        plot_id=plot_id,
        removed_records=removed_records,
    )
    return removed_records


def list_user_farm_records(
    user_id: str,
    *,
    plot_id: str | None,
    limit: int,
    cursor: tuple[str, str] | None,
) -> tuple[list[dict[str, Any]], bool]:
    return list_farm_records_page(user_id, plot_id=plot_id, limit=limit, cursor=cursor)


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
) -> dict[str, Any]:
    plot = require_plot_owner(plot_id, user_id)
    record = create_farm_record(
        user_id=user_id,
        plot_id=plot_id,
        kind=kind,
        happened_on=happened_on,
        # 作物默认取地块当前作物，允许改写以保留轮作历史。
        crop=crop.strip() or plot["crop"],
        detail=detail.strip(),
        quantity=quantity.strip(),
        cost=cost,
        material=material.strip(),
        safe_days=safe_days,
        yield_kg=yield_kg,
        unit_price=unit_price,
    )
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


def delete_user_farm_record(record_id: str, user_id: str, client_host: str) -> None:
    record = get_farm_record(record_id)
    if not record or record["user_id"] != user_id:
        raise not_found("农事记录不存在或已被删除。")
    delete_farm_record(record_id)
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


def summarize_user_farm_economics(user_id: str) -> dict[str, Any]:
    return {"plots": summarize_farm_economics(user_id)}

