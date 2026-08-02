from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ProviderUser


class AuthProvider(ABC):
    name: str = "base"

    def __init__(self, **options: Any):
        self._options = options

    @property
    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "options": {k: v for k, v in self._options.items() if k != "secret"}}

    @abstractmethod
    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        """Return a ProviderUser on success; raise ProviderError on failure."""
