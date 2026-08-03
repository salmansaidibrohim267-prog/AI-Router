from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from ..exceptions import ProviderError
from ..models import ProviderUser
from .base import AuthProvider

Transport = Callable[[str, dict[str, Any]], Any]


def default_transport(url: str, _: dict[str, Any] | None = None) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise ProviderError(f"HTTP transport failed: {exc}") from exc


class OAuth2Provider(AuthProvider):
    name = "oauth2"

    def __init__(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str = "",
        userinfo_endpoint: str = "",
        scope: str = "openid profile email",
        transport: Transport | None = None,
        username_field: str = "username",
        **options: Any,
    ):
        super().__init__(**options)
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._userinfo_endpoint = userinfo_endpoint
        self._scope = scope
        self._transport = transport or default_transport
        self._username_field = username_field

    def _exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        try:
            data = self._transport(self._token_endpoint, payload)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OAuth2 token exchange failed: {exc}") from exc
        if not isinstance(data, dict) or "access_token" not in data:
            raise ProviderError("OAuth2 token exchange failed")
        return data

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        grant = str(credentials.get("grant_type", ""))
        if grant == "authorization_code":
            data = self._exchange_code(str(credentials.get("code", "")), str(credentials.get("redirect_uri", "")))
        elif grant == "client_credentials":
            data = {"access_token": str(credentials.get("access_token", ""))}
            if not data["access_token"]:
                raise ProviderError("Missing access_token")
        elif grant == "password":
            data = self._password_grant(str(credentials.get("username", "")), str(credentials.get("password", "")))
        else:
            raise ProviderError(f"Unsupported grant type {grant!r}")

        access_token = data["access_token"]
        userinfo = self._fetch_userinfo(access_token)
        user_id = str(userinfo.get("sub") or userinfo.get("id") or userinfo.get(self._username_field) or "")
        if not user_id:
            raise ProviderError("Userinfo missing subject")
        return ProviderUser(
            id=user_id,
            username=str(userinfo.get(self._username_field) or userinfo.get("email") or user_id),
            email=str(userinfo.get("email", "")),
            display_name=str(userinfo.get("name", "")),
            roles=[str(r) for r in userinfo.get("roles", [])],
            attributes=userinfo,
        )

    def _password_grant(self, username: str, password: str) -> dict[str, Any]:
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scope,
        }
        try:
            data = self._transport(self._token_endpoint, payload)
        except Exception as exc:
            raise ProviderError(f"OAuth2 password grant failed: {exc}") from exc
        if not isinstance(data, dict) or "access_token" not in data:
            raise ProviderError("OAuth2 password grant failed")
        return data

    def _fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        if not self._userinfo_endpoint:
            return {"sub": access_token[:32], "username": f"oauth_{access_token[:8]}"}
        try:
            data = self._transport(self._userinfo_endpoint, {"access_token": access_token})
        except Exception as exc:
            raise ProviderError(f"OAuth2 userinfo failed: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("OAuth2 userinfo malformed")
        return data
