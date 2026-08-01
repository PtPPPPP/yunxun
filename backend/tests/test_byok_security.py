import base64
import socket
import unittest
from unittest.mock import patch

from backend.app.core.byok_security import CredentialCipher, validate_provider_base_url
from backend.app.core.errors import AppError, ErrorCode
from backend.tests.test_config_runtime import make_settings


TEST_MASTER_KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


class ByokSecurityTestCase(unittest.TestCase):
    def test_aes_gcm_round_trip_and_wrong_key_rejected(self) -> None:
        api_key = "sk-test-secret-value"
        encrypted, fingerprint = CredentialCipher(TEST_MASTER_KEY).encrypt(api_key)

        self.assertNotIn(api_key.encode(), encrypted)
        self.assertEqual(CredentialCipher(TEST_MASTER_KEY).decrypt(encrypted), api_key)
        self.assertEqual(len(fingerprint), 64)
        with self.assertRaises(AppError) as rejected:
            CredentialCipher(base64.urlsafe_b64encode(b"z" * 32).decode("ascii")).decrypt(encrypted)
        self.assertEqual(rejected.exception.code, ErrorCode.CREDENTIAL_ENCRYPTION_UNAVAILABLE)

    @patch("backend.app.core.byok_security.socket.getaddrinfo")
    def test_fixed_provider_accepts_only_preset_public_url(self, getaddrinfo) -> None:
        getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        settings = make_settings(byok_enabled=True)
        self.assertEqual(
            validate_provider_base_url("openai", "https://api.openai.com/v1", settings),
            "https://api.openai.com/v1",
        )
        with self.assertRaises(AppError):
            validate_provider_base_url("openai", "https://example.com/v1", settings)

    @patch("backend.app.core.byok_security.socket.getaddrinfo")
    def test_private_and_local_addresses_are_rejected(self, getaddrinfo) -> None:
        settings = make_settings(
            byok_enabled=True,
            byok_allowed_base_urls_raw="https://llm.example.com/v1",
        )
        getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with self.assertRaises(AppError) as rejected:
            validate_provider_base_url("openai-compatible", "https://llm.example.com/v1", settings)
        self.assertEqual(rejected.exception.code, ErrorCode.MODEL_BASE_URL_NOT_ALLOWED)

    def test_credentials_query_and_non_https_are_rejected(self) -> None:
        settings = make_settings(
            byok_enabled=True,
            byok_allowed_base_urls_raw="https://llm.example.com/v1",
        )
        for url in (
            "http://llm.example.com/v1",
            "https://user:pass@llm.example.com/v1",
            "https://llm.example.com/v1?api_key=secret",
        ):
            with self.subTest(url=url), self.assertRaises(AppError):
                validate_provider_base_url("openai-compatible", url, settings)


if __name__ == "__main__":
    unittest.main()
