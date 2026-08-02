from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Callable

from ..exceptions import InvalidTokenError, ProviderError
from ..models import ProviderUser
from .base import AuthProvider
from .oauth2 import Transport, default_transport

VerifyKey = Callable[[str], str | bytes | None]


class OIDCProvider(AuthProvider):
    name = "oidc"

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        issuer: str = "",
        discovery_url: str = "",
        transport: Transport | None = None,
        key_provider: VerifyKey | None = None,
        allowed_algs: tuple[str, ...] = ("HS256", "RS256"),
        **options: Any,
    ):
        super().__init__(**options)
        self._client_id = client_id
        self._client_secret = client_secret
        self._issuer = issuer
        self._discovery_url = discovery_url
        self._transport = transport or default_transport
        self._key_provider = key_provider
        self._allowed_algs = allowed_algs

    def _discover(self) -> dict[str, Any]:
        if not self._discovery_url:
            return {}
        try:
            data = self._transport(self._discovery_url, {})
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OIDC discovery failed: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("OIDC discovery malformed")
        return data

    def _decode_part(self, part: str) -> dict[str, Any]:
        padding = "=" * (-len(part) % 4)
        try:
            raw = base64.urlsafe_b64decode(part + padding)
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise InvalidTokenError("Malformed id_token") from None
        if not isinstance(payload, dict):
            raise InvalidTokenError("Malformed id_token")
        return payload

    def _verify_signature(self, header: dict[str, Any], signing_input: str, signature: str) -> None:
        alg = str(header.get("alg", ""))
        if alg not in self._allowed_algs:
            raise InvalidTokenError(f"Algorithm {alg!r} not allowed")
        key: str | bytes | None = None
        if alg == "RS256" and self._key_provider is not None:
            key = self._key_provider(str(header.get("kid", "")))
        elif alg == "HS256":
            key = self._client_secret
        if not key:
            raise InvalidTokenError("No signing key available")
        if isinstance(key, str):
            key = key.encode("utf-8")
        expected = hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
        padding = "=" * (-len(signature) % 4)
        actual = base64.urlsafe_b64decode(signature + padding)
        if not hmac.compare_digest(expected, actual):
            raise InvalidTokenError("Invalid id_token signature")

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        id_token = str(credentials.get("id_token", ""))
        if not id_token:
            raise ProviderError("Missing id_token")
        parts = id_token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Malformed id_token")
        header_raw, payload_raw, signature = parts
        header = self._decode_part(header_raw)
        payload = self._decode_part(payload_raw)
        self._verify_signature(header, f"{header_raw}.{payload_raw}", signature)

        issuer = self._issuer or (self._discover().get("issuer") or "")
        if issuer and payload.get("iss") != issuer:
            raise InvalidTokenError("Issuer mismatch")
        if payload.get("aud") not in (None, self._client_id) and self._client_id not in payload.get("aud", []):
            raise InvalidTokenError("Audience mismatch")
        now = time.time()
        if payload.get("exp", 0) <= now:
            raise InvalidTokenError("id_token expired")
        if payload.get("nbf", 0) > now:
            raise InvalidTokenError("id_token not yet valid")
        sub = str(payload.get("sub", ""))
        if not sub:
            raise InvalidTokenError("id_token missing subject")
        return ProviderUser(
            id=sub,
            username=str(payload.get("preferred_username") or payload.get("email") or sub),
            email=str(payload.get("email", "")),
            display_name=str(payload.get("name", "")),
            roles=[str(r) for r in payload.get("roles", [])],
            attributes=payload,
        )
