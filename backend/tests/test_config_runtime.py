import logging
import unittest

from backend.app.core.config import Settings, validate_startup_settings
from backend.app.core.runtime_status import (
    build_runtime_status,
    build_runtime_warnings,
    log_runtime_status,
)


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻智慧农业工作台软件",
        "app_version": "1.0.0",
        "environment": "intranet",
        "debug": False,
        "host": "0.0.0.0",
        "port": 8001,
        "backend_url": "http://192.168.1.10:8001",
        "jwt_secret": "change-me-in-production",
        "database_url": "sqlite:///./backend/yunxun.db",
        "db_path": "D:/Program/vscode/yunxun/backend/yunxun.db",
        "allowed_origins_raw": "http://192.168.1.10:5173",
        "cors_methods_raw": "GET,POST,PATCH,DELETE,OPTIONS",
        "cors_headers_raw": "Authorization,Content-Type",
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

    def test_runtime_status_exposes_environment_without_secrets(self) -> None:
        status = build_runtime_status(make_settings(jwt_secret="local-secret"))
        self.assertEqual(status["environment"], "intranet")
        self.assertEqual(status["requests_per_minute"], 20)
        self.assertNotIn("local-secret", str(status))

    def test_runtime_warnings_are_human_readable(self) -> None:
        """给农户看的文案不能是环境变量名，变量名只留在日志里。"""
        warnings = build_runtime_warnings(make_settings())
        self.assertTrue(any("安全设置未完成" in warning for warning in warnings))
        self.assertFalse(any("YUNXUN_" in warning for warning in warnings))

    def test_runtime_warnings_include_missing_origin_notice(self) -> None:
        warnings = build_runtime_warnings(make_settings(allowed_origins_raw=""))
        self.assertTrue(any("来源" in warning for warning in warnings))

    def test_runtime_log_names_the_variables_needing_configuration(self) -> None:
        logger = logging.getLogger("yunxun.backend")
        with self.assertLogs("yunxun.backend", level="WARNING") as captured:
            # 两个变量都留空，两条提醒才会都产生
            log_runtime_status(logger, make_settings(allowed_origins_raw=""))

        output = chr(10).join(captured.output)
        self.assertIn("YUNXUN_JWT_SECRET", output)
        self.assertIn("YUNXUN_ALLOWED_ORIGINS", output)


if __name__ == "__main__":
    unittest.main()
