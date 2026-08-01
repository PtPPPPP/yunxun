from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.repositories import public_user
from backend.app.schemas import LoginRequest, ProfileUpdateRequest, RegisterRequest
from backend.app.services.auth import get_current_user_from_header, guest_login, login_user, logout_user, register_user, update_profile
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import safe_fingerprint
from backend.app.core.config import get_settings
from backend.app.core.csrf import CSRF_COOKIE_NAME, create_csrf_token


router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_rate_limiter = InMemoryRateLimiter()


def _limit_auth(request: Request) -> None:
    host = request.client.host if request.client else "local"
    auth_rate_limiter.check(f"auth:{safe_fingerprint(host)}", 20, 60)


def _set_browser_session(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie("yunxun_session", token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)
    response.set_cookie(CSRF_COOKIE_NAME, create_csrf_token(), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)


@router.post("/register")
async def register_api(request: RegisterRequest, http_request: Request, response: Response) -> dict[str, object]:
    _limit_auth(http_request)
    payload = register_user(request.username, request.password, request.display_name)
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.get("/csrf", include_in_schema=False)
async def csrf_api(response: Response) -> dict[str, object]:
    settings = get_settings()
    response.set_cookie(CSRF_COOKIE_NAME, create_csrf_token(), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)
    return success_payload(message="CSRF token issued")


@router.post("/login")
async def login_api(request: LoginRequest, http_request: Request, response: Response) -> dict[str, object]:
    _limit_auth(http_request)
    payload = login_user(request.username, request.password)
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.post("/guest")
async def guest_login_api(request: Request, response: Response) -> dict[str, object]:
    _limit_auth(request)
    payload = guest_login()
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.post("/logout")
async def logout_api(http_request: Request, response: Response, authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization and http_request.cookies.get("yunxun_session"):
        authorization = f"Bearer {http_request.cookies['yunxun_session']}"
    user_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_current_user_from_header(authorization)["id"]
        except HTTPException:
            user_id = None
    logout_user(authorization, user_id=user_id)
    response.delete_cookie("yunxun_session", path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
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
