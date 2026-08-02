from __future__ import annotations

import os
from typing import Any

from app.memory.store import FileStore, MemoryStore, RedisStore, SQLiteStore


def create_store(backend: str = "", path: str = "") -> MemoryStore:
    backend = backend or os.environ.get("MEMORY_BACKEND", "sqlite")
    if backend == "sqlite":
        return SQLiteStore(path or os.environ.get("MEMORY_DB_PATH", "memory.db"))
    elif backend == "redis":
        return RedisStore(path or os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    elif backend == "file":
        return FileStore(path or os.environ.get("MEMORY_FILE_PATH", "/tmp/ai_router_memory"))
    else:
        return SQLiteStore()


class PersistenceManager:
    def __init__(self, store: MemoryStore | None = None):
        self._store = store or create_store()

    @property
    def store(self) -> MemoryStore:
        return self._store

    def create_session_store(self) -> MemoryStore:
        return self._store

    def create_task_store(self) -> MemoryStore:
        return self._store

    def close(self) -> None:
        self._store.close()

    def get_stats(self) -> dict[str, Any]:
        import time
        keys = self._store.keys()
        return {
            "backend": self._store.__class__.__name__,
            "total_keys": len(keys),
            "timestamp": time.time(),
        }
