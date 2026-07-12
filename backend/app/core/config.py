import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

CHAT_SYSTEM_PROMPT = """
你是“云寻AI”的农技助手，服务对象是一线农户、合作社和基层农技员。
回答时请遵循这些原则：
1. 先给结论，再解释原因，最后给出今天能执行的 2 到 4 条操作建议。
2. 使用口语化中文，少用术语；涉及药剂、肥料和剂量时，提醒以当地农技站、产品标签和安全间隔期为准。
3. 不确定时明确说明“暂时不能直接下结论”，并告诉用户需要补充哪些信息或照片。
4. 优先给出短、稳、能落地的建议，避免空泛表述。
""".strip()

VISION_SYSTEM_PROMPT = """
你是专业植物病虫害诊断助手。请根据图片给出初步判断，但不要假装百分之百确定。
输出格式：
1. 初步诊断：可能的病虫害或生理问题，并说明把握程度。
2. 依据：指出你从图片中看到的叶片、茎秆、果实或土壤特征。
3. 今日处理：给出田间管理、复查重点和用药方向建议。
4. 安全提醒：药剂必须按产品标签和当地农技部门建议使用。
""".strip()


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


def _normalize_example_key(value: str) -> str:
    cleaned = value.strip().strip("<>{}[]()\"'").strip()
    return re.sub(r"[\s_-]+", "", cleaned.casefold())


EXAMPLE_API_KEY_VALUES = {
    "",
    "your-doubao-api-key",
    "your_doubao_api_key",
    "your-api-key",
    "your_api_key",
    "change-me",
    "change_me",
    "change-me-in-production",
    "change_me_in_production",
    "你的真实 api key",
    "你的真实api key",
    "你的真实 Ark API Key",
    "你的真实Ark API Key",
}
EXAMPLE_API_KEYS = {_normalize_example_key(value) for value in EXAMPLE_API_KEY_VALUES}


def has_real_api_key(value: str | None) -> bool:
    normalized = _normalize_example_key(value or "")
    if not normalized:
        return False
    return normalized not in EXAMPLE_API_KEYS


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
    api_key: str
    base_url: str
    chat_endpoint: str
    vision_endpoint: str
    available_models_raw: str
    database_url: str
    db_path: str
    allowed_origins_raw: str
    cors_methods_raw: str
    cors_headers_raw: str
    max_message_length: int
    requests_per_minute: int
    token_hours: int
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_max_base64_length: int = 8_000_000
    request_timeout_seconds: float = 45.0
    ai_timeout_seconds: float = 45.0
    ai_max_retries: int = 1
    log_level: str = "INFO"
    default_page_size: int = 20
    max_page_size: int = 100
    idempotency_window_seconds: float = 10.0

    @property
    def idempotency_enabled(self) -> bool:
        return self.idempotency_window_seconds > 0

    @property
    def available_models(self) -> list[str]:
        return _parse_csv("DOUBAO_AVAILABLE_MODELS", self.available_models_raw, [self.chat_endpoint])

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
        return _parse_csv(
            "YUNXUN_CORS_HEADERS",
            self.cors_headers_raw,
            ["Authorization", "Content-Type", "X-Idempotency-Key"],
        )

    @property
    def ai_configured(self) -> bool:
        return bool(has_real_api_key(self.api_key) and self.base_url.strip() and self.chat_endpoint.strip())

    @property
    def docs_enabled(self) -> bool:
        return self.debug or self.environment != "production"

    @property
    def upload_max_megabytes(self) -> float:
        return round(self.upload_max_bytes / 1024 / 1024, 2)

    @property
    def normalized_log_level(self) -> str:
        level = self.log_level.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"YUNXUN_LOG_LEVEL 只能是 {', '.join(sorted(allowed))}，当前值为 {self.log_level!r}。")
        return level


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
    settings.normalized_log_level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_database_path = PROJECT_ROOT / "backend" / "yunxun.db"
    port = _parse_int("YUNXUN_PORT", _getenv("YUNXUN_PORT", _getenv("PORT", "8001")), default=8001, minimum=1, maximum=65535)
    token_hours = _parse_int("YUNXUN_TOKEN_EXPIRE_HOURS", _getenv("YUNXUN_TOKEN_EXPIRE_HOURS"), default=168, minimum=1, maximum=24 * 365)
    upload_max_bytes = _parse_int(
        "YUNXUN_UPLOAD_MAX_BYTES",
        _getenv("YUNXUN_UPLOAD_MAX_BYTES"),
        default=5 * 1024 * 1024,
        minimum=1,
        maximum=20 * 1024 * 1024,
    )
    database_url = _getenv("YUNXUN_DATABASE_URL", f"sqlite:///{default_database_path}") or f"sqlite:///{default_database_path}"

    return Settings(
        app_name=_parse_optional_str("YUNXUN_APP_NAME", _getenv("YUNXUN_APP_NAME"), default="云寻智慧农业AI工作台软件"),
        app_version=_parse_optional_str("YUNXUN_APP_VERSION", _getenv("YUNXUN_APP_VERSION"), default="1.0.0"),
        environment=_parse_optional_str("YUNXUN_ENV", _getenv("YUNXUN_ENV"), default="development"),
        debug=_parse_bool("YUNXUN_DEBUG", _getenv("YUNXUN_DEBUG"), default=False),
        host=_parse_optional_str("YUNXUN_HOST", _getenv("YUNXUN_HOST"), default="0.0.0.0"),
        port=port,
        backend_url=_parse_optional_str("YUNXUN_BACKEND_URL", _getenv("YUNXUN_BACKEND_URL"), default=f"http://127.0.0.1:{port}"),
        jwt_secret=_parse_optional_str("YUNXUN_JWT_SECRET", _getenv("YUNXUN_JWT_SECRET"), default="change-me-in-production"),
        api_key=_parse_optional_str("DOUBAO_API_KEY", _getenv("DOUBAO_API_KEY"), default=""),
        base_url=_parse_optional_str("DOUBAO_BASE_URL", _getenv("DOUBAO_BASE_URL"), default="https://ark.cn-beijing.volces.com/api/v3"),
        chat_endpoint=_parse_optional_str("DOUBAO_CHAT_ENDPOINT", _getenv("DOUBAO_CHAT_ENDPOINT"), default="doubao-seed-1-6-250615"),
        vision_endpoint=_parse_optional_str(
            "DOUBAO_VISION_ENDPOINT",
            _getenv("DOUBAO_VISION_ENDPOINT"),
            default=_getenv("DOUBAO_CHAT_ENDPOINT", "doubao-seed-1-6-250615") or "doubao-seed-1-6-250615",
        ),
        available_models_raw=_parse_optional_str(
            "DOUBAO_AVAILABLE_MODELS",
            _getenv("DOUBAO_AVAILABLE_MODELS"),
            default=_getenv("DOUBAO_CHAT_ENDPOINT", "doubao-seed-1-6-250615") or "doubao-seed-1-6-250615",
        ),
        database_url=database_url,
        db_path=_resolve_database_path(_getenv("YUNXUN_DB_PATH", database_url) or database_url),
        allowed_origins_raw=_getenv("YUNXUN_ALLOWED_ORIGINS", "") or "",
        cors_methods_raw=_getenv("YUNXUN_CORS_METHODS", "GET,POST,PATCH,DELETE,OPTIONS") or "GET,POST,PATCH,DELETE,OPTIONS",
        cors_headers_raw=_getenv(
            "YUNXUN_CORS_HEADERS",
            "Authorization,Content-Type,X-Idempotency-Key",
        )
        or "Authorization,Content-Type,X-Idempotency-Key",
        max_message_length=_parse_int("YUNXUN_MAX_MESSAGE_LENGTH", _getenv("YUNXUN_MAX_MESSAGE_LENGTH"), default=3000, minimum=1, maximum=20_000),
        requests_per_minute=_parse_int("YUNXUN_REQUESTS_PER_MINUTE", _getenv("YUNXUN_REQUESTS_PER_MINUTE"), default=20, minimum=1, maximum=600),
        token_hours=token_hours,
        upload_max_bytes=upload_max_bytes,
        upload_max_base64_length=int(upload_max_bytes * 1.38) + 128,
        request_timeout_seconds=_parse_float("YUNXUN_REQUEST_TIMEOUT_SECONDS", _getenv("YUNXUN_REQUEST_TIMEOUT_SECONDS"), default=45.0, minimum=1.0, maximum=180.0),
        ai_timeout_seconds=_parse_float("YUNXUN_AI_TIMEOUT_SECONDS", _getenv("YUNXUN_AI_TIMEOUT_SECONDS"), default=45.0, minimum=1.0, maximum=180.0),
        ai_max_retries=_parse_int("YUNXUN_AI_MAX_RETRIES", _getenv("YUNXUN_AI_MAX_RETRIES"), default=1, minimum=0, maximum=3),
        log_level=_parse_optional_str("YUNXUN_LOG_LEVEL", _getenv("YUNXUN_LOG_LEVEL"), default="INFO"),
        default_page_size=_parse_int("YUNXUN_DEFAULT_PAGE_SIZE", _getenv("YUNXUN_DEFAULT_PAGE_SIZE"), default=20, minimum=1, maximum=100),
        max_page_size=_parse_int("YUNXUN_MAX_PAGE_SIZE", _getenv("YUNXUN_MAX_PAGE_SIZE"), default=100, minimum=1, maximum=500),
        idempotency_window_seconds=_parse_float(
            "YUNXUN_IDEMPOTENCY_WINDOW_SECONDS",
            _getenv("YUNXUN_IDEMPOTENCY_WINDOW_SECONDS"),
            default=10.0,
            minimum=0.0,
            maximum=300.0,
        ),
    )
