from __future__ import annotations

import time
import uuid
from typing import Any

from app.retrieval.config import RetrievalConfig
from app.retrieval.exceptions import EmptyQueryError, InvalidQueryError, RetrievalError
from app.retrieval.filtering import MetadataFilterEngine
from app.retrieval.logging import RetrievalLogger
from app.retrieval.models import (
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from app.retrieval.pagination import Paginator
from app.retrieval.ranking import Ranker
from app.retrieval.similarity import create_similarity_strategy
from app.retrieval.statistics import RetrievalStatsTracker


class SemanticSearch:
    def __init__(
        self,
        vector_store: Any,
        embedding_service: Any | None = None,
        config: RetrievalConfig | None = None,
        ranker: Ranker | None = None,
        filter_engine: MetadataFilterEngine | None = None,
        paginator: Paginator | None = None,
        stats_tracker: RetrievalStatsTracker | None = None,
        logger: RetrievalLogger | None = None,
    ):
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._config = config or RetrievalConfig()
        self._ranker = ranker or Ranker(self._config)
        self._filter_engine = filter_engine or MetadataFilterEngine()
        self._paginator = paginator or Paginator(max_limit=self._config.top_k_max)
        self._stats = stats_tracker or RetrievalStatsTracker(track=self._config.track_statistics)
        self._logger = logger or RetrievalLogger(enabled=self._config.log_queries)

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.time()
        self._logger.log_query(query)
        try:
            await self._validate(query)
            results = await self._execute_search(query)
            response = self._build_response(query, results, start)
            self._logger.log_result(query, response, (time.time() - start) * 1000)
            return response
        except RetrievalError:
            raise
        except Exception as e:
            self._logger.log_error(query, e)
            raise RetrievalError(str(e)) from e

    async def search_async(self, query: SearchQuery) -> SearchResponse:
        return await self.search(query)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[SearchResultItem]:
        sq = SearchQuery(text=query, top_k=top_k, **kwargs)
        response = await self.search(sq)
        return response.results

    async def retrieve_with_scores(
        self,
        query: str,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[tuple[SearchResultItem, float]]:
        sq = SearchQuery(text=query, top_k=top_k, **kwargs)
        response = await self.search(sq)
        return [(r, r.final_score) for r in response.results]

    async def batch_search(
        self,
        queries: list[SearchQuery],
    ) -> list[SearchResponse]:
        return [await self.search(q) for q in queries]

    async def search_by_embedding(
        self,
        vector: list[float],
        top_k: int = 10,
        **kwargs: Any,
    ) -> SearchResponse:
        sq = SearchQuery(vector=vector, top_k=top_k, **kwargs)
        return await self.search(sq)

    async def _validate(self, query: SearchQuery) -> None:
        if not query.text and query.vector is None:
            raise EmptyQueryError()
        if query.vector is not None and len(query.vector) == 0:
            raise InvalidQueryError("Vector must not be empty")
        if query.top_k < 1:
            raise InvalidQueryError("top_k must be >= 1")
        if query.top_k > self._config.top_k_max:
            raise InvalidQueryError(f"top_k cannot exceed {self._config.top_k_max}")
        if query.offset < 0:
            raise InvalidQueryError("offset must be >= 0")

    async def _execute_search(self, query: SearchQuery) -> list[SearchResultItem]:
        if query.vector is None and query.text and self._embedding_service:
            embedding = await self._embedding_service.embed_text(query.text)
            query.vector = embedding.vector
        elif query.vector is None:
            raise InvalidQueryError("No vector or embedding service available")

        vs_filter = self._filter_engine.build_vector_store_filter(query)

        vs_results = await self._vector_store.search(
            vector=query.vector,
            top_k=query.top_k * 2,
            score_threshold=query.score_threshold,
            collection=query.collection,
            namespace=query.namespace,
            filter=vs_filter,
            include_metadata=query.include_metadata,
            include_vector=query.include_vector,
        )

        self._stats.record_cache_miss()

        scanned = len(vs_results)
        items = self._to_items(vs_results, query)

        similarity = create_similarity_strategy(query.similarity)
        for item in items:
            if item.vector:
                item.score = similarity.compute(query.vector, item.vector)

        if query.max_distance is not None:
            items = [it for it in items if (1.0 - it.score) <= query.max_distance]

        ranked = self._ranker.rank(items, query)

        paginated = self._paginator.apply(query, ranked)

        comparisons = len(items) * len(items) if items else 0
        self._stats.record_query(
            latency_ms=0,
            scanned=scanned,
            comparisons=comparisons,
        )

        return paginated

    def _to_items(
        self,
        vs_results: list[Any],
        query: SearchQuery,
    ) -> list[SearchResultItem]:
        items: list[SearchResultItem] = []
        for vsr in vs_results:
            meta = vsr.metadata if hasattr(vsr, "metadata") else {}
            vec = vsr.vector if hasattr(vsr, "vector") else None
            item = SearchResultItem(
                id=vsr.id if hasattr(vsr, "id") else str(uuid.uuid4().hex[:16]),
                score=vsr.score if hasattr(vsr, "score") else 0.0,
                vector=vec,
                metadata=meta if isinstance(meta, dict) else {},
                namespace=vsr.namespace if hasattr(vsr, "namespace") else query.namespace,
                collection=query.collection,
            )
            items.append(item)
        return items

    def _build_response(
        self,
        query: SearchQuery,
        results: list[SearchResultItem],
        start_time: float,
    ) -> SearchResponse:
        latency_ms = (time.time() - start_time) * 1000
        total = len(results)
        next_cursor = self._paginator.compute_next_cursor(query, results, total)
        stats = self._stats.snapshot()
        return SearchResponse(
            results=results,
            total=total,
            offset=query.offset,
            limit=query.limit,
            next_cursor=next_cursor,
            query_time_ms=round(latency_ms, 4),
            statistics=stats.to_dict(),
        )
