from __future__ import annotations

import json

import pytest

from app.evaluation import (
    BenchmarkDataset,
    BenchmarkRegistry,
    BenchmarkRunner,
    CitationEvaluator,
    CompositeEvaluator,
    EvaluationConfig,
    EvaluationDashboard,
    EvaluationLogger,
    EvaluationOrchestrator,
    EvaluatorRegistry,
    MCPToolUsageEvaluator,
    MemoryEvaluator,
    QualityGate,
    RAGEvaluator,
    ReportGenerator,
    RetrievalEvaluator,
    builtin_internal_dataset,
    create_benchmark_dataset,
    create_evaluator,
    create_orchestrator,
    load_benchmark_dataset,
)
from app.evaluation.benchmarks import builtin_internal_dataset as builtin_fn
from app.evaluation.exceptions import (
    ComparisonError,
    DatasetNotFoundError,
    EvaluatorNotFoundError,
    EvaluationError,
    ReportGenerationError,
)
from app.evaluation.evaluators.retrieval import (
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.evaluators.rag import _sentences, _token_overlap, sentence_support
from app.evaluation.models import (
    BenchmarkResult,
    ComparisonResult,
    DatasetType,
    EvaluationMetric,
    EvaluationResult,
    EvaluationSample,
    GateCheck,
    GateResult,
    MetricScore,
    RetrievedItem,
)
from app.evaluation.statistics import EvaluationMetricsTracker, distribution


def retrieval_sample(relevant=None, results=None):
    return EvaluationSample.retrieval(
        "r1",
        "gold prices",
        relevant or ["d1"],
        results
        or [
            {"id": "d1", "score": 0.9, "content": "gold rising"},
            {"id": "d2", "score": 0.8, "content": "silver falling"},
        ],
    )


def make_config(**kwargs):
    return EvaluationConfig(log_events=False, **kwargs)


class FakeJudge:
    def __init__(self, support=0.8, relevance=0.6):
        self.support_value = support
        self.relevance_value = relevance

    def support(self, claim, contexts):
        return self.support_value

    def relevance(self, query, answer):
        return self.relevance_value


class RecordingObserver:
    def __init__(self):
        self.events = []

    def handle(self, event, data):
        self.events.append((event, dict(data)))


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("EVAL_RECALL_AT_K", "3")
    monkeypatch.setenv("EVAL_GATE_ENABLED", "0")
    monkeypatch.setenv("EVAL_REGRESSION_TOLERANCE", "0.1")
    config = EvaluationConfig.from_env()
    assert config.recall_at_k == 3
    assert config.gate_enabled is False
    assert config.regression_tolerance == 0.1


def test_config_set_threshold():
    config = make_config()
    config.set_threshold("custom_metric", min=0.5)
    assert config.thresholds["custom_metric"] == {"min": 0.5, "max": None}
    config.set_threshold("custom_metric", max=0.9)
    assert config.thresholds["custom_metric"] == {"min": 0.5, "max": 0.9}


def test_default_thresholds_present():
    config = make_config()
    assert "recall_at_k" in config.thresholds
    assert config.thresholds["hallucination_rate"] == {"max": 0.3}


def test_evaluation_sample_builders():
    sample = EvaluationSample.retrieval("r", "q", ["a"], [RetrievedItem("a", 0.9)])
    assert sample.expected["relevant_ids"] == ["a"]
    assert isinstance(sample.actual["results"][0], RetrievedItem)

    sample = EvaluationSample.rag("r", "q", ["ctx"], "answer", "ref")
    assert sample.actual["answer"] == "answer"
    assert sample.expected["reference"] == "ref"

    sample = EvaluationSample.citation(
        "r", "text [1]", [{"source_id": "s1"}], [{"id": "s1"}]
    )
    assert sample.expected["sources"] == ["s1"]

    sample = EvaluationSample.memory(
        "r", "q", ["m1"], [{"id": "m1", "importance": 0.7}]
    )
    assert sample.actual["retrieved"][0].score == 0.7

    sample = EvaluationSample.mcp_tools(
        "r", ["t1"], [{"tool": "t1", "success": True, "arguments": {"a": 1}}]
    )
    assert sample.expected["tools"] == ["t1"]
    assert sample.metadata["evaluator"] == "mcp_tools"


def test_evaluation_sample_from_dict_object_items():
    item = RetrievedItem(id="x", score=0.5, content="c", rank=1)
    sample = EvaluationSample.retrieval("r", "q", ["x"], [item])
    converted = sample.actual["results"][0]
    assert converted.id == "x"
    assert converted.score == 0.5


def test_sample_from_retrieved_chunks_compat():
    from app.rag.models import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            content="gold market data",
            score=0.9,
            rerank_score=0.85,
            source="doc",
            metadata={"k": "v"},
        )
    ]
    sample = EvaluationSample.from_retrieved_chunks("s", "gold", ["c1"], chunks)
    item = sample.actual["results"][0]
    assert item.id == "c1"
    assert item.score == 0.85
    assert item.content == "gold market data"
    assert item.rank == 1


def test_sample_from_search_results_compat():
    from app.retrieval.models import SearchResultItem

    items = [SearchResultItem(id="r1", score=0.77, metadata={"m": 1})]
    sample = EvaluationSample.from_search_results("s", "gold", ["r1"], items)
    item = sample.actual["results"][0]
    assert item.id == "r1"
    assert item.score == 0.77
    assert item.metadata == {"m": 1}


def test_sample_from_memory_items_compat():
    from app.memory.models import MemoryItem

    items = [MemoryItem(id="m1", content="gold preference", importance=0.9)]
    sample = EvaluationSample.from_memory_items("s", "gold", ["m1"], items)
    item = sample.actual["retrieved"][0]
    assert item.id == "m1"
    assert item.score == 0.9
    assert item.content == "gold preference"


def test_benchmark_dataset_roundtrip():
    dataset = builtin_internal_dataset()
    payload = dataset.to_dict()
    assert payload["name"] == "internal-smoke"
    restored = BenchmarkDataset.from_dict(payload)
    assert restored.name == dataset.name
    assert restored.dataset_type == dataset.dataset_type
    assert len(restored.samples) == len(dataset.samples)
    assert restored.samples[0].query == dataset.samples[0].query


def test_evaluation_result_summary_and_metric():
    result = EvaluationResult(
        evaluator="retrieval",
        samples=[],
        metrics=[EvaluationMetric(name="mrr", value=0.5, samples=2)],
    )
    assert result.summary() == {"mrr": 0.5}
    assert result.metric("mrr").value == 0.5
    assert result.metric("missing") is None
    d = result.to_dict()
    assert d["evaluator"] == "retrieval"
    assert d["samples"] == 0


def test_metric_score_and_gate_models_to_dict():
    score = MetricScore("mrr", 0.5, {"k": "v"})
    assert score.to_dict()["metric"] == "mrr"
    check = GateCheck("mrr", 0.4, threshold_min=0.5, passed=False)
    assert check.to_dict()["passed"] is False
    gate = GateResult(passed=False, checks=[check])
    assert gate.to_dict()["passed"] is False
    comparison = ComparisonResult(base_name="b", current_name="c", metrics={}, regressions=["m"], passed=False)
    assert comparison.to_dict()["regressions"] == ["m"]


def test_distribution():
    d = distribution([1, 2, 3, 4, 5])
    assert d["mean"] == 3.0
    assert d["p50"] == 3
    assert d["min"] == 1
    assert d["max"] == 5
    assert d["p90"] == 5
    assert d["p95"] == 5
    assert distribution([]) == {}
    d2 = distribution([4.0, 6.0])
    assert d2["std"] == 1.0


def test_metrics_tracker():
    tracker = EvaluationMetricsTracker(make_config())
    tracker.record("mrr", 0.5, evaluator="retrieval")
    tracker.record("mrr", 0.9, evaluator="retrieval")
    assert tracker.aggregate("mrr")["mean"] == 0.7
    assert tracker.aggregate("missing") == {}
    assert tracker.by_evaluator()["retrieval.mrr"] == 0.7
    assert tracker.summary()["mrr"]["p50"] == 0.7
    tracker.record("x", 1.0)
    tracker.reset()
    assert tracker.summary() == {}
    assert tracker.uptime() >= 0
    assert tracker.enabled is True


def test_metrics_tracker_disabled():
    tracker = EvaluationMetricsTracker(make_config(track_metrics=False))
    tracker.record("mrr", 0.5)
    assert tracker.aggregate("mrr") == {}
    assert tracker.enabled is False


def test_registry_create_and_errors():
    registry = EvaluatorRegistry.default()
    assert registry.contains("retrieval")
    assert registry.names() == ["citation", "mcp_tools", "memory", "rag", "retrieval"]
    evaluator = registry.create("retrieval", config=make_config())
    assert isinstance(evaluator, RetrievalEvaluator)
    with pytest.raises(EvaluatorNotFoundError):
        registry.create("nope")
    with pytest.raises(EvaluatorNotFoundError):
        EvaluatorRegistry().create("retrieval")


def test_retrieval_metrics_functions():
    assert recall_at_k(["d1"], ["d1", "d2"], 1) == 1.0
    assert recall_at_k(["d1"], ["d2", "d1"], 1) == 0.0
    assert recall_at_k([], ["d1"], 1) == 0.0
    assert precision_at_k(["d1"], ["d1", "d3"], 2) == 0.5
    assert precision_at_k(["d1"], [], 5) == 0.0
    assert precision_at_k(["d1"], ["d2"], 1) == 0.0
    assert reciprocal_rank(["d2"], ["d1", "d2"]) == 0.5
    assert reciprocal_rank(["d9"], ["d1"]) == 0.0
    assert average_precision(["d1", "d2"], ["d1", "d3", "d2"]) == pytest.approx(0.8333, abs=0.001)
    assert average_precision([], ["d1"]) == 0.0
    assert ndcg_at_k(["d1"], ["d1", "d2"], 2) == pytest.approx(1.0)
    assert ndcg_at_k(["d1"], ["d2", "d1"], 2) == pytest.approx(0.6667, abs=0.001)
    assert ndcg_at_k([], ["d1"], 5) == 0.0
    assert ndcg_at_k(["d1"], ["d2"], 0) == 0.0


def test_retrieval_evaluator_batch():
    evaluator = RetrievalEvaluator(config=make_config(recall_at_k=1, precision_at_k=1, ndcg_k=2))
    samples = [
        retrieval_sample(relevant=["d1"], results=[{"id": "d1"}, {"id": "d2"}]),
        retrieval_sample(relevant=["d2"], results=[{"id": "d1"}, {"id": "d2"}]),
    ]
    result = evaluator.evaluate_batch(samples)
    result = run_sync(result)
    summary = result.summary()
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.75
    assert summary["map"] == pytest.approx(0.75, abs=0.001)
    assert result.duration_ms >= 0
    assert result.evaluator == "retrieval"


def test_retrieval_evaluator_batch_failure():
    evaluator = RetrievalEvaluator(config=make_config())

    class BadSample(EvaluationSample):
        pass

    sample = BadSample(id="x", query="q")
    sample.expected = None
    result = run_sync(evaluator.evaluate_batch([sample]))
    assert result.error
    assert result.metrics == []


def test_rag_evaluator_heuristic():
    evaluator = RAGEvaluator(config=make_config(token_overlap_threshold=0.4))
    sample = EvaluationSample.rag(
        "r",
        "gold prices rising",
        ["Gold prices are rising strongly this year."],
        "Gold prices are rising strongly. Silver is flat.",
    )
    scores = evaluator.evaluate_scores(sample)
    by_name = {s.metric: s.value for s in scores}
    assert by_name["faithfulness"] == 0.5
    assert by_name["groundedness"] == 0.5
    assert by_name["hallucination_rate"] == 0.5
    assert by_name["relevance"] >= 0


def test_rag_evaluator_no_claims():
    evaluator = RAGEvaluator(config=make_config())
    sample = EvaluationSample.rag("r", "q", ["ctx"], "")
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["faithfulness"] == 1.0
    assert scores["groundedness"] == 1.0
    assert scores["hallucination_rate"] == 0.0
    assert scores["relevance"] == 0.0


def test_rag_evaluator_judge():
    evaluator = RAGEvaluator(config=make_config(), judge=FakeJudge())
    sample = EvaluationSample.rag("r", "q", ["ctx"], "Claim one. Claim two.")
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["faithfulness"] == 0.8
    assert scores["relevance"] == 0.6
    assert scores["hallucination_rate"] == 0.2


def test_rag_evaluator_judge_no_claims():
    evaluator = RAGEvaluator(config=make_config(), judge=FakeJudge())
    sample = EvaluationSample.rag("r", "q", ["ctx"], "")
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["faithfulness"] == 1.0
    assert scores["relevance"] == 0.6


def test_rag_evaluator_judge_missing_methods():
    class PartialJudge:
        def support(self, claim, contexts):
            return 0.9

        def relevance(self, query, answer):
            raise TypeError("bad call")

    evaluator = RAGEvaluator(config=make_config(), judge=PartialJudge())
    sample = EvaluationSample.rag("r", "q", ["ctx"], "One sentence here.")
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["faithfulness"] == 0.9
    assert scores["relevance"] == 0.5

    class NoMethods:
        pass

    evaluator = RAGEvaluator(config=make_config(), judge=NoMethods())
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["relevance"] == 0.5
    assert scores["faithfulness"] == 0.5


def test_rag_helpers():
    assert _sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert _sentences("") == []
    assert _token_overlap("gold prices", "gold prices today") == 1.0
    assert _token_overlap("gold prices", "") == 0.0
    assert _token_overlap("a b", "gold") == 0.0
    assert sentence_support("gold rises", ["gold is rising"], 0.5) is True
    assert sentence_support("gold rises", ["nothing here"], 0.5) is False


def test_citation_evaluator():
    evaluator = CitationEvaluator(config=make_config(token_overlap_threshold=0.4))
    sample = EvaluationSample.citation(
        "c",
        "Gold hit a record high in 2026 [1]. Silver stayed flat.",
        [
            {"source_id": "s1", "index": 1, "claim": "Gold hit a record high in 2026."},
            {"source_id": "s2", "index": 2, "claim": "Silver stayed flat."},
        ],
        [
            {"id": "s1", "content": "Gold hit a record high in 2026 according to data."},
            {"id": "s2", "content": "Silver stayed flat throughout the year."},
        ],
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["citation_recall"] == 0.5
    assert scores["citation_verifiability"] == 1.0
    assert scores["citation_precision"] == 1.0
    assert scores["citation_density"] == 0.5


def test_citation_evaluator_no_sentences():
    evaluator = CitationEvaluator(config=make_config())
    sample = EvaluationSample.citation("c", " ", [], [])
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["citation_precision"] == 1.0
    assert scores["citation_recall"] == 1.0
    assert scores["citation_verifiability"] == 1.0
    assert scores["citation_density"] == 0.0


def test_citation_evaluator_unverifiable():
    evaluator = CitationEvaluator(config=make_config())
    sample = EvaluationSample.citation(
        "c",
        "Claim one [1]. Claim two [2].",
        [
            {"source_id": "s1", "index": 1, "claim": "Claim one."},
            {"source_id": "s2", "index": 2, "claim": "Claim two."},
        ],
        [{"id": "s1", "content": "Unrelated content about cooking."}],
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["citation_verifiability"] == 0.5
    assert scores["citation_precision"] == 0.0


def test_memory_evaluator():
    evaluator = MemoryEvaluator(config=make_config())
    sample = EvaluationSample.memory(
        "m",
        "preferences",
        ["m1"],
        [
            {"id": "m1", "importance": 0.9},
            {"id": "m3", "importance": 0.2},
        ],
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_hit_rate"] == 1.0
    assert scores["memory_precision"] == 0.5
    assert scores["memory_recall"] == 1.0
    assert scores["memory_relevance"] == 0.55


def test_memory_evaluator_no_retrieved():
    evaluator = MemoryEvaluator(config=make_config())
    sample = EvaluationSample.memory("m", "q", ["m1"], [])
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_hit_rate"] == 0.0
    assert scores["memory_precision"] == 0.0
    assert scores["memory_relevance"] == 0.0


def test_memory_evaluator_no_relevant():
    evaluator = MemoryEvaluator(config=make_config())
    sample = EvaluationSample.memory(
        "m", "q", [], [{"id": "m1", "importance": 0.8}]
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_recall"] == 0.0
    assert scores["memory_hit_rate"] == 0.0


def test_mcp_tool_evaluator():
    evaluator = MCPToolUsageEvaluator(config=make_config())
    sample = EvaluationSample.mcp_tools(
        "t",
        ["search_knowledge", "memory_save"],
        [
            {"tool": "search_knowledge", "success": True, "arguments": {"query": "gold"}},
            {"tool": "memory_save", "success": False, "error": "timeout", "arguments": {}},
            {"tool": "unknown_tool", "success": True, "arguments": {"a": 1}},
        ],
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["tool_success_rate"] == pytest.approx(0.6667, abs=0.001)
    assert scores["tool_error_rate"] == pytest.approx(0.3333, abs=0.001)
    assert scores["tool_completeness"] == 1.0
    assert scores["tool_precision"] == pytest.approx(0.6667, abs=0.001)
    assert scores["tool_correctness"] == pytest.approx(0.6667, abs=0.001)


def test_mcp_tool_evaluator_no_calls():
    evaluator = MCPToolUsageEvaluator(config=make_config())
    sample = EvaluationSample.mcp_tools("t", ["a"], [])
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["tool_success_rate"] == 1.0
    assert scores["tool_completeness"] == 0.0
    assert scores["tool_precision"] == 0.0


def test_mcp_tool_evaluator_list_arguments():
    evaluator = MCPToolUsageEvaluator(config=make_config())
    assert evaluator._call_correct({"success": True, "arguments": ["a"]}) is True
    assert evaluator._call_correct({"success": True, "arguments": []}) is False
    assert evaluator._call_correct({"success": True, "arguments": None}) is False


def test_quality_gate():
    config = make_config()
    config.set_threshold("mrr", min=0.5)
    config.set_threshold("hallucination_rate", max=0.3)
    gate = QualityGate(config)
    metrics = [
        EvaluationMetric(name="mrr", value=0.6, samples=1),
        EvaluationMetric(name="hallucination_rate", value=0.2, samples=1),
        EvaluationMetric(name="unconstrained", value=0.0, samples=1),
    ]
    result = gate.check(metrics)
    assert result.passed is True
    assert len(result.checks) == 2
    metrics[0].value = 0.3
    result = gate.check(metrics)
    assert result.passed is False
    assert result.checks[0].passed is False
    assert gate.config is config


def test_composite_evaluator():
    registry = EvaluatorRegistry.default()
    composite = CompositeEvaluator(
        evaluators=[
            registry.create("retrieval", config=make_config()),
            registry.create("rag", config=make_config()),
        ]
    )
    samples = [
        retrieval_sample(),
        EvaluationSample.rag("r", "gold", ["gold is rising"], "Gold is rising."),
    ]
    result = run_sync(composite.evaluate_batch(samples))
    assert result.evaluator == "composite"
    assert result.metric("mrr") is not None
    assert result.metric("faithfulness") is not None
    assert composite.evaluators[0].name == "retrieval"
    with pytest.raises(NotImplementedError):
        composite.evaluate_scores(samples[0])


def test_benchmark_registry_and_runner():
    runner = BenchmarkRunner(config=make_config())
    assert runner.datasets.contains("internal-smoke")
    assert "internal-smoke" in runner.datasets.names()
    result = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    assert result.name == "internal-smoke-run"
    assert result.dataset_type == "internal"
    assert len(result.results) == 1
    assert result.gate is not None
    with pytest.raises(DatasetNotFoundError):
        run_sync(runner.run("missing"))


def test_benchmark_runner_with_dataset_object():
    runner = BenchmarkRunner(config=make_config(gate_enabled=False))
    dataset = builtin_internal_dataset()
    result = run_sync(runner.run(dataset, evaluators=["retrieval", "memory"], name="custom-run"))
    assert result.name == "custom-run"
    assert result.gate is None
    assert len(result.results) == 2


def test_benchmark_runner_evaluator_error():
    registry = EvaluatorRegistry()

    class BrokenEvaluator(RetrievalEvaluator):
        kind = "broken"

    registry.register("broken", BrokenEvaluator)
    runner = BenchmarkRunner(
        evaluator_registry=registry,
        config=make_config(gate_enabled=False),
    )

    class BadSample(EvaluationSample):
        pass

    dataset = BenchmarkDataset(
        name="bad", dataset_type=DatasetType.CUSTOM, samples=[]
    )
    dataset.samples = [BadSample(id="x", query="q", expected=None)]
    result = run_sync(runner.run(dataset, evaluators=["broken"]))
    assert len(result.results) == 1
    assert result.results[0].error
    assert result.gate is None


def test_benchmark_json_loading(tmp_path):
    path = tmp_path / "dataset.json"
    dataset = builtin_internal_dataset()
    path.write_text(json.dumps(dataset.to_dict()))
    registry = BenchmarkRegistry()
    loaded = registry.load_json(str(path), name="loaded-ds", dataset_type=DatasetType.REGRESSION)
    assert loaded.name == "loaded-ds"
    assert loaded.dataset_type == DatasetType.REGRESSION
    assert registry.contains("loaded-ds")
    assert len(registry.list()) == 2


def test_benchmark_result_to_dict():
    benchmark = BenchmarkResult(
        name="b", dataset_name="ds", dataset_type="internal",
        results=[EvaluationResult(evaluator="retrieval", metrics=[EvaluationMetric(name="mrr", value=0.5)])],
    )
    payload = benchmark.to_dict()
    assert payload["name"] == "b"
    assert payload["results"][0]["evaluator"] == "retrieval"
    assert payload["duration_ms"] >= 0


def test_sample_to_dict_with_plain_objects():
    class PlainItem:
        def __init__(self):
            self.chunk_id = "p1"
            self.id = "p1"
            self.content = "plain content"
            self.score = 0.6
            self.rank = 1
            self.metadata = {}

    sample = EvaluationSample.retrieval("r", "q", ["p1"], [PlainItem()])
    assert sample.actual["results"][0].id == "p1"
    payload = sample.to_dict()
    assert payload["actual"]["results"][0]["id"] == "p1"

    sample = EvaluationSample.from_retrieved_chunks("r", "q", ["p1"], [PlainItem()])
    assert sample.actual["results"][0].id == "p1"
    sample = EvaluationSample.from_search_results("r", "q", ["p1"], [PlainItem()])
    assert sample.actual["results"][0].id == "p1"
    sample = EvaluationSample.from_memory_items("r", "q", ["p1"], [PlainItem()])
    assert sample.actual["retrieved"][0].id == "p1"


def test_sample_to_retrieved_item_dicts():
    item = EvaluationSample._to_retrieved_item(
        {"chunk_id": "x", "rerank_score": 0.9, "text": "t", "rank": 2}
    )
    assert item.id == "x"
    assert item.score == 0.9
    assert item.rank == 2

    class Obj:
        def __init__(self):
            self.item_id = "o1"
            self.importance = 0.4
            self.content = "obj"
            self.metadata = {}

    item = EvaluationSample._to_retrieved_item(Obj())
    assert item.id == "o1"
    assert item.score == 0.4


def test_benchmark_result_to_dict_with_gate():
    benchmark = BenchmarkResult(
        name="b", dataset_name="ds", dataset_type="regression",
        gate={"passed": True, "checks": []},
    )
    assert benchmark.to_dict()["gate"]["passed"] is True


def test_memory_evaluator_object_items():
    evaluator = MemoryEvaluator(config=make_config())
    items = [
        RetrievedItem(id="m1", score=0.9),
        RetrievedItem(id="m3", score=0.1),
    ]
    sample = EvaluationSample.memory("m", "q", ["m1"], items)
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_precision"] == 0.5
    assert scores["memory_recall"] == 1.0
    assert scores["memory_relevance"] == 0.5

    class ConfidenceItem:
        def __init__(self):
            self.id = "m9"
            self.confidence = 0.75

    sample = EvaluationSample(
        id="m",
        query="q",
        expected={"relevant_ids": []},
        actual={"retrieved": [ConfidenceItem()], "stored": []},
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_relevance"] == 0.75


def test_memory_evaluator_raw_dict_items():
    evaluator = MemoryEvaluator(config=make_config())
    sample = EvaluationSample(
        id="m",
        query="q",
        expected={"relevant_ids": ["m1"]},
        actual={
            "retrieved": [
                {"id": "m1", "importance": 0.9},
                {"item_id": "m2", "score": 0.4},
                {"id": "m3"},
            ],
            "stored": [],
        },
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["memory_precision"] == pytest.approx(0.3333, abs=0.001)
    assert scores["memory_relevance"] == pytest.approx(0.65, abs=0.001)


def test_sample_from_dict_items():
    sample = EvaluationSample.from_retrieved_chunks(
        "r",
        "q",
        ["d1"],
        [{"chunk_id": "d1", "score": 0.5, "content": "c", "metadata": {}}],
    )
    assert sample.actual["results"][0].id == "d1"
    sample = EvaluationSample.from_memory_items(
        "r", "q", ["m1"], [{"id": "m1", "importance": 0.6}]
    )
    assert sample.actual["retrieved"][0].score == 0.6


def test_mcp_tool_evaluator_empty_calls_with_args_list():
    evaluator = MCPToolUsageEvaluator(config=make_config())
    sample = EvaluationSample.mcp_tools(
        "t", ["a"], [{"tool": "a", "success": True, "arguments": []}]
    )
    scores = {s.metric: s.value for s in evaluator.evaluate_scores(sample)}
    assert scores["tool_correctness"] == 0.0


def test_composite_evaluator_with_error():
    from app.evaluation.registry import BaseEvaluator

    class ExplodingEvaluator(BaseEvaluator):
        kind = "exploding"

        def evaluate_scores(self, sample):
            raise RuntimeError("boom")

    composite = CompositeEvaluator(
        config=make_config(), evaluators=[ExplodingEvaluator()]
    )
    sample = EvaluationSample.retrieval("r", "q", ["a"], [])
    result = run_sync(composite.evaluate_batch([sample]))
    assert result.error == "boom"
    assert result.metrics == []


def test_benchmark_runner_create_error_captured():
    class ExplodingRegistry(EvaluatorRegistry):
        def create(self, name, **kwargs):
            raise RuntimeError("cannot create")

    runner = BenchmarkRunner(evaluator_registry=ExplodingRegistry(), config=make_config(gate_enabled=False))
    result = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    assert result.results == []
    assert result.gate is None


def test_report_markdown_with_error():
    generator = ReportGenerator(make_config())
    result = EvaluationResult(evaluator="rag", samples=[], metrics=[], error="boom")
    assert "**Error:** boom" in generator.to_markdown(result)


def test_report_html_no_gate_and_na_metric():
    generator = ReportGenerator(make_config())
    runner = BenchmarkRunner(config=make_config(gate_enabled=False))
    benchmark = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    html_out = generator.to_html(benchmark)
    assert "<table>" in html_out
    result = EvaluationResult(
        evaluator="x",
        metrics=[EvaluationMetric(name="free", value=0.5, passed=None)],
    )
    html_out = generator.to_html(result)
    assert 'class="na"' in html_out


def test_orchestrator_properties():
    orchestrator = EvaluationOrchestrator(config=make_config())
    assert orchestrator.registry is not None
    assert orchestrator.benchmark_runner is not None
    evaluator = orchestrator.create_evaluator("retrieval")
    assert evaluator.config is orchestrator._config
    assert evaluator.judge is None


def test_orchestrator_compare_dict_with_summary():
    orchestrator = EvaluationOrchestrator(config=make_config())
    base = {"name": "b", "summary": {"mrr": 0.5}}
    current = {"name": "c", "summary": {"mrr": 0.6}}
    comparison = run_sync(orchestrator.compare(base, current))
    assert comparison.metrics["mrr"]["delta"] == 0.1
    assert comparison.passed is True


def test_logger_fallback():
    class Unserializable:
        def __str__(self):
            raise ValueError("nope")

    logger = EvaluationLogger()
    logger.log_event("test", value=Unserializable())


def test_compare_with_unknown_metrics_skipped():
    orchestrator = EvaluationOrchestrator(config=make_config())
    base = {"metrics": {"a": 1.0}}
    current = {"metrics": {"b": 1.0}}
    comparison = run_sync(orchestrator.compare(base, current))
    assert comparison.metrics == {}
    assert comparison.passed is True


def test_orchestrator_run_async():
    orchestrator = EvaluationOrchestrator(config=make_config())
    result = run_sync(
        orchestrator.run_async("retrieval", [retrieval_sample()])
    )
    assert result.evaluator == "retrieval"
    assert result.metric("mrr") is not None
    assert orchestrator.tracker.aggregate("mrr")["mean"] > 0


def test_orchestrator_run_sync():
    orchestrator = EvaluationOrchestrator(config=make_config())
    result = orchestrator.run("retrieval", [retrieval_sample()])
    assert result.evaluator == "retrieval"


async def test_orchestrator_run_inside_loop_raises():
    orchestrator = EvaluationOrchestrator(config=make_config())
    with pytest.raises(EvaluationError):
        orchestrator.run("retrieval", [retrieval_sample()])


def test_orchestrator_create_evaluator_and_benchmark():
    orchestrator = EvaluationOrchestrator(config=make_config())
    evaluator = orchestrator.create_evaluator("rag")
    assert isinstance(evaluator, RAGEvaluator)
    benchmark = run_sync(orchestrator.benchmark("internal-smoke"))
    assert isinstance(benchmark, BenchmarkResult)
    assert benchmark.gate is not None
    assert len(orchestrator.dashboard.history) >= 1


def test_orchestrator_benchmark_no_gate():
    orchestrator = EvaluationOrchestrator(config=make_config(gate_enabled=False))
    benchmark = run_sync(orchestrator.benchmark("internal-smoke", apply_gate=True))
    assert benchmark.gate is None


def test_orchestrator_compare():
    orchestrator = EvaluationOrchestrator(config=make_config())
    base = run_sync(orchestrator.benchmark("internal-smoke", name="base"))
    current = run_sync(orchestrator.benchmark("internal-smoke", name="current"))
    comparison = run_sync(orchestrator.compare(base, current))
    assert comparison.passed is True
    assert "mrr" in comparison.metrics
    assert comparison.metrics["mrr"]["delta"] == 0.0


def test_orchestrator_compare_regression():
    orchestrator = EvaluationOrchestrator(config=make_config(regression_tolerance=0.01))
    base = run_sync(orchestrator.benchmark("internal-smoke", name="base"))
    current = EvaluationOrchestrator(config=make_config(regression_tolerance=0.01))
    current_result = run_sync(current.benchmark("internal-smoke", name="current"))

    class DegradedDataset:
        pass

    degraded = builtin_internal_dataset()
    degraded.samples[0].actual["results"] = []
    runner = BenchmarkRunner(config=make_config(gate_enabled=False))
    degraded_result = run_sync(runner.run(degraded, evaluators=["retrieval"]))
    comparison = run_sync(orchestrator.compare(base, degraded_result))
    assert comparison.regressions
    assert comparison.passed is False
    assert comparison.base_name == "base"


def test_orchestrator_compare_empty_base_raises():
    orchestrator = EvaluationOrchestrator(config=make_config())
    current = run_sync(orchestrator.benchmark("internal-smoke"))
    with pytest.raises(ComparisonError):
        run_sync(orchestrator.compare({}, current))


def test_orchestrator_compare_dict_sources():
    orchestrator = EvaluationOrchestrator(config=make_config())
    base = {"name": "b", "metrics": {"mrr": 0.5}}
    current = {"name": "c", "metrics": {"mrr": 0.6, "extra": 1.0}}
    comparison = run_sync(orchestrator.compare(base, current))
    assert comparison.metrics["mrr"]["delta"] == 0.1
    assert "extra" not in comparison.metrics


def test_orchestrator_observers():
    orchestrator = EvaluationOrchestrator(config=make_config())
    observer = RecordingObserver()
    orchestrator.attach(observer)
    orchestrator.attach(observer)
    run_sync(orchestrator.run_async("retrieval", [retrieval_sample()]))
    orchestrator.detach(observer)
    run_sync(orchestrator.run_async("retrieval", [retrieval_sample()]))
    events = [e for e, _ in observer.events]
    assert "run_started" in events
    assert "run_completed" in events
    assert len([e for e in events if e == "run_completed"]) == 1


def test_orchestrator_generate_report(tmp_path):
    orchestrator = EvaluationOrchestrator(config=make_config(report_formats=("json", "csv")))
    result = run_sync(orchestrator.run_async("retrieval", [retrieval_sample()]))
    outputs = run_sync(orchestrator.generate_report(result, directory=str(tmp_path)))
    assert "json" in outputs
    assert "csv" in outputs
    assert (tmp_path / "retrieval.json").exists()
    assert (tmp_path / "retrieval.csv").exists()


def test_report_generator_json():
    generator = ReportGenerator(make_config())
    result = run_sync(RetrievalEvaluator(make_config()).evaluate_batch([retrieval_sample()]))
    payload = json.loads(generator.to_json(result))
    assert payload["evaluator"] == "retrieval"


def test_report_generator_markdown():
    generator = ReportGenerator(make_config())
    result = run_sync(RetrievalEvaluator(make_config()).evaluate_batch([retrieval_sample()]))
    markdown = generator.to_markdown(result)
    assert "retrieval" in markdown
    assert "| Metric | Value" in markdown


def test_report_generator_markdown_benchmark():
    generator = ReportGenerator(make_config())
    runner = BenchmarkRunner(config=make_config())
    benchmark = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    markdown = generator.to_markdown(benchmark)
    assert "Benchmark: internal-smoke-run" in markdown
    assert "Quality Gate" in markdown


def test_report_generator_html():
    generator = ReportGenerator(make_config())
    result = run_sync(RetrievalEvaluator(make_config()).evaluate_batch([retrieval_sample()]))
    html_out = generator.to_html(result)
    assert "<table>" in html_out
    assert "retrieval" in html_out
    runner = BenchmarkRunner(config=make_config())
    benchmark = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    html_bench = generator.to_html(benchmark)
    assert "Quality Gate" in html_bench


def test_report_generator_csv():
    generator = ReportGenerator(make_config())
    runner = BenchmarkRunner(config=make_config())
    benchmark = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    csv_out = generator.to_csv(benchmark)
    assert "evaluator,metric,value" in csv_out.splitlines()[0]
    assert "retrieval,mrr" in csv_out


def test_report_generator_unsupported_format():
    generator = ReportGenerator(make_config())
    result = run_sync(RetrievalEvaluator(make_config()).evaluate_batch([retrieval_sample()]))
    with pytest.raises(ReportGenerationError):
        generator.generate(result, formats=("pdf",), directory="/tmp")


def test_dashboard():
    dashboard = EvaluationDashboard(make_config())
    assert dashboard.snapshot()["records"] == 0
    runner = BenchmarkRunner(config=make_config())
    benchmark = run_sync(runner.run("internal-smoke", evaluators=["retrieval"]))
    dashboard.record(benchmark)
    snapshot = dashboard.snapshot()
    assert snapshot["records"] == 1
    assert "mrr" in snapshot["metrics"]
    assert dashboard.series("mrr") == [benchmark.summary()["mrr"]]
    assert dashboard.summary()["records"] == 1
    assert dashboard.history[0]["name"] == "internal-smoke-run"


def test_dashboard_records_evaluation_result():
    dashboard = EvaluationDashboard(make_config())
    result = run_sync(RetrievalEvaluator(make_config()).evaluate_batch([retrieval_sample()]))
    dashboard.record(result)
    assert dashboard.snapshot()["latest"]["name"] == "retrieval"


def test_factories():
    evaluator = create_evaluator("memory", config=make_config())
    assert isinstance(evaluator, MemoryEvaluator)
    orchestrator = create_orchestrator(config=make_config())
    assert isinstance(orchestrator, EvaluationOrchestrator)
    dataset = create_benchmark_dataset("ds", [retrieval_sample()], DatasetType.REGRESSION)
    assert dataset.dataset_type == DatasetType.REGRESSION
    assert dataset.name == "ds"


def test_load_benchmark_dataset(tmp_path):
    path = tmp_path / "external.json"
    dataset = builtin_fn()
    path.write_text(json.dumps(dataset.to_dict()))
    loaded = load_benchmark_dataset(str(path), name="external", dataset_type=DatasetType.PUBLIC)
    assert loaded.dataset_type == DatasetType.PUBLIC


def test_builtin_dataset_helpers():
    dataset = builtin_internal_dataset()
    assert len(dataset.samples) == 5
    assert dataset.description
    assert dataset.version == "1.0.0"


def test_evaluator_unknown_kind_registry_error():
    with pytest.raises(EvaluatorNotFoundError):
        create_evaluator("unknown")


def run_sync(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()
