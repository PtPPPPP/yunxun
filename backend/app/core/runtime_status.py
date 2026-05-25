import logging
from typing import Any

from backend.app.core.config import Settings


def build_runtime_warnings(settings: Settings) -> list[str]:
    warnings: list[str] = []

    if settings.jwt_secret == "change-me-in-production":
        warnings.append("当前仍使用默认安全密钥，内网试用前建议修改 YUNXUN_JWT_SECRET。")
    if not settings.allowed_origins_raw.strip():
        warnings.append("当前未显式配置 CORS 来源，系统会使用本机默认来源；局域网访问前请配置 YUNXUN_ALLOWED_ORIGINS。")
    if not settings.ai_configured:
        warnings.append("当前未配置真实模型 Key，系统会进入本地演示模式。")

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
        "mode": "AI 模式" if settings.ai_configured else "本地演示模式",
        "ai_configured": settings.ai_configured,
        "model_status": "已配置真实模型 Key" if settings.ai_configured else "未配置真实模型 Key",
        "available_models": settings.available_models,
        "database_path": settings.db_path,
        "allowed_origins": settings.allowed_origins,
        "max_message_length": settings.max_message_length,
        "requests_per_minute": settings.requests_per_minute,
        "token_hours": settings.token_hours,
        "warnings": build_runtime_warnings(settings),
    }


def log_runtime_status(logger: logging.Logger, settings: Settings) -> None:
    status = build_runtime_status(settings)
    logger.info(
        "Runtime status: environment=%s debug=%s host=%s port=%s mode=%s database=%s origins=%s",
        status["environment"],
        status["debug"],
        status["host"],
        status["port"],
        status["mode"],
        status["database_path"],
        ",".join(status["allowed_origins"]),
    )
    for warning in status["warnings"]:
        logger.warning("Runtime warning: %s", warning)
