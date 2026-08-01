from __future__ import annotations

import logging
from typing import Any

from backend.app.core.audit import log_event
from backend.app.core.byok_security import CredentialCipher, validate_provider_base_url
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, ErrorCode, model_config_error
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import safe_fingerprint
from backend.app.model_config_repository import (
    create_model_config,
    delete_model_config,
    get_default_model_config,
    get_model_config,
    list_model_configs,
    public_model_config,
    save_verification_result,
    set_default_model_config,
    update_model_config,
)
from backend.app.services.byok_provider import call_chat_completion


logger = logging.getLogger("yunxun.backend.model_configs")
verify_rate_limiter = InMemoryRateLimiter()


def _require_byok(*, persistence: bool = False) -> None:
    settings = get_settings()
    if not settings.byok_enabled:
        raise model_config_error(ErrorCode.MODEL_CONFIG_CONFLICT, "管理员尚未启用用户模型配置。", 403)
    if persistence and not settings.byok_allow_persistence:
        raise model_config_error(ErrorCode.MODEL_CONFIG_CONFLICT, "管理员未启用 API Key 持久化。", 403)


def _owned_config(user_id: str, config_id: str, *, require_enabled: bool = False) -> dict[str, Any]:
    record = get_model_config(config_id)
    if not record or record["user_id"] != user_id:
        raise model_config_error(ErrorCode.MODEL_CONFIG_NOT_FOUND, "模型配置不存在或已被删除。", 404)
    if require_enabled and not record["is_enabled"]:
        raise model_config_error(ErrorCode.MODEL_CONFIG_CONFLICT, "该模型配置已停用。", 409)
    return record


def model_config_status(user_id: str) -> dict[str, Any]:
    settings = get_settings()
    configs = [public_model_config(item) for item in list_model_configs(user_id)] if settings.byok_enabled else []
    return {
        "enabled": settings.byok_enabled,
        "persistence_enabled": settings.byok_allow_persistence,
        "allowed_providers": settings.byok_allowed_providers if settings.byok_enabled else [],
        "system_model_available": settings.ai_configured,
        "configs": configs,
    }


def create_user_model_config(user_id: str, payload: Any) -> dict[str, Any]:
    _require_byok(persistence=True)
    base_url = validate_provider_base_url(payload.provider, payload.base_url)
    encrypted, fingerprint = CredentialCipher().encrypt(payload.api_key)
    record = create_model_config(
        user_id=user_id,
        provider=payload.provider.strip().lower(),
        display_name=payload.display_name.strip(),
        model=payload.model.strip(),
        base_url=base_url,
        encrypted_api_key=encrypted,
        key_fingerprint=fingerprint,
        is_default=payload.is_default,
    )
    log_event(logger, "model_config_create", user_id=user_id, config_id=record["id"], provider=record["provider"])
    return public_model_config(record)


def update_user_model_config(user_id: str, config_id: str, payload: Any) -> dict[str, Any]:
    _require_byok(persistence=True)
    current = _owned_config(user_id, config_id)
    base_url = validate_provider_base_url(payload.provider, payload.base_url)
    encrypted: bytes | None = None
    fingerprint: str | None = None
    if payload.replace_api_key:
        if not payload.api_key:
            raise model_config_error(ErrorCode.MODEL_KEY_REQUIRED, "替换密钥时必须填写新的 API Key。", 400)
        encrypted, fingerprint = CredentialCipher().encrypt(payload.api_key)
    elif payload.api_key:
        raise model_config_error(ErrorCode.MODEL_CONFIG_CONFLICT, "请先明确选择替换密钥。", 400)
    record = update_model_config(
        config_id,
        provider=payload.provider.strip().lower(),
        display_name=payload.display_name.strip(),
        model=payload.model.strip(),
        base_url=base_url,
        is_enabled=payload.is_enabled,
        encrypted_api_key=encrypted,
        key_fingerprint=fingerprint,
    )
    if record is None:
        raise model_config_error(ErrorCode.MODEL_CONFIG_NOT_FOUND, "模型配置不存在或已被删除。", 404)
    log_event(
        logger,
        "model_config_key_replace" if encrypted is not None else "model_config_update",
        user_id=user_id,
        config_id=config_id,
        provider=record["provider"],
        previous_provider=current["provider"],
    )
    return public_model_config(record)


def set_user_default_model_config(user_id: str, config_id: str) -> dict[str, Any]:
    _require_byok(persistence=True)
    _owned_config(user_id, config_id, require_enabled=True)
    record = set_default_model_config(user_id, config_id)
    if record is None:
        raise model_config_error(ErrorCode.MODEL_CONFIG_NOT_FOUND, "模型配置不存在或已停用。", 404)
    log_event(logger, "model_config_set_default", user_id=user_id, config_id=config_id)
    return public_model_config(record)


def delete_user_model_config(user_id: str, config_id: str) -> None:
    _require_byok(persistence=True)
    _owned_config(user_id, config_id)
    if not delete_model_config(user_id, config_id):
        raise model_config_error(ErrorCode.MODEL_CONFIG_NOT_FOUND, "模型配置不存在或已被删除。", 404)
    log_event(logger, "model_config_delete", user_id=user_id, config_id=config_id)


async def test_unsaved_model_config(user_id: str, client_host: str, payload: Any) -> dict[str, Any]:
    _require_byok()
    settings = get_settings()
    verify_rate_limiter.check(
        f"byok-test:{user_id}:{safe_fingerprint(client_host)}",
        settings.byok_test_requests_per_minute,
        60,
    )
    base_url = validate_provider_base_url(payload.provider, payload.base_url)
    try:
        _, elapsed_ms = await call_chat_completion(
            base_url=base_url,
            api_key=payload.api_key.strip(),
            model=payload.model.strip(),
            history=[{"role": "user", "content": "Reply with OK."}],
            verification=True,
        )
    except AppError as exc:
        log_event(
            logger,
            "model_config_test_failed",
            user_id=user_id,
            provider=payload.provider,
            model=payload.model,
            error_code=exc.code,
        )
        raise
    log_event(logger, "model_config_test_success", user_id=user_id, provider=payload.provider, model=payload.model)
    return {"status": "success", "provider": payload.provider.strip().lower(), "model": payload.model.strip(), "elapsed_ms": elapsed_ms}


async def verify_saved_model_config(user_id: str, client_host: str, config_id: str) -> dict[str, Any]:
    _require_byok()
    record = _owned_config(user_id, config_id, require_enabled=True)
    settings = get_settings()
    verify_rate_limiter.check(
        f"byok-verify:{user_id}:{safe_fingerprint(client_host)}",
        settings.byok_test_requests_per_minute,
        60,
    )
    try:
        base_url = validate_provider_base_url(record["provider"], record["base_url"])
        api_key = CredentialCipher().decrypt(record["encrypted_api_key"])
        _, elapsed_ms = await call_chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=record["model"],
            history=[{"role": "user", "content": "Reply with OK."}],
            verification=True,
        )
    except AppError as exc:
        save_verification_result(config_id, "failed", exc.code)
        log_event(logger, "model_config_verify_failed", user_id=user_id, config_id=config_id, error_code=exc.code)
        raise
    save_verification_result(config_id, "success", None)
    log_event(logger, "model_config_verify_success", user_id=user_id, config_id=config_id)
    return {"status": "success", "provider": record["provider"], "model": record["model"], "elapsed_ms": elapsed_ms}


def resolve_runtime_model_config(
    user_id: str,
    explicit_config_id: str | None,
    session_config_id: str | None,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.byok_enabled:
        return None
    selected_id = explicit_config_id or session_config_id
    record = _owned_config(user_id, selected_id, require_enabled=True) if selected_id else get_default_model_config(user_id)
    if record is None:
        return None
    base_url = validate_provider_base_url(record["provider"], record["base_url"])
    api_key = CredentialCipher().decrypt(record["encrypted_api_key"])
    return {**record, "base_url": base_url, "api_key": api_key}
