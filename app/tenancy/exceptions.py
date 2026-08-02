from __future__ import annotations


class TenancyError(Exception):
    pass


class TenantNotFoundError(TenancyError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant {tenant_id!r} not found")
        self.tenant_id = tenant_id


class TenantAlreadyExistsError(TenancyError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant {tenant_id!r} already exists")
        self.tenant_id = tenant_id


class TenantSuspendedError(TenancyError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant {tenant_id!r} is suspended")
        self.tenant_id = tenant_id


class TenantDeletedError(TenancyError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant {tenant_id!r} is deleted")
        self.tenant_id = tenant_id


class TenantResolutionError(TenancyError):
    pass


class TenantContextMissingError(TenancyError):
    def __init__(self, msg: str = "No tenant context is set for the current request"):
        super().__init__(msg)


class TenantIsolationError(TenancyError):
    pass


class TenantLimitError(TenancyError):
    pass
