import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _getenv(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _format_bounds(minimum: int | float | None, maximum: int | float | None) -> str:
    parts: list[str] = []
    if minimum is not None:
        parts.append(f"不能小于 {minimum}")
    if maximum is not None:
        parts.append(f"不能大于 {maximum}")
    return "，".join(parts)


def _parse_int(
    name: str,
    value: str | None,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数，当前值为 {value!r}。") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} 配置无效：{parsed}，{_format_bounds(minimum, maximum)}。")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{name} 配置无效：{parsed}，{_format_bounds(minimum, maximum)}。")
    return parsed


def _parse_float(
    name: str,
    value: str | None,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if value is None:
        return default
    try:
        parsed = float(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字，当前值为 {value!r}。") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} 配置无效：{parsed}，{_format_bounds(minimum, maximum)}。")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{name} 配置无效：{parsed}，{_format_bounds(minimum, maximum)}。")
    return parsed


def _parse_bool(name: str, value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    truthy = {"1", "true", "yes", "y", "on"}
    falsy = {"0", "false", "no", "n", "off"}
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise ValueError(f"{name} 必须是布尔值，可用 true/false、yes/no、1/0，当前值为 {value!r}。")


def _parse_csv(name: str, value: str | None, fallback: list[str] | None = None) -> list[str]:
    fallback = fallback or []
    if value is None:
        return fallback
    items = [item.strip() for item in value.split(",")]
    normalized: list[str] = []
    for item in items:
        if item and item not in normalized:
            normalized.append(item)
    return normalized or fallback


def _parse_optional_str(name: str, value: str | None, *, default: str = "") -> str:
    if value is None:
        return default
    cleaned = value.strip()
    if "\x00" in cleaned:
        raise ValueError(f"{name} 不能包含空字符。")
    return cleaned


def _resolve_database_path(raw_database_url: str) -> str:
    if raw_database_url.startswith("sqlite:///"):
        raw_path = raw_database_url.removeprefix("sqlite:///")
    else:
        raw_path = raw_database_url

    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / raw_path
    return str(path.resolve())


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    debug: bool
    host: str
    port: int
    backend_url: str
    jwt_secret: str
    database_url: str
    db_path: str
    allowed_origins_raw: str
    cors_methods_raw: str
    cors_headers_raw: str
    requests_per_minute: int
    token_hours: int
    request_timeout_seconds: float = 45.0
    log_level: str = "INFO"
    cookie_secure: bool = False
    cookie_same_site: str = "lax"

    @property
    def allowed_origins(self) -> list[str]:
        return _parse_csv(
            "YUNXUN_ALLOWED_ORIGINS",
            self.allowed_origins_raw,
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174",
                "http://localhost:4173",
                "http://127.0.0.1:4173",
                "http://localhost:8501",
                "http://127.0.0.1:8501",
            ],
        )

    @property
    def cors_methods(self) -> list[str]:
        methods = _parse_csv("YUNXUN_CORS_METHODS", self.cors_methods_raw, ["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
        return [method.upper() for method in methods]

    @property
    def cors_headers(self) -> list[str]:
        headers = _parse_csv(
            "YUNXUN_CORS_HEADERS",
            self.cors_headers_raw,
            ["Authorization", "Content-Type", "X-CSRF-Token"],
        )
        if "X-CSRF-Token" not in headers:
            headers.append("X-CSRF-Token")
        return headers

    @property
    def docs_enabled(self) -> bool:
        return self.debug or self.environment != "production"

    @property
    def normalized_log_level(self) -> str:
        level = self.log_level.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"YUNXUN_LOG_LEVEL 只能是 {', '.join(sorted(allowed))}，当前值为 {self.log_level!r}。")
        return level

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


def validate_startup_settings(settings: Settings) -> None:
    environment = settings.environment.strip().lower()
    if not settings.jwt_secret.strip():
        raise ValueError("YUNXUN_JWT_SECRET 不能为空。")
    if environment == "production":
        if settings.jwt_secret == "change-me-in-production" or len(settings.jwt_secret) < 32:
            raise ValueError("生产环境的 YUNXUN_JWT_SECRET 必须是至少 32 字符的随机值。")
        if settings.debug:
            raise ValueError("生产环境禁止启用 YUNXUN_DEBUG。")
        if not settings.allowed_origins or "*" in settings.allowed_origins:
            raise ValueError("生产环境必须配置明确的 YUNXUN_ALLOWED_ORIGINS，禁止使用通配符。")
        if not settings.cookie_secure:
            raise ValueError("生产环境必须启用 YUNXUN_COOKIE_SECURE。")
    settings.normalized_log_level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_database_path = PROJECT_ROOT / "backend" / "yunxun.db"
    port = _parse_int("YUNXUN_PORT", _getenv("YUNXUN_PORT", _getenv("PORT", "8001")), default=8001, minimum=1, maximum=65535)
    token_hours = _parse_int("YUNXUN_TOKEN_EXPIRE_HOURS", _getenv("YUNXUN_TOKEN_EXPIRE_HOURS"), default=168, minimum=1, maximum=24 * 365)
    database_url = _getenv("YUNXUN_DATABASE_URL", f"sqlite:///{default_database_path}") or f"sqlite:///{default_database_path}"

    return Settings(
        app_name=_parse_optional_str("YUNXUN_APP_NAME", _getenv("YUNXUN_APP_NAME"), default="云寻智慧农业工作台软件"),
        app_version=_parse_optional_str("YUNXUN_APP_VERSION", _getenv("YUNXUN_APP_VERSION"), default="1.0.0"),
        environment=_parse_optional_str("YUNXUN_ENV", _getenv("YUNXUN_ENV"), default="development"),
        debug=_parse_bool("YUNXUN_DEBUG", _getenv("YUNXUN_DEBUG"), default=False),
        host=_parse_optional_str("YUNXUN_HOST", _getenv("YUNXUN_HOST"), default="0.0.0.0"),
        port=port,
        backend_url=_parse_optional_str("YUNXUN_BACKEND_URL", _getenv("YUNXUN_BACKEND_URL"), default=f"http://127.0.0.1:{port}"),
        jwt_secret=_parse_optional_str("YUNXUN_JWT_SECRET", _getenv("YUNXUN_JWT_SECRET"), default="change-me-in-production"),
        database_url=database_url,
        db_path=_resolve_database_path(_getenv("YUNXUN_DB_PATH", database_url) or database_url),
        allowed_origins_raw=_getenv("YUNXUN_ALLOWED_ORIGINS", "") or "",
        cors_methods_raw=_getenv("YUNXUN_CORS_METHODS", "GET,POST,PATCH,DELETE,OPTIONS") or "GET,POST,PATCH,DELETE,OPTIONS",
        cors_headers_raw=_getenv(
            "YUNXUN_CORS_HEADERS",
            "Authorization,Content-Type,X-CSRF-Token",
        )
        or "Authorization,Content-Type,X-CSRF-Token",
        requests_per_minute=_parse_int("YUNXUN_REQUESTS_PER_MINUTE", _getenv("YUNXUN_REQUESTS_PER_MINUTE"), default=20, minimum=1, maximum=600),
        token_hours=token_hours,
        request_timeout_seconds=_parse_float("YUNXUN_REQUEST_TIMEOUT_SECONDS", _getenv("YUNXUN_REQUEST_TIMEOUT_SECONDS"), default=45.0, minimum=1.0, maximum=180.0),
        log_level=_parse_optional_str("YUNXUN_LOG_LEVEL", _getenv("YUNXUN_LOG_LEVEL"), default="INFO"),
        cookie_secure=_parse_bool("YUNXUN_COOKIE_SECURE", _getenv("YUNXUN_COOKIE_SECURE"), default=False),
        cookie_same_site=_parse_optional_str("YUNXUN_COOKIE_SAME_SITE", _getenv("YUNXUN_COOKIE_SAME_SITE"), default="lax").lower(),
    )
