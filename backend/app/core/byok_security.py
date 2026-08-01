from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import ErrorCode, model_config_error


PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
}


def _encryption_error(message: str = "凭据加密服务不可用，请联系管理员。"):
    return model_config_error(ErrorCode.CREDENTIAL_ENCRYPTION_UNAVAILABLE, message, 503)


def _decode_master_key(raw_key: str) -> bytes:
    if not raw_key.strip():
        raise _encryption_error()
    try:
        padding = "=" * (-len(raw_key.strip()) % 4)
        key = base64.urlsafe_b64decode((raw_key.strip() + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise _encryption_error("凭据加密主密钥格式无效。") from exc
    if len(key) != 32:
        raise _encryption_error("凭据加密主密钥必须是 32 字节的 URL-safe Base64。")
    return key


class CredentialCipher:
    VERSION = b"\x01"

    def __init__(self, raw_key: str | None = None) -> None:
        settings = get_settings()
        self._key = _decode_master_key(settings.credential_encryption_key if raw_key is None else raw_key)

    def encrypt(self, api_key: str) -> tuple[bytes, str]:
        normalized = api_key.strip()
        if len(normalized) < 8:
            raise model_config_error(ErrorCode.MODEL_KEY_INVALID, "API Key 格式无效。", 400)
        nonce = __import__("secrets").token_bytes(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, normalized.encode("utf-8"), b"yunxun-byok-v1")
        fingerprint = hmac.new(self._key, b"fingerprint:" + normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        return self.VERSION + nonce + ciphertext, fingerprint

    def decrypt(self, encrypted: bytes) -> str:
        try:
            payload = bytes(encrypted)
            if len(payload) < 30 or payload[:1] != self.VERSION:
                raise ValueError("unsupported credential payload")
            plaintext = AESGCM(self._key).decrypt(payload[1:13], payload[13:], b"yunxun-byok-v1")
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise _encryption_error("API Key 无法解密，请重新配置。") from exc


def _normalize_url(raw_url: str, *, allow_http: bool) -> str:
    try:
        parsed = urlsplit(raw_url.strip())
    except ValueError as exc:
        raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "API Base URL 格式无效。", 400) from exc
    allowed_schemes = {"https"} | ({"http"} if allow_http else set())
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "API Base URL 必须使用 HTTPS。", 400)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise model_config_error(
            ErrorCode.MODEL_BASE_URL_NOT_ALLOWED,
            "API Base URL 不能包含账号、密码、查询参数或片段。",
            400,
        )
    host = parsed.hostname.rstrip(".").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "API Base URL 端口无效。", 400) from exc
    default_port = (parsed.scheme.lower() == "https" and port == 443) or (parsed.scheme.lower() == "http" and port == 80)
    netloc = f"[{host}]" if ":" in host else host
    if port and not default_port:
        netloc = f"{netloc}:{port}"
    path = "/" + parsed.path.strip("/") if parsed.path.strip("/") else ""
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _assert_public_host(hostname: str, port: int) -> None:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "API Base URL 域名无法解析。", 400) from exc
    if not addresses:
        raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "API Base URL 域名无法解析。", 400)
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise model_config_error(
                ErrorCode.MODEL_BASE_URL_NOT_ALLOWED,
                "API Base URL 不能指向内网、回环、保留或链路本地地址。",
                400,
            )


def validate_provider_base_url(provider: str, raw_url: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    normalized_provider = provider.strip().lower()
    if normalized_provider not in settings.byok_allowed_providers:
        raise model_config_error(ErrorCode.MODEL_PROVIDER_UNSUPPORTED, "暂不支持该模型服务商。", 400)

    preset = PROVIDER_BASE_URLS.get(normalized_provider)
    if preset:
        normalized = _normalize_url(raw_url or preset, allow_http=False)
        if normalized != preset:
            raise model_config_error(
                ErrorCode.MODEL_BASE_URL_NOT_ALLOWED,
                "该服务商只能使用系统预设的 API Base URL。",
                400,
            )
    elif normalized_provider == "openai-compatible":
        if not raw_url.strip():
            raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "请填写允许的 API Base URL。", 400)
        normalized = _normalize_url(raw_url, allow_http=settings.byok_allow_http and not settings.is_production)
        allowed = {
            _normalize_url(item, allow_http=settings.byok_allow_http and not settings.is_production)
            for item in settings.byok_allowed_base_urls
        }
        if normalized not in allowed:
            raise model_config_error(ErrorCode.MODEL_BASE_URL_NOT_ALLOWED, "该 API Base URL 不在管理员白名单中。", 400)
    else:
        raise model_config_error(ErrorCode.MODEL_PROVIDER_UNSUPPORTED, "暂不支持该模型服务商。", 400)

    parsed = urlsplit(normalized)
    _assert_public_host(parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80))
    return normalized
