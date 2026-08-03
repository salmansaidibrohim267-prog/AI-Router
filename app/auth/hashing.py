from __future__ import annotations

import hashlib
import hmac
import secrets

from .config import AuthConfig


def hash_password(password: str, iterations: int = 100_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations=iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations_str, salt_hex, digest_hex = stored.split("$")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations=iterations)
    return hmac.compare_digest(digest, expected)


def is_strong_password(password: str, config: AuthConfig | None = None) -> bool:
    cfg = config or AuthConfig()
    if len(password) < cfg.password_min_length:
        return False
    checks = [any(c.isupper() for c in password), any(c.islower() for c in password)]
    checks.append(any(c.isdigit() for c in password))
    if not cfg.mfa_enabled:
        checks.append(any(c in "!@#$%^&*()-_=+[]{};:,.<>?/" for c in password))
    return all(checks)
