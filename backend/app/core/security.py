import hashlib
import hmac
import secrets

from backend.app.core.config import get_settings


def hash_password(password: str, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120000)
    return f"{salt_value}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, _ = password_hash.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), password_hash)


def create_token() -> str:
    return secrets.token_urlsafe(32)


def hash_auth_token(raw_token: str) -> str:
    secret = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def safe_fingerprint(value: str) -> str:
    secret = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
