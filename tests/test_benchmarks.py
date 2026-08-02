"""Tests for the benchmark suites (Stage 10.10)."""

import pytest

from benchmarks.suites import (
    BenchmarkReport,
    ConcurrencySuite,
    CpuSuite,
    FailoverSuite,
    LatencySuite,
    MemorySuite,
    RagDoc,
    RagQualitySuite,
    SuiteResult,
    SuiteRunner,
    ThroughputSuite,
    mean,
    percentile,
)


class TestStats:
    def test_mean(self):
        assert mean([1.0, 2.0, 3.0]) == 2.0
        assert mean([]) == 0.0

    def test_percentile(self):
        values = list(range(100))
        assert percentile(values, 0.50) == 50
        assert percentile(values, 0.95) == 95
        assert percentile([], 0.5) == 0.0


class TestThroughputSuite:
    def test_run(self):
        suite = ThroughputSuite(duration=0.05)
        result = suite.run(lambda: None)
        assert result.name == "throughput"
        assert result.metrics["requests_per_second"] > 0
        assert result.metrics["requests"] > 0


class TestLatencySuite:
    def test_run(self):
        suite = LatencySuite(iterations=10)
        result = suite.run(lambda: None)
        assert result.name == "latency"
        assert result.metrics["iterations"] == 10.0
        assert 0 <= result.metrics["mean_ms"] <= result.metrics["max_ms"]


class TestMemorySuite:
    def test_run(self):
        suite = MemorySuite(iterations=100, alloc_bytes=128)
        result = suite.run(lambda: None)
        assert result.name == "memory"
        assert result.metrics["peak_bytes"] >= 0


class TestCpuSuite:
    def test_run(self):
        suite = CpuSuite(loops=1000)
        result = suite.run(lambda: 1 + 1)
        assert result.name == "cpu"
        assert result.metrics["loops"] == 1000.0
        assert result.metrics["loops_per_second"] > 0


class TestConcurrencySuite:
    def test_run(self):
        suite = ConcurrencySuite(workers=4, per_worker=5)
        result = suite.run(lambda: None)
        assert result.passed is True
        assert result.metrics["total_requests"] == 20.0
        assert result.metrics["errors"] == 0.0

    def test_run_with_errors(self):
        def flaky():
            raise RuntimeError("boom")

        suite = ConcurrencySuite(workers=2, per_worker=3)
        result = suite.run(flaky)
        assert result.passed is False
        assert result.metrics["errors"] == 6.0


class TestFailoverSuite:
    def test_recovery(self):
        state = {"failing": True, "until": 0.0}

        def flaky():
            if state["failing"]:
                raise RuntimeError("down")

        suite = FailoverSuite(failure_seconds=0.05, probe_interval=0.005)
        state["until"] = 0
        result = suite.run(flaky)
        assert result.passed is False

    def test_recovery_after_window(self):
        suite = FailoverSuite(failure_seconds=0.05, probe_interval=0.005)
        state = {"calls": 0}

        def target():
            state["calls"] += 1
            if state["calls"] < 3:
                raise RuntimeError("down")

        result = suite.run(target)
        assert result.passed is True
        assert result.metrics["recovered"] == 1.0
        assert result.metrics["recovery_ms"] > 0


class TestRagQualitySuite:
    @staticmethod
    def _term_retriever(corpus):
        def retriever(query):
            terms = [t for t in query.lower().split() if len(t) > 3]
            best, best_score = None, -1
            for doc in corpus:
                words = doc.text.lower().split()
                score = sum(1 for t in terms if any(w.startswith(t) or t.startswith(w) for w in words))
                if score > best_score:
                    best, best_score = doc, score
            return [best] if best is not None else []

        return retriever

    def test_perfect_retrieval(self):
        suite = RagQualitySuite()
        result = suite.run(self._term_retriever(suite.corpus))
        assert result.metrics["precision"] == 1.0
        assert result.metrics["recall"] == 1.0
        assert result.passed is True

    def test_retrieval_miss(self):
        corpus = [RagDoc("d1", "a"), RagDoc("d2", "b")]
        queries = [("q", "d1")]
        suite = RagQualitySuite(corpus=corpus, queries=queries)
        result = suite.run(lambda query: [corpus[1]])
        assert result.metrics["precision"] == 0.0
        assert result.metrics["recall"] == 0.0
        assert result.passed is False

    def test_f1(self):
        suite = RagQualitySuite()
        result = suite.run(lambda query: [suite.corpus[0]])
        assert result.metrics["f1"] == pytest.approx(0.25, abs=0.001)

    def test_empty_retrieval(self):
        suite = RagQualitySuite()
        result = suite.run(lambda query: [])
        assert result.metrics["precision"] == 0.0
        assert result.metrics["recall"] == 0.0


class TestSuiteRunner:
    def test_run_all(self):
        runner = SuiteRunner(target=lambda: None)
        report = runner.run(["throughput", "latency", "cpu"])
        assert isinstance(report, BenchmarkReport)
        assert len(report.results) == 3
        assert report.overall_passed() is True

    def test_run_all_default(self):
        runner = SuiteRunner(target=lambda: None)
        report = runner.run(["throughput"])
        assert report.results[0].name == "throughput"

    def test_requires_target(self):
        with pytest.raises(ValueError):
            SuiteRunner().run(["throughput"])

    def test_unknown_suite_raises(self):
        runner = SuiteRunner(target=lambda: None)
        with pytest.raises(ValueError):
            runner.run(["bogus"])

    def test_register_custom(self):
        runner = SuiteRunner(target=lambda: None)
        runner.register("custom", ThroughputSuite(duration=0.01))
        report = runner.run(["custom"])
        assert report.results[0].name == "throughput"

    def test_target_name(self):
        runner = SuiteRunner(target=lambda: None, target_name="bench")
        assert runner.run(["throughput"]).target_name == "bench"

    def test_bad_suite_return_raises(self):
        runner = SuiteRunner(target=lambda: None)

        class BadSuite:
            def run(self, target):
                return 42

        runner.register("bad", BadSuite())
        with pytest.raises(TypeError):
            runner.run(["bad"])

    def test_report_to_dict(self):
        runner = SuiteRunner(target=lambda: None)
        report = runner.run(["throughput"])
        data = report.to_dict()
        assert data["overall_passed"] is True
        assert data["results"][0]["name"] == "throughput"


class TestBenchmarkCli:
    def test_main_text_output(self, capsys):
        from benchmarks.suites.cli import main

        code = main(["--target-name", "t", "--suites", "throughput"])
        out = capsys.readouterr().out
        assert code == 0
        assert "Benchmark report for t" in out
        assert "[PASS] throughput" in out

    def test_main_json_output(self, capsys):
        import json

        from benchmarks.suites.cli import main

        code = main(["--suites", "throughput", "--json"])
        out = capsys.readouterr().out
        assert code == 0
        data = json.loads(out)
        assert data["overall_passed"] is True

    def test_main_with_latency_iterations(self, capsys):
        from benchmarks.suites.cli import main

        code = main(["--suites", "latency", "--iterations", "5"])
        out = capsys.readouterr().out
        assert code == 0
        assert "latency" in out

    def test_main_unknown_suite_raises(self):
        from benchmarks.suites.cli import main

        with pytest.raises(ValueError):
            main(["--suites", "bogus"])
