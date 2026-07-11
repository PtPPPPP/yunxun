import unittest

from backend.app.core.request_context import get_request_id, normalize_request_id, reset_request_id, set_request_id


class RequestContextTestCase(unittest.TestCase):
    def test_safe_client_request_id_is_preserved(self) -> None:
        self.assertEqual(normalize_request_id("client-request_123"), "client-request_123")

    def test_unsafe_request_id_is_replaced(self) -> None:
        self.assertNotEqual(normalize_request_id("bad id\nsecret"), "bad id\nsecret")

    def test_short_request_id_is_replaced(self) -> None:
        self.assertEqual(len(normalize_request_id("short")), 32)

    def test_context_is_reset_after_request(self) -> None:
        token = set_request_id("request-123")
        self.assertEqual(get_request_id(), "request-123")
        reset_request_id(token)
        self.assertEqual(get_request_id(), "")
