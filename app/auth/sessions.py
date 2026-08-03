from __future__ import annotations

import time
import uuid

from .config import AuthConfig
from .exceptions import SessionExpiredError, SessionLimitError
from .logging import AuthLogger
from .models import Session
from .repository import SessionRepository
from .statistics import AuthMetricsTracker


class SessionManager:
    def __init__(
        self,
        config: AuthConfig | None = None,
        repository: SessionRepository | None = None,
        logger: AuthLogger | None = None,
        metrics: AuthMetricsTracker | None = None,
    ):
        self._config = config or AuthConfig()
        self._repository = repository or SessionRepository()
        self._logger = logger or AuthLogger()
        self._metrics = metrics or AuthMetricsTracker(self._config)

    @property
    def repository(self) -> SessionRepository:
        return self._repository

    def create(self, user_id: str, tenant_id: str = "", device: str = "default", refresh_jti: str = "") -> Session:
        active = self._repository.count_active(user_id)
        limit = self._config.max_concurrent_sessions
        if active >= limit:
            if self._config.evict_oldest_on_limit:
                oldest = sorted(
                    self._repository.list_for_user(user_id),
                    key=lambda s: s.created_at,
                )
                for session in oldest[: active - limit + 1]:
                    self._repository.update(
                        Session(
                            id=session.id,
                            user_id=user_id,
                            tenant_id=session.tenant_id,
                            device=session.device,
                            created_at=session.created_at,
                            last_active=session.last_active,
                            expires_at=session.expires_at,
                            refresh_jti=session.refresh_jti,
                            revoked=True,
                        )
                    )
            else:
                self._metrics.record("session_limit_exceeded", tenant_id)
                raise SessionLimitError(f"Session limit of {limit} reached")
        now = time.time()
        session = Session(
            id=f"ses_{uuid.uuid4().hex[:24]}",
            user_id=user_id,
            tenant_id=tenant_id,
            device=device,
            created_at=now,
            last_active=now,
            expires_at=now + self._config.session_absolute_timeout,
            refresh_jti=refresh_jti,
        )
        self._repository.create(session)
        self._metrics.record("session_created", tenant_id)
        return session

    def touch(self, session_id: str) -> Session:
        session = self.get(session_id)
        now = time.time()
        if session.last_active and now - session.last_active > self._config.session_idle_timeout:
            session.expires_at = now
            session.revoked = True
            self._repository.update(session)
            raise SessionExpiredError("Session idle timeout exceeded")
        session.last_active = now
        return self._repository.update(session)

    def validate(self, session_id: str) -> Session:
        session = self.get(session_id)
        now = time.time()
        if session.revoked:
            raise SessionExpiredError("Session revoked")
        if session.expires_at and now > session.expires_at:
            session.revoked = True
            self._repository.update(session)
            raise SessionExpiredError("Session expired")
        return session

    def get(self, session_id: str) -> Session:
        session = self._repository.get(session_id)
        if session is None:
            raise SessionExpiredError("Session not found")
        return session

    def revoke(self, session_id: str) -> bool:
        session = self.get(session_id)
        session.revoked = True
        self._repository.update(session)
        return True

    def revoke_all(self, user_id: str) -> int:
        count = 0
        for session in self._repository.list_for_user(user_id):
            session.revoked = True
            self._repository.update(session)
            count += 1
        return count

    def list(self, user_id: str | None = None) -> list[Session]:
        if user_id is not None:
            return self._repository.list_for_user(user_id)
        return self._repository.list_all()
