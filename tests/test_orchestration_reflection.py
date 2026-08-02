import pytest

from app.orchestration.reflection import ReflectionEngine
from app.orchestration.models import AgentResult, ReflectionScore


class FakeReflectionRouter:
    def __init__(self, scores: str = '{"correctness": 0.9, "hallucination": 0.8, "completeness": 0.9}'):
        self._scores = scores

    async def chat(self, request):
        from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
        return ChatResponse(
            id="r1",
            model="test",
            choices=[ChatChoice(
                index=0,
                message=Message(role=MessageRole.ASSISTANT, content=self._scores),
                finish_reason="stop",
            )],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class TestReflectionEngine:
    async def test_evaluate_good_response(self):
        engine = ReflectionEngine({"threshold": 0.5})
        router = FakeReflectionRouter('{"correctness": 0.9, "hallucination": 0.8, "completeness": 0.9}')
        result = AgentResult(agent="test", step="s1", content="Good response")
        score = await engine.evaluate(result, router)
        assert score.overall > 0.5
        assert score.should_retry is False

    async def test_evaluate_poor_response(self):
        engine = ReflectionEngine({"threshold": 0.9})
        router = FakeReflectionRouter('{"correctness": 0.3, "hallucination": 0.4, "completeness": 0.2}')
        result = AgentResult(agent="test", step="s1", content="Poor response")
        score = await engine.evaluate(result, router)
        assert score.overall < 0.5
        assert score.should_retry is True

    def test_parse_scores_json(self):
        engine = ReflectionEngine()
        scores = engine._parse_scores('{"correctness": 0.8, "hallucination": 0.7, "completeness": 0.9}')
        assert scores["correctness"] == 0.8
        assert scores["hallucination"] == 0.7
        assert scores["completeness"] == 0.9

    def test_parse_scores_fallback(self):
        engine = ReflectionEngine()
        scores = engine._parse_scores('Some text "correctness": 0.75 something "hallucination": 0.65 "completeness": 0.85')
        assert scores["correctness"] == 0.75
        assert scores["hallucination"] == 0.65
        assert scores["completeness"] == 0.85

    def test_parse_scores_invalid(self):
        engine = ReflectionEngine()
        scores = engine._parse_scores("no numbers here")
        assert scores["correctness"] == 0.5
        assert scores["hallucination"] == 0.5
        assert scores["completeness"] == 0.5

    async def test_evaluate_empty_content(self):
        engine = ReflectionEngine()
        router = FakeReflectionRouter()
        result = AgentResult(agent="test", step="s1", content="")
        score = await engine.evaluate(result, router)
        assert score.overall == 0.0
        assert score.should_retry is True

    def test_should_retry_below_threshold(self):
        engine = ReflectionEngine({"threshold": 0.7, "max_retries": 2})
        assert engine._threshold == 0.7
        assert engine._max_retries == 2

    async def test_reflect_and_retry_improves(self):
        class RetryRouter:
            def __init__(self):
                self.call_count = 0
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                self.call_count += 1
                return ChatResponse(
                    id="r1",
                    model="test",
                    choices=[ChatChoice(
                        index=0,
                        message=Message(role=MessageRole.ASSISTANT, content='{"correctness": 0.9, "hallucination": 0.8, "completeness": 0.9}'),
                        finish_reason="stop",
                    )],
                    usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )

        engine = ReflectionEngine({"threshold": 0.5, "max_retries": 3})
        router = RetryRouter()
        result = AgentResult(agent="test", step="s1", content="Initial response")
        final, score = await engine.reflect_and_retry(result, router)
        assert score.should_retry is False
        assert score.overall > 0.5
