from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import AuthConfig
from .exceptions import (
    APIKeyError,
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    PermissionDeniedError,
    ServiceAccountError,
    TokenExpiredError,
)
from .logging import AuthLogger
from .manager import AuthenticationManager
from .rbac import PermissionPolicy, Principal
from .statistics import AuthMetricsTracker
from app.tenancy.context import get_tenant_context_manager


class AuthMiddleware:
    def __init__(
        self,
        app: Any,
        manager: AuthenticationManager,
        config: AuthConfig | None = None,
        logger: AuthLogger | None = None,
        metrics: AuthMetricsTracker | None = None,
        policy: PermissionPolicy | None = None,
        required_permissions: dict[str, str] | None = None,
    ):
        self.app = app
        self._manager = manager
        self._config = config or AuthConfig()
        self._logger = logger or AuthLogger()
        self._metrics = metrics or AuthMetricsTracker(self._config)
        self._policy = policy or manager.policy
        self._required_permissions = required_permissions or {}
        self._context = get_tenant_context_manager()

    @property
    def manager(self) -> AuthenticationManager:
        return self._manager

    def _is_public(self, path: str) -> bool:
        if not self._config.require_auth:
            return True
        for prefix in self._config.public_paths:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    @staticmethod
    def _headers_from_scope(scope: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for raw_key, raw_value in scope.get("headers", []) or []:
            key = raw_key.decode("latin-1") if isinstance(raw_key, bytes) else str(raw_key)
            value = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else str(raw_value)
            headers[key] = value
        return headers

    @staticmethod
    def _error_body(message: str) -> dict[str, str]:
        return {"error": message}

    async def _error_response(self, send: Any, status_code: int, body: str) -> None:
        body_bytes = f'{{"error": "{body}"}}'.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body_bytes)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body_bytes})

    def _require_permission(self, principal: Principal, path: str) -> None:
        for prefix, permission in self._required_permissions.items():
            if path == prefix or path.startswith(prefix + "/"):
                self._policy.enforce(principal, permission)
                return

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if self._is_public(path):
            await self.app(scope, receive, send)
            return
        headers = self._headers_from_scope(scope)
        try:
            principal = await self._manager.authenticate(headers=headers)
        except TokenExpiredError:
            self._metrics.record("token_expired")
            return await self._error_response(send, 401, "token expired")
        except PermissionDeniedError as exc:
            self._metrics.record("permission_denied", exc.user_id)
            return await self._error_response(send, 403, str(exc))
        except (InvalidTokenError, InvalidCredentialsError, APIKeyError, ServiceAccountError):
            self._metrics.record("auth_failed")
            return await self._error_response(send, 401, "unauthorized")
        except Exception:
            self._metrics.record("auth_error")
            return await self._error_response(send, 500, "authentication error")

        try:
            self._require_permission(principal, path)
        except PermissionDeniedError as exc:
            self._metrics.record("permission_denied", principal.tenant_id)
            return await self._error_response(send, 403, f"permission denied: {exc.permission}")

        await self.app(scope, receive, send)

    async def fastapi_http(self, request: Request, call_next: Any) -> Any:
        if self._is_public(request.url.path):
            return await call_next(request)
        headers = {k: v for k, v in request.headers.items()}
        try:
            principal = await self._manager.authenticate(headers=headers)
            self._require_permission(principal, request.url.path)
        except TokenExpiredError:
            return JSONResponse(status_code=401, content=self._error_body("token expired"))
        except PermissionDeniedError as exc:
            return JSONResponse(
                status_code=403, content=self._error_body(f"permission denied: {exc.permission}")
            )
        except (InvalidTokenError, InvalidCredentialsError, APIKeyError, ServiceAccountError):
            return JSONResponse(status_code=401, content=self._error_body("unauthorized"))
        except Exception:
            return JSONResponse(status_code=500, content=self._error_body("authentication error"))
        return await call_next(request)


def create_auth_middleware(
    app: Any,
    manager: AuthenticationManager,
    config: AuthConfig | None = None,
    logger: AuthLogger | None = None,
    metrics: AuthMetricsTracker | None = None,
    policy: PermissionPolicy | None = None,
    required_permissions: dict[str, str] | None = None,
) -> AuthMiddleware:
    return AuthMiddleware(
        app=app,
        manager=manager,
        config=config,
        logger=logger,
        metrics=metrics,
        policy=policy,
        required_permissions=required_permissions,
    )
