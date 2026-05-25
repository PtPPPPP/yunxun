import logging
import unittest

from backend.app.core.audit import log_event


class AuditLogTestCase(unittest.TestCase):
    def test_log_event_redacts_sensitive_fields(self) -> None:
        logger = logging.getLogger("yunxun.backend.test_audit")
        with self.assertLogs(logger, level="INFO") as captured:
            log_event(
                logger,
                "auth_login_attempt",
                username="demo",
                password="secret-password",
                token="secret-token",
                image_base64="abc123",
                message_length=12,
            )

        output = "\n".join(captured.output)
        self.assertIn("event=auth_login_attempt", output)
        self.assertIn("username=demo", output)
        self.assertIn("message_length=12", output)
        self.assertIn("password=[redacted]", output)
        self.assertIn("token=[redacted]", output)
        self.assertIn("image_base64=[redacted]", output)
        self.assertNotIn("secret-password", output)
        self.assertNotIn("secret-token", output)
        self.assertNotIn("abc123", output)

    def test_log_event_redacts_sensitive_fields_case_insensitively(self) -> None:
        logger = logging.getLogger("yunxun.backend.test_audit_case")
        with self.assertLogs(logger, level="INFO") as captured:
            log_event(
                logger,
                "auth_token_seen",
                Authorization="Bearer secret-authorization",
                API_KEY="secret-api-key",
                Token="secret-token",
                Password="secret-password",
                username="demo",
            )

        output = "\n".join(captured.output)
        self.assertIn("Authorization=[redacted]", output)
        self.assertIn("API_KEY=[redacted]", output)
        self.assertIn("Token=[redacted]", output)
        self.assertIn("Password=[redacted]", output)
        self.assertIn("username=demo", output)
        self.assertNotIn("Bearer secret-authorization", output)
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("secret-token", output)
        self.assertNotIn("secret-password", output)


if __name__ == "__main__":
    unittest.main()
