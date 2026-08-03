"""Pluggable storage backend for persistent provider statistics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderStats:
    """Persistent provider statistics snapshot."""

    name: str = ""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    ewma_latency: float = 0.0
    total_cost: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    uptime_seconds: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    consecutive_failures: int = 0
    consecutive_success: int = 0


class StorageBackend(ABC):
    """Abstract interface for provider statistics storage."""

    @abstractmethod
    async def load_provider(self, name: str) -> ProviderStats | None:
        """Load stats for a single provider."""
        ...

    @abstractmethod
    async def save_provider(self, stats: ProviderStats) -> None:
        """Save/upsert stats for a provider."""
        ...

    @abstractmethod
    async def load_all_providers(self) -> list[ProviderStats]:
        """Load stats for all known providers."""
        ...

    @abstractmethod
    async def delete_provider(self, name: str) -> None:
        """Delete stats for a provider."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the storage backend."""
        ...


class InMemoryBackend(StorageBackend):
    """In-memory storage backend (for testing)."""

    def __init__(self):
        self._data: dict[str, ProviderStats] = {}

    async def load_provider(self, name: str) -> ProviderStats | None:
        return self._data.get(name)

    async def save_provider(self, stats: ProviderStats) -> None:
        self._data[stats.name] = stats

    async def load_all_providers(self) -> list[ProviderStats]:
        return list(self._data.values())

    async def delete_provider(self, name: str) -> None:
        self._data.pop(name, None)

    async def close(self) -> None:
        self._data.clear()
