from __future__ import annotations

import pytest

from app.mcp_integration import (
    MCPCitationResolver,
    MCPIntegrationConfig,
    MCPIntegrationCoordinator,
    MCPMemoryAdapter,
    MCPRetriever,
    create_mcp_citation_resolver,
    create_mcp_integration,
    create_mcp_memory_adapter,
    create_mcp_retriever,
)
from app.mcp_integration.exceptions import (
    MCPCitationResolverError,
    MCPIntegrationCoordinatorError,
    MCPMemoryAdapterError,
    MCPRetrieverError,
)
from app.mcp_integration.models import (
    MCPIntegrationMetrics,
    MCPRAGIntegrationResult,
    MCPRetrievalResult,
)


class FakeResource:
    def __init__(self, uri, text, mime_type="text/plain"):
        self.uri = uri
        self.text = text
        self.mime_type = mime_type


class FakeMCPClient:
    def __init__(self, chunks=None, resources=None, memories=None):
        self.connected = False
        self.chunks = chunks or []
        self.resources = resources or []
        self.memories = memories or {}
        self.tool_calls = []
        self.resource_reads = []
        self.connect_count = 0
        self.disconnect_count = 0
        self.fail_tools = set()
        self.error_content = False

    async def connect(self):
        self.connected = True
        self.connect_count += 1

    async def disconnect(self):
        self.connected = False
        self.disconnect_count += 1

    def _tool_call(self, name, arguments):
        if name in self.fail_tools:
            raise RuntimeError(f"tool {name} exploded")
        if self.error_content:
            return FakeCallResult(
                content=[{"text": "boom"}],
                is_error=True,
                structured_content=None,
            )
        if name == "search_knowledge":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            scored = sorted(
                self.chunks,
                key=lambda c: sum(1 for t in query.lower().split() if t in c["content"].lower()),
                reverse=True,
            )
            return FakeCallResult(
                content=[],
                is_error=False,
                structured_content={"results": scored[:limit]},
            )
        if name == "memory_save":
            item = {
                "id": f"m{len(self.memories) + 1}",
                "content": arguments.get("content", ""),
                "memory_type": arguments.get("memory_type", "short_term"),
                "category": arguments.get("category", "general"),
                "importance": 0.5,
                "confidence": 1.0,
                "metadata": arguments.get("metadata", {}),
            }
            self.memories[item["id"]] = item
            return FakeCallResult(
                content=[],
                is_error=False,
                structured_content={"item": item},
            )
        if name == "memory_search":
            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            items = list(self.memories.values())
            if query:
                items = [
                    i
                    for i in items
                    if query.lower() in i["content"].lower() or not i["content"]
                ]
            return FakeCallResult(
                content=[],
                is_error=False,
                structured_content={"items": items[:top_k]},
            )
        if name == "memory_delete":
            item_id = arguments.get("id")
            self.memories.pop(item_id, None)
            return FakeCallResult(content=[], is_error=False, structured_content={})
        raise RuntimeError(f"unknown tool {name}")

    async def call_tool(self, name, arguments=None, timeout=None):
        self.tool_calls.append((name, arguments))
        return self._tool_call(name, arguments or {})

    async def list_resources(self):
        return self.resources

    async def read_resource(self, uri):
        self.resource_reads.append(uri)
        for r in self.resources:
            if r.uri == uri:
                return r
        raise RuntimeError(f"missing resource {uri}")


class FakeCallResult:
    def __init__(self, content, is_error=False, structured_content=None):
        self.content = content
        self.is_error = is_error
        self.structured_content = structured_content


class FakeCitationEngine:
    def __init__(self, fail=False, verified=True):
        self.fail = fail
        self.verified = verified
        self.calls = []

    async def generate_async(self, text, sources, citation_format):
        self.calls.append((text, sources, citation_format))
        if self.fail:
            raise RuntimeError("engine exploded")

        class _Source:
            def __init__(self, s):
                self.s = s

            def to_dict(self):
                return dict(self.s)

        class _Result:
            def __init__(self, text, sources, verified):
                self.text = text
                self.rendered = text + " [1]"
                self.format = "numeric"
                self.sources = [_Source(s) for s in sources]
                self.mappings = []
                self.confidence = 1.0
                self.references = []
                self.errors = []
                self.warnings = []
                self.verified = verified

        return _Result(text, sources, self.verified)


class FakeGenerator:
    def __init__(self, answer="generated answer"):
        self.answer = answer
        self.calls = []

    async def __call__(self, query, context, chunks):
        self.calls.append((query, context, chunks))
        return self.answer


def make_client(**kwargs):
    return FakeMCPClient(**kwargs)


def make_config(**kwargs):
    defaults = {"log_events": False, "track_metrics": True}
    defaults.update(kwargs)
    return MCPIntegrationConfig(**defaults)


@pytest.fixture
def client():
    return make_client(
        chunks=[
            {
                "id": "c1",
                "content": "Gold prices reached an all-time high in 2026.",
                "score": 0.9,
                "metadata": {"source": "market"},
            },
            {
                "id": "c2",
                "content": "Interest rates affect gold demand.",
                "score": 0.7,
                "metadata": {"source": "market"},
            },
        ],
        resources=[
            FakeResource("mcp://notes/1", "Trading strategy notes for gold."),
            FakeResource("mcp://other/1", "Unrelated cooking recipes."),
        ],
    )


@pytest.fixture
def config():
    return make_config()


def test_retriever_search_async(client, config):
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_async("gold prices", top_k=1))
    assert len(results) == 1
    assert results[0].id == "c1"
    assert "Gold prices" in results[0].content
    assert results[0].score == 0.9
    assert client.connect_count == 1
    assert client.tool_calls[0][0] == "search_knowledge"
    assert client.tool_calls[0][1] == {"query": "gold prices", "limit": 1}


def test_retriever_search_async_no_content(client, config):
    client.chunks = []
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_async("gold", top_k=10))
    assert results == []


def test_retriever_search_async_tool_error(client, config):
    client.fail_tools.add("search_knowledge")
    retriever = MCPRetriever(client, config)
    with pytest.raises(MCPRetrieverError):
        asyncio_run(retriever.search_async("gold", top_k=5))


def test_retriever_search_async_tool_error_content(client, config):
    client.error_content = True
    retriever = MCPRetriever(client, config)
    with pytest.raises(MCPRetrieverError):
        asyncio_run(retriever.search_async("gold", top_k=5))


def test_retriever_parse_structured_and_content_blocks(client, config):
    client.chunks = []
    client._tool_call = lambda name, args: FakeCallResult(
        content=[
            {"text": "first block", "score": 0.8},
            "second block",
            {"content": "third block", "id": "c3", "rerank_score": 0.6},
        ],
        is_error=False,
        structured_content=None,
    )
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_async("gold", top_k=5))
    assert [r.content for r in results] == ["first block", "second block", "third block"]
    assert results[0].score == 0.8
    assert results[1].score == 0.5
    assert results[2].id == "c3"
    assert results[2].score == 0.6


def test_retriever_search_resources_async(client, config):
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_resources_async("trading strategy", top_k=5))
    assert len(results) == 2
    assert results[0].id == "mcp://notes/1"
    assert results[0].score > results[1].score
    assert results[1].id == "mcp://other/1"
    assert client.resource_reads == ["mcp://notes/1", "mcp://other/1"]


def test_retriever_search_resources_prefix_filter(client, config):
    config.resource_prefix = "mcp://notes"
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_resources_async("trading", top_k=5))
    assert [r.id for r in results] == ["mcp://notes/1"]


def test_retriever_search_resources_async_raises_on_list_error(client, config):
    async def boom():
        raise RuntimeError("list failed")

    client.list_resources = boom
    retriever = MCPRetriever(client, config)
    with pytest.raises(MCPRetrieverError):
        asyncio_run(retriever.search_resources_async("gold", top_k=5))


def test_retriever_search_sync_requires_cache(config):
    client = make_client()
    retriever = MCPRetriever(client, config)
    with pytest.raises(MCPRetrieverError):
        retriever.search("gold", top_k=5)


def test_retriever_search_sync_with_cache(config):
    client = make_client()
    retriever = MCPRetriever(client, config)
    retriever.cache_resources(
        [
            {"id": "r1", "content": "gold market overview", "metadata": {}},
            {"id": "r2", "content": "silver overview", "metadata": {}},
            {"id": "r3", "content": "", "metadata": {}},
        ]
    )
    results = retriever.search("gold market", top_k=5)
    assert [r.id for r in results] == ["r1", "r2"]
    assert results[0].score > 0
    assert results[1].score == 0


def test_retriever_not_connected_raises(config):
    class NoConnect:
        connected = False

    retriever = MCPRetriever(NoConnect(), config)
    with pytest.raises(MCPRetrieverError):
        asyncio_run(retriever.search_async("gold", top_k=5))


def test_retriever_config_property(config):
    client = make_client()
    retriever = MCPRetriever(client, config)
    assert retriever.config is config


def test_retriever_structured_items_skip_junk(config):
    client = make_client()
    client._tool_call = lambda name, args: FakeCallResult(
        content=[],
        is_error=False,
        structured_content={"results": ["junk", {"id": "c1", "content": "ok", "score": 0.4}, {"id": "c2", "content": 123}]},
    )
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_async("gold", top_k=5))
    assert [r.id for r in results] == ["c1"]
    assert results[0].score == 0.4


def test_retriever_score_text_no_tokens(config):
    client = make_client()
    retriever = MCPRetriever(client, config)
    assert retriever._score_text("a b", "gold market") == 0.0
    assert retriever._score_text("", "gold market") == 0.0
    assert retriever._score_text("gold", "GOLD MARKET") == 1.0


def test_retriever_search_resources_skips_broken(config):
    client = make_client(
        resources=[
            FakeResource("mcp://notes/1", "trading strategy gold"),
            FakeResource("mcp://notes/2", None),
            FakeResource("mcp://notes/3", "gold scalping plan"),
        ]
    )
    async def broken_read(uri):
        if uri == "mcp://notes/1":
            raise RuntimeError("read failed")
        for r in client.resources:
            if r.uri == uri:
                return r
        raise RuntimeError(f"missing resource {uri}")

    client.read_resource = broken_read
    retriever = MCPRetriever(client, config)
    results = asyncio_run(retriever.search_resources_async("trading", top_k=5))
    assert [r.id for r in results] == ["mcp://notes/3"]


def test_memory_store(client, config):
    adapter = MCPMemoryAdapter(client, config)
    item = asyncio_run(
        adapter.store("remember the trade", category="trades", metadata={"k": "v"})
    )
    assert item["id"] == "m1"
    assert item["content"] == "remember the trade"
    assert item["category"] == "trades"
    assert item["metadata"] == {"k": "v"}
    assert client.memories["m1"]["content"] == "remember the trade"


def test_memory_store_with_scope(client, config):
    adapter = MCPMemoryAdapter(client, config)
    asyncio_run(adapter.store("hello", scope={"user_id": "u1"}))
    assert client.tool_calls[-1][1]["scope"] == {"user_id": "u1"}


def test_memory_store_error(client, config):
    client.fail_tools.add("memory_save")
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.store("hello"))


def test_memory_store_error_content(client, config):
    client.error_content = True
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.store("hello"))


def test_memory_store_fallback_item(client, config):
    client.memories = None  # force non-dict handling
    client._tool_call = lambda name, args: FakeCallResult(
        content=[{"text": "fallback text"}],
        is_error=False,
        structured_content=None,
    )
    adapter = MCPMemoryAdapter(client, config)
    item = asyncio_run(adapter.store("hello"))
    assert item["content"] == "hello"
    assert item["id"] == ""


def test_memory_search(client, config):
    client.memories = {
        "m1": {
            "id": "m1",
            "content": "user prefers gold scalping",
            "memory_type": "long_term",
            "category": "preference",
            "importance": 0.8,
            "confidence": 1.0,
            "metadata": {},
        },
        "m2": {
            "id": "m2",
            "content": "user dislikes silver",
            "memory_type": "short_term",
            "category": "general",
            "importance": 0.3,
            "confidence": 1.0,
            "metadata": {},
        },
    }
    adapter = MCPMemoryAdapter(client, config)
    items = asyncio_run(adapter.search("gold", top_k=5))
    assert len(items) == 1
    assert items[0]["id"] == "m1"
    assert items[0]["memory_type"] == "long_term"
    assert items[0]["importance"] == 0.8


def test_memory_retrieve_no_query(client, config):
    client.memories = {
        "m1": {
            "id": "m1",
            "content": "anything",
            "memory_type": "short_term",
            "category": "general",
            "importance": 0.5,
            "confidence": 1.0,
            "metadata": {},
        }
    }
    adapter = MCPMemoryAdapter(client, config)
    items = asyncio_run(adapter.retrieve(scope={"session_id": "s1"}, top_k=1))
    assert len(items) == 1
    assert client.tool_calls[-1][1]["scope"] == {"session_id": "s1"}


def test_memory_search_error(client, config):
    client.fail_tools.add("memory_search")
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.search("gold"))


def test_memory_delete(client, config):
    client.memories = {
        "m1": {
            "id": "m1",
            "content": "x",
            "memory_type": "short_term",
            "category": "general",
            "importance": 0.5,
            "confidence": 1.0,
            "metadata": {},
        }
    }
    adapter = MCPMemoryAdapter(client, config)
    assert asyncio_run(adapter.delete("m1")) is True
    assert "m1" not in client.memories
    assert client.tool_calls[-1][1] == {"id": "m1"}


def test_memory_delete_error(client, config):
    client.fail_tools.add("memory_delete")
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.delete("m1"))


def test_memory_not_connected_raises(config):
    class NoConnect:
        connected = False

    adapter = MCPMemoryAdapter(NoConnect(), config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.store("hello"))
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.search("hello"))
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.delete("m1"))


def test_memory_search_error_content(client, config):
    client.error_content = True
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.search("gold"))


def test_memory_delete_error_content(client, config):
    client.error_content = True
    adapter = MCPMemoryAdapter(client, config)
    with pytest.raises(MCPMemoryAdapterError):
        asyncio_run(adapter.delete("m1"))


def test_memory_parse_from_content_blocks(client, config):
    client._tool_call = lambda name, args: FakeCallResult(
        content=[{"text": "block memory text"}],
        is_error=False,
        structured_content={},
    )
    adapter = MCPMemoryAdapter(client, config)
    items = asyncio_run(adapter.search("anything"))
    assert len(items) == 1
    assert items[0]["content"] == "block memory text"


def test_memory_to_chunks():
    items = [
        {"id": "m1", "content": "gold preference", "memory_type": "long_term", "category": "preference", "importance": 0.8, "metadata": {}},
        {"id": "m2", "content": "", "memory_type": "short_term", "category": "general", "importance": 0.5, "metadata": {}},
    ]
    chunks = MCPMemoryAdapter.to_chunks(items)
    assert len(chunks) == 1
    assert chunks[0]["id"] == "m1"
    assert chunks[0]["score"] == 0.8
    assert chunks[0]["metadata"]["source"] == "memory"
    assert chunks[0]["metadata"]["category"] == "preference"


def test_citation_resolve_async(client, config):
    resolver = MCPCitationResolver(client, config)
    resolved = asyncio_run(
        resolver.resolve_async(
            [{"uri": "mcp://notes/1", "source_id": "s1", "title": "Notes"}]
        )
    )
    assert len(resolved) == 1
    assert resolved[0]["source_id"] == "s1"
    assert resolved[0]["content"] == "Trading strategy notes for gold."
    assert resolved[0]["uri"] == "mcp://notes/1"


def test_citation_resolve_async_skips_non_matching_uri(config):
    client = make_client()
    resolver = MCPCitationResolver(client, config)
    resolved = asyncio_run(
        resolver.resolve_async([{"uri": "file:///tmp/x", "source_id": "s1"}])
    )
    assert resolved == []


def test_citation_resolve_async_skips_without_uri(config):
    client = make_client()
    resolver = MCPCitationResolver(client, config)
    resolved = asyncio_run(resolver.resolve_async([{"content": "x"}]))
    assert resolved == []


def test_citation_resolve_async_non_text_resource(config):
    client = make_client(resources=[FakeResource("mcp://notes/1", None)])
    resolver = MCPCitationResolver(client, config)
    resolved = asyncio_run(
        resolver.resolve_async([{"uri": "mcp://notes/1", "source_id": "s1"}])
    )
    assert len(resolved) == 1
    assert resolved[0]["content"] == ""


def test_citation_resolve_async_raises_on_missing_resource(client, config):
    resolver = MCPCitationResolver(client, config)
    with pytest.raises(MCPCitationResolverError):
        asyncio_run(resolver.resolve_async([{"uri": "mcp://missing/1"}]))


def test_citation_cite_async(client, config):
    resolver = MCPCitationResolver(client, config, engine=FakeCitationEngine())
    result = asyncio_run(
        resolver.cite_async(
            "Gold is up.",
            [MCPRetrievalResult(id="c1", content="Gold data.", score=0.9)],
        )
    )
    assert result["verified"] is True
    assert result["rendered"] == "Gold is up. [1]"
    assert result["sources"][0]["source_id"] == "c1"


def test_citation_cite_async_without_engine(client, config):
    resolver = MCPCitationResolver(client, config)
    with pytest.raises(MCPCitationResolverError):
        asyncio_run(
            resolver.cite_async(
                "text", [MCPRetrievalResult(id="c1", content="x", score=0.5)]
            )
        )


def test_citation_cite_async_engine_failure(client, config):
    resolver = MCPCitationResolver(client, config, engine=FakeCitationEngine(fail=True))
    with pytest.raises(MCPCitationResolverError):
        asyncio_run(
            resolver.cite_async(
                "text", [MCPRetrievalResult(id="c1", content="x", score=0.5)]
            )
        )


def test_citation_cite_async_with_resources(client, config):
    resolver = MCPCitationResolver(client, config, engine=FakeCitationEngine())
    result = asyncio_run(
        resolver.cite_async(
            "text",
            [MCPRetrievalResult(id="c1", content="x", score=0.5, metadata={"uri": "mcp://notes/1"})],
        )
    )
    assert result["verified"] is True
    assert client.resource_reads == ["mcp://notes/1"]


def test_citation_cite_async_resolve_fallback(client, config):
    resolver = MCPCitationResolver(client, config, engine=FakeCitationEngine())
    result = asyncio_run(
        resolver.cite_async(
            "text",
            [MCPRetrievalResult(id="c1", content="x", score=0.5, metadata={"uri": "mcp://missing/1"})],
        )
    )
    assert result["verified"] is True
    assert result["sources"][0]["source_id"] == "c1"


def test_citation_cite_async_engine_resolver_error(client, config):
    class ResolverErrorEngine:
        async def generate_async(self, text, sources, citation_format):
            raise MCPCitationResolverError("propagate me")

    resolver = MCPCitationResolver(client, config, engine=ResolverErrorEngine())
    with pytest.raises(MCPCitationResolverError):
        asyncio_run(
            resolver.cite_async(
                "text", [MCPRetrievalResult(id="c1", content="x", score=0.5)]
            )
        )


def test_coordinator_answer(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    generator = FakeGenerator()
    result = asyncio_run(
        coordinator.answer("gold prices", top_k=5, generator=generator)
    )
    assert result.answer == "generated answer"
    assert len(result.chunks) == 2
    assert result.chunks[0].id == "c1"
    assert generator.calls[0][0] == "gold prices"
    assert "Gold prices" in generator.calls[0][1]
    assert result.error == ""
    assert result.latency_ms > 0
    # auto_store_turns stored the Q/A pair
    assert any("Q: gold prices" in m["content"] for m in client.memories.values())


def test_coordinator_answer_with_memory(client, config):
    client.memories = {
        "m1": {
            "id": "m1",
            "content": "user trades gold on 5m charts",
            "memory_type": "long_term",
            "category": "preference",
            "importance": 0.9,
            "confidence": 1.0,
            "metadata": {},
        }
    }
    coordinator = MCPIntegrationCoordinator(client, config)
    generator = FakeGenerator()
    result = asyncio_run(coordinator.answer("gold", generator=generator))
    assert len(result.memories) == 1
    assert result.memories[0]["id"] == "m1"
    assert "user trades gold" in generator.calls[0][1]


def test_coordinator_answer_citations(client, config):
    client.chunks = [client.chunks[0]]
    coordinator = MCPIntegrationCoordinator(
        client, config, citation_resolver=create_mcp_citation_resolver(
            client, config, engine=FakeCitationEngine()
        )
    )
    result = asyncio_run(coordinator.answer("gold prices", top_k=5, generator=FakeGenerator()))
    assert result.citation_result is not None
    assert result.citation_result["verified"] is True


def test_coordinator_answer_citation_failure_skips(client, config):
    client.chunks = [client.chunks[0]]
    coordinator = MCPIntegrationCoordinator(
        client, config, citation_resolver=create_mcp_citation_resolver(
            client, config, engine=FakeCitationEngine(fail=True)
        )
    )
    result = asyncio_run(coordinator.answer("gold prices", top_k=5, generator=FakeGenerator()))
    assert result.citation_result is None
    assert result.error == ""


def test_coordinator_answer_resource_fallback(client, config):
    client.fail_tools.add("search_knowledge")
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("trading", top_k=5, generator=FakeGenerator()))
    assert len(result.chunks) >= 1
    assert result.chunks[0].id == "mcp://notes/1"


def test_coordinator_answer_no_fallback(client, config):
    client.fail_tools.add("search_knowledge")
    config.allow_resource_fallback = False
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    assert "MCP retrieval failed" in result.error
    assert result.chunks == []


def test_coordinator_answer_no_generator(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("gold", top_k=5))
    assert "No answer generator configured" in result.error
    assert result.answer == ""


def test_coordinator_answer_no_auto_store(client, config):
    config.auto_store_turns = False
    coordinator = MCPIntegrationCoordinator(client, config)
    asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    assert client.memories == {}


def test_coordinator_answer_without_memory(client, config):
    config.include_memory_in_rag = False
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    assert result.memories == []


def test_coordinator_retrieval_fallback_logged(client, config):
    client.fail_tools.add("search_knowledge")
    config.log_events = True
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("trading", top_k=5, generator=FakeGenerator()))
    assert len(result.chunks) >= 1
    assert result.error == ""


def test_coordinator_build_context_skips_and_budget(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    chunks = [
        MCPRetrievalResult(id="c-empty", content="  ", score=0.5),
        MCPRetrievalResult(id="c-big", content="x" * 500, score=0.5),
        MCPRetrievalResult(id="c-small", content="small chunk", score=0.5),
    ]
    context = coordinator._build_context(chunks, [], budget=100)
    assert context == ""
    context = coordinator._build_context(chunks, [], budget=520)
    assert "c-big" in context
    assert "c-small" not in context
    memories = [
        {"content": "", "metadata": {"category": "general"}},
        {"content": "y" * 500, "metadata": {"category": "notes"}},
        {"content": "tiny memory", "metadata": {"category": "notes"}},
    ]
    context = coordinator._build_context([], memories, budget=100)
    assert context == ""
    context = coordinator._build_context([], memories, budget=520)
    assert "notes" in context
    assert "tiny memory" not in context


def test_exception_hierarchy():
    from app.mcp_integration.exceptions import (
        MCPIntegrationConnectionError,
        MCPIntegrationError,
    )

    assert issubclass(MCPIntegrationConnectionError, MCPIntegrationError)
    assert issubclass(MCPRetrieverError, MCPIntegrationError)
    assert issubclass(MCPMemoryAdapterError, MCPIntegrationError)
    assert issubclass(MCPCitationResolverError, MCPIntegrationError)
    assert issubclass(MCPIntegrationCoordinatorError, MCPIntegrationError)
    assert "boom" in str(MCPIntegrationConnectionError("boom"))


def test_logger_fallback_on_serialization_failure():
    from app.mcp_integration.logging import MCPIntegrationLogger

    class Unserializable:
        def __str__(self):
            raise ValueError("cannot serialize")

    logger = MCPIntegrationLogger()
    logger.log_event("test", value=Unserializable())


def test_coordinator_memory_ops(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    item = asyncio_run(coordinator.store_memory("remember x", category="notes"))
    assert item["id"] == "m1"
    items = asyncio_run(coordinator.retrieve_memories(query="remember"))
    assert len(items) == 1
    assert asyncio_run(coordinator.delete_memory(item["id"])) is True
    assert client.memories == {}


def test_coordinator_metrics(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    metrics = coordinator.get_metrics()
    assert metrics["total_answers"] == 1
    assert metrics["total_retrievals"] >= 1
    assert metrics["total_memories_stored"] >= 1
    assert metrics["total_errors"] == 0


def test_coordinator_close(client, config):
    coordinator = MCPIntegrationCoordinator(client, config)
    asyncio_run(coordinator.close())
    assert client.disconnect_count == 1


def test_metrics_tracker_disabled(config):
    config.track_metrics = False
    coordinator = MCPIntegrationCoordinator(client=make_client(), config=config)
    asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    metrics = coordinator.get_metrics()
    assert metrics["total_answers"] == 0


def test_metrics_tracker_reset(client, config):
    import time

    coordinator = MCPIntegrationCoordinator(client, config)
    asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    metrics_tracker = coordinator._metrics
    metrics_tracker.reset()
    assert metrics_tracker.get_metrics().total_answers == 0
    assert coordinator.get_metrics()["total_answers"] == 0
    assert metrics_tracker.enabled is True
    assert metrics_tracker.elapsed(time.perf_counter()) >= 0


def test_metrics_model_to_dict(client, config):
    metrics = MCPIntegrationMetrics()
    metrics.record_retrieval(10.5)
    metrics.record_tool_call()
    metrics.record_resource_read()
    metrics.record_memory_store()
    metrics.record_memory_retrieve(3)
    metrics.record_citation()
    metrics.record_answer(20.5)
    metrics.record_error()
    d = metrics.to_dict()
    assert d["total_retrievals"] == 1
    assert d["total_tool_calls"] == 1
    assert d["total_resource_reads"] == 1
    assert d["total_memories_stored"] == 1
    assert d["total_memories_retrieved"] == 3
    assert d["total_citations_generated"] == 1
    assert d["total_answers"] == 1
    assert d["total_errors"] == 1
    assert d["average_retrieval_latency_ms"] == 10.5
    assert d["uptime_seconds"] >= 0


def test_metrics_model_empty_averages():
    d = MCPIntegrationMetrics().to_dict()
    assert d["average_retrieval_latency_ms"] == 0.0
    assert d["average_answer_latency_ms"] == 0.0


def test_mcp_retrieval_result_to_dict():
    r = MCPRetrievalResult(id="x", content="y", score=0.7, metadata={"k": "v"})
    assert r.to_dict() == {
        "id": "x",
        "content": "y",
        "score": 0.7,
        "metadata": {"k": "v"},
    }


def test_mcp_rag_result_to_dict(client, config):
    client.memories = {
        "m1": {
            "id": "m1",
            "content": "gold scalping preferred",
            "memory_type": "long_term",
            "category": "preference",
            "importance": 0.9,
            "confidence": 1.0,
            "metadata": {},
        }
    }
    coordinator = MCPIntegrationCoordinator(client, config)
    result = asyncio_run(coordinator.answer("gold", top_k=5, generator=FakeGenerator()))
    d = result.to_dict()
    assert d["query"] == "gold"
    assert d["answer"] == "generated answer"
    assert d["chunks"]
    assert d["memories"]
    assert d["error"] == ""


def test_factories(client, config):
    retriever = create_mcp_retriever(client, config)
    memory = create_mcp_memory_adapter(client, config)
    citations = create_mcp_citation_resolver(client, config)
    coordinator = create_mcp_integration(client, config)
    assert isinstance(retriever, MCPRetriever)
    assert isinstance(memory, MCPMemoryAdapter)
    assert isinstance(citations, MCPCitationResolver)
    assert isinstance(coordinator, MCPIntegrationCoordinator)
    assert coordinator.retriever is not None
    assert coordinator.memory is not None
    assert coordinator.citations is not None


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("MCPI_RETRIEVER_TOOL", "search_docs")
    monkeypatch.setenv("MCPI_TIMEOUT", "45")
    monkeypatch.setenv("MCPI_MEMORY_TOP_K", "7")
    monkeypatch.setenv("MCPI_CITATION_ENABLED", "0")
    config = MCPIntegrationConfig.from_env()
    assert config.retriever_tool == "search_docs"
    assert config.timeout == 45.0
    assert config.memory_top_k == 7
    assert config.citation_enabled is False


def test_coordinator_raises_without_generator_direct():
    client = make_client()
    coordinator = MCPIntegrationCoordinator(client, make_config())

    async def run():
        with pytest.raises(MCPIntegrationCoordinatorError):
            await coordinator._generate_answer(None, "q", "ctx", [])
        return True

    assert asyncio_run(run()) is True


def asyncio_run(coro):
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()
