import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import auth, chat, system, tools
from backend.app.core.config import get_settings, validate_startup_settings
from backend.app.core.database import init_db
from backend.app.core.exceptions import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from backend.app.core.runtime_status import log_runtime_status
from backend.app.core.request_context import normalize_request_id, reset_request_id, set_request_id
from backend.app.core.csrf import validate_csrf_request


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yunxun.backend")


def create_app() -> FastAPI:
    settings = get_settings()
    validate_startup_settings(settings)
    log_runtime_status(logger, settings)
    init_db()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )

    @app.middleware("http")
    async def request_context(request, call_next):
        request_id = normalize_request_id(request.headers.get("X-Request-ID"))
        context_token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            if request.url.path.startswith("/api/"):
                validate_csrf_request(request)
            content_length = request.headers.get("content-length", "")
            if content_length.isdigit() and int(content_length) > 10 * 1024 * 1024:
                from fastapi.responses import JSONResponse
                response = JSONResponse(status_code=413, content={"success": False, "error": "请求体过大。", "code": "REQUEST_TOO_LARGE"})
                response.headers["X-Request-ID"] = request_id
                status_code = 413
                return response
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
                response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            return response
        finally:
            logger.info(
                "event=http_request method=%s path=%s status_code=%d duration_ms=%d request_id=%s",
                request.method,
                request.url.path,
                status_code,
                round((time.perf_counter() - started) * 1000),
                request_id,
            )
            reset_request_id(context_token)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(tools.router)

    logger.info("Application initialized", extra={"host": settings.host, "port": settings.port})
    return app


app = create_app()
