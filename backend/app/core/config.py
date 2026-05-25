import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

CHAT_SYSTEM_PROMPT = """
你是“云寻 AI”的农技助手，服务对象是一线农户、合作社和基层农技员。
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


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback
    items = [item.strip() for item in value.split(",")]
    normalized = [item for item in items if item]
    return normalized or fallback


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

    @property
    def available_models(self) -> list[str]:
        return _parse_csv(self.available_models_raw, [self.chat_endpoint])

    @property
    def allowed_origins(self) -> list[str]:
        return _parse_csv(
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
        return _parse_csv(self.cors_methods_raw, ["GET", "POST", "PATCH", "DELETE", "OPTIONS"])

    @property
    def cors_headers(self) -> list[str]:
        return _parse_csv(self.cors_headers_raw, ["Authorization", "Content-Type"])

    @property
    def ai_configured(self) -> bool:
        return bool(has_real_api_key(self.api_key) and self.base_url.strip() and self.chat_endpoint.strip())

    @property
    def docs_enabled(self) -> bool:
        return self.debug or self.environment != "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_database_path = PROJECT_ROOT / "backend" / "yunxun.db"
    database_url = os.getenv("YUNXUN_DATABASE_URL", f"sqlite:///{default_database_path}")

    return Settings(
        app_name=os.getenv("YUNXUN_APP_NAME", "云寻 AI"),
        app_version=os.getenv("YUNXUN_APP_VERSION", "4.0.0"),
        environment=os.getenv("YUNXUN_ENV", "development"),
        debug=_parse_bool(os.getenv("YUNXUN_DEBUG"), default=False),
        host=os.getenv("YUNXUN_HOST", "0.0.0.0"),
        port=int(os.getenv("YUNXUN_PORT", os.getenv("PORT", "8001"))),
        backend_url=os.getenv("YUNXUN_BACKEND_URL", f"http://127.0.0.1:{os.getenv('YUNXUN_PORT', os.getenv('PORT', '8001'))}"),
        jwt_secret=os.getenv("YUNXUN_JWT_SECRET", "change-me-in-production"),
        api_key=os.getenv("DOUBAO_API_KEY", ""),
        base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        chat_endpoint=os.getenv("DOUBAO_CHAT_ENDPOINT", "doubao-seed-1-6-250615"),
        vision_endpoint=os.getenv(
            "DOUBAO_VISION_ENDPOINT",
            os.getenv("DOUBAO_CHAT_ENDPOINT", "doubao-seed-1-6-250615"),
        ),
        available_models_raw=os.getenv(
            "DOUBAO_AVAILABLE_MODELS",
            os.getenv("DOUBAO_CHAT_ENDPOINT", "doubao-seed-1-6-250615"),
        ),
        database_url=database_url,
        db_path=_resolve_database_path(os.getenv("YUNXUN_DB_PATH", database_url)),
        allowed_origins_raw=os.getenv("YUNXUN_ALLOWED_ORIGINS", ""),
        cors_methods_raw=os.getenv("YUNXUN_CORS_METHODS", "GET,POST,PATCH,DELETE,OPTIONS"),
        cors_headers_raw=os.getenv("YUNXUN_CORS_HEADERS", "Authorization,Content-Type"),
        max_message_length=int(os.getenv("YUNXUN_MAX_MESSAGE_LENGTH", "3000")),
        requests_per_minute=int(os.getenv("YUNXUN_REQUESTS_PER_MINUTE", "20")),
        token_hours=int(os.getenv("YUNXUN_TOKEN_EXPIRE_HOURS", "168")),
    )
