from __future__ import annotations

import contextvars
from typing import Any

from .config import TenancyConfig
from .exceptions import TenantContextMissingError
from .models import TenantContext


class TenantContextManager:
    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()
        self._var: contextvars.ContextVar[TenantContext | None] = contextvars.ContextVar(
            self._config.context_var_name, default=None
        )

    @property
    def config(self) -> TenancyConfig:
        return self._config

    def set(self, context: TenantContext) -> contextvars.Token:
        return self._var.set(context)

    def get(self) -> TenantContext | None:
        return self._var.get()

    def require(self) -> TenantContext:
        context = self._var.get()
        if context is None or not context.tenant_id:
            raise TenantContextMissingError()
        return context

    def get_or_anonymous(self) -> TenantContext:
        context = self._var.get()
        if context is not None and context.tenant_id:
            return context
        return TenantContext.anonymous(self._config.anonymous_tenant)

    def is_set(self) -> bool:
        context = self._var.get()
        return context is not None and bool(context.tenant_id)

    def clear(self, token: contextvars.Token | None = None) -> None:
        if token is not None:
            self._var.reset(token)
        else:
            self._var.set(None)

    async def run_with_context(self, context: TenantContext, coro: Any) -> Any:
        token = self.set(context)
        try:
            return await coro
        finally:
            self.clear(token)


_default_manager: TenantContextManager | None = None


def get_tenant_context_manager() -> TenantContextManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = TenantContextManager()
    return _default_manager


def get_current_tenant() -> TenantContext | None:
    return get_tenant_context_manager().get()


def require_current_tenant() -> TenantContext:
    return get_tenant_context_manager().require()


def set_current_tenant(context: TenantContext) -> contextvars.Token:
    return get_tenant_context_manager().set(context)
