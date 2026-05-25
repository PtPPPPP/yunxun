from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.core.runtime_status import build_runtime_status


def build_health_payload() -> dict[str, object]:
    settings = get_settings()
    status = build_runtime_status(settings)
    return {
        "mode": status["mode"],
        "ai_configured": status["ai_configured"],
        "model_status": status["model_status"],
        "environment": status["environment"],
        "backend_url": status["backend_url"],
        "available_models": status["available_models"],
        "max_message_length": status["max_message_length"],
        "requests_per_minute": status["requests_per_minute"],
        "debug": status["debug"],
        "database_path": Path(str(status["database_path"])).name,
        "allowed_origins": status["allowed_origins"],
        "warnings": status["warnings"],
    }
