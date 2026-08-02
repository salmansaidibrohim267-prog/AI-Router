from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from typing import Any, Callable

from .config import TenancyConfig
from .exceptions import (
    TenantResolutionError,
    TenantSuspendedError,
)
from .logging import TenancyLogger
from .models import TenantContext
from .statistics import TenancyMetricsTracker


def decode_jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT structure")
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise ValueError("Invalid JWT payload encoding") from exc
    claims = json.loads(decoded.decode("utf-8"))
    if not isinstance(claims, dict):
        raise ValueError("Invalid JWT payload")
    return claims


class TenantResolutionStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        raise NotImplementedError


class HeaderStrategy(TenantResolutionStrategy):
    name = "header"

    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()

    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        headers = request.get("headers") or {}
        tenant_id = headers.get(self._config.header_name) or headers.get(
            self._config.header_name.lower()
        )
        if not tenant_id:
            return None
        return TenantContext(
            tenant_id=str(tenant_id),
            resolved_by=self.name,
            auth_method="header",
        )


class JWTStrategy(TenantResolutionStrategy):
    name = "jwt"

    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()

    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        claims = request.get("jwt_claims")
        if claims is None:
            token = request.get("jwt")
            if token:
                try:
                    claims = decode_jwt_claims(str(token))
                except ValueError:
                    claims = None
        if not claims:
            return None
        issuer = claims.get(self._config.jwt_issuer_claim)
        if issuer is not None and issuer not in self._config.allowed_issuers:
            return None
        tenant_id = claims.get(self._config.jwt_claim)
        if not tenant_id:
            return None
        return TenantContext(
            tenant_id=str(tenant_id),
            resolved_by=self.name,
            auth_method="jwt",
            user_id=str(claims.get("sub", "")),
        )


class APIKeyStrategy(TenantResolutionStrategy):
    name = "api_key"

    def __init__(
        self,
        config: TenancyConfig | None = None,
        lookup: Callable[[str], str | None] | None = None,
    ):
        self._config = config or TenancyConfig()
        self._lookup = lookup

    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        api_key = request.get("api_key")
        if not api_key:
            headers = request.get("headers") or {}
            api_key = headers.get(self._config.api_key_header) or headers.get(
                self._config.api_key_header.lower()
            )
        if not api_key:
            return None
        tenant_id = None
        if self._lookup is not None:
            try:
                tenant_id = self._lookup(str(api_key))
            except Exception:
                tenant_id = None
        else:
            tenant_id = str(api_key).split(".")[0]
        if not tenant_id:
            return None
        return TenantContext(
            tenant_id=tenant_id,
            resolved_by=self.name,
            auth_method="api_key",
            attributes={"api_key": str(api_key)},
        )


class SubdomainStrategy(TenantResolutionStrategy):
    name = "subdomain"

    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()

    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        host = request.get("host") or ""
        if not host:
            headers = request.get("headers") or {}
            host = headers.get(self._config.subdomain_header) or headers.get(
                self._config.subdomain_header.lower()
            )
        host = str(host or "")
        normalized = host.split(":")[0]
        suffix = self._config.subdomain_suffix
        if suffix and normalized.endswith(suffix):
            label = normalized[: -len(suffix)]
            if label and "." not in label:
                return TenantContext(
                    tenant_id=label,
                    resolved_by=self.name,
                    auth_method="subdomain",
                    attributes={"host": normalized},
                )
        if not suffix and "." in normalized:
            label = normalized.split(".")[0]
            if label:
                return TenantContext(
                    tenant_id=label,
                    resolved_by=self.name,
                    auth_method="subdomain",
                    attributes={"host": normalized},
                )
        return None


class CustomDomainStrategy(TenantResolutionStrategy):
    name = "custom_domain"

    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()

    def resolve(self, request: dict[str, Any]) -> TenantContext | None:
        host = request.get("host") or ""
        host = str(host).split(":")[0]
        if not host:
            return None
        tenant_id = self._config.custom_domain_map.get(host)
        if not tenant_id:
            return None
        return TenantContext(
            tenant_id=tenant_id,
            resolved_by=self.name,
            auth_method="custom_domain",
            attributes={"host": host},
        )


class TenantResolver:
    def __init__(
        self,
        manager: Any | None = None,
        config: TenancyConfig | None = None,
        logger: TenancyLogger | None = None,
        metrics: TenancyMetricsTracker | None = None,
        strategies: list[TenantResolutionStrategy] | None = None,
    ):
        self._config = config or TenancyConfig()
        self._logger = logger or TenancyLogger()
        self._metrics = metrics or TenancyMetricsTracker(self._config)
        self._manager = manager
        self._strategies: list[TenantResolutionStrategy] = strategies or [
            HeaderStrategy(self._config),
            JWTStrategy(self._config),
            APIKeyStrategy(self._config),
            SubdomainStrategy(self._config),
            CustomDomainStrategy(self._config),
        ]

    @property
    def config(self) -> TenancyConfig:
        return self._config

    @property
    def strategies(self) -> list[TenantResolutionStrategy]:
        return self._strategies

    def register(self, strategy: TenantResolutionStrategy) -> None:
        self._strategies.append(strategy)

    def resolve(
        self,
        request: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        jwt_claims: dict[str, Any] | None = None,
        jwt: str | None = None,
        api_key: str | None = None,
        host: str | None = None,
        tenant_id: str | None = None,
        user_id: str = "",
    ) -> TenantContext:
        if tenant_id:
            context = TenantContext(
                tenant_id=tenant_id,
                resolved_by="explicit",
                auth_method="explicit",
                user_id=user_id,
            )
        else:
            parts: dict[str, Any] = {"headers": headers or {}}
            if jwt_claims is not None:
                parts["jwt_claims"] = jwt_claims
            if jwt:
                parts["jwt"] = jwt
            if api_key:
                parts["api_key"] = api_key
            if host:
                parts["host"] = host
            if request is not None:
                merged = dict(request)
                merged.setdefault("headers", {})
                merged.update(
                    {k: v for k, v in parts.items() if k not in ("headers",) or v}
                )
                parts = merged
            context = None
            for strategy in self._strategies:
                try:
                    context = strategy.resolve(parts)
                except Exception:
                    continue
                if context is not None:
                    break
            if context is None and self._config.allow_anonymous:
                context = TenantContext.anonymous(self._config.anonymous_tenant)
            if context is None:
                raise TenantResolutionError(
                    "Could not resolve a tenant from the request context"
                )
            if context.resolved_by:
                self._metrics.record_resolution(context.tenant_id, context.resolved_by, success=True)
        return self._enrich(context)

    def _enrich(self, context: TenantContext) -> TenantContext:
        if self._manager is None:
            return context
        try:
            tenant = self._manager.get(context.tenant_id)
        except Exception:
            raise TenantResolutionError(
                f"Resolved tenant {context.tenant_id!r} does not exist"
            )
        if tenant.is_deleted:
            raise TenantResolutionError(f"Tenant {context.tenant_id!r} is deleted")
        if tenant.is_suspended and self._config.enforce_active:
            raise TenantSuspendedError(context.tenant_id)
        return context.merged(tenant)

    async def resolve_async(self, **kwargs: Any) -> TenantContext:
        return self.resolve(**kwargs)


def create_tenant_resolver(
    manager: Any | None = None,
    config: TenancyConfig | None = None,
    logger: TenancyLogger | None = None,
    metrics: TenancyMetricsTracker | None = None,
    strategies: list[TenantResolutionStrategy] | None = None,
) -> TenantResolver:
    return TenantResolver(
        manager=manager,
        config=config,
        logger=logger,
        metrics=metrics,
        strategies=strategies,
    )
