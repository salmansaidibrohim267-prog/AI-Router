from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class TenancyConfig:
    header_name: str = "X-Tenant-ID"
    jwt_claim: str = "tenant_id"
    jwt_issuer_claim: str = "iss"
    allowed_issuers: tuple[str, ...] = ("airouter",)
    api_key_header: str = "X-API-Key"
    subdomain_header: str = "Host"
    subdomain_suffix: str = ".airouter.app"
    custom_domain_map: dict[str, str] = field(default_factory=dict)
    context_var_name: str = "tenant_context"
    allow_anonymous: bool = False
    anonymous_tenant: str = "default"
    isolation_prefix: str = "tenant"
    cache_namespace: str = "cache"
    kb_namespace: str = "kb"
    vector_namespace: str = "vectors"
    memory_namespace: str = "memory"
    citation_namespace: str = "citations"
    mcp_namespace: str = "mcp"
    metrics_namespace: str = "metrics"
    log_namespace: str = "logs"
    enforce_active: bool = True
    log_events: bool = True
    track_metrics: bool = True
    audit_enabled: bool = True

    @classmethod
    def from_env(cls) -> TenancyConfig:
        return cls(
            header_name=os.getenv("TEN_HEADER", "X-Tenant-ID"),
            jwt_claim=os.getenv("TEN_JWT_CLAIM", "tenant_id"),
            jwt_issuer_claim=os.getenv("TEN_JWT_ISSUER_CLAIM", "iss"),
            allowed_issuers=tuple(os.getenv("TEN_ALLOWED_ISSUERS", "airouter").split(",")),
            api_key_header=os.getenv("TEN_API_KEY_HEADER", "X-API-Key"),
            subdomain_header=os.getenv("TEN_SUBDOMAIN_HEADER", "Host"),
            subdomain_suffix=os.getenv("TEN_SUBDOMAIN_SUFFIX", ".airouter.app"),
            context_var_name=os.getenv("TEN_CONTEXT_VAR", "tenant_context"),
            allow_anonymous=os.getenv("TEN_ALLOW_ANONYMOUS", "0") == "1",
            anonymous_tenant=os.getenv("TEN_ANONYMOUS_TENANT", "default"),
            isolation_prefix=os.getenv("TEN_ISOLATION_PREFIX", "tenant"),
            enforce_active=os.getenv("TEN_ENFORCE_ACTIVE", "1") == "1",
            log_events=os.getenv("TEN_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("TEN_TRACK_METRICS", "1") == "1",
            audit_enabled=os.getenv("TEN_AUDIT_ENABLED", "1") == "1",
        )
