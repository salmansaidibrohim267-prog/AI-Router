from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from typing import Any

from .config import AuthConfig
from .exceptions import InvalidTokenError, TokenExpiredError, TokenRevokedError
from .models import TokenClaims, TokenPair


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class SigningKeyStore:
    def __init__(self, secret: str, rotation_seconds: int = 86400, max_history: int = 5):
        self._lock = threading.Lock()
        self._rotation_seconds = rotation_seconds
        self._max_history = max(max_history, 1)
        now = time.time()
        self._keys: list[dict[str, Any]] = [
            {
                "kid": self._derive_kid(secret, now),
                "key": secret,
                "created_at": now,
            }
        ]

    @staticmethod
    def _derive_kid(secret: str, created_at: float) -> str:
        return hashlib.sha256(f"{created_at}:{secret}".encode()).hexdigest()[:16]

    @property
    def current(self) -> tuple[str, str]:
        with self._lock:
            entry = self._keys[0]
            return entry["kid"], entry["key"]

    def rotate(self, new_secret: str | None = None) -> tuple[str, str]:
        with self._lock:
            now = time.time()
            secret = new_secret or secrets.token_hex(32)
            self._keys.insert(0, {"kid": self._derive_kid(secret, now), "key": secret, "created_at": now})
            while len(self._keys) > self._max_history:
                self._keys.pop()
            entry = self._keys[0]
            return entry["kid"], entry["key"]

    def should_rotate(self, now: float | None = None) -> bool:
        with self._lock:
            created_at = self._keys[0]["created_at"]
            return (now or time.time()) - created_at >= self._rotation_seconds

    def get(self, kid: str) -> str | None:
        with self._lock:
            for entry in self._keys:
                if entry["kid"] == kid:
                    return entry["key"]
        return None

    def list_kids(self) -> list[str]:
        with self._lock:
            return [entry["kid"] for entry in self._keys]

    def export_keys(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(entry) for entry in self._keys]


class TokenDenylist:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, float] = {}

    def revoke(self, jti: str, until: float) -> None:
        with self._lock:
            self._entries[jti] = until

    def is_revoked(self, jti: str, now: float | None = None) -> bool:
        current = now or time.time()
        with self._lock:
            for entry in list(self._entries):
                if self._entries[entry] < current:
                    del self._entries[entry]
            return jti in self._entries

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class JWTManager:
    def __init__(
        self,
        secret: str,
        config: AuthConfig | None = None,
        key_store: SigningKeyStore | None = None,
        denylist: TokenDenylist | None = None,
    ):
        self._config = config or AuthConfig()
        self._key_store = key_store or SigningKeyStore(
            secret,
            rotation_seconds=self._config.signing_key_rotation_seconds,
            max_history=self._config.max_key_history,
        )
        self._denylist = denylist or TokenDenylist()

    @property
    def key_store(self) -> SigningKeyStore:
        return self._key_store

    @property
    def denylist(self) -> TokenDenylist:
        return self._denylist

    def rotate_keys(self, new_secret: str | None = None) -> str:
        kid, _ = self._key_store.rotate(new_secret)
        return kid

    @staticmethod
    def _encode_part(payload: dict[str, Any]) -> str:
        return _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def _sign(self, header: str, body: str, key: str) -> str:
        signing_input = f"{header}.{body}".encode("ascii")
        digest = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return _b64url_encode(digest)

    def issue(self, claims: TokenClaims) -> str:
        now = claims.iat or time.time()
        exp = claims.exp or (now + self._config.access_token_ttl)
        kid, key = self._key_store.current
        header = self._encode_part({"alg": "HS256", "typ": "JWT", "kid": kid})
        payload = self._encode_part(
            {
                "sub": claims.sub,
                "type": claims.token_type,
                "jti": claims.jti or uuid.uuid4().hex,
                "sid": claims.session_id,
                "tenant_id": claims.tenant_id,
                "roles": claims.roles,
                "iat": now,
                "exp": exp,
            }
        )
        signature = self._sign(header, payload, key)
        return f"{header}.{payload}.{signature}"

    def parse(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Malformed token")
        header_raw, body_raw, signature = parts
        try:
            header = json.loads(_b64url_decode(header_raw).decode("utf-8"))
            payload = json.loads(_b64url_decode(body_raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise InvalidTokenError("Malformed token") from None
        if not isinstance(payload, dict):
            raise InvalidTokenError("Malformed token")
        kid = header.get("kid", "")
        key = self._key_store.get(kid)
        if key is None:
            raise InvalidTokenError("Unknown signing key")
        expected = self._sign(header_raw, body_raw, key)
        if not hmac.compare_digest(expected, signature):
            raise InvalidTokenError("Invalid signature")
        return payload

    def validate(self, token: str, token_type: str = "access") -> TokenClaims:
        payload = self.parse(token)
        claims = TokenClaims.from_dict(payload)
        if claims.token_type != token_type:
            raise InvalidTokenError(f"Expected {token_type} token")
        if claims.exp <= time.time():
            raise TokenExpiredError("Token expired")
        if self._denylist.is_revoked(claims.jti):
            raise TokenRevokedError("Token revoked")
        return claims

    def issue_pair(self, user_id: str, tenant_id: str, roles: list[str], session_id: str) -> TokenPair:
        now = time.time()
        access_claims = TokenClaims(
            sub=user_id,
            tenant_id=tenant_id,
            roles=roles,
            token_type="access",
            jti=uuid.uuid4().hex,
            session_id=session_id,
            iat=now,
            exp=now + self._config.access_token_ttl,
        )
        refresh_claims = TokenClaims(
            sub=user_id,
            tenant_id=tenant_id,
            roles=roles,
            token_type="refresh",
            jti=uuid.uuid4().hex,
            session_id=session_id,
            iat=now,
            exp=now + self._config.refresh_token_ttl,
        )
        access_token = self.issue(access_claims)
        refresh_token = self.issue(refresh_claims)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_jti=access_claims.jti,
            refresh_jti=refresh_claims.jti,
            expires_in=self._config.access_token_ttl,
        )

    def revoke_token(self, token: str) -> str:
        payload = self.parse(token)
        claims = TokenClaims.from_dict(payload)
        self._denylist.revoke(claims.jti, claims.exp)
        return claims.jti

    def rotate_pair(self, refresh_token: str, session_id: str) -> TokenPair:
        claims = self.validate(refresh_token, token_type="refresh")
        self._denylist.revoke(claims.jti, claims.exp)
        return self.issue_pair(claims.sub, claims.tenant_id, claims.roles, session_id)
