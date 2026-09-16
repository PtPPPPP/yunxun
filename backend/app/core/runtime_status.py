import logging
from typing import Any

from backend.app.core.config import Settings


def build_runtime_warnings(settings: Settings) -> list[str]:
    warnings: list[str] = []

    if settings.jwt_secret == "change-me-in-production":
        warnings.append("本机安全设置未完成（仍在使用默认密钥），正式启用前请联系部署人员。")
    if not settings.allowed_origins_raw.strip():
        warnings.append("本机安全设置未完成（未指定允许访问的来源），局域网访问前请联系部署人员。")

    return warnings


def build_runtime_status(settings: Settings) -> dict[str, Any]:
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "host": settings.host,
        "port": settings.port,
        "backend_url": settings.backend_url,
        "database_path": settings.db_path,
        "allowed_origins": settings.allowed_origins,
        "requests_per_minute": settings.requests_per_minute,
        "token_hours": settings.token_hours,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "warnings": build_runtime_warnings(settings),
    }


def log_runtime_status(logger: logging.Logger, settings: Settings) -> None:
    status = build_runtime_status(settings)
    # 变量名只留在日志里给部署的人看，界面上给的是人能读的提示。
    for name, configured in (("YUNXUN_JWT_SECRET", settings.jwt_secret != "change-me-in-production"),
                             ("YUNXUN_ALLOWED_ORIGINS", bool(settings.allowed_origins_raw.strip()))):
        if not configured:
            logger.warning("Runtime config gap: %s is not set for production use.", name)

    logger.info(
        "Runtime status: environment=%s debug=%s host=%s port=%s database=%s origins=%s",
        status["environment"],
        status["debug"],
        status["host"],
        status["port"],
        status["database_path"],
        ",".join(status["allowed_origins"]),
    )
    for warning in status["warnings"]:
        logger.warning("Runtime warning: %s", warning)
