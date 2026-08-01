from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.schemas import ModelConfigCreateRequest, ModelConfigTestRequest, ModelConfigUpdateRequest
from backend.app.services.model_configs import (
    create_user_model_config,
    delete_user_model_config,
    model_config_status,
    set_user_default_model_config,
    test_unsaved_model_config,
    update_user_model_config,
    verify_saved_model_config,
)


router = APIRouter(prefix="/api/model-configs", tags=["model-configs"])


@router.get("")
async def list_model_configs_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return success_payload(**model_config_status(user["id"]))


@router.post("")
async def create_model_config_api(
    payload: ModelConfigCreateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(config=create_user_model_config(user["id"], payload))


@router.put("/{config_id}")
async def update_model_config_api(
    config_id: str,
    payload: ModelConfigUpdateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(config=update_user_model_config(user["id"], config_id, payload))


@router.delete("/{config_id}")
async def delete_model_config_api(
    config_id: str,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    delete_user_model_config(user["id"], config_id)
    return success_payload(message="模型配置已删除。")


@router.post("/{config_id}/set-default")
async def set_default_model_config_api(
    config_id: str,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    return success_payload(config=set_user_default_model_config(user["id"], config_id))


@router.post("/test")
async def test_model_config_api(
    payload: ModelConfigTestRequest,
    request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    host = request.client.host if request.client else "unknown"
    return success_payload(**await test_unsaved_model_config(user["id"], host, payload))


@router.post("/{config_id}/verify")
async def verify_model_config_api(
    config_id: str,
    request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    host = request.client.host if request.client else "unknown"
    return success_payload(**await verify_saved_model_config(user["id"], host, config_id))
