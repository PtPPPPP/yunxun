import asyncio
import json
import unittest

from fastapi import HTTPException

from backend.app.core import exceptions
from backend.app.core.errors import (
    AppError,
    ErrorCode,
    duplicate_request,
    forbidden,
    message_empty,
    message_too_long,
    model_unavailable,
    not_found,
    session_not_found,
)


def body(response) -> dict:
    return json.loads(response.body)


class AppErrorTestCase(unittest.TestCase):
    def test_app_error_is_http_exception_for_backward_compatibility(self) -> None:
        error = session_not_found("abc")
        self.assertIsInstance(error, HTTPException)
        self.assertIsInstance(error, AppError)
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.code, ErrorCode.SESSION_NOT_FOUND)
        self.assertEqual(error.message, "会话不存在。")
        self.assertEqual(error.detail, "会话不存在。")

    def test_factories_carry_stable_codes_and_messages(self) -> None:
        self.assertEqual(forbidden().code, ErrorCode.FORBIDDEN)
        self.assertEqual(forbidden().status_code, 403)
        self.assertEqual(message_empty().code, ErrorCode.MESSAGE_EMPTY)
        self.assertEqual(message_empty().status_code, 400)
        self.assertEqual(message_too_long(3000).message, "输入内容不能超过 3000 个字符。")
        self.assertEqual(model_unavailable().code, ErrorCode.MODEL_UNAVAILABLE)
        self.assertEqual(model_unavailable().status_code, 502)
        self.assertEqual(duplicate_request().status_code, 409)
        self.assertEqual(duplicate_request().code, ErrorCode.DUPLICATE_REQUEST)
        self.assertEqual(not_found().code, ErrorCode.NOT_FOUND)


class ErrorResponseTestCase(unittest.TestCase):
    def test_plain_error_has_no_code_field(self) -> None:
        response = exceptions.error_response("出错了", 400)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body(response), {"success": False, "error": "出错了"})

    def test_error_with_code_includes_code_field(self) -> None:
        response = exceptions.error_response("会话不存在。", 404, code=ErrorCode.SESSION_NOT_FOUND)
        self.assertEqual(
            body(response),
            {"success": False, "error": "会话不存在。", "code": "SESSION_NOT_FOUND"},
        )

    def test_http_exception_handler_surfaces_app_error_code(self) -> None:
        response = asyncio.run(exceptions.http_exception_handler(None, session_not_found("abc")))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body(response)["code"], "SESSION_NOT_FOUND")

    def test_http_exception_handler_keeps_legacy_shape_without_code(self) -> None:
        legacy = HTTPException(status_code=429, detail="太快了")
        response = asyncio.run(exceptions.http_exception_handler(None, legacy))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body(response), {"success": False, "error": "太快了"})


if __name__ == "__main__":
    unittest.main()
