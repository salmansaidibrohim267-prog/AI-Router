from __future__ import annotations

from app.knowledge.vector_store.models import VectorStoreStats


class VectorStoreStatistics:
    def __init__(self):
        self._total_vectors: int = 0
        self._total_collections: int = 0
        self._search_times: list[float] = []
        self._batch_sizes: list[int] = []
        self._provider: str = ""
        self._dimensions: int = 0

    def record_search(self, latency: float) -> None:
        self._search_times.append(latency)

    def record_upsert(self, count: int) -> None:
        self._total_vectors += count
        if count > 1:
            self._batch_sizes.append(count)

    def record_delete(self, count: int) -> None:
        self._total_vectors = max(0, self._total_vectors - count)

    def set_collections(self, count: int) -> None:
        self._total_collections = count

    def set_provider(self, provider: str) -> None:
        self._provider = provider

    def set_dimensions(self, dimensions: int) -> None:
        self._dimensions = dimensions

    def snapshot(self) -> VectorStoreStats:
        avg_latency = 0.0
        if self._search_times:
            avg_latency = sum(self._search_times) / len(self._search_times)
        batch_throughput = 0.0
        if self._batch_sizes:
            batch_throughput = sum(self._batch_sizes) / len(self._batch_sizes)
        return VectorStoreStats(
            total_collections=self._total_collections,
            total_vectors=self._total_vectors,
            average_search_latency=round(avg_latency, 6),
            provider=self._provider,
            dimensions=self._dimensions,
            batch_throughput=round(batch_throughput, 2),
        )
