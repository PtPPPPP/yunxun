import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.core.errors import AppError


logger = logging.getLogger("yunxun.backend")


def success_payload(**payload: Any) -> dict[str, Any]:
    return {"success": True, **payload}


def error_response(message: str, status_code: int, *, code: str | None = None) -> JSONResponse:
    """构造统一的错误响应。

    ``code`` 仅在 ``AppError``（或显式传入）时出现，普通错误载荷保持
    ``{"success": False, "error": message}`` 的历史结构，确保向后兼容。
    """
    body: dict[str, Any] = {"success": False, "error": message}
    if code:
        body["code"] = code
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求处理失败。"
    # AppError 是 HTTPException 的子类，统一在这里暴露稳定的 code 字段。
    code = getattr(exc, "code", None)
    return error_response(detail, exc.status_code, code=code)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    field_name = ".".join(str(item) for item in first_error.get("loc", [])[1:]) or "参数"
    message = first_error.get("msg", "参数格式不正确。")
    return error_response(f"{field_name}: {message}", 422)


async def unexpected_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error", exc_info=exc)
    return error_response("服务暂时不可用，请稍后重试。", 500)
