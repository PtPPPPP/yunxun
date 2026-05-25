from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.repositories import public_user
from backend.app.schemas import ProfileUpdateRequest
from backend.app.services.auth import update_profile
from backend.app.services.system import build_health_payload


router = APIRouter(tags=["system"])


@router.get("/")
async def root_api() -> dict[str, str]:
    return success_payload(message="云寻 AI 后端已启动。")


@router.get("/api/health")
async def health_api() -> dict[str, object]:
    return success_payload(**build_health_payload())


@router.get("/api/me")
async def me_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return success_payload(user=public_user(user))


@router.patch("/api/me/profile")
async def profile_api(
    request: ProfileUpdateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    updated_user = update_profile(user["id"], request.display_name, request.preferred_model)
    return success_payload(user=updated_user)
