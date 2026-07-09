import base64
import binascii
import re
from dataclasses import dataclass

from fastapi import HTTPException


DATA_URL_PATTERN = re.compile(r"^data:(?P<mime>[-\w.]+/[-\w.+]+);base64,(?P<data>.+)$", re.DOTALL)
MIME_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
DEFAULT_ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(frozen=True)
class ImageUploadPolicy:
    max_bytes: int
    allowed_mime_types: frozenset[str] = DEFAULT_ALLOWED_MIME_TYPES


@dataclass(frozen=True)
class ValidatedImagePayload:
    base64_data: str
    mime_type: str
    size_bytes: int


def validate_image_payload(payload: str, policy: ImageUploadPolicy) -> ValidatedImagePayload:
    normalized = payload.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="图片内容不能为空。")

    declared_mime, base64_data = _split_data_url(normalized)
    if declared_mime and declared_mime not in policy.allowed_mime_types:
        raise HTTPException(status_code=400, detail=f"仅支持 {', '.join(sorted(policy.allowed_mime_types))} 图片。")

    raw_bytes = _decode_base64(base64_data)
    if len(raw_bytes) > policy.max_bytes:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {_format_bytes(policy.max_bytes)}。")

    detected_mime = _detect_mime_type(raw_bytes)
    if detected_mime not in policy.allowed_mime_types:
        raise HTTPException(status_code=400, detail=f"图片格式不受支持，仅支持 {', '.join(sorted(policy.allowed_mime_types))}。")
    if declared_mime and declared_mime != detected_mime:
        raise HTTPException(status_code=400, detail="图片 MIME 类型与实际内容不一致。")

    return ValidatedImagePayload(base64_data=base64_data, mime_type=detected_mime, size_bytes=len(raw_bytes))


def _split_data_url(payload: str) -> tuple[str | None, str]:
    match = DATA_URL_PATTERN.match(payload)
    if not match:
        return None, _compact_base64(payload)
    return match.group("mime").lower(), _compact_base64(match.group("data"))


def _compact_base64(value: str) -> str:
    return "".join(value.split())


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="图片 Base64 格式不正确。") from exc


def _detect_mime_type(raw_bytes: bytes) -> str:
    if raw_bytes.startswith(MIME_SIGNATURES["image/png"][0]):
        return "image/png"
    if raw_bytes.startswith(MIME_SIGNATURES["image/jpeg"][0]):
        return "image/jpeg"
    if raw_bytes.startswith(MIME_SIGNATURES["image/webp"][0]) and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(status_code=400, detail="无法识别图片类型，请上传 JPG、PNG 或 WebP。")


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
