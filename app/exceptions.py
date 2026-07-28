"""Custom exceptions for AI Router."""


class AIRouterError(Exception):
    """Base exception for AI Router."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ConfigurationError(AIRouterError):
    """Configuration-related errors."""

    def __init__(
        self,
        message: str,
        code: str = "CONFIGURATION_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ):
        super().__init__(message, code, status_code, details)


class ValidationError(AIRouterError):
    """Input validation errors."""

    def __init__(
        self,
        message: str,
        code: str = "VALIDATION_ERROR",
        status_code: int = 400,
        details: dict | None = None,
    ):
        super().__init__(message, code, status_code, details)


class ProviderError(AIRouterError):
    """Provider-related errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        code: str = "PROVIDER_ERROR",
        status_code: int = 502,
        details: dict | None = None,
    ):
        super().__init__(message, code, status_code, details)
        self.provider = provider
        self.model = model
        if provider:
            self.details["provider"] = provider
        if model:
            self.details["model"] = model


class ProviderUnavailableError(ProviderError):
    """Provider is unavailable."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            provider=provider,
            model=model,
            code="PROVIDER_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            provider=provider,
            model=model,
            code="PROVIDER_TIMEOUT",
            status_code=504,
            details=details,
        )
        if timeout:
            self.details["timeout"] = timeout


class ProviderAuthError(ProviderError):
    """Provider authentication failed."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            provider=provider,
            code="PROVIDER_AUTH_ERROR",
            status_code=401,
            details=details,
        )


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        retry_after: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            provider=provider,
            code="PROVIDER_RATE_LIMIT",
            status_code=429,
            details=details,
        )
        if retry_after:
            self.details["retry_after"] = retry_after


class RouterError(AIRouterError):
    """Router-specific errors."""

    def __init__(
        self,
        message: str,
        code: str = "ROUTER_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ):
        super().__init__(message, code, status_code, details)


class NoHealthyProviderError(RouterError):
    """No healthy provider available for task."""

    def __init__(
        self,
        task: str,
        tried_providers: list[str] | None = None,
        details: dict | None = None,
    ):
        message = f"No healthy provider available for task: {task}"
        super().__init__(
            message,
            code="NO_HEALTHY_PROVIDER",
            status_code=503,
            details=details,
        )
        self.task = task
        self.details["task"] = task
        if tried_providers:
            self.details["tried_providers"] = tried_providers


class AllProvidersFailedError(RouterError):
    """All providers failed for a request."""

    def __init__(
        self,
        task: str,
        errors: list[ProviderError] | None = None,
        details: dict | None = None,
    ):
        message = f"All providers failed for task: {task}"
        super().__init__(
            message,
            code="ALL_PROVIDERS_FAILED",
            status_code=502,
            details=details,
        )
        self.task = task
        self.details["task"] = task
        if errors:
            self.details["errors"] = [e.to_dict() for e in errors]


class CacheError(AIRouterError):
    """Cache-related errors."""

    def __init__(
        self,
        message: str,
        code: str = "CACHE_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ):
        super().__init__(message, code, status_code, details)


class RateLimitError(AIRouterError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(
            message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )
        if retry_after:
            self.details["retry_after"] = retry_after