import unittest
from unittest.mock import patch

from backend.app.core.config import Settings
from backend.app.services import system as system_service


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻智慧农业AI工作台软件",
        "app_version": "1.0.0",
        "environment": "intranet",
        "debug": False,
        "host": "0.0.0.0",
        "port": 8001,
        "backend_url": "http://192.168.1.10:8001",
        "jwt_secret": "local-secret",
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


class SystemServiceTestCase(unittest.TestCase):
    def test_health_payload_contains_safe_runtime_fields(self) -> None:
        settings = make_settings()
        with patch.object(system_service, "get_settings", return_value=settings):
            payload = system_service.build_health_payload()

        self.assertEqual(payload["mode"], "本地演示模式")
        self.assertEqual(payload["environment"], "intranet")
        self.assertEqual(payload["backend_url"], "http://192.168.1.10:8001")
        self.assertEqual(payload["database_path"], "yunxun.db")
        self.assertNotIn("D:/Program", str(payload))
        self.assertEqual(payload["model_status"], "未配置真实模型 Key")
        self.assertEqual(payload["allowed_origins"], ["http://192.168.1.10:5173"])
        self.assertNotIn("api_key", payload)

    def test_liveness_payload_is_minimal_and_safe(self) -> None:
        settings = make_settings()
        with patch.object(system_service, "get_settings", return_value=settings):
            payload = system_service.build_liveness_payload()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "云寻智慧农业AI工作台软件")
        self.assertNotIn("api_key", str(payload))
        self.assertNotIn("local-secret", str(payload))

    def test_readiness_payload_reports_database_and_ai_state(self) -> None:
        settings = make_settings(api_key="sk-real-example-value")
        with (
            patch.object(system_service, "get_settings", return_value=settings),
            patch.object(system_service, "check_database_ready", return_value={"ready": True, "schema_version": 1}),
        ):
            payload = system_service.build_readiness_payload()

        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["checks"]["database"])
        self.assertTrue(payload["checks"]["ai_configured"])
        self.assertNotIn("sk-real-example-value", str(payload))

    def test_readiness_payload_is_degraded_when_database_is_unavailable(self) -> None:
        settings = make_settings()
        with (
            patch.object(system_service, "get_settings", return_value=settings),
            patch.object(system_service, "check_database_ready", return_value={"ready": False, "schema_version": None}),
        ):
            payload = system_service.build_readiness_payload()

        self.assertEqual(payload["status"], "degraded")
        self.assertFalse(payload["checks"]["database"])
        self.assertFalse(payload["checks"]["ai_configured"])


if __name__ == "__main__":
    unittest.main()
