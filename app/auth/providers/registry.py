from __future__ import annotations

from typing import Any

from ..config import AuthConfig
from ..exceptions import ProviderNotFoundError
from ..repository import UserRepository
from .base import AuthProvider
from .custom import CustomProvider
from .ldap import LDAPProvider
from .local import LocalProvider
from .oauth2 import OAuth2Provider
from .oidc import OIDCProvider
from .saml import SAMLProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, AuthProvider] = {}

    def register(self, provider: AuthProvider) -> AuthProvider:
        self._providers[provider.name] = provider
        return provider

    def get(self, name: str) -> AuthProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderNotFoundError(name)
        return provider

    def has(self, name: str) -> bool:
        return name in self._providers

    def names(self) -> list[str]:
        return sorted(self._providers)

    def unregister(self, name: str) -> bool:
        return self._providers.pop(name, None) is not None


def create_provider(
    name: str,
    registry: ProviderRegistry | None = None,
    users: UserRepository | None = None,
    config: AuthConfig | None = None,
    **options: Any,
) -> AuthProvider:
    if registry is not None and registry.has(name):
        return registry.get(name)
    if name == "local":
        return LocalProvider(users=users, config=config)
    if name == "custom":
        return CustomProvider(**options)
    if name == "oauth2":
        return OAuth2Provider(**options)
    if name == "oidc":
        return OIDCProvider(**options)
    if name == "ldap":
        return LDAPProvider(**options)
    if name == "saml":
        return SAMLProvider(**options)
    raise ProviderNotFoundError(name)


def register_builtin_providers(
    registry: ProviderRegistry,
    users: UserRepository | None = None,
    config: AuthConfig | None = None,
) -> None:
    if not registry.has("local"):
        registry.register(LocalProvider(users=users, config=config))
