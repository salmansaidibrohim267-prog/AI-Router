from __future__ import annotations

import base64
import json
from typing import Any, Protocol

import httpx

from app.mcp.config import MCPConfig
from app.mcp.exceptions import MCPAuthError
from app.mcp.models import MCPAuthType


class Authenticator(Protocol):
    name: str

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:  # pragma: no cover
        ...

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        ...


class NoAuth:
    name = "none"

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return headers

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


class APIKeyAuth:
    name = "api_key"

    def __init__(self, api_key: str, header: str = "X-API-Key"):
        self._api_key = api_key
        self._header = header

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:
        headers = dict(headers)
        headers[self._header] = self._api_key
        return headers

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


class BearerTokenAuth:
    name = "bearer"

    def __init__(self, token: str):
        self._token = token

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:
        headers = dict(headers)
        headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


class OAuth2Auth:
    name = "oauth2"

    def __init__(self, token: str = "", client_id: str = "", client_secret: str = "",
                 token_url: str = "", scope: str = ""):
        self._token = token
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope

    def _basic_auth(self) -> str:
        raw = f"{self._client_id}:{self._client_secret}".encode()
        return base64.b64encode(raw).decode()

    async def acquire_token(self) -> str:
        if self._token:
            return self._token
        if not self._token_url:
            raise MCPAuthError("OAuth2 requires a token or token_url")

        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "scope": self._scope,
        }
        headers = {"Authorization": f"Basic {self._basic_auth()}"}
        async with httpx.AsyncClient() as client:
            response = await client.post(self._token_url, data=payload, headers=headers)
            if response.status_code >= 400:
                raise MCPAuthError(f"OAuth2 token acquisition failed: HTTP {response.status_code}")
            body = response.json()
        token = str(body.get("access_token", ""))
        if not token:
            raise MCPAuthError("OAuth2 token response missing access_token")
        return token

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:
        headers = dict(headers)
        headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


class CustomHeadersAuth:
    name = "custom_headers"

    def __init__(self, headers: dict[str, str]):
        self._headers = dict(headers)

    def apply_headers(self, headers: dict[str, str]) -> dict[str, str]:
        merged = dict(headers)
        merged.update(self._headers)
        return merged

    def apply_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


class AuthFactory:
    def create(self, auth_type: str | MCPAuthType, config: MCPConfig | None = None) -> Authenticator:
        config = config or MCPConfig()
        try:
            kind = MCPAuthType(auth_type) if isinstance(auth_type, str) else auth_type
        except ValueError as e:
            raise MCPAuthError(f"Unsupported auth type: {auth_type}") from e
        if kind == MCPAuthType.NONE:
            return NoAuth()
        if kind == MCPAuthType.API_KEY:
            return APIKeyAuth(config.api_key, config.api_key_header)
        if kind == MCPAuthType.BEARER:
            return BearerTokenAuth(config.bearer_token)
        if kind == MCPAuthType.OAUTH2:
            return OAuth2Auth(
                token=config.oauth2_token,
                client_id=config.oauth2_client_id,
                client_secret=config.oauth2_client_secret,
                token_url=config.oauth2_token_url,
            )
        if kind == MCPAuthType.CUSTOM_HEADERS:
            return CustomHeadersAuth(config.custom_headers)
        raise MCPAuthError(f"Unsupported auth type: {auth_type}")  # pragma: no cover

    def names(self) -> list[str]:
        return [t.value for t in MCPAuthType]
