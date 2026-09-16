from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.schemas import PlotCreateRequest, PlotUpdateRequest
from backend.app.services.farm import (
    create_user_plot,
    delete_user_plot,
    list_user_plots,
    update_user_plot,
)


router = APIRouter(prefix="/api", tags=["farm"])


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
    removed_records = delete_user_plot(plot_id, user["id"], client_host)
    return success_payload(message="地块已删除。", deleted_records=removed_records)
