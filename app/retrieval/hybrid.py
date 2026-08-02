from __future__ import annotations

import time
from typing import Any

from app.retrieval.bm25 import BM25InvertedIndex
from app.retrieval.config import RetrievalConfig
from app.retrieval.exceptions import EmptyQueryError, InvalidQueryError, RetrievalError
from app.retrieval.filtering import MetadataFilterEngine
from app.retrieval.fusion import FusionStrategy, create_fusion_strategy
from app.retrieval.logging import RetrievalLogger
from app.retrieval.models import (
    SearchQuery,
    SearchResponse,
    SearchResultItem,
    SimilarityMetric,
)
from app.retrieval.normalization import NormalizationStrategy, create_normalization_strategy
from app.retrieval.pagination import Paginator
from app.retrieval.query_expansion import QueryExpander
from app.retrieval.ranking import Ranker
from app.retrieval.similarity import SimilarityStrategy, create_similarity_strategy
from app.retrieval.statistics import RetrievalStatsTracker


class HybridSearch:
    def __init__(
        self,
        vector_store: Any,
        embedding_service: Any | None = None,
        bm25_index: BM25InvertedIndex | None = None,
        config: RetrievalConfig | None = None,
        ranker: Ranker | None = None,
        filter_engine: MetadataFilterEngine | None = None,
        paginator: Paginator | None = None,
        stats_tracker: RetrievalStatsTracker | None = None,
        logger: RetrievalLogger | None = None,
        query_expander: QueryExpander | None = None,
    ):
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._bm25 = bm25_index or BM25InvertedIndex()
        self._config = config or RetrievalConfig()
        self._ranker = ranker or Ranker(self._config)
        self._filter_engine = filter_engine or MetadataFilterEngine()
        self._paginator = paginator or Paginator(max_limit=self._config.top_k_max)
        self._stats = stats_tracker or RetrievalStatsTracker(track=self._config.track_statistics)
        self._logger = logger or RetrievalLogger(enabled=self._config.log_queries)
        self._query_expander = query_expander or QueryExpander()

    async def search(self, query: SearchQuery) -> SearchResponse:
        start = time.time()
        self._logger.log_query(query)
        try:
            await self._validate(query)
            results = await self._execute_hybrid_search(query)
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

    async def batch_search(self, queries: list[SearchQuery]) -> list[SearchResponse]:
        return [await self.search(q) for q in queries]

    def index_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._bm25.index_document(doc_id, text, metadata)

    def remove_document(self, doc_id: str) -> bool:
        return self._bm25.remove_document(doc_id)

    def get_bm25_index(self) -> BM25InvertedIndex:
        return self._bm25

    async def _validate(self, query: SearchQuery) -> None:
        if not query.text:
            raise EmptyQueryError()
        if query.top_k < 1:
            raise InvalidQueryError("top_k must be >= 1")
        if query.top_k > self._config.top_k_max:
            raise InvalidQueryError(f"top_k cannot exceed {self._config.top_k_max}")
        if query.offset < 0:
            raise InvalidQueryError("offset must be >= 0")

    async def _execute_hybrid_search(self, query: SearchQuery) -> list[SearchResultItem]:
        expanded_queries = self._query_expander.expand(query.text)
        combined_text = " ".join(expanded_queries)

        # Semantic search
        semantic_results = await self._semantic_search(query, combined_text)

        # BM25 keyword search
        keyword_results = self._keyword_search(combined_text, query)

        # Normalize scores
        semantic_scores = {r.id: r.score for r in semantic_results}
        keyword_scores = {r[0]: r[1] for r in keyword_results}

        fusion_name = getattr(query, "fusion_strategy", "weighted_sum")
        norm_name = getattr(query, "normalization_strategy", "min_max")
        semantic_weight = getattr(query, "semantic_weight", 0.5)
        keyword_weight = getattr(query, "keyword_weight", 0.5)

        norm = create_normalization_strategy(norm_name)
        if semantic_scores:
            norm_sem = norm.normalize(list(semantic_scores.values()))
            semantic_scores = dict(zip(semantic_scores.keys(), norm_sem))
        if keyword_scores:
            norm_kw = norm.normalize(list(keyword_scores.values()))
            keyword_scores = dict(zip(keyword_scores.keys(), norm_kw))

        fusion = create_fusion_strategy(fusion_name)
        fused = fusion.fuse(semantic_scores, keyword_scores, semantic_weight, keyword_weight)

        # Merge metadata from both sources
        meta_map: dict[str, dict[str, Any]] = {}
        for r in semantic_results:
            meta_map[r.id] = r.metadata
        for doc_id, _, meta in keyword_results:
            if doc_id not in meta_map:
                meta_map[doc_id] = meta
            else:
                meta_map[doc_id].update(meta)

        items: list[SearchResultItem] = []
        for doc_id, score in fused[: query.top_k * 2]:
            item = SearchResultItem(
                id=doc_id,
                score=score,
                final_score=score,
                metadata=meta_map.get(doc_id, {}),
                namespace=query.namespace,
                collection=query.collection,
            )
            items.append(item)

        items = self._ranker.rank(items, query)

        paginated = self._paginator.apply(query, items)
        scanned = len(semantic_results) + len(keyword_results)
        self._stats.record_query(latency_ms=0, scanned=scanned, comparisons=len(fused))
        return paginated

    async def _semantic_search(
        self,
        query: SearchQuery,
        text: str,
    ) -> list[SearchResultItem]:
        has_semantic = (
            self._embedding_service is not None or query.vector is not None
        )
        if not has_semantic:
            return []

        try:
            vs_filter = self._filter_engine.build_vector_store_filter(query)
            vector = query.vector
            if vector is None and self._embedding_service:
                embedding = await self._embedding_service.embed_text(text)
                vector = embedding.vector
            if vector is None:
                return []

            vs_results = await self._vector_store.search(
                vector=vector,
                top_k=query.top_k,
                score_threshold=query.score_threshold,
                collection=query.collection,
                namespace=query.namespace,
                filter=vs_filter,
                include_metadata=True,
                include_vector=False,
            )

            items: list[SearchResultItem] = []
            for vsr in vs_results:
                meta = vsr.metadata if hasattr(vsr, "metadata") else {}
                item = SearchResultItem(
                    id=vsr.id if hasattr(vsr, "id") else "",
                    score=vsr.score if hasattr(vsr, "score") else 0.0,
                    metadata=meta if isinstance(meta, dict) else {},
                    namespace=query.namespace,
                    collection=query.collection,
                )
                items.append(item)
            return items
        except Exception:
            return []

    def _keyword_search(
        self,
        text: str,
        query: SearchQuery,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        return self._bm25.search(text, top_k=query.top_k)

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
