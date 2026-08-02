import pytest

from app.orchestration.consensus import VotingEngine, ConsensusEngine
from app.orchestration.models import ConsensusResult, VoteScore


class TestVotingEngine:
    def setup_method(self):
        self.voting = VotingEngine()

    def test_score_quality_long_content(self):
        score = self.voting._score_quality("A" * 100)
        assert score >= 0.5

    def test_score_quality_empty(self):
        score = self.voting._score_quality("")
        assert score == 0.0

    def test_score_quality_short_content(self):
        score = self.voting._score_quality("Hi")
        assert score < 0.5

    def test_score_latency_fast(self):
        score = self.voting._score_latency(100)
        assert score >= 0.9

    def test_score_latency_slow(self):
        score = self.voting._score_latency(15000)
        assert score <= 0.3

    def test_score_latency_zero(self):
        score = self.voting._score_latency(0)
        assert score == 0.5

    def test_score_response_returns_votescore(self):
        score = self.voting.score_response("A good detailed response.", 500, "openai", "gpt-4")
        assert isinstance(score, VoteScore)
        assert score.overall > 0

    def test_score_response_all_components(self):
        score = self.voting.score_response("Test content", 1000, "openai", "gpt-4")
        assert hasattr(score, "quality")
        assert hasattr(score, "cost")
        assert hasattr(score, "latency")
        assert hasattr(score, "reliability")
        assert hasattr(score, "overall")

    def test_choose_winner(self):
        votes = [
            ("openai", "gpt-4", "Response A", VoteScore(quality=0.5, cost=0.5, latency=0.5, reliability=0.5, overall=0.5)),
            ("anthropic", "claude", "Response B", VoteScore(quality=0.9, cost=0.5, latency=0.9, reliability=0.8, overall=0.8)),
        ]
        winner = self.voting.choose_winner(votes)
        assert winner[0] == "anthropic"

    def test_choose_winner_empty(self):
        winner = self.voting.choose_winner([])
        assert winner[0] == ""


class TestConsensusEngine:
    def setup_method(self):
        self.engine = ConsensusEngine()

    def test_initialization(self):
        assert self.engine is not None

    async def test_first_success_strategy(self):
        class FakeRouter:
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                return ChatResponse(
                    id="r1", model="gpt-4",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="response"), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )

        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Hello")], model="gpt-4")
        result = await self.engine.run_consensus(req, ["openai"], FakeRouter(), "first_success")
        assert result.strategy == "first_success"
        assert result.content == "response"

    async def test_best_latency_strategy(self):
        class FakeRouter:
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                return ChatResponse(
                    id="r1", model="gpt-4",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="fast"), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )
        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Hello")], model="gpt-4")
        result = await self.engine.run_consensus(req, ["openai"], FakeRouter(), "best_latency")
        assert result.strategy == "best_latency"

    async def test_consensus_with_all_failures(self):
        class FailingRouter:
            async def chat(self, request):
                raise Exception("provider failed")
        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Hello")], model="gpt-4")
        result = await self.engine.run_consensus(req, ["openai", "anthropic"], FailingRouter())
        assert result.content == ""

    async def test_consensus_no_providers(self):
        class FakeRouter:
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                return ChatResponse(
                    id="r1", model="gpt-4",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="resp"), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )
        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Hello")], model="gpt-4")
        result = await self.engine.run_consensus(req, [], FakeRouter())
        assert result.content == ""
