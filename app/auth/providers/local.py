from __future__ import annotations

import time
from typing import Any

from ..config import AuthConfig
from ..exceptions import (
    AccountInactiveError,
    AccountLockedError,
    InvalidCredentialsError,
)
from ..hashing import verify_password
from ..models import ProviderUser, User, UserStatus
from ..repository import InMemoryUserRepository, UserRepository
from .base import AuthProvider


class LocalProvider(AuthProvider):
    name = "local"

    def __init__(
        self,
        users: UserRepository | None = None,
        config: AuthConfig | None = None,
        **options: Any,
    ):
        super().__init__(**options)
        self._users = users or InMemoryUserRepository()
        self._config = config or AuthConfig()

    @property
    def users(self) -> UserRepository:
        return self._users

    def register_user(self, user: User) -> User:
        return self._users.create(user)

    def find_user(self, username: str, tenant_id: str = "") -> User:
        return self._users.get_by_username(username, tenant_id)

    def _check_locked(self, user: User) -> None:
        if user.is_locked:
            raise AccountLockedError(user.locked_until)

    def _record_failure(self, user: User) -> None:
        user.failed_attempts += 1
        if user.failed_attempts >= self._config.max_login_attempts:
            user.locked_until = time.time() + self._config.lockout_seconds
            user.status = UserStatus.LOCKED
        self._users.update(user)

    def _reset_failures(self, user: User) -> None:
        if user.failed_attempts:
            user.failed_attempts = 0
            user.locked_until = 0.0
            if user.status == UserStatus.LOCKED:
                user.status = UserStatus.ACTIVE
            self._users.update(user)

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))
        tenant_id = str(credentials.get("tenant_id", ""))
        if not username or not password:
            raise InvalidCredentialsError("Missing credentials")
        user = self.find_user(username, tenant_id)
        self._check_locked(user)
        if user.status.value in ("suspended", "disabled"):
            raise AccountInactiveError(f"Account is {user.status.value}")
        if not verify_password(password, user.password_hash):
            self._record_failure(user)
            raise InvalidCredentialsError("Invalid password")
        self._reset_failures(user)
        return ProviderUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.username,
            roles=user.roles,
            tenant_id=user.tenant_id or tenant_id,
        )
