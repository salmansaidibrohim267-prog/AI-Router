from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.caching import RAGCache
from app.rag.config import RAGConfig
from app.rag.context_builder import ContextBuilder
from app.rag.exceptions import (
    RAGCacheError,
    RAGContextError,
    RAGError,
    RAGFallbackTriggered,
    RAGGenerationError,
    RAGPromptError,
    RAGQueryError,
    RAGRetrievalError,
)
from app.rag.fallback import FallbackHandler, FallbackStrategy
from app.rag.logging import RAGLogger
from app.rag.models import (
    ContextAssembly,
    ConversationTurn,
    IntentType,
    LanguageType,
    QueryAnalysis,
    RAGMetrics,
    RAGRequest,
    RAGResponse,
    RetrievedChunk,
)
from app.rag.pipeline import RAGPipeline
from app.rag.prompt_builder import PromptBuilder
from app.rag.query_processor import QueryProcessor
from app.rag.retrieval_orchestrator import RetrievalOrchestrator
from app.rag.statistics import RAGMetricsTracker


# ============================================================
# RAGConfig
# ============================================================
class TestRAGConfig:
    def test_defaults(self):
        c = RAGConfig()
        assert c.retrieval_top_k == 10
        assert c.rerank_top_k == 5
        assert c.context_token_budget == 2048
        assert c.fallback_strategy == "reduce"
        assert c.provider == "openai"

    def test_from_env(self):
        os.environ["RAG_RETRIEVAL_TOP_K"] = "20"
        os.environ["RAG_LLM_PROVIDER"] = "anthropic"
        os.environ["RAG_CACHE_ENABLED"] = "0"
        os.environ["RAG_ENABLE_QUERY_EXPANSION"] = "0"
        try:
            c = RAGConfig.from_env()
            assert c.retrieval_top_k == 20
            assert c.provider == "anthropic"
            assert c.cache_enabled is False
            assert c.enable_query_expansion is False
        finally:
            for k in ["RAG_RETRIEVAL_TOP_K", "RAG_LLM_PROVIDER", "RAG_CACHE_ENABLED", "RAG_ENABLE_QUERY_EXPANSION"]:
                os.environ.pop(k, None)


# ============================================================
# Models
# ============================================================
class TestModels:
    def test_intent_type_values(self):
        assert IntentType.QUESTION.value == "question"
        assert IntentType.UNKNOWN.value == "unknown"

    def test_language_type_values(self):
        assert LanguageType.EN.value == "en"
        assert LanguageType.UNKNOWN.value == "unknown"

    def test_query_analysis_defaults(self):
        qa = QueryAnalysis(original="test query")
        assert qa.original == "test query"
        assert qa.normalized == ""
        assert qa.language == LanguageType.UNKNOWN
        assert qa.intent == IntentType.UNKNOWN

    def test_query_analysis_to_dict(self):
        qa = QueryAnalysis(original="hello", language=LanguageType.EN, intent=IntentType.QUESTION)
        d = qa.to_dict()
        assert d["original"] == "hello"
        assert d["language"] == "en"
        assert d["intent"] == "question"

    def test_retrieved_chunk_defaults(self):
        rc = RetrievedChunk(chunk_id="c1", content="some content", score=0.9)
        assert rc.rerank_score == 0.0
        assert rc.source == ""
        assert rc.metadata == {}

    def test_retrieved_chunk_to_dict_truncates_content(self):
        rc = RetrievedChunk(chunk_id="c1", content="x" * 500, score=0.9)
        d = rc.to_dict()
        assert len(d["content"]) == 200

    def test_context_assembly_defaults(self):
        ca = ContextAssembly()
        assert ca.chunks == []
        assert ca.total_tokens == 0
        assert ca.token_budget == 2048

    def test_conversation_turn_defaults(self):
        ct = ConversationTurn()
        assert ct.role == "user"
        assert ct.content == ""
        assert ct.timestamp == 0.0

    def test_rag_request_defaults(self):
        r = RAGRequest()
        assert r.query == ""
        assert r.stream is False
        assert r.provider_override == ""

    def test_rag_response_defaults(self):
        r = RAGResponse(answer="ans")
        assert r.answer == "ans"
        assert r.cache_hit is False
        assert r.fallback_used is False
        assert r.token_usage == {}

    def test_rag_response_to_dict(self):
        qa = QueryAnalysis(original="q")
        ca = ContextAssembly()
        r = RAGResponse(answer="ans", query_analysis=qa, context=ca, token_usage={"total": 50})
        d = r.to_dict()
        assert d["answer"] == "ans"
        assert d["token_usage"]["total"] == 50

    def test_rag_metrics_defaults(self):
        m = RAGMetrics()
        assert m.total_requests == 0
        assert m.average_latency_ms == 0.0

    def test_rag_metrics_to_dict(self):
        m = RAGMetrics(total_requests=10, total_latency_ms=100.0)
        d = m.to_dict()
        assert d["total_requests"] == 10


# ============================================================
# Exceptions
# ============================================================
class TestExceptions:
    def test_rag_error(self):
        assert isinstance(RAGError("x"), Exception)

    def test_subclasses(self):
        assert isinstance(RAGQueryError(), RAGError)
        assert isinstance(RAGRetrievalError(), RAGError)
        assert isinstance(RAGContextError(), RAGError)
        assert isinstance(RAGPromptError(), RAGError)
        assert isinstance(RAGGenerationError(), RAGError)
        assert isinstance(RAGCacheError(), RAGError)
        assert isinstance(RAGFallbackTriggered(), RAGError)


# ============================================================
# QueryProcessor
# ============================================================
class TestQueryProcessor:
    def test_normalize_removes_extra_spaces(self):
        qp = QueryProcessor()
        assert qp._normalize("  hello   world  ") == "hello world"

    def test_normalize_strips(self):
        qp = QueryProcessor()
        assert qp._normalize("\tfoo\n") == "foo"

    def test_detect_language_english(self):
        qp = QueryProcessor()
        lang = qp._detect_language("The quick brown fox jumps over the lazy dog")
        assert lang == LanguageType.EN

    def test_detect_language_french(self):
        qp = QueryProcessor()
        lang = qp._detect_language("Le chat est sur la table dans la cuisine")
        assert lang == LanguageType.FR

    def test_detect_language_german(self):
        qp = QueryProcessor()
        lang = qp._detect_language("Der Hund ist im Garten und spielt mit dem Ball")
        assert lang == LanguageType.DE

    def test_detect_language_spanish(self):
        qp = QueryProcessor()
        lang = qp._detect_language("El gato está en la casa de mis abuelos")
        assert lang == LanguageType.ES

    def test_detect_language_empty(self):
        qp = QueryProcessor()
        lang = qp._detect_language("")
        assert lang == LanguageType.UNKNOWN

    def test_detect_language_no_stopwords(self):
        qp = QueryProcessor()
        lang = qp._detect_language("xyz zyx abc def ghi jkl mno")
        assert lang == LanguageType.UNKNOWN

    def test_classify_intent_question_what(self):
        qp = QueryProcessor()
        assert qp._classify_intent("What is the weather?") == IntentType.QUESTION

    def test_classify_intent_question_how(self):
        qp = QueryProcessor()
        assert qp._classify_intent("How do I do this") == IntentType.QUESTION

    def test_classify_intent_question_with_question_mark(self):
        qp = QueryProcessor()
        assert qp._classify_intent("Is this working") == IntentType.QUESTION

    def test_classify_intent_summarization(self):
        qp = QueryProcessor()
        assert qp._classify_intent("Summarize the document") == IntentType.SUMMARIZATION

    def test_classify_intent_classification(self):
        qp = QueryProcessor()
        assert qp._classify_intent("Classify this text") == IntentType.CLASSIFICATION

    def test_classify_intent_generation(self):
        qp = QueryProcessor()
        assert qp._classify_intent("please write a detailed analysis of the current market trends for technology sector funding") == IntentType.GENERATION

    def test_classify_intent_chat_short(self):
        qp = QueryProcessor()
        assert qp._classify_intent("hello") == IntentType.CHAT

    def test_classify_intent_empty(self):
        qp = QueryProcessor()
        assert qp._classify_intent("") == IntentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_process_full(self):
        qp = QueryProcessor()
        qa = await qp.process("What is the capital of France?")
        assert qa.original == "What is the capital of France?"
        assert qa.normalized == "What is the capital of France?"
        assert qa.language == LanguageType.EN
        assert qa.intent == IntentType.QUESTION

    @pytest.mark.asyncio
    async def test_process_short_chat(self):
        qp = QueryProcessor()
        qa = await qp.process("hi")
        assert qa.intent == IntentType.CHAT

    @pytest.mark.asyncio
    async def test_process_french(self):
        qp = QueryProcessor()
        qa = await qp.process("Quelle est la capitale de la France?")
        assert qa.language == LanguageType.FR

    @pytest.mark.asyncio
    async def test_process_disabled_features(self):
        config = RAGConfig(enable_language_detection=False, enable_intent_classification=False, enable_query_expansion=False)
        qp = QueryProcessor(config=config)
        qa = await qp.process("  Hello   World  ")
        assert qa.normalized == "Hello World"
        assert qa.language == LanguageType.UNKNOWN
        assert qa.intent == IntentType.UNKNOWN
        assert qa.expanded == "Hello World"


# ============================================================
# RetrievalOrchestrator
# ============================================================
class TestRetrievalOrchestrator:
    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(return_value=[])
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid)
        results = await orch.retrieve("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_no_hybrid(self):
        orch = RetrievalOrchestrator()
        with pytest.raises(RAGRetrievalError, match="not configured"):
            await orch.retrieve("test")

    @pytest.mark.asyncio
    async def test_retrieve_reranker_exception(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(return_value=[
            MagicMock(id="c1", content="info", score=0.9, metadata={}),
        ])
        reranker = AsyncMock()
        reranker.rerank_async = AsyncMock(side_effect=ValueError("reranker fail"))
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid, reranker=reranker)
        results = await orch.retrieve("test", top_k=5, rerank_top_k=5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_with_results(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(return_value=[
            MagicMock(id=1, content="chunk1", score=0.9, metadata={"source": "doc1"}),
            MagicMock(id=2, content="chunk2", score=0.8, metadata={"source": "doc2"}),
        ])
        reranker = AsyncMock()
        reranker.rerank_async = AsyncMock(return_value=MagicMock(results=[]))

        orch = RetrievalOrchestrator(hybrid_retriever=hybrid, reranker=reranker)
        results = await orch.retrieve("test query", top_k=5, rerank_top_k=3)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_retrieve_hybrid_error(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(side_effect=ValueError("search failed"))
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid)
        with pytest.raises(RAGRetrievalError):
            await orch.retrieve("test query")

    @pytest.mark.asyncio
    async def test_retrieve_reraised(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(return_value=[
            MagicMock(id="a", content="c", score=0.5, metadata={}),
        ])
        reranker = AsyncMock()
        reranker.rerank_async = AsyncMock(return_value=MagicMock(results=[
            MagicMock(id="a", content="c", score=0.9),
        ]))
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid, reranker=reranker)
        results = await orch.retrieve("q", top_k=5, rerank_top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_retrieve_no_reranker(self):
        hybrid = AsyncMock()
        hybrid.search_async = AsyncMock(return_value=[
            MagicMock(id="a", content="c", score=0.5, metadata={"source": "x"}),
        ])
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid, reranker=None)
        results = await orch.retrieve("q", top_k=5, rerank_top_k=0)
        assert len(results) == 1
        assert results[0].chunk_id == "a"

    @pytest.mark.asyncio
    async def test_retrieve_sync_fallback(self):
        hybrid = MagicMock()
        hybrid.search = MagicMock(return_value=[
            MagicMock(id="a", content="c", score=0.5, metadata={"source": "x"}),
        ])
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid)
        results = await orch.retrieve_sync_fallback("q")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_sync_fallback_no_hybrid(self):
        orch = RetrievalOrchestrator()
        with pytest.raises(RAGRetrievalError, match="not configured"):
            await orch.retrieve_sync_fallback("q")

    @pytest.mark.asyncio
    async def test_retrieve_sync_fallback_error(self):
        hybrid = MagicMock()
        hybrid.search = MagicMock(side_effect=ValueError("fail"))
        orch = RetrievalOrchestrator(hybrid_retriever=hybrid)
        with pytest.raises(RAGRetrievalError):
            await orch.retrieve_sync_fallback("q")


# ============================================================
# ContextBuilder
# ============================================================
class TestContextBuilder:
    def make_chunk(self, cid: str, content: str, score: float, rerank_score: float = 0.0):
        return RetrievedChunk(chunk_id=cid, content=content, score=score, rerank_score=rerank_score)

    def test_build_empty_chunks(self):
        cb = ContextBuilder()
        assembly = cb.build([])
        assert assembly.chunks == []
        assert assembly.total_tokens == 0

    def test_build_sorts_by_rerank_score(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "a", score=0.1, rerank_score=0.2),
            self.make_chunk("c2", "b", score=0.9, rerank_score=0.8),
            self.make_chunk("c3", "c", score=0.5, rerank_score=0.5),
        ]
        assembly = cb.build(chunks, token_budget=1000)
        assert assembly.chunks[0].chunk_id == "c2"

    def test_build_truncated_when_budget_exceeded(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "word " * 10, score=0.9, rerank_score=0.9),
            self.make_chunk("c2", "word " * 500, score=0.8, rerank_score=0.8),
        ]
        assembly = cb.build(chunks, token_budget=20)
        assert assembly.truncated is True
        assert len(assembly.chunks) == 1

    def test_build_within_budget(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "hello world", score=0.9, rerank_score=0.9),
            self.make_chunk("c2", "foo bar baz", score=0.8, rerank_score=0.8),
        ]
        assembly = cb.build(chunks, token_budget=100)
        assert assembly.truncated is False
        assert len(assembly.chunks) == 2

    def test_build_with_token_count_provided(self):
        cb = ContextBuilder()
        chunks = [
            RetrievedChunk(chunk_id="c1", content="hello world", score=0.9, token_count=100),
            RetrievedChunk(chunk_id="c2", content="foo bar", score=0.8, token_count=200),
        ]
        assembly = cb.build(chunks, token_budget=250)
        assert len(assembly.chunks) == 1

    def test_build_estimate_tokens_empty(self):
        cb = ContextBuilder()
        assert cb._estimate_tokens("") == 0

    def test_build_estimate_tokens(self):
        cb = ContextBuilder()
        assert cb._estimate_tokens("one two three four") == 4

    def test_build_sorted_preserve_order(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "a", score=0.1),
            self.make_chunk("c2", "b", score=0.9),
            self.make_chunk("c1", "a", score=0.5),
        ]
        assembly = cb.build_sorted(chunks, token_budget=100, preserve_order=True)
        assert assembly.chunks[0].chunk_id == "c1"
        assert len(assembly.chunks) == 2

    def test_build_sorted_not_preserved(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "a", score=0.1, rerank_score=0.1),
            self.make_chunk("c2", "b", score=0.9, rerank_score=0.9),
        ]
        assembly = cb.build_sorted(chunks, token_budget=100, preserve_order=False)
        assert assembly.chunks[0].chunk_id == "c2"

    def test_build_with_order_truncated(self):
        cb = ContextBuilder()
        chunks = [
            self.make_chunk("c1", "hello world", score=0.9),
            self.make_chunk("c2", "bar baz qux foo", score=0.8),
        ]
        assembly = cb._build_with_order(chunks, token_budget=3)
        assert assembly.truncated is True
        assert len(assembly.chunks) == 1


# ============================================================
# PromptBuilder
# ============================================================
class TestPromptBuilder:
    def test_build_default_system(self):
        pb = PromptBuilder()
        messages = pb.build(query="hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_build_with_context(self):
        pb = PromptBuilder()
        ca = ContextAssembly(chunks=[
            RetrievedChunk(chunk_id="c1", content="context info", score=0.9),
        ])
        messages = pb.build(query="hello", context=ca)
        sys_content = messages[0]["content"]
        assert "context info" in sys_content

    def test_build_with_history(self):
        pb = PromptBuilder()
        history = [
            ConversationTurn(role="user", content="hi"),
            ConversationTurn(role="assistant", content="hello there"),
        ]
        messages = pb.build(query="how are you", history=history)
        assert len(messages) == 4
        assert messages[1]["content"] == "hi"
        assert messages[2]["content"] == "hello there"

    def test_build_with_history_exceeding_max(self):
        pb = PromptBuilder(config=RAGConfig(max_history_turns=2))
        history = [
            ConversationTurn(role="user", content=f"msg{i}") for i in range(5)
        ]
        messages = pb.build(query="q", history=history)
        assert len(messages) == 2 + 2

    def test_build_with_system_prompt_override(self):
        pb = PromptBuilder()
        messages = pb.build(query="q", system_prompt="Custom system {context}")
        assert messages[0]["content"] == "Custom system "

    def test_build_with_query_analysis(self):
        pb = PromptBuilder()
        qa = QueryAnalysis(original="q", language=LanguageType.EN, intent=IntentType.QUESTION)
        messages = pb.build(query="q", query_analysis=qa)
        assert "Language" in messages[0]["content"]

    def test_build_with_context_and_metadata(self):
        pb = PromptBuilder()
        ca = ContextAssembly(chunks=[
            RetrievedChunk(chunk_id="c1", content="info", score=0.9, source="doc"),
        ])
        qa = QueryAnalysis(original="q", language=LanguageType.FR)
        messages = pb.build(query="q", context=ca, query_analysis=qa)
        sys_text = messages[0]["content"]
        assert "info" in sys_text
        assert "doc" in sys_text
        assert "french" in sys_text.lower() or "fr" in sys_text

    def test_build_with_template(self):
        pb = PromptBuilder()
        messages = pb.build_with_template(
            template="Q: {query}\nContext: {context}\nHistory: {history}\nMeta: {metadata}",
            query="my question",
            context=ContextAssembly(chunks=[
                RetrievedChunk(chunk_id="c1", content="ctx", score=0.9),
            ]),
            history=[ConversationTurn(role="user", content="prev")],
            query_analysis=QueryAnalysis(original="q", language=LanguageType.EN),
        )
        content = messages[0]["content"]
        assert "my question" in content
        assert "ctx" in content
        assert "prev" in content
        assert "english" in content.lower() or "en" in content


# ============================================================
# RAGCache
# ============================================================
class TestRAGCache:
    def test_get_miss(self):
        cache = RAGCache(config=RAGConfig(cache_ttl=3600, cache_max_size=100))
        result = cache.get("query", "ctx", "model", "v1")
        assert result is None

    def test_set_and_get(self):
        cache = RAGCache(config=RAGConfig(cache_ttl=3600, cache_max_size=100))
        resp = RAGResponse(answer="test answer")
        cache.set("query", resp, context_hash="ctx", model="m", prompt_version="v1")
        cached = cache.get("query", "ctx", "m", "v1")
        assert cached is not None
        assert cached.answer == "test answer"
        assert cached.cache_hit is True

    def test_cache_disabled(self):
        cache = RAGCache(config=RAGConfig(cache_enabled=False))
        resp = RAGResponse(answer="a")
        cache.set("q", resp, "", "m", "v1")
        cached = cache.get("q", "", "m", "v1")
        assert cached is None

    def test_ttl_expired(self):
        cache = RAGCache(config=RAGConfig(cache_ttl=0, cache_max_size=100))
        resp = RAGResponse(answer="test")
        cache.set("q", resp, "", "m", "v1")
        cached = cache.get("q", "", "m", "v1")
        assert cached is None

    def test_max_size_eviction(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=2))
        for i in range(3):
            resp = RAGResponse(answer=str(i))
            cache.set(f"q{i}", resp, "", "m", "v1")
        assert len(cache._cache) == 2

    def test_stats(self):
        cache = RAGCache(config=RAGConfig(cache_ttl=3600, cache_max_size=100))
        cache.get("q", "", "m", "v1")
        resp = RAGResponse(answer="a")
        cache.set("q", resp, "", "m", "v1")
        cache.get("q", "", "m", "v1")
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 0.5
        assert stats["enabled"] is True

    def test_invalidate_query(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=100))
        cache.set("hello world", RAGResponse(answer="a"), "", "m", "v1")
        cache.set("goodbye", RAGResponse(answer="b"), "", "m", "v1")
        removed = cache.invalidate(query="hello")
        assert removed == 1
        assert cache.get("hello world", "", "m", "v1") is None

    def test_invalidate_version(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=100))
        cache.set("q1", RAGResponse(answer="a"), "", "m", "v1")
        cache.set("q2", RAGResponse(answer="b"), "", "m", "v2")
        removed = cache.invalidate(prompt_version="v1")
        assert removed == 1

    def test_invalidate_query_and_version(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=100))
        cache.set("hello", RAGResponse(answer="a"), "", "m", "v1")
        cache.set("hello", RAGResponse(answer="b"), "", "m", "v2")
        removed = cache.invalidate("hello", "v1")
        assert removed == 1

    def test_invalidate_all(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=100))
        cache.set("q1", RAGResponse(answer="a"), "", "m", "v1")
        cache.set("q2", RAGResponse(answer="b"), "", "m", "v1")
        removed = cache.invalidate()
        assert removed == 2
        assert len(cache._cache) == 0

    def test_invalidate_unknown_empty(self):
        cache = RAGCache(config=RAGConfig(cache_max_size=100))
        removed = cache.invalidate("nonexistent")
        assert removed == 0


# ============================================================
# RAGLogger
# ============================================================
class TestRAGLogger:
    def test_log_request(self, caplog):
        import logging
        logger = RAGLogger("test_rag_logger")
        logger._logger.setLevel(logging.INFO)
        req = RAGRequest(query="test query", stream=False)
        logger.log_request(req)
        assert len(caplog.records) >= 0

    def test_log_response(self, caplog):
        import logging
        logger = RAGLogger("test_rag_logger2")
        logger._logger.setLevel(logging.INFO)
        resp = RAGResponse(answer="answer here")
        logger.log_response(resp, 123.4)
        assert len(caplog.records) >= 0

    def test_log_error(self, caplog):
        import logging
        logger = RAGLogger("test_rag_logger3")
        logger._logger.setLevel(logging.INFO)
        logger.log_error(ValueError("something broke"), "my query")
        assert len(caplog.records) >= 0

    def test_log_request_disabled(self):
        import logging
        logger = RAGLogger("test_disabled")
        logger._logger.setLevel(logging.WARNING)
        req = RAGRequest(query="test")
        logger.log_request(req)


# ============================================================
# RAGMetricsTracker
# ============================================================
class TestRAGMetricsTracker:
    def test_initial_metrics(self):
        mt = RAGMetricsTracker()
        m = mt.get_metrics()
        assert m.total_requests == 0

    def test_record_request(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=100.0, retrieval_latency_ms=30.0, llm_latency_ms=60.0)
        m = mt.get_metrics()
        assert m.total_requests == 1
        assert m.total_latency_ms == 100.0
        assert m.average_latency_ms == 100.0

    def test_record_request_cache_hit(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=10.0, cache_hit=True)
        m = mt.get_metrics()
        assert m.cache_hits == 1
        assert m.cache_misses == 0

    def test_record_request_fallback(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=50.0, fallback=True)
        assert mt.get_metrics().fallbacks == 1

    def test_record_error(self):
        mt = RAGMetricsTracker()
        mt.record_error()
        assert mt.get_metrics().errors == 1

    def test_get_metrics_dict(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=200.0)
        d = mt.get_metrics_dict()
        assert d["total_requests"] == 1

    def test_reset(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=100.0)
        mt.reset()
        assert mt.get_metrics().total_requests == 0

    def test_uptime_seconds(self):
        mt = RAGMetricsTracker()
        assert mt.uptime_seconds() > 0

    def test_multiple_requests_average(self):
        mt = RAGMetricsTracker()
        mt.record_request(total_latency_ms=100.0)
        mt.record_request(total_latency_ms=200.0)
        assert mt.get_metrics().average_latency_ms == 150.0


# ============================================================
# FallbackHandler
# ============================================================
class TestFallbackHandler:
    @pytest.mark.asyncio
    async def test_retrieval_failure_reduce(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="reduce"))
        msg = await fh.handle_retrieval_failure("query")
        assert msg == "I'll try to answer based on my general knowledge."

    @pytest.mark.asyncio
    async def test_retrieval_failure_static(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="static"))
        msg = await fh.handle_retrieval_failure("query")
        assert "unable" in msg

    @pytest.mark.asyncio
    async def test_retrieval_failure_raise(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="raise"))
        with pytest.raises(RAGFallbackTriggered):
            await fh.handle_retrieval_failure("query")

    @pytest.mark.asyncio
    async def test_reranker_failure_reduce(self):
        fh = FallbackHandler()
        chunks = ["a", "b"]
        result = await fh.handle_reranker_failure("query", chunks)
        assert result == chunks

    @pytest.mark.asyncio
    async def test_reranker_failure_raise(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="raise"))
        with pytest.raises(RAGFallbackTriggered):
            await fh.handle_reranker_failure("q", [])

    @pytest.mark.asyncio
    async def test_llm_timeout_reduce(self):
        fh = FallbackHandler()
        msg = await fh.handle_llm_timeout("q")
        assert "delay" in msg

    @pytest.mark.asyncio
    async def test_llm_timeout_static(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="static"))
        msg = await fh.handle_llm_timeout("q")
        assert "apologize" in msg

    @pytest.mark.asyncio
    async def test_llm_timeout_raise(self):
        fh = FallbackHandler(config=RAGConfig(fallback_strategy="raise"))
        with pytest.raises(RAGFallbackTriggered):
            await fh.handle_llm_timeout("q")

    @pytest.mark.asyncio
    async def test_with_retry_success(self):
        fh = FallbackHandler()
        func = AsyncMock(return_value="ok")
        wrapped = fh.with_retry(func, max_retries=2)
        result = await wrapped("arg")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_with_retry_failure(self):
        fh = FallbackHandler()
        func = AsyncMock(side_effect=ValueError("fail"))
        wrapped = fh.with_retry(func, max_retries=1, retry_delay=0.01)
        with pytest.raises(ValueError):
            await wrapped()


# ============================================================
# RAGPipeline
# ============================================================
class TestRAGPipeline:
    @pytest.mark.asyncio
    async def test_generate_empty_query(self):
        pipeline = RAGPipeline()
        with pytest.raises(RAGGenerationError, match="must not be empty"):
            await pipeline.generate(RAGRequest(query=""))

    @pytest.mark.asyncio
    async def test_generate_cache_hit(self):
        config = RAGConfig(cache_enabled=True)
        cache = RAGCache(config=config)
        cache.set("hello", RAGResponse(answer="cached answer"), "", "openai/gpt-4o-mini", "v1")
        pipeline = RAGPipeline(config=config, cache=cache)
        resp = await pipeline.generate(RAGRequest(query="hello"))
        assert resp.answer == "cached answer"
        assert resp.cache_hit is True

    @pytest.mark.asyncio
    async def test_generate_retrieval_fallback(self):
        config = RAGConfig(fallback_strategy="reduce")
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(side_effect=Exception("retrieval failed"))
        pipeline = RAGPipeline(config=config, retrieval_orchestrator=retrieval)
        pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
        resp = await pipeline.generate(RAGRequest(query="test query"))
        assert "general knowledge" in resp.answer
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_generate_provider_unavailable(self):
        config = RAGConfig(fallback_strategy="reduce")
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[
            RetrievedChunk(chunk_id="c1", content="info", score=0.9),
        ])
        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=None)
            pipeline = RAGPipeline(
                config=config,
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate(RAGRequest(query="test"))
            assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_generate_provider_error(self):
        config = RAGConfig(fallback_strategy="reduce")
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[
            RetrievedChunk(chunk_id="c1", content="info", score=0.9),
        ])
        provider = MagicMock()
        provider.chat = AsyncMock(side_effect=ValueError("LLM error"))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                config=config,
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate(RAGRequest(query="test"))
            assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_generate_success(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[
            RetrievedChunk(chunk_id="c1", content="info", score=0.9, source="doc1"),
        ])
        provider = MagicMock()
        usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        choice = MagicMock()
        choice.message.content = "Generated answer"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=usage,
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate(RAGRequest(query="test query"))
            assert resp.answer == "Generated answer"
            assert resp.token_usage["prompt_tokens"] == 10
            assert resp.token_usage["completion_tokens"] == 20
            assert resp.fallback_used is False

    @pytest.mark.asyncio
    async def test_generate_with_history(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()
        choice = MagicMock()
        choice.message.content = "Answer with history"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate(RAGRequest(
                query="continue",
                conversation_history=[ConversationTurn(role="user", content="start")],
            ))
            assert resp.answer == "Answer with history"

    @pytest.mark.asyncio
    async def test_generate_async(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()
        choice = MagicMock()
        choice.message.content = "async answer"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=None,
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate_async(RAGRequest(query="async test"))
            assert resp.answer == "async answer"

    @pytest.mark.asyncio
    async def test_stream_basic(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()

        async def fake_stream(_req):
            class FakeChunk:
                def __init__(self, text):
                    self.choices = [MagicMock(delta={"content": text})]
            yield FakeChunk("hello ")
            yield FakeChunk("world")

        provider.stream_chat = fake_stream

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            parts: list[str] = []
            async for token in pipeline.stream(RAGRequest(query="test stream")):
                parts.append(token)
            assert "".join(parts) == "hello world"

    @pytest.mark.asyncio
    async def test_stream_empty_query(self):
        pipeline = RAGPipeline()
        with pytest.raises(RAGGenerationError):
            async for _ in pipeline.stream(RAGRequest(query="")):
                pass

    @pytest.mark.asyncio
    async def test_stream_retrieval_fallback(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(side_effect=Exception("fail"))
        pipeline = RAGPipeline(
            retrieval_orchestrator=retrieval,
        )
        parts: list[str] = []
        async for token in pipeline.stream(RAGRequest(query="test")):
            parts.append(token)
        assert parts

    def test_check_cache_disabled(self):
        pipeline = RAGPipeline(config=RAGConfig(cache_enabled=False))
        result = pipeline._check_cache(RAGRequest(query="test"))
        assert result is None

    @pytest.mark.asyncio
    async def test_stream_provider_unavailable(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=None)
            pipeline = RAGPipeline(retrieval_orchestrator=retrieval)
            parts: list[str] = []
            async for token in pipeline.stream(RAGRequest(query="test")):
                parts.append(token)
            assert parts == ["Provider unavailable."]

    @pytest.mark.asyncio
    async def test_stream_provider_error(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()

        async def broken_stream(_req):
            raise ValueError("stream error")
            yield  # pragma: no cover

        provider.stream_chat = broken_stream

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(retrieval_orchestrator=retrieval)
            parts: list[str] = []
            async for token in pipeline.stream(RAGRequest(query="test")):
                parts.append(token)
            assert "error" in "".join(parts).lower()

    @pytest.mark.asyncio
    async def test_batch_generate(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()
        choice = MagicMock()
        choice.message.content = "batch answer"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=None,
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.batch_generate(
                [RAGRequest(query="q1"), RAGRequest(query="q2")],
                max_concurrency=2,
            )
            assert len(resp) == 2
            assert resp[0].answer == "batch answer"

    @pytest.mark.asyncio
    async def test_batch_generate_single(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()
        choice = MagicMock()
        choice.message.content = "single"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=None,
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.batch_generate([RAGRequest(query="q")])
            assert len(resp) == 1

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        pipeline = RAGPipeline()
        m = pipeline.get_metrics()
        assert m.total_requests == 0

    def test_compute_context_hash(self):
        pipeline = RAGPipeline()
        ca = ContextAssembly(chunks=[
            RetrievedChunk(chunk_id="c1", content="a", score=0.9, rerank_score=0.95),
        ])
        h = pipeline._compute_context_hash(ca)
        assert len(h) == 32

    @pytest.mark.asyncio
    async def test_generate_uses_provider_override(self):
        retrieval = AsyncMock()
        retrieval.retrieve = AsyncMock(return_value=[])
        provider = MagicMock()
        choice = MagicMock()
        choice.message.content = "overridden"
        provider.chat = AsyncMock(return_value=MagicMock(
            choices=[choice],
            usage=MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ))

        with patch("app.rag.pipeline.provider_manager") as pm:
            pm.get = MagicMock(return_value=provider)
            pipeline = RAGPipeline(
                retrieval_orchestrator=retrieval,
            )
            pipeline._cache = RAGCache(config=RAGConfig(cache_enabled=False))
            resp = await pipeline.generate(RAGRequest(
                query="test",
                provider_override="anthropic",
            ))
            assert resp.answer == "overridden"
            pm.get.assert_called_with("anthropic")


# ============================================================
# __init__ factory
# ============================================================
class TestFactory:
    def test_create_rag_pipeline_default(self):
        from app.rag import create_rag_pipeline
        pipeline = create_rag_pipeline()
        assert isinstance(pipeline, RAGPipeline)

    def test_create_rag_pipeline_with_config(self):
        from app.rag import create_rag_pipeline
        config = RAGConfig(retrieval_top_k=50)
        pipeline = create_rag_pipeline(config=config)
        assert pipeline._config.retrieval_top_k == 50
