"""Exception hierarchy for the API Gateway (Stage 10.4)."""

from __future__ import annotations

from typing import Any


class GatewayError(Exception):
    """Base class for all gateway errors."""

    status_code: int = 500
    error_code: str = "gateway_error"

    def __init__(
        self, message: str = "", *, status_code: int | None = None, error_code: str | None = None, **details: Any
    ):  # noqa: E501
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error_code, "message": self.message, **self.details}


class RouteNotFoundError(GatewayError):
    status_code = 404
    error_code = "route_not_found"

    def __init__(self, path: str, method: str = ""):
        message = f"No route registered for {method or 'ANY'} {path!r}"
        super().__init__(message, path=path, method=method)


class MethodNotAllowedError(GatewayError):
    status_code = 405
    error_code = "method_not_allowed"

    def __init__(self, path: str, method: str, allowed: list[str]):
        message = f"Method {method!r} not allowed for {path!r}"
        super().__init__(message, path=path, method=method, allowed=allowed)


class VersionNotSupportedError(GatewayError):
    status_code = 400
    error_code = "version_not_supported"

    def __init__(self, version: str, supported: list[str]):
        message = f"API version {version!r} is not supported"
        super().__init__(message, version=version, supported=supported)


class VersionDeprecatedError(GatewayError):
    status_code = 410
    error_code = "version_deprecated"

    def __init__(self, version: str):
        message = f"API version {version!r} is deprecated and no longer served"
        super().__init__(message, version=version)


class RateLimitExceededError(GatewayError):
    status_code = 429
    error_code = "rate_limit_exceeded"

    def __init__(self, key: str, strategy: str, retry_after: float = 0.0, limit: int = 0):
        message = f"Rate limit exceeded for {key!r}"
        super().__init__(message, key=key, strategy=strategy, retry_after=retry_after, limit=limit)


class QuotaExceededError(GatewayError):
    status_code = 429
    error_code = "quota_exceeded"

    def __init__(self, bucket: str, limit: int, used: int):
        message = f"Quota exceeded for bucket {bucket!r} ({used}/{limit})"
        super().__init__(message, bucket=bucket, limit=limit, used=used)


class ValidationError(GatewayError):
    status_code = 400
    error_code = "validation_error"

    def __init__(self, message: str, field: str = ""):
        super().__init__(message, field=field)


class UpstreamError(GatewayError):
    status_code = 502
    error_code = "upstream_error"

    def __init__(self, service: str, message: str = "", status_code: int | None = None):
        super().__init__(message or f"Upstream service {service!r} failed", service=service, status_code=status_code)


class ServiceUnavailableError(GatewayError):
    status_code = 503
    error_code = "service_unavailable"

    def __init__(self, service: str = ""):
        super().__init__(f"Service {service or 'unknown'} is unavailable", service=service)


class GatewayTimeoutError(GatewayError):
    status_code = 504
    error_code = "gateway_timeout"

    def __init__(self, service: str = "", timeout: float = 0.0):
        super().__init__(f"Gateway timed out calling {service or 'service'}", service=service, timeout=timeout)


class UnsupportedMediaTypeError(GatewayError):
    status_code = 415
    error_code = "unsupported_media_type"

    def __init__(self, content_type: str = ""):
        super().__init__(f"Unsupported media type {content_type!r}", content_type=content_type)


class RequestBodyTooLargeError(GatewayError):
    status_code = 413
    error_code = "request_body_too_large"

    def __init__(self, size: int, limit: int):
        super().__init__(f"Request body of {size} bytes exceeds limit of {limit} bytes", size=size, limit=limit)


class CacheError(GatewayError):
    status_code = 500
    error_code = "cache_error"

    def __init__(self, message: str = ""):
        super().__init__(message or "Cache operation failed")


class WebhookError(GatewayError):
    status_code = 500
    error_code = "webhook_error"

    def __init__(self, message: str = "", webhook_id: str = ""):
        super().__init__(message or "Webhook operation failed", webhook_id=webhook_id)


class WebhookDeliveryError(GatewayError):
    status_code = 502
    error_code = "webhook_delivery_failed"

    def __init__(self, webhook_id: str, url: str, attempt: int = 0, status_code: int | None = None):
        message = f"Webhook {webhook_id!r} delivery to {url!r} failed (attempt {attempt})"
        super().__init__(message, webhook_id=webhook_id, url=url, attempt=attempt, status_code=status_code)


class WebSocketUpgradeError(GatewayError):
    status_code = 400
    error_code = "websocket_upgrade_failed"

    def __init__(self, message: str = "WebSocket upgrade failed"):
        super().__init__(message)


class AuthenticationFailedError(GatewayError):
    status_code = 401
    error_code = "authentication_failed"

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class ForbiddenError(GatewayError):
    status_code = 403
    error_code = "forbidden"

    def __init__(self, message: str = "Access denied"):
        super().__init__(message)


class TenantIsolationError(GatewayError):
    status_code = 403
    error_code = "tenant_isolation_error"

    def __init__(self, message: str = "Tenant isolation violation"):
        super().__init__(message)
