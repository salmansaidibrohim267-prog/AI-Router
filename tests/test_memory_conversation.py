import pytest

from app.memory.conversation import ConversationMemory
from app.memory.session import SessionManager
from app.memory.summary import ConversationSummarizer
from app.memory.store import SQLiteStore, FileStore


class FakeRouter:
    async def chat(self, request):
        from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
        return ChatResponse(
            id="fake", model="test",
            choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="summary text"), finish_reason="stop")],
            usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        )

    async def stream_chat(self, request):
        return
        yield


class TestSessionManager:
    def test_create_session(self):
        store = SQLiteStore(":memory:")
        mgr = SessionManager(store=store)
        sid = mgr.create_session({"user": "test"})
        assert sid
        session = mgr.get_session(sid)
        assert session is not None
        assert session["metadata"]["user"] == "test"

    def test_delete_session(self):
        store = SQLiteStore(":memory:")
        mgr = SessionManager(store=store)
        sid = mgr.create_session()
        mgr.delete_session(sid)
        assert mgr.get_session(sid) is None

    def test_list_sessions(self):
        store = SQLiteStore(":memory:")
        mgr = SessionManager(store=store)
        mgr.create_session()
        mgr.create_session()
        sessions = mgr.list_sessions()
        assert len(sessions) >= 2

    def test_get_stats(self):
        store = SQLiteStore(":memory:")
        mgr = SessionManager(store=store)
        stats = mgr.get_stats()
        assert "active_sessions" in stats
        assert "total_messages" in stats


class TestConversationMemory:
    def test_add_and_get_messages(self):
        store = SQLiteStore(":memory:")
        mem = ConversationMemory(store=store)
        sid = mem.create_session()
        mem.add_message(sid, "user", "Hello")
        mem.add_message(sid, "assistant", "Hi there")
        history = mem.get_history(sid)
        assert len(history) >= 2

    def test_clear_session(self):
        store = SQLiteStore(":memory:")
        mem = ConversationMemory(store=store)
        sid = mem.create_session()
        mem.add_message(sid, "user", "Hello")
        mem.clear_session(sid)
        history = mem.get_history(sid)
        assert len(history) == 0

    def test_get_stats(self):
        store = SQLiteStore(":memory:")
        mem = ConversationMemory(store=store)
        sid = mem.create_session()
        mem.add_message(sid, "user", "Hello")
        stats = mem.get_stats(sid)
        assert stats["session_id"] == sid
        assert stats["message_count"] >= 1

    def test_get_session_ids(self):
        store = SQLiteStore(":memory:")
        mem = ConversationMemory(store=store)
        sid = mem.create_session()
        ids = mem.get_session_ids()
        assert sid in ids

    def test_honors_token_budget(self):
        store = SQLiteStore(":memory:")
        mem = ConversationMemory(store=store, config={"max_token_budget": 10})
        sid = mem.create_session()
        mem.add_message(sid, "user", "A" * 100)
        mem.add_message(sid, "assistant", "B" * 100)
        msgs = mem.get_messages_for_request(sid)
        budget = sum(len(m.get("content", "")) for m in msgs) // 4
        assert budget <= 100


class TestFileStore:
    def test_set_and_get(self, tmp_path):
        store = FileStore(str(tmp_path))
        store.set("test_key", {"hello": "world"})
        assert store.get("test_key") == {"hello": "world"}

    def test_delete(self, tmp_path):
        store = FileStore(str(tmp_path))
        store.set("test_key", {"data": 1})
        store.delete("test_key")
        assert store.get("test_key") is None

    def test_clear(self, tmp_path):
        store = FileStore(str(tmp_path))
        store.set("a", {})
        store.set("b", {})
        store.clear()
        assert len(store.keys()) == 0
