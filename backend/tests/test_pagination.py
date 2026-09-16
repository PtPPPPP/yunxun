import unittest

from backend.app.core.pagination import decode_cursor, encode_cursor


class CursorTestCase(unittest.TestCase):
    def test_cursor_round_trip(self) -> None:
        cursor = encode_cursor("2026-01-01T00:00:00+00:00", "message-id")
        self.assertEqual(decode_cursor(cursor), ("2026-01-01T00:00:00+00:00", "message-id"))

    def test_cursor_is_url_safe(self) -> None:
        cursor = encode_cursor("2026-01-01T00:00:00+00:00", "id/with+symbols")
        self.assertNotIn("=", cursor)
        self.assertNotIn("/", cursor)

    def test_invalid_cursor_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            decode_cursor("not-json")

    def test_incomplete_cursor_is_rejected(self) -> None:
        import base64

        value = base64.urlsafe_b64encode(b'["only-one"]') .decode().rstrip("=")
        with self.assertRaises(ValueError):
            decode_cursor(value)


if __name__ == "__main__":
    unittest.main()
