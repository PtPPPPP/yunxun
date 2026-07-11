import unittest
from unittest.mock import patch

from backend.app.core import config


class ConfigParsingTestCase(unittest.TestCase):
    def test_parse_int_uses_default_and_enforces_bounds(self) -> None:
        self.assertEqual(config._parse_int("YUNXUN_PORT", None, default=8001, minimum=1, maximum=65535), 8001)
        self.assertEqual(config._parse_int("YUNXUN_PORT", "9000", default=8001, minimum=1, maximum=65535), 9000)

        with self.assertRaises(ValueError) as below_minimum:
            config._parse_int("YUNXUN_PORT", "0", default=8001, minimum=1, maximum=65535)
        self.assertIn("YUNXUN_PORT", str(below_minimum.exception))
        self.assertIn("不能小于 1", str(below_minimum.exception))

        with self.assertRaises(ValueError) as above_maximum:
            config._parse_int("YUNXUN_PORT", "70000", default=8001, minimum=1, maximum=65535)
        self.assertIn("不能大于 65535", str(above_maximum.exception))

    def test_parse_int_reports_invalid_value(self) -> None:
        with self.assertRaises(ValueError) as invalid:
            config._parse_int("YUNXUN_MAX_MESSAGE_LENGTH", "abc", default=3000, minimum=1)
        self.assertIn("必须是整数", str(invalid.exception))
        self.assertIn("abc", str(invalid.exception))

    def test_parse_bool_rejects_ambiguous_values(self) -> None:
        self.assertTrue(config._parse_bool("YUNXUN_DEBUG", "yes", default=False))
        self.assertFalse(config._parse_bool("YUNXUN_DEBUG", "off", default=True))

        with self.assertRaises(ValueError) as invalid:
            config._parse_bool("YUNXUN_DEBUG", "maybe", default=False)
        self.assertIn("必须是布尔值", str(invalid.exception))

    def test_parse_csv_trims_and_deduplicates_values(self) -> None:
        values = config._parse_csv("YUNXUN_ALLOWED_ORIGINS", " http://a.test, http://a.test, http://b.test ")
        self.assertEqual(values, ["http://a.test", "http://b.test"])

    def test_default_cors_headers_allow_idempotency_key(self) -> None:
        config.get_settings.cache_clear()
        with patch.dict("os.environ", {}, clear=True):
            settings = config.get_settings()

        self.assertIn("X-Idempotency-Key", settings.cors_headers)
        config.get_settings.cache_clear()

    def test_get_settings_uses_safe_numeric_parsers(self) -> None:
        config.get_settings.cache_clear()
        with patch.dict(
            "os.environ",
            {
                "YUNXUN_PORT": "8123",
                "YUNXUN_MAX_MESSAGE_LENGTH": "2048",
                "YUNXUN_REQUESTS_PER_MINUTE": "12",
                "YUNXUN_TOKEN_EXPIRE_HOURS": "24",
                "YUNXUN_UPLOAD_MAX_BYTES": "2097152",
            },
            clear=False,
        ):
            settings = config.get_settings()

        self.assertEqual(settings.port, 8123)
        self.assertEqual(settings.max_message_length, 2048)
        self.assertEqual(settings.requests_per_minute, 12)
        self.assertEqual(settings.token_hours, 24)
        self.assertEqual(settings.upload_max_bytes, 2_097_152)
        config.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
