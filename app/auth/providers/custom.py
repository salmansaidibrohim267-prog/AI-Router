from __future__ import annotations

from typing import Any, Callable

from ..exceptions import ProviderError
from ..models import ProviderUser
from .base import AuthProvider

CustomHandler = Callable[[dict[str, Any]], ProviderUser]


class CustomProvider(AuthProvider):
    name = "custom"

    def __init__(
        self,
        handler: CustomHandler | None = None,
        **options: Any,
    ):
        super().__init__(**options)
        self._handler = handler

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        if self._handler is None:
            raise ProviderError("Custom provider has no handler")
        try:
            result = self._handler(credentials)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Custom provider failed: {exc}") from exc
        if not isinstance(result, ProviderUser):
            raise ProviderError("Custom handler must return a ProviderUser")
        return result
