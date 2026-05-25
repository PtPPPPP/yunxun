import unittest

from backend.app.core.config import Settings, has_real_api_key
from backend.app.core.runtime_status import build_runtime_status, build_runtime_warnings


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻 AI",
        "app_version": "4.0.0",
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
    def test_example_api_key_is_not_treated_as_configured(self) -> None:
        self.assertFalse(has_real_api_key(""))
        self.assertFalse(has_real_api_key("your-doubao-api-key"))
        self.assertFalse(has_real_api_key("YOUR_DOUBAO_API_KEY"))
        self.assertFalse(has_real_api_key("<your-doubao-api-key>"))
        self.assertFalse(has_real_api_key("你的真实 API Key"))
        self.assertFalse(has_real_api_key("你的真实Ark API Key"))
        self.assertFalse(has_real_api_key("change-me"))
        self.assertTrue(has_real_api_key("sk-real-example-value"))

    def test_runtime_status_uses_demo_mode_for_example_key(self) -> None:
        settings = make_settings(api_key="your-doubao-api-key")
        status = build_runtime_status(settings)

        self.assertEqual(status["mode"], "本地演示模式")
        self.assertFalse(status["ai_configured"])
        self.assertEqual(status["model_status"], "未配置真实模型 Key")
        self.assertNotIn("your-doubao-api-key", str(status))

    def test_runtime_status_includes_local_intranet_details(self) -> None:
        settings = make_settings(api_key="sk-real-example-value", jwt_secret="local-secret")
        status = build_runtime_status(settings)

        self.assertEqual(status["mode"], "AI 模式")
        self.assertTrue(status["ai_configured"])
        self.assertEqual(status["environment"], "intranet")
        self.assertEqual(status["backend_url"], "http://192.168.1.10:8001")
        self.assertEqual(status["database_path"], "D:/Program/vscode/yunxun/backend/yunxun.db")
        self.assertEqual(status["allowed_origins"], ["http://192.168.1.10:5173"])

    def test_runtime_warnings_include_default_secret_warning(self) -> None:
        warnings = build_runtime_warnings(
            make_settings(api_key="sk-real-example-value", allowed_origins_raw="http://192.168.1.10:5173")
        )

        self.assertIn("当前仍使用默认安全密钥，内网试用前建议修改 YUNXUN_JWT_SECRET。", warnings)

    def test_runtime_warnings_include_missing_explicit_cors_warning(self) -> None:
        warnings = build_runtime_warnings(
            make_settings(
                api_key="sk-real-example-value",
                jwt_secret="local-secret",
                allowed_origins_raw="",
            )
        )

        self.assertIn("当前未显式配置 CORS 来源，系统会使用本机默认来源；局域网访问前请配置 YUNXUN_ALLOWED_ORIGINS。", warnings)

    def test_runtime_warnings_include_ai_demo_warning(self) -> None:
        warnings = build_runtime_warnings(
            make_settings(
                api_key="your-doubao-api-key",
                jwt_secret="local-secret",
                allowed_origins_raw="http://192.168.1.10:5173",
            )
        )

        self.assertIn("当前未配置真实模型 Key，系统会进入本地演示模式。", warnings)


if __name__ == "__main__":
    unittest.main()
