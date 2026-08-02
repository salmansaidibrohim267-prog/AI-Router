from __future__ import annotations

import time
import uuid
from typing import Any

from app.memory.store import MemoryStore, SQLiteStore


class SessionManager:
    def __init__(self, store: MemoryStore | None = None, config: dict[str, Any] | None = None):
        self._store = store or SQLiteStore()
        self._config = config or {}
        self._session_ttl = self._config.get("session_ttl", 3600)
        self._max_sessions = self._config.get("max_sessions", 1000)

    def create_session(self, metadata: dict[str, Any] | None = None) -> str:
        session_id = uuid.uuid4().hex[:16]
        now = time.time()
        data = {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "metadata": metadata or {},
            "summaries": [],
        }
        self._store.set(f"session:{session_id}", data, ttl=self._session_ttl)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        data = self._store.get(f"session:{session_id}")
        if data:
            self._touch(session_id)
        return data

    def delete_session(self, session_id: str) -> None:
        self._store.delete(f"session:{session_id}")
        self._store.delete(f"messages:{session_id}")
        self._store.delete(f"summary:{session_id}")

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for key in self._store.keys("session:*"):
            sid = key.split(":", 1)[1]
            data = self._store.get(key)
            if data:
                sessions.append(data)
        return sessions

    def update_metadata(self, session_id: str, metadata: dict[str, Any]) -> None:
        data = self._store.get(f"session:{session_id}")
        if data:
            data["metadata"].update(metadata)
            self._store.set(f"session:{session_id}", data, ttl=self._session_ttl)

    def _touch(self, session_id: str) -> None:
        data = self._store.get(f"session:{session_id}")
        if data:
            data["updated_at"] = time.time()
            self._store.set(f"session:{session_id}", data, ttl=self._session_ttl)

    def prune_expired(self) -> int:
        count = 0
        for key in self._store.keys("session:*"):
            data = self._store.get(key)
            if data is None:
                continue
            created = data.get("created_at", 0)
            if time.time() - created > self._session_ttl:
                sid = key.split(":", 1)[1]
                self.delete_session(sid)
                count += 1
        prune_count = getattr(self._store, "prune_expired", lambda: 0)()
        return count + (prune_count or 0)

    def get_stats(self) -> dict[str, Any]:
        sessions = self.list_sessions()
        total_messages = sum(s.get("message_count", 0) for s in sessions)
        total_tokens = sum(s.get("total_tokens", 0) for s in sessions)
        return {
            "active_sessions": len(sessions),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "total_cost": sum(s.get("total_cost", 0.0) for s in sessions),
            "max_sessions": self._max_sessions,
            "session_ttl": self._session_ttl,
        }
