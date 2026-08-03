from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from .exceptions import InvalidCredentialsError
from .models import APIKey, ServiceAccount, Session, User

MISSING = object()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


class UserRepository(ABC):
    @abstractmethod
    def create(self, user: User) -> User: ...

    @abstractmethod
    def get(self, user_id: str) -> User: ...

    @abstractmethod
    def get_by_username(self, username: str, tenant_id: str = "") -> User: ...

    @abstractmethod
    def update(self, user: User) -> User: ...

    @abstractmethod
    def delete(self, user_id: str) -> bool: ...

    @abstractmethod
    def list(self, tenant_id: str = "") -> list[User]: ...


class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}

    def create(self, user: User) -> User:
        with self._lock:
            if user.id in self._users:
                raise InvalidCredentialsError("User already exists")
            self._users[user.id] = user
            return user

    def get(self, user_id: str) -> User:
        with self._lock:
            user = self._users.get(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")
        return user

    def get_by_username(self, username: str, tenant_id: str = "") -> User:
        with self._lock:
            for user in self._users.values():
                if user.username == username and (not tenant_id or user.tenant_id == tenant_id):
                    return user
        raise InvalidCredentialsError("User not found")

    def update(self, user: User) -> User:
        with self._lock:
            if user.id not in self._users:
                raise InvalidCredentialsError("User not found")
            user.updated_at = time.time()
            self._users[user.id] = user
            return user

    def delete(self, user_id: str) -> bool:
        with self._lock:
            return self._users.pop(user_id, None) is not None

    def list(self, tenant_id: str = "") -> list[User]:
        with self._lock:
            users = [u for u in self._users.values()]
        if tenant_id:
            users = [u for u in users if u.tenant_id == tenant_id]
        return sorted(users, key=lambda u: u.created_at)


class SessionRepository:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_for_user(self, user_id: str) -> list[Session]:
        with self._lock:
            return [s for s in self._sessions.values() if s.user_id == user_id and not s.revoked]

    def list_all(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def update(self, session: Session) -> Session:
        with self._lock:
            if session.id in self._sessions:
                self._sessions[session.id] = session
            return session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def delete_for_user(self, user_id: str) -> int:
        with self._lock:
            ids = [sid for sid, s in self._sessions.items() if s.user_id == user_id]
            for sid in ids:
                del self._sessions[sid]
            return len(ids)

    def count_active(self, user_id: str) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if s.user_id == user_id and not s.revoked)


class APIKeyRepository:
    def __init__(self):
        self._lock = threading.Lock()
        self._keys: dict[str, APIKey] = {}

    def create(self, key: APIKey) -> APIKey:
        with self._lock:
            self._keys[key.id] = key
            return key

    def get(self, key_id: str) -> APIKey | None:
        with self._lock:
            return self._keys.get(key_id)

    def get_by_hash(self, key_hash: str) -> APIKey | None:
        with self._lock:
            for key in self._keys.values():
                if key.key_hash == key_hash:
                    return key
        return None

    def list_for_tenant(self, tenant_id: str) -> list[APIKey]:
        with self._lock:
            return [k for k in self._keys.values() if k.tenant_id == tenant_id]

    def list_all(self) -> list[APIKey]:
        with self._lock:
            return list(self._keys.values())

    def update(self, key: APIKey) -> APIKey:
        with self._lock:
            self._keys[key.id] = key
            return key

    def delete(self, key_id: str) -> bool:
        with self._lock:
            return self._keys.pop(key_id, None) is not None


class ServiceAccountRepository:
    def __init__(self):
        self._lock = threading.Lock()
        self._accounts: dict[str, ServiceAccount] = {}

    def create(self, account: ServiceAccount) -> ServiceAccount:
        with self._lock:
            self._accounts[account.id] = account
            return account

    def get(self, account_id: str) -> ServiceAccount | None:
        with self._lock:
            return self._accounts.get(account_id)

    def get_by_token_hash(self, token_hash: str) -> ServiceAccount | None:
        with self._lock:
            for account in self._accounts.values():
                if account.token_hash == token_hash:
                    return account
        return None

    def list_for_tenant(self, tenant_id: str) -> list[ServiceAccount]:
        with self._lock:
            return [a for a in self._accounts.values() if a.tenant_id == tenant_id]

    def list_all(self) -> list[ServiceAccount]:
        with self._lock:
            return list(self._accounts.values())

    def update(self, account: ServiceAccount) -> ServiceAccount:
        with self._lock:
            self._accounts[account.id] = account
            return account

    def delete(self, account_id: str) -> bool:
        with self._lock:
            return self._accounts.pop(account_id, None) is not None


def generate_secret_token() -> str:
    return f"tok_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
