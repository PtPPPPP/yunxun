import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from backend.app.api.deps import get_current_user, get_session_reference
from backend.app.core.exceptions import success_payload
from backend.app.repositories import public_user
from backend.app.schemas import GuestUpgradeRequest, LoginRequest, LogoutRequest, ProfileUpdateRequest, RegisterRequest, PasswordChangeRequest, PasswordProofRequest, PasswordRecoveryRequest
from backend.app.services.auth import get_current_user_from_header, guest_login, login_user, logout_user, register_user, update_profile, upgrade_guest_user
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import safe_fingerprint
from backend.app.core.config import get_settings
from backend.app.core.csrf import CSRF_COOKIE_NAME, create_csrf_token
from backend.app.core.audit import log_event
from backend.app.repositories_account import manage_credentials, recover_password
from backend.app.services.auth import logger


router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_rate_limiter = InMemoryRateLimiter()
credential_rate_limiter = InMemoryRateLimiter()


def _limit_credential_proof(user_id: str) -> None:
    credential_rate_limiter.cleanup()
    credential_rate_limiter.check(f"proof:{user_id}", 5, 600)


def _clear_browser_session(response: Response) -> None:
    response.delete_cookie("yunxun_session", path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    response.headers["Cache-Control"] = "no-store"


@router.post("/change-password")
def change_password_api(request: PasswordChangeRequest, response: Response, user: dict = Depends(get_current_user)) -> dict[str, object]:
    _limit_credential_proof(user["id"])
    manage_credentials(user, request.current_password, new_password=request.new_password)
    _clear_browser_session(response)
    log_event(logger, "auth_password_changed", user_id=user["id"])
    return success_payload(message="密码已修改，全部设备已退出登录，旧恢复码已失效。请重新登录并生成新恢复码。")


@router.post("/recovery-code")
def recovery_code_api(request: PasswordProofRequest, response: Response, user: dict = Depends(get_current_user)) -> dict[str, object]:
    _limit_credential_proof(user["id"])
    code = manage_credentials(user, request.current_password)
    response.headers["Cache-Control"] = "no-store"
    log_event(logger, "auth_recovery_code_generated", user_id=user["id"])
    return success_payload(recovery_code=code, message="仅本次展示，请离线保存；旧恢复码已失效。")


@router.post("/recover-password")
def recover_password_api(request: PasswordRecoveryRequest, http_request: Request, response: Response) -> dict[str, object]:
    _limit_auth(http_request)
    host = http_request.client.host if http_request.client else "local"
    credential_rate_limiter.cleanup()
    # 存在、不存在、访客和未启用恢复的账号走同一限流与错误路径。
    credential_rate_limiter.check(f"recover-ip:{safe_fingerprint(host)}", 20, 600)
    credential_rate_limiter.check(f"recover-account:{safe_fingerprint(request.username.strip().lower())}", 5, 600)
    user_id = recover_password(request.username, request.recovery_code, request.new_password)
    _clear_browser_session(response)
    log_event(logger, "auth_password_recovered", user_id=user_id)
    return success_payload(message="密码已重置，恢复码已使用，全部设备已退出登录。请重新登录并生成新恢复码。")


def _limit_auth(request: Request) -> None:
    settings = get_settings()
    host = request.client.host if request.client else "local"
    auth_rate_limiter.check(
        f"auth:{safe_fingerprint(host)}",
        settings.auth_requests_per_minute,
        settings.auth_window_seconds,
    )


def _set_browser_session(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie("yunxun_session", token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)
    response.set_cookie(CSRF_COOKIE_NAME, create_csrf_token(), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)


@router.post("/register")
def register_api(request: RegisterRequest, http_request: Request, response: Response) -> dict[str, object]:
    _limit_auth(http_request)
    payload = register_user(request.username, request.password, request.display_name)
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.get("/csrf", include_in_schema=False)
def csrf_api(response: Response) -> dict[str, object]:
    settings = get_settings()
    response.set_cookie(CSRF_COOKIE_NAME, create_csrf_token(), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_same_site, path="/", max_age=settings.token_hours * 3600)
    return success_payload(message="CSRF token issued")


@router.post("/login")
def login_api(request: LoginRequest, http_request: Request, response: Response) -> dict[str, object]:
    _limit_auth(http_request)
    payload = login_user(request.username, request.password)
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.post("/guest")
def guest_login_api(request: Request, response: Response) -> dict[str, object]:
    _limit_auth(request)
    payload = guest_login()
    _set_browser_session(response, str(payload["token"]))
    return success_payload(**payload)


@router.post("/logout")
def logout_api(http_request: Request, response: Response, authorization: str | None = Header(default=None), request: LogoutRequest | None = None) -> dict[str, object]:
    current_session = get_session_reference(http_request, authorization)
    if request and current_session and not secrets.compare_digest(request.session_id, current_session):
        raise HTTPException(status_code=409, detail="当前会话已变化，旧退出请求不能退出新会话。")
    if http_request.cookies.get("yunxun_session"):
        authorization = f"Bearer {http_request.cookies['yunxun_session']}"
    user_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_current_user_from_header(authorization)["id"]
        except HTTPException:
            user_id = None
    logout_user(authorization, user_id=user_id)
    # 撤销即退出。不能发 Set-Cookie：迟到响应可能删除其后登录的新 Cookie。
    # 已撤销的 HttpOnly Cookie 不再能认证，由下次登录覆盖或自然过期。
    response.headers["Cache-Control"] = "no-store"
    return success_payload(message="已退出登录。")


@router.post("/upgrade-guest")
def upgrade_guest_api(
    request: GuestUpgradeRequest, http_request: Request, response: Response,
    user: dict = Depends(get_current_user),
) -> dict[str, object]:
    _limit_auth(http_request)
    payload = upgrade_guest_user(user, request.username, request.password, request.display_name)
    _set_browser_session(response, str(payload["token"]))
    response.headers["Cache-Control"] = "no-store"
    return success_payload(**payload, message="账号已保存，原有数据全部保留。")


@router.get("/me", include_in_schema=False)
def auth_me_api(user: dict[str, str] = Depends(get_current_user), session_id: str = Depends(get_session_reference)) -> dict[str, object]:
    return success_payload(user=public_user(user), session_id=session_id)


@router.patch("/profile", include_in_schema=False)
def auth_profile_api(
    request: ProfileUpdateRequest,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    updated_user = update_profile(user["id"], request.display_name)
    return success_payload(user=updated_user)
