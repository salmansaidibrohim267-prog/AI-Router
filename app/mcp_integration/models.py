from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPRetrievalResult:
    id: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class MCPRAGIntegrationResult:
    query: str
    answer: str = ""
    chunks: list[MCPRetrievalResult] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    citation_result: dict[str, Any] | None = None
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "chunks": [c.to_dict() for c in self.chunks],
            "memories": self.memories,
            "citation_result": self.citation_result,
            "latency_ms": round(self.latency_ms, 4),
            "error": self.error,
        }


@dataclass
class MCPIntegrationMetrics:
    total_retrievals: int = 0
    total_tool_calls: int = 0
    total_resource_reads: int = 0
    total_memories_stored: int = 0
    total_memories_retrieved: int = 0
    total_citations_generated: int = 0
    total_answers: int = 0
    total_errors: int = 0
    retrieval_latency_ms: float = 0.0
    answer_latency_ms: float = 0.0
    started_at: float = field(default_factory=time.time)

    def record_retrieval(self, latency_ms: float) -> None:
        self.total_retrievals += 1
        self.retrieval_latency_ms += latency_ms

    def record_tool_call(self) -> None:
        self.total_tool_calls += 1

    def record_resource_read(self) -> None:
        self.total_resource_reads += 1

    def record_memory_store(self) -> None:
        self.total_memories_stored += 1

    def record_memory_retrieve(self, count: int = 1) -> None:
        self.total_memories_retrieved += count

    def record_citation(self) -> None:
        self.total_citations_generated += 1

    def record_answer(self, latency_ms: float) -> None:
        self.total_answers += 1
        self.answer_latency_ms += latency_ms

    def record_error(self) -> None:
        self.total_errors += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_retrievals": self.total_retrievals,
            "total_tool_calls": self.total_tool_calls,
            "total_resource_reads": self.total_resource_reads,
            "total_memories_stored": self.total_memories_stored,
            "total_memories_retrieved": self.total_memories_retrieved,
            "total_citations_generated": self.total_citations_generated,
            "total_answers": self.total_answers,
            "total_errors": self.total_errors,
            "average_retrieval_latency_ms": (
                round(self.retrieval_latency_ms / self.total_retrievals, 4) if self.total_retrievals else 0.0
            ),
            "average_answer_latency_ms": (
                round(self.answer_latency_ms / self.total_answers, 4) if self.total_answers else 0.0
            ),
            "uptime_seconds": round(time.time() - self.started_at, 4),
        }
