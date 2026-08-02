from __future__ import annotations

from typing import Any

from .api_keys import APIKeyManager
from .config import AuthConfig
from .exceptions import (
    AccountInactiveError,
    AccountLockedError,
    APIKeyError,
    AuthError,
    AuthenticationError,
    InvalidCredentialsError,
    InvalidTokenError,
    MFARequiredError,
    PermissionDeniedError,
    ProviderError,
    ProviderNotFoundError,
    ServiceAccountError,
    SessionExpiredError,
    SessionLimitError,
    TokenExpiredError,
    TokenRevokedError,
)
from .hashing import hash_password, is_strong_password, verify_password
from .logging import AuthLogger
from .manager import AuthenticationManager, _totp_code
from .middleware import AuthMiddleware, create_auth_middleware
from .models import (
    APIKey,
    AuthResult,
    ProviderUser,
    ServiceAccount,
    Session,
    TokenClaims,
    TokenPair,
    User,
    UserStatus,
)
from .rbac import PermissionPolicy, Principal
from .repository import (
    APIKeyRepository,
    InMemoryUserRepository,
    ServiceAccountRepository,
    SessionRepository,
    UserRepository,
)
from .sessions import SessionManager
from .service_accounts import ServiceAccountManager
from .statistics import AuthMetricsTracker
from .tokens import JWTManager, SigningKeyStore, TokenDenylist

__all__ = [
    "APIKey",
    "APIKeyError",
    "APIKeyManager",
    "APIKeyRepository",
    "AccountInactiveError",
    "AccountLockedError",
    "AuthConfig",
    "AuthError",
    "AuthLogger",
    "AuthMetricsTracker",
    "AuthMiddleware",
    "AuthResult",
    "AuthenticationError",
    "AuthenticationManager",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "InMemoryUserRepository",
    "JWTManager",
    "MFARequiredError",
    "PermissionDeniedError",
    "PermissionPolicy",
    "Principal",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderUser",
    "ServiceAccount",
    "ServiceAccountError",
    "ServiceAccountManager",
    "ServiceAccountRepository",
    "Session",
    "SessionExpiredError",
    "SessionLimitError",
    "SessionManager",
    "SessionRepository",
    "SigningKeyStore",
    "TokenClaims",
    "TokenDenylist",
    "TokenExpiredError",
    "TokenPair",
    "TokenRevokedError",
    "User",
    "UserRepository",
    "UserStatus",
    "create_auth_middleware",
    "hash_password",
    "is_strong_password",
    "verify_password",
]


def create_auth_manager(
    users: UserRepository | None = None,
    sessions: SessionManager | None = None,
    tokens: JWTManager | None = None,
    api_keys: APIKeyManager | None = None,
    service_accounts: ServiceAccountManager | None = None,
    providers: Any | None = None,
    policy: PermissionPolicy | None = None,
    tenant_manager: Any | None = None,
    config: AuthConfig | None = None,
    logger: AuthLogger | None = None,
    metrics: AuthMetricsTracker | None = None,
    audit: Any | None = None,
) -> AuthenticationManager:
    return AuthenticationManager(
        users=users,
        sessions=sessions,
        tokens=tokens,
        api_keys=api_keys,
        service_accounts=service_accounts,
        providers=providers,
        policy=policy,
        tenant_manager=tenant_manager,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
