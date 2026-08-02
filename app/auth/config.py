from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AuthConfig:
    access_token_ttl: int = 900
    refresh_token_ttl: int = 604800
    signing_key_rotation_seconds: int = 86400
    max_key_history: int = 5
    session_idle_timeout: int = 1800
    session_absolute_timeout: int = 86400
    max_concurrent_sessions: int = 5
    evict_oldest_on_limit: bool = True
    password_min_length: int = 8
    password_hash_iterations: int = 100_000
    max_login_attempts: int = 5
    lockout_seconds: int = 300
    mfa_enabled: bool = False
    api_key_ttl_default: int = 2_592_000
    service_account_ttl_default: int = 2_592_000
    require_auth: bool = True
    public_paths: tuple[str, ...] = ("/health", "/metrics")
    provider_http_timeout: float = 10.0
    log_events: bool = True
    track_metrics: bool = True
    audit_enabled: bool = True

    @classmethod
    def from_env(cls) -> AuthConfig:
        return cls(
            access_token_ttl=int(os.getenv("AUTH_ACCESS_TTL", "900")),
            refresh_token_ttl=int(os.getenv("AUTH_REFRESH_TTL", "604800")),
            signing_key_rotation_seconds=int(os.getenv("AUTH_KEY_ROTATION", "86400")),
            max_key_history=int(os.getenv("AUTH_MAX_KEY_HISTORY", "5")),
            session_idle_timeout=int(os.getenv("AUTH_SESSION_IDLE", "1800")),
            session_absolute_timeout=int(os.getenv("AUTH_SESSION_ABSOLUTE", "86400")),
            max_concurrent_sessions=int(os.getenv("AUTH_MAX_SESSIONS", "5")),
            evict_oldest_on_limit=os.getenv("AUTH_EVICT_OLDEST", "1") == "1",
            password_min_length=int(os.getenv("AUTH_PASSWORD_MIN_LENGTH", "8")),
            password_hash_iterations=int(os.getenv("AUTH_HASH_ITERATIONS", "100000")),
            max_login_attempts=int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "5")),
            lockout_seconds=int(os.getenv("AUTH_LOCKOUT_SECONDS", "300")),
            mfa_enabled=os.getenv("AUTH_MFA_ENABLED", "0") == "1",
            api_key_ttl_default=int(os.getenv("AUTH_API_KEY_TTL", "2592000")),
            service_account_ttl_default=int(os.getenv("AUTH_SA_TTL", "2592000")),
            require_auth=os.getenv("AUTH_REQUIRE_AUTH", "1") == "1",
            public_paths=tuple(os.getenv("AUTH_PUBLIC_PATHS", "/health,/metrics").split(",")),
            log_events=os.getenv("AUTH_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("AUTH_TRACK_METRICS", "1") == "1",
            audit_enabled=os.getenv("AUTH_AUDIT_ENABLED", "1") == "1",
        )
