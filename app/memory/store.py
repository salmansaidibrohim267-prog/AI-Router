from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MemoryStore(ABC):
    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl: float = 0) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def keys(self, pattern: str = "") -> list[str]: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class SQLiteStore(MemoryStore):
    def __init__(self, path: str = ""):
        if not path:
            path = os.environ.get("MEMORY_DB_PATH", "memory.db")
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS memory_store (key TEXT PRIMARY KEY, value TEXT, expires_at REAL)"
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON memory_store(expires_at)")
            self._conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute("SELECT value, expires_at FROM memory_store WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            value, expires_at = row
            if expires_at and time.time() > expires_at:
                self._conn.execute("DELETE FROM memory_store WHERE key = ?", (key,))
                self._conn.commit()
                return None
            return json.loads(value)

    def set(self, key: str, value: dict[str, Any], ttl: float = 0) -> None:
        expires_at = (time.time() + ttl) if ttl > 0 else 0
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_store (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires_at),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_store WHERE key = ?", (key,))
            self._conn.commit()

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self, pattern: str = "") -> list[str]:
        with self._lock:
            if pattern:
                sql_pattern = pattern.replace("*", "%")
                cur = self._conn.execute("SELECT key FROM memory_store WHERE key LIKE ?", (sql_pattern,))
            else:
                cur = self._conn.execute("SELECT key FROM memory_store")
            return [row[0] for row in cur.fetchall()]

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_store")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def prune_expired(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute("DELETE FROM memory_store WHERE expires_at > 0 AND expires_at <= ?", (now,))
            self._conn.commit()
            return cur.rowcount


class RedisStore(MemoryStore):
    def __init__(self, url: str = ""):
        self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None
        self._connect()

    def _connect(self) -> None:
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._url)
        except ImportError:
            try:
                import redis

                self._redis = redis.from_url(self._url)
            except ImportError:
                raise ImportError("redis package not installed. Install with: pip install redis") from None

    def _ensure_sync(self) -> Any:
        if hasattr(self._redis, "get"):
            return self._redis
        return None

    def get(self, key: str) -> dict[str, Any] | None:
        r = self._ensure_sync()
        if r is None:
            return None
        val = r.get(key)
        if val is None:
            return None
        return json.loads(val)

    def set(self, key: str, value: dict[str, Any], ttl: float = 0) -> None:
        r = self._ensure_sync()
        if r is None:
            return
        if ttl > 0:
            r.setex(key, int(ttl), json.dumps(value))
        else:
            r.set(key, json.dumps(value))

    def delete(self, key: str) -> None:
        r = self._ensure_sync()
        if r:
            r.delete(key)

    def exists(self, key: str) -> bool:
        r = self._ensure_sync()
        if r is None:
            return False
        return bool(r.exists(key))

    def keys(self, pattern: str = "") -> list[str]:
        r = self._ensure_sync()
        if r is None:
            return []
        pattern = pattern or "*"
        return [k.decode() if isinstance(k, bytes) else k for k in r.keys(pattern)]

    def clear(self) -> None:
        r = self._ensure_sync()
        if r:
            r.flushdb()

    def close(self) -> None:
        if self._redis:
            self._redis.close()


class FileStore(MemoryStore):
    def __init__(self, path: str = ""):
        if not path:
            path = os.environ.get("MEMORY_FILE_PATH", "/tmp/ai_router_memory")
        self._base = Path(path)
        self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._base / f"{safe}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            with open(p) as f:
                data = json.load(f)
            expires_at = data.get("_expires_at", 0)
            if expires_at and time.time() > expires_at:
                p.unlink(missing_ok=True)
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: dict[str, Any], ttl: float = 0) -> None:
        if ttl > 0:
            value["_expires_at"] = time.time() + ttl
        with self._lock:
            with open(self._path(key), "w") as f:
                json.dump(value, f)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def keys(self, pattern: str = "") -> list[str]:
        all_keys = [p.stem for p in self._base.glob("*.json")]
        if pattern:
            safe_pat = pattern.replace("*", "").replace("?", "")
            return [k for k in all_keys if safe_pat in k]
        return all_keys

    def clear(self) -> None:
        for p in self._base.glob("*.json"):
            p.unlink()

    def close(self) -> None:
        pass
