import pytest

from app.orchestration.debate import DebateEngine
from app.orchestration.models import DebateResult


class TestDebateEngine:
    def setup_method(self):
        self.engine = DebateEngine()

    async def test_both_providers_succeed(self):
        class FakeRouter:
            call_count = 0
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                self.call_count += 1
                content = "Argument from provider A" if self.call_count <= 2 else '{"winner": "A", "reason": "Better quality"}'
                return ChatResponse(
                    id="r1", model="test",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content=content), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )

        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Debate this")], model="gpt-4")
        result = await self.engine.run_debate(req, "openai", "anthropic", FakeRouter())
        assert result.argument_a != ""
        assert result.argument_b != ""

    async def test_first_provider_fails(self):
        class FailingRouter:
            call_count = 0
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                self.call_count += 1
                if self.call_count == 1:
                    raise Exception("provider A failed")
                return ChatResponse(
                    id="r1", model="test",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="Argument B"), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )

        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Debate this")], model="gpt-4")
        result = await self.engine.run_debate(req, "openai", "anthropic", FailingRouter())
        assert result.winner == "anthropic"

    async def test_both_providers_fail(self):
        class FailingRouter:
            async def chat(self, request):
                raise Exception("all providers failed")

        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Debate this")], model="gpt-4")
        result = await self.engine.run_debate(req, "openai", "anthropic", FailingRouter())
        assert result.winner == ""
        assert "failed" in result.reviewer_notes

    async def test_debate_result_structure(self):
        class FakeRouter:
            call_count = 0
            async def chat(self, request):
                from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
                self.call_count += 1
                if self.call_count <= 2:
                    content = "Argument content"
                else:
                    content = '{"winner": "A", "reason": "Clear winner"}'
                return ChatResponse(
                    id="r1", model="test",
                    choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content=content), finish_reason="stop")],
                    usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                )

        from app.models import ChatRequest, Message as ChatMsg, MessageRole
        req = ChatRequest(messages=[ChatMsg(role=MessageRole.USER, content="Debate this")], model="gpt-4")
        result = await self.engine.run_debate(req, "openai", "anthropic", FakeRouter())
        assert isinstance(result, DebateResult)
        assert result.provider_a == "openai"
        assert result.provider_b == "anthropic"
        assert result.final_content != ""
