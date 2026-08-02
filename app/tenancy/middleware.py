from __future__ import annotations

import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import TenancyConfig
from .context import TenantContextManager
from .exceptions import (
    TenantContextMissingError,
    TenantIsolationError,
    TenantResolutionError,
    TenantSuspendedError,
)
from .isolation import TenantIsolation
from .logging import TenancyLogger
from .resolver import TenantResolver
from .statistics import TenancyMetricsTracker


class TenantMiddleware:
    def __init__(
        self,
        app: Any,
        resolver: TenantResolver | None = None,
        config: TenancyConfig | None = None,
        logger: TenancyLogger | None = None,
        metrics: TenancyMetricsTracker | None = None,
        context_manager: TenantContextManager | None = None,
        isolation: TenantIsolation | None = None,
    ):
        self.app = app
        self._config = config or TenancyConfig()
        self._resolver = resolver or TenantResolver(config=self._config)
        self._logger = logger or TenancyLogger()
        self._metrics = metrics or TenancyMetricsTracker(self._config)
        from .context import get_tenant_context_manager

        self._context = context_manager or get_tenant_context_manager()
        self._isolation = isolation or TenantIsolation(self._config)

    @property
    def context_manager(self) -> TenantContextManager:
        return self._context

    def _headers_from_scope(self, scope: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for raw_key, raw_value in scope.get("headers", []) or []:
            key = raw_key.decode("latin-1") if isinstance(raw_key, bytes) else str(raw_key)
            value = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else str(raw_value)
            headers[key] = value
        return headers

    async def _resolve(self, scope: dict[str, Any]) -> Any:
        headers = self._headers_from_scope(scope)
        host = headers.get("Host", headers.get("host", ""))
        return self._resolver.resolve(headers=headers, host=host)

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

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        try:
            context = await self._resolve(scope)
            self._isolation.enforce(context)
        except (TenantSuspendedError, TenantIsolationError) as exc:
            self._logger.log_event("suspended_request", tenant_id=getattr(exc, "tenant_id", ""))
            self._metrics.record_error(getattr(exc, "tenant_id", ""), "blocked")
            return await self._error_response(send, 403, "tenant blocked")
        except (TenantResolutionError, TenantContextMissingError):
            self._logger.log_event("resolution_failed")
            return await self._error_response(send, 401, "tenant resolution failed")
        except Exception:
            self._logger.log_event("resolution_error")
            return await self._error_response(send, 401, "tenant resolution failed")

        token = self._context.set(context)
        status_code = [200]
        try:

            async def wrapped_send(message: dict[str, Any]) -> None:
                if message.get("type") == "http.response.start":
                    status_code[0] = int(message.get("status", 200))
                await send(message)

            await self.app(scope, receive, wrapped_send)
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 4)
            self._metrics.record_request(
                context.tenant_id, latency_ms, success=status_code[0] < 400
            )
            self._logger.log_event(
                "request",
                tenant_id=context.tenant_id,
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                status=status_code[0],
                latency_ms=latency_ms,
            )
            self._context.clear(token)

    async def fastapi_http(self, request: Request, call_next: Any) -> Any:
        headers = {k: v for k, v in request.headers.items()}
        context = self._resolver.resolve(headers=headers, host=request.url.hostname or "")
        token = self._context.set(context)
        try:
            response = await call_next(request)
        except Exception:
            raise
        finally:
            self._context.clear(token)
        return response


def create_tenant_middleware(
    app: Any,
    resolver: TenantResolver | None = None,
    config: TenancyConfig | None = None,
    logger: TenancyLogger | None = None,
    metrics: TenancyMetricsTracker | None = None,
    context_manager: TenantContextManager | None = None,
    isolation: TenantIsolation | None = None,
) -> TenantMiddleware:
    return TenantMiddleware(
        app=app,
        resolver=resolver,
        config=config,
        logger=logger,
        metrics=metrics,
        context_manager=context_manager,
        isolation=isolation,
    )
