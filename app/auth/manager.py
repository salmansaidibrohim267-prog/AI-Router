from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

from .api_keys import APIKeyManager
from .config import AuthConfig
from .exceptions import (
    AccountInactiveError,
    AuthenticationError,
    InvalidCredentialsError,
    SessionExpiredError,
)
from .hashing import hash_password, is_strong_password, verify_password
from .logging import AuthLogger
from .models import AuthResult, ProviderUser, Session, TokenPair, User
from .providers import ProviderRegistry, register_builtin_providers
from .rbac import PermissionPolicy, Principal
from .repository import InMemoryUserRepository, UserRepository
from .service_accounts import ServiceAccountManager
from .sessions import SessionManager
from .statistics import AuthMetricsTracker
from .tokens import JWTManager


def _totp_code(secret: str, now: float | None = None) -> str:
    counter = int((now or time.time()) // 30)
    key = base64.b32decode(secret.upper().ljust((len(secret) + 7) // 8 * 8, "="))
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


class AuthenticationManager:
    def __init__(
        self,
        users: UserRepository | None = None,
        sessions: SessionManager | None = None,
        tokens: JWTManager | None = None,
        api_keys: APIKeyManager | None = None,
        service_accounts: ServiceAccountManager | None = None,
        providers: ProviderRegistry | None = None,
        policy: PermissionPolicy | None = None,
        tenant_manager: Any | None = None,
        config: AuthConfig | None = None,
        logger: AuthLogger | None = None,
        metrics: AuthMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._config = config or AuthConfig()
        self._users = users or InMemoryUserRepository()
        self._logger = logger or AuthLogger()
        self._metrics = metrics or AuthMetricsTracker(self._config)
        self._providers = providers or ProviderRegistry()
        register_builtin_providers(self._providers, users=self._users, config=self._config)
        self._sessions = sessions or SessionManager(self._config, logger=self._logger, metrics=self._metrics)
        self._tokens = tokens or JWTManager(secrets.token_hex(32), self._config)
        self._api_keys = api_keys or APIKeyManager(self._config, logger=self._logger, metrics=self._metrics)
        self._service_accounts = service_accounts or ServiceAccountManager(
            self._config, logger=self._logger, metrics=self._metrics
        )
        self._policy = policy or PermissionPolicy()
        self._tenant_manager = tenant_manager
        self._audit = audit

    @property
    def config(self) -> AuthConfig:
        return self._config

    @property
    def users(self) -> UserRepository:
        return self._users

    @property
    def sessions(self) -> SessionManager:
        return self._sessions

    @property
    def tokens(self) -> JWTManager:
        return self._tokens

    @property
    def api_keys(self) -> APIKeyManager:
        return self._api_keys

    @property
    def service_accounts(self) -> ServiceAccountManager:
        return self._service_accounts

    @property
    def providers(self) -> ProviderRegistry:
        return self._providers

    @property
    def policy(self) -> PermissionPolicy:
        return self._policy

    def _audit_event(self, action: str, tenant_id: str, actor: str, outcome: str = "success", **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(
                action=action,
                tenant_id=tenant_id,
                actor=actor,
                resource="auth",
                outcome=outcome,
                details=details,
            )
        except Exception:
            pass

    def _check_tenant(self, tenant_id: str) -> None:
        if not tenant_id:
            return
        if self._tenant_manager is None:
            return
        try:
            self._tenant_manager.get_active(tenant_id)
        except Exception as exc:
            raise AuthenticationError(f"Tenant not available: {exc}") from exc

    def register_user(
        self,
        username: str,
        password: str,
        tenant_id: str = "",
        email: str = "",
        roles: list[str] | None = None,
        user_id: str | None = None,
        mfa_secret: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> User:
        if not is_strong_password(password, self._config):
            raise InvalidCredentialsError("Password does not meet policy")
        user = User(
            id=user_id or f"u_{uuid.uuid4().hex[:16]}",
            username=username,
            email=email,
            password_hash=hash_password(password, self._config.password_hash_iterations),
            roles=roles or ["viewer"],
            tenant_id=tenant_id,
            mfa_secret=mfa_secret,
            metadata=metadata or {},
        )
        self._users.create(user)
        self._metrics.record("user_registered", tenant_id)
        self._logger.log_event("user_registered", tenant_id=tenant_id, user_id=user.id)
        return user

    async def _issue_principal_tokens(self, provider_user: ProviderUser, device: str) -> tuple[TokenPair, Session]:
        session = self._sessions.create(
            user_id=provider_user.id,
            tenant_id=provider_user.tenant_id,
            device=device,
            refresh_jti="",
        )
        pair = self._tokens.issue_pair(
            user_id=provider_user.id,
            tenant_id=provider_user.tenant_id,
            roles=provider_user.roles,
            session_id=session.id,
        )
        session.refresh_jti = pair.refresh_jti
        self._sessions.repository.update(session)
        return pair, session

    def _resolve_mfa(self, user: User, mfa_code: str | None) -> bool:
        if not self._config.mfa_enabled or not user.mfa_secret:
            return True
        if not mfa_code:
            return False
        return _totp_code(user.mfa_secret) == mfa_code

    async def login(
        self,
        username: str,
        password: str,
        tenant_id: str = "",
        device: str = "default",
        mfa_code: str | None = None,
        provider: str = "local",
    ) -> AuthResult:
        self._check_tenant(tenant_id)
        credentials = {"username": username, "password": password, "tenant_id": tenant_id}
        try:
            provider_user = await self._providers.get(provider).authenticate(credentials)
        except AuthenticationError as exc:
            self._metrics.record("login_failed", tenant_id)
            self._audit_event("auth.login", tenant_id, username, outcome="failure", reason=str(exc))
            raise
        user = self._users.get(provider_user.id) if provider == "local" else None
        if provider != "local" and user is None:
            user = self._reconcile_provider_user(provider_user)
        if user is not None and not self._resolve_mfa(user, mfa_code):
            self._metrics.record("mfa_required", tenant_id)
            return AuthResult(user=user, mfa_required=True, method=provider)
        pair, session = await self._issue_principal_tokens(provider_user, device)
        self._metrics.record("login_success", tenant_id)
        self._audit_event("auth.login", tenant_id, provider_user.id, details={"method": provider, "device": device})
        self._logger.log_event("login", tenant_id=tenant_id, user_id=provider_user.id, provider=provider)
        principal = Principal(
            user_id=provider_user.id,
            tenant_id=provider_user.tenant_id,
            roles=provider_user.roles,
            method=provider,
            username=provider_user.username,
        )
        return AuthResult(
            user=user,
            token_pair=pair,
            session=session,
            method=provider,
            principal=principal,
        )

    def _reconcile_provider_user(self, provider_user: ProviderUser) -> User:
        try:
            existing = self._users.get(provider_user.id)
            if existing.status.value in ("suspended", "disabled"):
                raise AccountInactiveError(f"Account is {existing.status.value}")
            return existing
        except InvalidCredentialsError:
            user = User(
                id=provider_user.id,
                username=provider_user.username,
                email=provider_user.email,
                roles=provider_user.roles or ["viewer"],
                tenant_id=provider_user.tenant_id,
            )
            self._users.create(user)
            return user

    async def login_with(self, provider: str, credentials: dict[str, Any], device: str = "default") -> AuthResult:
        provider_user = await self._providers.get(provider).authenticate(credentials)
        tenant_id = provider_user.tenant_id or str(credentials.get("tenant_id", ""))
        provider_user.tenant_id = tenant_id
        self._check_tenant(tenant_id)
        user = self._reconcile_provider_user(provider_user)
        pair, session = await self._issue_principal_tokens(provider_user, device)
        self._metrics.record("login_success", tenant_id)
        self._audit_event("auth.login", tenant_id, provider_user.id, details={"method": provider})
        return AuthResult(
            user=user,
            token_pair=pair,
            session=session,
            method=provider,
            principal=Principal.from_user(user, method=provider),
        )

    async def logout(self, refresh_token: str) -> str:
        claims = self._tokens.validate(refresh_token, token_type="refresh")
        self._tokens.denylist.revoke(claims.jti, claims.exp)
        if claims.session_id:
            try:
                self._sessions.revoke(claims.session_id)
            except SessionExpiredError:
                pass
        self._metrics.record("logout", claims.tenant_id)
        self._audit_event("auth.logout", claims.tenant_id, claims.sub)
        return claims.jti

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._tokens.validate(refresh_token, token_type="refresh")
        if claims.session_id:
            session = self._sessions.validate(claims.session_id)
            session = self._sessions.touch(claims.session_id)
            pair = self._tokens.rotate_pair(refresh_token, session.id)
            session.refresh_jti = pair.refresh_jti
            self._sessions.repository.update(session)
        else:
            pair = self._tokens.rotate_pair(refresh_token, "")
        self._metrics.record("token_refreshed", claims.tenant_id)
        return pair

    def validate(self, token: str) -> Principal:
        claims = self._tokens.validate(token, token_type="access")
        if claims.session_id:
            self._sessions.validate(claims.session_id)
        return Principal(
            user_id=claims.sub,
            tenant_id=claims.tenant_id,
            roles=claims.roles,
            method="token",
        )

    async def authenticate(self, headers: dict[str, str] | None = None, authorization: str | None = None) -> Principal:
        if authorization is None and headers:
            lowered = {k.lower(): v for k, v in headers.items()}
            authorization = lowered.get("authorization", "")
        if not authorization:
            raise InvalidCredentialsError("Missing Authorization header")
        scheme, _, value = authorization.partition(" ")
        scheme = scheme.lower()
        if scheme == "bearer":
            return self.validate(value.strip())
        if scheme in ("apikey", "x-api-key", "token"):
            key = self.authenticate_api_key(value.strip())
            return Principal(
                user_id=key.user_id or f"apikey:{key.id}",
                tenant_id=key.tenant_id,
                roles=[],
                scopes=key.scopes,
                method="apikey",
                service=True,
            )
        if scheme == "service":
            account = self.authenticate_service_account(value.strip())
            return Principal(
                user_id=f"sa:{account.id}",
                tenant_id=account.tenant_id,
                roles=[],
                scopes=account.scopes,
                method="service_account",
                service=True,
            )
        raise InvalidCredentialsError(f"Unsupported auth scheme {scheme!r}")

    def authenticate_api_key(self, raw_key: str, require_scopes: list[str] | None = None) -> Any:
        return self._api_keys.authenticate(raw_key, require_scopes)

    def authenticate_service_account(self, raw_token: str, require_scopes: list[str] | None = None) -> Any:
        return self._service_accounts.authenticate(raw_token, require_scopes)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        user = self._users.get(user_id)
        if not verify_password(old_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        if not is_strong_password(new_password, self._config):
            raise InvalidCredentialsError("New password does not meet policy")
        user.password_hash = hash_password(new_password, self._config.password_hash_iterations)
        self._users.update(user)
        self._audit_event("auth.password_changed", user.tenant_id, user_id)
        return True

    async def revoke_all_sessions(self, user_id: str) -> int:
        count = self._sessions.revoke_all(user_id)
        self._metrics.record("sessions_revoked", "", count)
        return count

    async def revoke_session(self, session_id: str) -> bool:
        return self._sessions.revoke(session_id)

    async def rotate_signing_keys(self) -> str:
        return self._tokens.rotate_keys()

    def get_metrics(self) -> dict[str, Any]:
        return self._metrics.summary()

    def close(self) -> None:
        pass
