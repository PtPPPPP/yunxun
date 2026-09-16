import logging
from typing import Any

from backend.app.core.audit import log_event
from backend.app.core.errors import not_found
from backend.app.core.security import safe_fingerprint
from backend.app.repositories import (
    create_plot,
    delete_plot_with_records,
    get_plot,
    list_plots,
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


def list_user_plots(user_id: str) -> list[dict[str, Any]]:
    return list_plots(user_id)


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
