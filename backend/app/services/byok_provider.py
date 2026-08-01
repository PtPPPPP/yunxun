from __future__ import annotations

import json
import time
from typing import Any

import httpx

from backend.app.core.config import CHAT_SYSTEM_PROMPT, get_settings
from backend.app.core.errors import ErrorCode, model_config_error


MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


def _provider_error(code: str, message: str, status: int):
    return model_config_error(code, message, status)


async def _read_limited_response(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_PROVIDER_RESPONSE_BYTES:
            raise _provider_error(ErrorCode.MODEL_RESPONSE_INVALID, "模型响应体过大，已安全中止。", 502)
        chunks.append(chunk)
    return b"".join(chunks)


async def call_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    history: list[dict[str, str]],
    verification: bool = False,
) -> tuple[str, int]:
    settings = get_settings()
    started = time.perf_counter()
    timeout_seconds = min(settings.ai_timeout_seconds, 12.0) if verification else settings.ai_timeout_seconds
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *history],
        "temperature": 0 if verification else 0.35,
        "max_tokens": 8 if verification else 1200,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            ) as response:
                body = await _read_limited_response(response)
                status = response.status_code
    except httpx.TimeoutException as exc:
        raise _provider_error(ErrorCode.MODEL_TIMEOUT, "模型服务响应超时，请稍后重试。", 504) from exc
    except httpx.RequestError as exc:
        raise _provider_error(ErrorCode.MODEL_UNAVAILABLE, "模型服务暂时不可用，请稍后重试。", 502) from exc

    if status in {301, 302, 303, 307, 308}:
        raise _provider_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "模型服务重定向已被安全策略阻止。", 400)
    if status in {401, 403}:
        raise _provider_error(ErrorCode.MODEL_AUTH_FAILED, "API Key 鉴权失败，请检查后重试。", 400)
    if status == 429:
        raise _provider_error(ErrorCode.MODEL_RATE_LIMITED, "模型服务繁忙，请稍后重试。", 429)
    if status == 404:
        raise _provider_error(ErrorCode.MODEL_RESPONSE_INVALID, "模型不存在或接口地址不正确。", 400)
    if status < 200 or status >= 300:
        raise _provider_error(ErrorCode.MODEL_UNAVAILABLE, "模型服务暂时不可用，请稍后重试。", 502)

    try:
        data = json.loads(body)
        reply = data["choices"][0]["message"]["content"].strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise _provider_error(ErrorCode.MODEL_RESPONSE_INVALID, "模型返回格式不正确。", 502) from exc
    if not reply:
        raise _provider_error(ErrorCode.MODEL_RESPONSE_INVALID, "模型没有返回有效内容。", 502)
    return reply, round((time.perf_counter() - started) * 1000)
