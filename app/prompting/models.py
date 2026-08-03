from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN = "plain"
    JSON = "json"
    CUSTOM = "custom"


class ContextSource(str, Enum):
    USER = "user"
    DOCUMENTS = "documents"
    HISTORY = "history"
    METADATA = "metadata"
    SYSTEM = "system"
    MEMORY = "memory"
    TOOLS = "tools"
    CUSTOM = "custom"


@dataclass
class ContextItem:
    content: str
    source: ContextSource = ContextSource.CUSTOM
    score: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source.value,
            "score": self.score,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "token_count": self.token_count,
        }


@dataclass
class ConversationMessage:
    role: str = "user"
    content: str = ""
    timestamp: float = 0.0


@dataclass
class MemoryEntry:
    content: str = ""
    importance: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptBuildRequest:
    user_query: str = ""
    system_instructions: str = ""
    context_items: list[ContextItem] = field(default_factory=list)
    conversation_history: list[ConversationMessage] = field(default_factory=list)
    memory_entries: list[MemoryEntry] = field(default_factory=list)
    tools: list[ToolDefinition] = field(default_factory=list)
    custom_variables: dict[str, Any] = field(default_factory=dict)
    template: str = ""
    output_format: OutputFormat | None = None
    token_budget: int | None = None
    response_reservation: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptSection:
    name: str
    content: str = ""
    tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "tokens": self.tokens,
        }


@dataclass
class PromptBuildResult:
    text: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    section_tokens: dict[str, int] = field(default_factory=dict)
    total_tokens: int = 0
    used_tokens: int = 0
    budget_tokens: int = 0
    reserved_tokens: int = 0
    available_tokens: int = 0
    truncated: bool = False
    format: OutputFormat = OutputFormat.MARKDOWN
    warnings: list[str] = field(default_factory=list)
    build_latency_ms: float = 0.0
    context_items_used: int = 0
    context_items_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "sections": self.sections,
            "section_tokens": self.section_tokens,
            "total_tokens": self.total_tokens,
            "used_tokens": self.used_tokens,
            "budget_tokens": self.budget_tokens,
            "reserved_tokens": self.reserved_tokens,
            "available_tokens": self.available_tokens,
            "truncated": self.truncated,
            "format": self.format.value,
            "warnings": self.warnings,
            "build_latency_ms": round(self.build_latency_ms, 4),
            "context_items_used": self.context_items_used,
            "context_items_total": self.context_items_total,
        }


@dataclass
class PromptMetrics:
    total_builds: int = 0
    total_tokens_built: int = 0
    total_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    truncations: int = 0
    validation_failures: int = 0
    average_tokens_per_build: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_builds": self.total_builds,
            "total_tokens_built": self.total_tokens_built,
            "total_latency_ms": round(self.total_latency_ms, 4),
            "average_latency_ms": round(self.average_latency_ms, 4),
            "truncations": self.truncations,
            "validation_failures": self.validation_failures,
            "average_tokens_per_build": round(self.average_tokens_per_build, 4),
        }
