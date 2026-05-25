import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import auth, chat, system, tools
from backend.app.core.config import get_settings
from backend.app.core.database import init_db
from backend.app.core.exceptions import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from backend.app.core.runtime_status import log_runtime_status


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yunxun.backend")


def create_app() -> FastAPI:
    settings = get_settings()
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
