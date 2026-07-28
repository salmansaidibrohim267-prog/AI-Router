import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.models import (
    ChatRequest, Message, EmbeddingRequest,
    ProviderStatus,
)
from app.providers.openai import OpenAIProvider
from app.providers.google import GoogleProvider
from app.providers.groq import GroqProvider
from app.providers.mistral import MistralProvider


class AsyncIter:
    def __init__(self, items):
        self.items = list(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


@pytest.fixture
def chat_request():
    return ChatRequest(model="test-model", messages=[Message(role="user", content="hello")])


@pytest.fixture
def embed_request():
    return EmbeddingRequest(model="test-embed", input="hello world")


def make_mock_http_response(json_data, status_code=200):
    r = MagicMock()
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    r.status_code = status_code
    return r


def make_mock_client():
    mc = MagicMock()
    mc.get = AsyncMock()
    mc.post = AsyncMock()
    mc.request = AsyncMock()
    mc.stream = MagicMock()
    return mc


class TestOpenAIProviderMock:
    @pytest.mark.asyncio
    async def test_chat(self, chat_request):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "id": "1", "model": "m",
                "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            })
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hi"
            assert resp.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_embeddings(self, embed_request):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "data": [{"embedding": [0.1, 0.2], "index": 0}],
                "model": "m",
                "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
            })
            resp = await provider.embeddings(embed_request)
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "m1"}]})
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            from httpx import TimeoutException
            mc.get.side_effect = TimeoutException("timeout")
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "gpt-4", "created": 123, "owned_by": "openai"}]})
            mock_get.return_value = mc
            models = await provider.list_models()
            assert len(models) == 1

    @pytest.mark.asyncio
    async def test_stream(self, chat_request):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.aiter_lines = MagicMock(return_value=AsyncIter([
                'data: {"id":"1","model":"m","choices":[{"index":0,"delta":{"content":"hi"}}]}',
                'data: [DONE]',
            ]))
            ctx = MagicMock()
            ctx.__aenter__.return_value = r
            mc.stream.return_value = ctx
            mock_get.return_value = mc
            chunks = [c async for c in provider.stream_chat(chat_request)]
            assert len(chunks) == 1


class TestGoogleProviderMock:
    @pytest.mark.asyncio
    async def test_chat(self, chat_request):
        provider = GoogleProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "candidates": [{"content": {"parts": [{"text": "hello back"}]}, "finishReason": "stop"}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 10, "totalTokenCount": 15},
            })
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hello back"

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = GoogleProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"models": [{"name": "models/gemini-pro"}]})
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_embeddings(self, embed_request):
        provider = GoogleProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({"embedding": {"values": [0.1, 0.2]}})
            resp = await provider.embeddings(embed_request)
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = GoogleProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"models": [{"name": "models/gemini-pro", "displayName": "Gemini Pro", "supportedGenerationMethods": ["generateContent", "streamGenerateContent"]}]})
            mock_get.return_value = mc
            models = await provider.list_models()
            assert len(models) == 1


class TestGroqProviderMock:
    @pytest.mark.asyncio
    async def test_chat(self, chat_request):
        provider = GroqProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({"id": "1", "model": "m", "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}})
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hi"

    @pytest.mark.asyncio
    async def test_embeddings_not_supported(self, embed_request):
        provider = GroqProvider(api_key="test-key")
        from app.exceptions import ProviderError
        with pytest.raises(ProviderError):
            await provider.embeddings(embed_request)

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = GroqProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "m1"}]})
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = GroqProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "llama3", "created": 123, "owned_by": "groq"}]})
            mock_get.return_value = mc
            models = await provider.list_models()
            assert len(models) == 1


class TestMistralProviderMock:
    @pytest.mark.asyncio
    async def test_chat(self, chat_request):
        provider = MistralProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({"id": "1", "model": "m", "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}})
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hi"

    @pytest.mark.asyncio
    async def test_embeddings(self, embed_request):
        provider = MistralProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({"data": [{"embedding": [0.1, 0.2], "index": 0}], "model": "m", "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5}})
            resp = await provider.embeddings(embed_request)
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = MistralProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "m1"}]})
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = MistralProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "mistral-large", "created": 123, "owned_by": "mistral"}]})
            mock_get.return_value = mc
            models = await provider.list_models()
            assert len(models) == 1
