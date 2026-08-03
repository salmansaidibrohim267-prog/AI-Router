from app.memory.config import MemoryVectorConfig
from app.memory.conversation import ConversationMemory
from app.memory.manager import MemoryManager
from app.memory.models import (
    ExtractedMemory,
    MemoryCategory,
    MemoryEventType,
    MemoryItem,
    MemoryMetrics,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
    MemorySummary,
    MemoryType,
)
from app.memory.session import SessionManager
from app.memory.store import FileStore, MemoryStore, RedisStore, SQLiteStore
from app.memory.summary import ConversationSummarizer


def create_memory_manager(
    config: MemoryVectorConfig | None = None,
    **kwargs,
) -> MemoryManager:
    if config is None:
        config = MemoryVectorConfig.from_env()
    return MemoryManager(config=config, **kwargs)


__all__ = [
    "ConversationMemory",
    "SessionManager",
    "ConversationSummarizer",
    "MemoryStore",
    "SQLiteStore",
    "RedisStore",
    "FileStore",
    "MemoryManager",
    "MemoryVectorConfig",
    "MemoryItem",
    "MemoryScope",
    "MemoryQuery",
    "MemorySearchResult",
    "MemorySummary",
    "MemoryMetrics",
    "MemoryType",
    "MemoryCategory",
    "MemoryEventType",
    "ExtractedMemory",
    "create_memory_manager",
]
