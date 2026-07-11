import unittest

from backend.app.core.pagination import Page, PageParams, build_page, decode_cursor, encode_cursor, parse_page_params


class ParsePageParamsTestCase(unittest.TestCase):
    def test_no_params_returns_none_to_keep_legacy_full_list_behavior(self) -> None:
        self.assertIsNone(parse_page_params(None, None, default_page_size=20, max_page_size=100))

    def test_only_page_given_uses_default_page_size(self) -> None:
        params = parse_page_params("2", None, default_page_size=20, max_page_size=100)
        self.assertIsNotNone(params)
        assert params is not None  # 为类型检查器
        self.assertEqual(params.page, 2)
        self.assertEqual(params.page_size, 20)
        self.assertEqual(params.offset, 20)
        self.assertEqual(params.limit, 20)

    def test_explicit_page_and_page_size(self) -> None:
        params = parse_page_params("3", "15", default_page_size=20, max_page_size=100)
        assert params is not None
        self.assertEqual(params.page, 3)
        self.assertEqual(params.offset, 30)

    def test_invalid_page_size_values_raise(self) -> None:
        with self.assertRaises(ValueError):
            parse_page_params("0", None, default_page_size=20, max_page_size=100)
        with self.assertRaises(ValueError):
            parse_page_params("1", "0", default_page_size=20, max_page_size=100)
        with self.assertRaises(ValueError):
            parse_page_params("1", "101", default_page_size=20, max_page_size=100)

    def test_non_integer_params_raise(self) -> None:
        with self.assertRaises(ValueError):
            parse_page_params("abc", None, default_page_size=20, max_page_size=100)


class PageTestCase(unittest.TestCase):
    def test_total_pages_and_navigation_flags(self) -> None:
        params = PageParams(page=2, page_size=10)
        page = build_page(["a", "b"], total=25, params=params)
        self.assertEqual(page.total_pages, 3)
        self.assertTrue(page.has_prev)
        self.assertTrue(page.has_next)

    def test_last_page_has_no_next(self) -> None:
        params = PageParams(page=3, page_size=10)
        page = build_page(["z"], total=25, params=params)
        self.assertFalse(page.has_next)
        self.assertTrue(page.has_prev)

    def test_to_payload_shape(self) -> None:
        params = PageParams(page=1, page_size=5)
        payload = build_page(["a"], total=1, params=params).to_payload()
        self.assertEqual(
            payload,
            {"page": 1, "page_size": 5, "total": 1, "total_pages": 1, "has_prev": False, "has_next": False},
        )


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
