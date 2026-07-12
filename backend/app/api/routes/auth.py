from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.repositories import public_user
from backend.app.schemas import LoginRequest, ProfileUpdateRequest, RegisterRequest
from backend.app.services.auth import get_current_user_from_header, guest_login, login_user, logout_user, register_user, update_profile
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import safe_fingerprint


router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_rate_limiter = InMemoryRateLimiter()


def _limit_auth(request: Request) -> None:
    host = request.client.host if request.client else "local"
    auth_rate_limiter.check(f"auth:{safe_fingerprint(host)}", 20, 60)


@router.post("/register")
async def register_api(request: RegisterRequest, http_request: Request) -> dict[str, object]:
    _limit_auth(http_request)
    payload = register_user(request.username, request.password, request.display_name)
    return success_payload(**payload)


@router.post("/login")
async def login_api(request: LoginRequest, http_request: Request) -> dict[str, object]:
    _limit_auth(http_request)
    payload = login_user(request.username, request.password)
    return success_payload(**payload)


@router.post("/guest")
async def guest_login_api(request: Request) -> dict[str, object]:
    _limit_auth(request)
    payload = guest_login()
    return success_payload(**payload)


@router.post("/logout")
async def logout_api(authorization: str | None = Header(default=None)) -> dict[str, str]:
    user_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_current_user_from_header(authorization)["id"]
        except HTTPException:
            user_id = None
    logout_user(authorization, user_id=user_id)
    return success_payload(message="已退出登录。")


@router.get("/me", include_in_schema=False)
async def auth_me_api(user: dict[str, str] = Depends(get_current_user)) -> dict[str, object]:
    return success_payload(user=public_user(user))


@router.patch("/profile", include_in_schema=False)
async def auth_profile_api(
    request: ProfileUpdateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    updated_user = update_profile(user["id"], request.display_name, request.preferred_model)
    return success_payload(user=updated_user)
