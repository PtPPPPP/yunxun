import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from backend.app.core.errors import AppError, ErrorCode
from backend.app.services.byok_provider import call_chat_completion


REAL_ASYNC_CLIENT = httpx.AsyncClient


def run_call(handler):
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    with patch("backend.app.services.byok_provider.httpx.AsyncClient", side_effect=client_factory):
        return asyncio.run(
            call_chat_completion(
                base_url="https://api.example.com/v1",
                api_key="sk-test-secret",
                model="test-model",
                history=[{"role": "user", "content": "Reply with OK."}],
                verification=True,
            )
        )


class ByokProviderTestCase(unittest.TestCase):
    def test_success_parses_expected_response(self) -> None:
        reply, elapsed = run_call(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "OK"}}]},
                request=request,
            )
        )
        self.assertEqual(reply, "OK")
        self.assertGreaterEqual(elapsed, 0)

    def test_safe_status_mapping(self) -> None:
        for status, code in (
            (401, ErrorCode.MODEL_AUTH_FAILED),
            (429, ErrorCode.MODEL_RATE_LIMITED),
            (404, ErrorCode.MODEL_RESPONSE_INVALID),
            (307, ErrorCode.MODEL_BASE_URL_NOT_ALLOWED),
            (503, ErrorCode.MODEL_UNAVAILABLE),
        ):
            with self.subTest(status=status), self.assertRaises(AppError) as rejected:
                run_call(lambda request, status=status: httpx.Response(status, content=b"provider secret error", request=request))
            self.assertEqual(rejected.exception.code, code)
            self.assertNotIn("provider secret error", str(rejected.exception.detail))

    def test_timeout_empty_and_invalid_response(self) -> None:
        def timeout_handler(request):
            raise httpx.ReadTimeout("secret timeout detail", request=request)

        with self.assertRaises(AppError) as timeout:
            run_call(timeout_handler)
        self.assertEqual(timeout.exception.code, ErrorCode.MODEL_TIMEOUT)

        for body in (b"", json.dumps({"choices": []}).encode()):
            with self.subTest(body=body), self.assertRaises(AppError) as rejected:
                run_call(lambda request, body=body: httpx.Response(200, content=body, request=request))
            self.assertEqual(rejected.exception.code, ErrorCode.MODEL_RESPONSE_INVALID)


if __name__ == "__main__":
    unittest.main()
