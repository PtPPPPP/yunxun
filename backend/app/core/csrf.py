import secrets

from fastapi import HTTPException, Request


CSRF_COOKIE_NAME = "yunxun_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf_request(request: Request) -> None:
    if request.method in SAFE_METHODS or request.url.path.startswith("/health"):
        return
    # Bearer 用于 CLI 与迁移期调试；浏览器 Cookie 会话才需要 CSRF 防护。
    if request.headers.get("authorization", "").startswith("Bearer ") or not request.cookies.get("yunxun_session"):
        return
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="CSRF 验证失败，请刷新页面后重试。")
