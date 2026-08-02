from __future__ import annotations

import time
from typing import Any

from app.memory.session import SessionManager
from app.memory.store import MemoryStore, SQLiteStore
from app.memory.summary import ConversationSummarizer


class ConversationMemory:
    def __init__(
        self,
        store: MemoryStore | None = None,
        session_manager: SessionManager | None = None,
        summarizer: ConversationSummarizer | None = None,
        config: dict[str, Any] | None = None,
    ):
        self._store = store or SQLiteStore()
        self._session_manager = session_manager or SessionManager(self._store)
        self._summarizer = summarizer
        self._config = config or {}
        self._max_tokens = self._config.get("max_token_budget", 8000)
        self._message_ttl = self._config.get("message_ttl", 7200)
        self._prune_threshold = self._config.get("prune_threshold", 100)

    def create_session(self, metadata: dict[str, Any] | None = None) -> str:
        return self._session_manager.create_session(metadata)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._session_manager.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        self._session_manager.delete_session(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        messages = self._get_messages(session_id)
        now = time.time()
        msg = {
            "role": role,
            "content": content,
            "timestamp": now,
            "metadata": metadata or {},
        }
        messages.append(msg)
        self._save_messages(session_id, messages)
        session = self._session_manager.get_session(session_id)
        if session:
            session["message_count"] = len(messages)
            session["total_tokens"] = self._estimate_tokens(messages)
            self._store.set(f"session:{session_id}", session, ttl=self._message_ttl)

    def get_history(
        self,
        session_id: str,
        limit: int = 0,
        include_summary: bool = True,
    ) -> list[dict[str, Any]]:
        messages = self._get_messages(session_id)
        if include_summary and self._summarizer:
            summary_data = self._store.get(f"summary:{session_id}")
            if summary_data and messages:
                summary_msg = {
                    "role": "system",
                    "content": f"Conversation summary: {summary_data.get('text', '')}",
                }
                messages = [summary_msg] + messages
        if limit > 0 and len(messages) > limit:
            messages = messages[-limit:]
        return messages

    def get_messages_for_request(
        self,
        session_id: str,
        token_budget: int = 0,
    ) -> list[dict[str, Any]]:
        messages = self._get_messages(session_id)
        budget = token_budget or self._max_tokens
        total = self._estimate_tokens(messages)
        if total <= budget:
            return self.get_history(session_id, include_summary=True)
        if self._summarizer and messages:
            summary_data = self._store.get(f"summary:{session_id}")
            existing = summary_data.get("text", "") if summary_data else ""
            if len(messages) > 4:
                older = messages[:-4]
                recent = messages[-4:]
                newest_msg = messages[-1]
                summary_text = f"{existing}\n{self._format_messages(older)}" if existing else self._format_messages(older)
                summary_msg = {"role": "system", "content": f"Conversation summary: {summary_text}"}
                result = [summary_msg] + recent
                if self._estimate_tokens(result) <= budget:
                    return result
                return [summary_msg, newest_msg]
        if len(messages) > 1:
            return [messages[-1]]
        return messages

    def clear_session(self, session_id: str) -> None:
        self._store.delete(f"messages:{session_id}")

    def get_stats(self, session_id: str = "") -> dict[str, Any]:
        if session_id:
            messages = self._get_messages(session_id)
            session = self._session_manager.get_session(session_id)
            return {
                "session_id": session_id,
                "message_count": len(messages),
                "total_tokens": self._estimate_tokens(messages),
                "created_at": session.get("created_at", 0) if session else 0,
                "updated_at": session.get("updated_at", 0) if session else 0,
            }
        return self._session_manager.get_stats()

    def prune_old_sessions(self) -> int:
        return self._session_manager.prune_expired()

    def _get_messages(self, session_id: str) -> list[dict[str, Any]]:
        data = self._store.get(f"messages:{session_id}")
        return data if isinstance(data, list) else []

    def _save_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self._store.set(f"messages:{session_id}", messages, ttl=self._message_ttl)

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        return ConversationSummarizer.estimate_tokens(
            " ".join(m.get("content", "") for m in messages)
        )

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)

    def get_session_ids(self) -> list[str]:
        keys = self._store.keys("session:*")
        return [k.split(":", 1)[1] for k in keys]
