from __future__ import annotations

from fastapi import HTTPException


class ErrorCode:
    AUTH_REQUIRED = "AUTH_REQUIRED"
    GUEST_ALREADY_UPGRADED = "GUEST_ALREADY_UPGRADED"
    CONFLICT = "CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    RATE_LIMITED = "RATE_LIMITED"


class AppError(HTTPException):
    """客户端按 code 区分业务错误，message 用于展示。"""

    code: str = ErrorCode.BAD_REQUEST

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message


def rate_limited(retry_after: int) -> AppError:
    error = AppError(
        code=ErrorCode.RATE_LIMITED,
        message=f"请求太频繁了，请 {retry_after} 秒后再试。",
        status_code=429,
    )
    error.headers = {"Retry-After": str(retry_after)}
    return error


def conflict(message: str) -> AppError:
    return AppError(code=ErrorCode.CONFLICT, message=message, status_code=409)


def not_found(message: str = "资源不存在或已被删除。") -> AppError:
    return AppError(code=ErrorCode.NOT_FOUND, message=message, status_code=404)
