"""统一异常与错误码体系。

把过去散落在各处的 ``raise HTTPException(detail=...)`` 收敛为一套带稳定
机器可读 ``code`` 的领域异常。这样前端可以按 ``code`` 做精确分支（例如
会话不存在、权限不足、重复请求），而不是只能猜测 HTTP 状态码；同时把
面向用户的话术集中在一处维护。

``AppError`` 继承自 ``HTTPException``，因此：

* 现有 ``assertRaises(HTTPException)`` 形式的单测无需改动仍然成立；
* 仍由 ``exceptions.http_exception_handler`` 统一处理，只需在该处理器里
  读取 ``code`` 字段并入参到响应体即可，不破坏既有错误载荷结构。
"""

from __future__ import annotations

from fastapi import HTTPException


class ErrorCode:
    """稳定的错误码常量。

    命名遵循 ``DOMAIN_REASON`` 约定。新增场景时只在这里追加常量，避免
    在调用处出现魔法字符串。
    """

    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    MESSAGE_EMPTY = "MESSAGE_EMPTY"
    MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    RATE_LIMITED = "RATE_LIMITED"


class AppError(HTTPException):
    """携带稳定 ``code`` 的领域异常。

    与普通 ``HTTPException`` 的区别：响应体里会多一个 ``code`` 字段（见
    :func:`backend.app.core.exceptions.error_response`），其余行为完全一致，
    所以老调用方和测试都不受影响。
    """

    code: str = ErrorCode.BAD_REQUEST

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message


def session_not_found(session_id: str) -> AppError:
    return AppError(
        code=ErrorCode.SESSION_NOT_FOUND,
        message="会话不存在。",
        status_code=404,
    )


def forbidden(message: str = "你无权访问这个会话。") -> AppError:
    return AppError(code=ErrorCode.FORBIDDEN, message=message, status_code=403)


def message_empty() -> AppError:
    return AppError(code=ErrorCode.MESSAGE_EMPTY, message="输入内容不能为空。", status_code=400)


def message_too_long(limit: int) -> AppError:
    return AppError(
        code=ErrorCode.MESSAGE_TOO_LONG,
        message=f"输入内容不能超过 {limit} 个字符。",
        status_code=400,
    )


def model_unavailable(message: str = "模型服务暂时不可用，请稍后重试。") -> AppError:
    return AppError(code=ErrorCode.MODEL_UNAVAILABLE, message=message, status_code=502)


def duplicate_request() -> AppError:
    return AppError(
        code=ErrorCode.DUPLICATE_REQUEST,
        message="检测到重复请求，相同内容刚提交过，请稍后再试。",
        status_code=409,
    )


def idempotency_conflict() -> AppError:
    return AppError(
        code=ErrorCode.IDEMPOTENCY_CONFLICT,
        message="同一请求标识不能用于不同内容，请刷新后重试。",
        status_code=409,
    )


def rate_limited(retry_after: int) -> AppError:
    error = AppError(
        code=ErrorCode.RATE_LIMITED,
        message=f"请求太频繁了，请 {retry_after} 秒后再试。",
        status_code=429,
    )
    error.headers = {"Retry-After": str(retry_after)}
    return error


def not_found(message: str = "资源不存在或已被删除。") -> AppError:
    return AppError(code=ErrorCode.NOT_FOUND, message=message, status_code=404)
