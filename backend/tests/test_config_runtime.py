import unittest

from backend.app.core.config import Settings, has_real_api_key, validate_startup_settings
from backend.app.core.runtime_status import build_runtime_status, build_runtime_warnings


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻智慧农业AI工作台软件",
        "app_version": "1.0.0",
        "environment": "intranet",
        "debug": False,
        "host": "0.0.0.0",
        "port": 8001,
        "backend_url": "http://192.168.1.10:8001",
        "jwt_secret": "change-me-in-production",
        "api_key": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_endpoint": "doubao-seed-1-6-250615",
        "vision_endpoint": "doubao-seed-1-6-250615",
        "available_models_raw": "doubao-seed-1-6-250615",
        "database_url": "sqlite:///./backend/yunxun.db",
        "db_path": "D:/Program/vscode/yunxun/backend/yunxun.db",
        "allowed_origins_raw": "http://192.168.1.10:5173",
        "cors_methods_raw": "GET,POST,PATCH,DELETE,OPTIONS",
        "cors_headers_raw": "Authorization,Content-Type",
        "max_message_length": 3000,
        "requests_per_minute": 20,
        "token_hours": 168,
    }
    values.update(overrides)
    return Settings(**values)


class ConfigRuntimeTestCase(unittest.TestCase):
    def test_production_validation(self) -> None:
        with self.assertRaises(ValueError):
            validate_startup_settings(make_settings(environment="production", allowed_origins_raw="https://example.com"))
        validate_startup_settings(make_settings(environment="production", jwt_secret="x" * 32, allowed_origins_raw="https://example.com", cookie_secure=True))

    def test_example_api_key_is_not_treated_as_configured(self) -> None:
        self.assertFalse(has_real_api_key(""))
        self.assertFalse(has_real_api_key("your-doubao-api-key"))
        self.assertFalse(has_real_api_key("YOUR_DOUBAO_API_KEY"))
        self.assertTrue(has_real_api_key("sk-real-example-value"))

    def test_runtime_status_uses_demo_mode_for_example_key(self) -> None:
        status = build_runtime_status(make_settings(api_key="your-doubao-api-key"))
        self.assertFalse(status["ai_configured"])
        self.assertNotIn("your-doubao-api-key", str(status))

    def test_runtime_status_includes_system_model_details(self) -> None:
        status = build_runtime_status(make_settings(api_key="sk-real-example-value", jwt_secret="local-secret"))
        self.assertTrue(status["ai_configured"])
        self.assertEqual(status["available_models"], ["doubao-seed-1-6-250615"])

    def test_runtime_warnings_include_missing_ai_warning(self) -> None:
        warnings = build_runtime_warnings(make_settings(api_key="your-doubao-api-key", jwt_secret="local-secret"))
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
