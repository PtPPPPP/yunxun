from pathlib import Path
import sqlite3

from backend.app.core.config import get_settings
from backend.app.core.database import SCHEMA_VERSION, get_connection
from backend.app.core.backup import CORE_TABLES
from backend.app.core.request_context import get_request_id
from backend.app.core.runtime_status import build_runtime_status


def build_health_payload() -> dict[str, object]:
    status = build_runtime_status(get_settings())
    return {
        "app_name": status["app_name"],
        "app_version": status["app_version"],
        "environment": status["environment"],
        "backend_url": status["backend_url"],
        "requests_per_minute": status["requests_per_minute"],
        "debug": status["debug"],
        "database_path": Path(str(status["database_path"])).name,
        "allowed_origins": status["allowed_origins"],
        "warnings": status["warnings"],
    }


def build_liveness_payload() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "request_id": get_request_id(),
    }


def build_readiness_payload() -> dict[str, object]:
    settings = get_settings()
    database = check_database_ready()
    checks = {
        "application": True,
        "database": database["ready"],
        "schema_version": database["schema_version"],
    }
    return {
        "status": "ready" if checks["application"] and database["ready"] else "degraded",
        "checks": checks,
        "database": Path(settings.db_path).name,
        "warnings": build_runtime_status(settings)["warnings"],
        "request_id": get_request_id(),
    }


def check_database_ready() -> dict[str, object]:
    try:
        with get_connection() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except (OSError, sqlite3.Error):
        return {"ready": False, "schema_version": None}
    return {"ready": version == SCHEMA_VERSION and CORE_TABLES.issubset(tables), "schema_version": version}
