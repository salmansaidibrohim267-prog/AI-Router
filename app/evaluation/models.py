from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvaluatorKind(str, Enum):
    RETRIEVAL = "retrieval"
    RAG = "rag"
    CITATION = "citation"
    MEMORY = "memory"
    MCP_TOOLS = "mcp_tools"


class DatasetType(str, Enum):
    INTERNAL = "internal"
    PUBLIC = "public"
    REGRESSION = "regression"
    CUSTOM = "custom"


@dataclass
class RetrievedItem:
    id: str
    score: float = 0.0
    content: str = ""
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "content": self.content,
            "rank": self.rank,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationSample:
    id: str
    query: str
    expected: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "expected": self.expected,
            "actual": self._json_safe(self.actual),
            "metadata": self.metadata,
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, list):
            return [EvaluationSample._json_safe(v) for v in value]
        if isinstance(value, dict):
            return {k: EvaluationSample._json_safe(v) for k, v in value.items()}
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return value

    @classmethod
    def retrieval(
        cls,
        id: str,
        query: str,
        relevant_ids: list[str],
        results: list[Any],
    ) -> EvaluationSample:
        return cls(
            id=id,
            query=query,
            expected={"relevant_ids": relevant_ids},
            actual={"results": [cls._to_retrieved_item(r) for r in results]},
            metadata={"evaluator": EvaluatorKind.RETRIEVAL.value},
        )

    @classmethod
    def rag(
        cls,
        id: str,
        query: str,
        contexts: list[str],
        answer: str,
        reference: str = "",
    ) -> EvaluationSample:
        return cls(
            id=id,
            query=query,
            expected={"reference": reference},
            actual={"contexts": contexts, "answer": answer},
            metadata={"evaluator": EvaluatorKind.RAG.value},
        )

    @classmethod
    def citation(
        cls,
        id: str,
        text: str,
        citations: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> EvaluationSample:
        return cls(
            id=id,
            query=text,
            expected={"sources": [s.get("id", s.get("source_id", "")) for s in sources]},
            actual={"text": text, "citations": citations, "sources": sources},
            metadata={"evaluator": EvaluatorKind.CITATION.value},
        )

    @classmethod
    def memory(
        cls,
        id: str,
        query: str,
        relevant_ids: list[str],
        retrieved: list[Any],
        stored: list[Any] | None = None,
    ) -> EvaluationSample:
        return cls(
            id=id,
            query=query,
            expected={"relevant_ids": relevant_ids},
            actual={
                "retrieved": [cls._to_retrieved_item(r) for r in retrieved],
                "stored": stored or [],
            },
            metadata={"evaluator": EvaluatorKind.MEMORY.value},
        )

    @classmethod
    def mcp_tools(
        cls,
        id: str,
        expected_tools: list[str],
        calls: list[dict[str, Any]],
    ) -> EvaluationSample:
        return cls(
            id=id,
            query=id,
            expected={"tools": expected_tools},
            actual={"calls": calls},
            metadata={"evaluator": EvaluatorKind.MCP_TOOLS.value},
        )

    @classmethod
    def from_retrieved_chunks(cls, id: str, query: str, relevant_ids: list[str], chunks: list[Any]) -> EvaluationSample:
        items: list[RetrievedItem] = []
        for i, chunk in enumerate(chunks):
            items.append(
                RetrievedItem(
                    id=_attr(chunk, "chunk_id", _attr(chunk, "id", str(i))),
                    score=_attr(chunk, "rerank_score", _attr(chunk, "score", 0.0)),
                    content=_attr(chunk, "content", ""),
                    rank=i + 1,
                    metadata=_attr(chunk, "metadata", {}),
                )
            )
        return cls.retrieval(id, query, relevant_ids, items)

    @classmethod
    def from_search_results(cls, id: str, query: str, relevant_ids: list[str], items: list[Any]) -> EvaluationSample:
        converted: list[RetrievedItem] = []
        for i, item in enumerate(items):
            converted.append(
                RetrievedItem(
                    id=_attr(item, "id", str(i)),
                    score=_attr(item, "score", 0.0),
                    content=_attr(item, "content", _attr(item, "text", "")),
                    rank=i + 1,
                    metadata=_attr(item, "metadata", {}),
                )
            )
        return cls.retrieval(id, query, relevant_ids, converted)

    @classmethod
    def from_memory_items(cls, id: str, query: str, relevant_ids: list[str], items: list[Any]) -> EvaluationSample:
        converted: list[RetrievedItem] = []
        for i, item in enumerate(items):
            converted.append(
                RetrievedItem(
                    id=_attr(item, "id", str(i)),
                    score=_attr(item, "importance", _attr(item, "score", 0.0)),
                    content=_attr(item, "content", ""),
                    rank=i + 1,
                    metadata=_attr(item, "metadata", {}),
                )
            )
        return cls.memory(id, query, relevant_ids, converted)

    @staticmethod
    def _to_retrieved_item(item: Any) -> RetrievedItem:
        if isinstance(item, RetrievedItem):
            return item
        if isinstance(item, dict):
            return RetrievedItem(
                id=str(item.get("id", item.get("chunk_id", ""))),
                score=float(item.get("score", item.get("rerank_score", item.get("importance", 0.0)))),
                content=str(item.get("content", item.get("text", ""))),
                rank=int(item.get("rank", 0)),
                metadata=item.get("metadata", {}),
            )
        return RetrievedItem(
            id=_attr(item, "chunk_id", _attr(item, "id", _attr(item, "item_id", ""))),
            score=_attr(item, "rerank_score", _attr(item, "score", _attr(item, "importance", 0.0))),
            content=_attr(item, "content", ""),
            rank=_attr(item, "rank", 0),
            metadata=_attr(item, "metadata", {}),
        )


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class MetricScore:
    metric: str
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "value": self.value, "metadata": self.metadata}


@dataclass
class EvaluationMetric:
    name: str
    value: float
    samples: int = 0
    distribution: dict[str, float] = field(default_factory=dict)
    threshold_min: float | None = None
    threshold_max: float | None = None
    passed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "samples": self.samples,
            "distribution": {k: round(v, 4) for k, v in self.distribution.items()},
            "threshold_min": self.threshold_min,
            "threshold_max": self.threshold_max,
            "passed": self.passed,
        }


@dataclass
class EvaluationResult:
    evaluator: str
    samples: list[EvaluationSample] = field(default_factory=list)
    metrics: list[EvaluationMetric] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def summary(self) -> dict[str, float]:
        return {m.name: m.value for m in self.metrics}

    def metric(self, name: str) -> EvaluationMetric | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "samples": len(self.samples),
            "metrics": [m.to_dict() for m in self.metrics],
            "error": self.error,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 4),
        }


@dataclass
class GateCheck:
    metric: str
    value: float
    threshold_min: float | None = None
    threshold_max: float | None = None
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": round(self.value, 4),
            "threshold_min": self.threshold_min,
            "threshold_max": self.threshold_max,
            "passed": self.passed,
        }


@dataclass
class GateResult:
    passed: bool
    checks: list[GateCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [c.to_dict() for c in self.checks]}


@dataclass
class BenchmarkDataset:
    name: str
    dataset_type: DatasetType
    samples: list[EvaluationSample]
    description: str = ""
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset_type": self.dataset_type.value,
            "description": self.description,
            "version": self.version,
            "samples": [s.to_dict() for s in self.samples],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BenchmarkDataset:
        dataset_type = DatasetType(payload.get("dataset_type", "custom"))
        samples = [
            EvaluationSample(
                id=str(s.get("id", "")),
                query=str(s.get("query", "")),
                expected=s.get("expected", {}),
                actual=s.get("actual", {}),
                metadata=s.get("metadata", {}),
            )
            for s in payload.get("samples", [])
        ]
        return cls(
            name=str(payload.get("name", "unnamed")),
            dataset_type=dataset_type,
            samples=samples,
            description=str(payload.get("description", "")),
            version=str(payload.get("version", "1.0.0")),
        )


@dataclass
class BenchmarkResult:
    name: str
    dataset_name: str
    dataset_type: str
    results: list[EvaluationResult] = field(default_factory=list)
    gate: dict[str, Any] | None = None
    started_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def summary(self) -> dict[str, float]:
        merged: dict[str, float] = {}
        for result in self.results:
            merged.update(result.summary())
        return merged

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset_name": self.dataset_name,
            "dataset_type": self.dataset_type,
            "results": [r.to_dict() for r in self.results],
            "gate": self.gate,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 4),
        }


@dataclass
class ComparisonResult:
    base_name: str
    current_name: str
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    regressions: list[str] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_name": self.base_name,
            "current_name": self.current_name,
            "metrics": self.metrics,
            "regressions": self.regressions,
            "passed": self.passed,
        }
