import asyncio
import json
import unittest

from fastapi import HTTPException

from backend.app.core import exceptions
from backend.app.core.errors import AppError, ErrorCode, not_found, rate_limited


def body(response) -> dict:
    return json.loads(response.body)


class AppErrorTestCase(unittest.TestCase):
    def test_app_error_is_http_exception_for_backward_compatibility(self) -> None:
        error = not_found()
        self.assertIsInstance(error, HTTPException)
        self.assertIsInstance(error, AppError)
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.code, ErrorCode.NOT_FOUND)
        self.assertEqual(error.message, "资源不存在或已被删除。")
        self.assertEqual(error.detail, "资源不存在或已被删除。")

    def test_factories_carry_stable_codes_and_messages(self) -> None:
        self.assertEqual(not_found().code, ErrorCode.NOT_FOUND)
        self.assertEqual(not_found("会话不存在。").message, "会话不存在。")

        limited = rate_limited(30)
        self.assertEqual(limited.code, ErrorCode.RATE_LIMITED)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "30")


class ErrorResponseTestCase(unittest.TestCase):
    def test_plain_error_has_no_code_field(self) -> None:
        response = exceptions.error_response("出错了", 400)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body(response), {"success": False, "error": "出错了"})

    def test_error_with_code_includes_code_field(self) -> None:
        response = exceptions.error_response("资源不存在。", 404, code=ErrorCode.NOT_FOUND)
        self.assertEqual(
            body(response),
            {"success": False, "error": "资源不存在。", "code": "NOT_FOUND"},
        )

    def test_http_exception_handler_surfaces_app_error_code(self) -> None:
        response = asyncio.run(exceptions.http_exception_handler(None, not_found()))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body(response)["code"], "NOT_FOUND")

    def test_http_exception_handler_keeps_legacy_shape_without_code(self) -> None:
        legacy = HTTPException(status_code=429, detail="太快了")
        response = asyncio.run(exceptions.http_exception_handler(None, legacy))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body(response), {"success": False, "error": "太快了"})


if __name__ == "__main__":
    unittest.main()
