from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from .exceptions import TenantNotFoundError
from .models import Tenant


class TenantRepository(ABC):
    @abstractmethod
    def create(self, tenant: Tenant) -> Tenant:
        raise NotImplementedError

    @abstractmethod
    def get(self, tenant_id: str) -> Tenant:
        raise NotImplementedError

    @abstractmethod
    def update(self, tenant: Tenant) -> Tenant:
        raise NotImplementedError

    @abstractmethod
    def delete(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Tenant]:
        raise NotImplementedError


class InMemoryTenantRepository(TenantRepository):
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._lock = threading.Lock()

    def create(self, tenant: Tenant) -> Tenant:
        with self._lock:
            self._tenants[tenant.id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant:
        with self._lock:
            tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)
        return tenant

    def update(self, tenant: Tenant) -> Tenant:
        with self._lock:
            if tenant.id not in self._tenants:
                raise TenantNotFoundError(tenant.id)
            self._tenants[tenant.id] = tenant
        return tenant

    def delete(self, tenant_id: str) -> bool:
        with self._lock:
            if tenant_id not in self._tenants:
                raise TenantNotFoundError(tenant_id)
            del self._tenants[tenant_id]
        return True

    def list(self) -> list[Tenant]:
        with self._lock:
            return list(self._tenants.values())
