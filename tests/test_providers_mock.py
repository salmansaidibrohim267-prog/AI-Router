import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.models import (
    ChatRequest, ChatResponse, ChatChoice, Message, Usage,
    EmbeddingRequest, EmbeddingResponse, EmbeddingData,
    StreamChunk, StreamChoice, HealthCheckResponse, ProviderStatus,
)


def make_mock_client():
    mc = MagicMock()
    mc.get = AsyncMock()
    mc.post = AsyncMock()
    mc.request = AsyncMock()
    mc.stream = MagicMock()
    return mc


def make_mock_http_response(json_data, status_code=200):
    r = MagicMock()
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    r.status_code = status_code
    return r


class AsyncIter:
    def __init__(self, items):
        self.items = list(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)
from app.providers.openrouter import OpenRouterProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider


@pytest.fixture
def chat_request():
    return ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="hello")],
    )


@pytest.fixture
def embed_request():
    return EmbeddingRequest(model="test-embed", input="hello world")


class TestOpenRouterProviderMock:
    @pytest.mark.asyncio
    async def test_chat_success(self, chat_request):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "id": "test-id",
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })
            resp = await provider.chat(chat_request)
            assert resp.id == "test-id"
            assert resp.choices[0].message.content == "hi"
            assert resp.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({"data": [{"id": "model1"}]})
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.HEALTHY
            assert health.latency_ms is not None

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            from httpx import TimeoutException
            mc.get.side_effect = TimeoutException("timeout")
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            mc.get.return_value = make_mock_http_response({
                "data": [{"id": "model1", "created": 123, "owned_by": "test"}]
            })
            mock_get.return_value = mc
            models = await provider.list_models()
            assert len(models) == 1
            assert models[0].id == "model1"

    @pytest.mark.asyncio
    async def test_stream_chat(self, chat_request):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.aiter_lines = MagicMock(return_value=AsyncIter([
                'data: {"id":"1","model":"m","choices":[{"index":0,"delta":{"content":"hi"}}]}',
                'data: [DONE]',
            ]))
            mock_context = MagicMock()
            mock_context.__aenter__.return_value = mock_response
            mock_client.stream.return_value = mock_context
            mock_get_client.return_value = mock_client
            chunks = []
            async for chunk in provider.stream_chat(chat_request):
                chunks.append(chunk)
            assert len(chunks) == 1
            assert chunks[0].choices[0].delta.get("content") == "hi"


class TestOllamaProviderMock:
    @pytest.mark.asyncio
    async def test_chat_success(self, chat_request):
        provider = OllamaProvider(base_url="http://localhost:11434")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "id": "test-id",
                "model": "test-model",
                "message": {"role": "assistant", "content": "hi"},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 5,
            })
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hi"
            assert resp.usage.prompt_tokens == 10
            assert resp.usage.completion_tokens == 5

    @pytest.mark.asyncio
    async def test_health_check_connect_error(self):
        provider = OllamaProvider(base_url="http://localhost:11434")
        with patch.object(provider, '_get_client', new_callable=AsyncMock) as mock_get:
            mc = make_mock_client()
            from httpx import ConnectError
            mc.get.side_effect = ConnectError("connection refused")
            mock_get.return_value = mc
            health = await provider.health_check()
            assert health.status == ProviderStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_embeddings(self, embed_request):
        provider = OllamaProvider(base_url="http://localhost:11434")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({"embedding": [0.1, 0.2, 0.3]})
            resp = await provider.embeddings(embed_request)
            assert len(resp.data) == 1
            assert resp.data[0].embedding == [0.1, 0.2, 0.3]


class TestAnthropicProviderMock:
    @pytest.mark.asyncio
    async def test_chat_success(self, chat_request):
        provider = AnthropicProvider(api_key="test-key")
        with patch.object(provider, '_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = make_mock_http_response({
                "id": "msg-1",
                "model": "claude-3",
                "content": [{"type": "text", "text": "hello back"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            })
            resp = await provider.chat(chat_request)
            assert resp.choices[0].message.content == "hello back"
            assert resp.usage.prompt_tokens == 10
            assert resp.usage.completion_tokens == 5

    @pytest.mark.asyncio
    async def test_embeddings_not_supported(self, embed_request):
        provider = AnthropicProvider(api_key="test-key")
        from app.exceptions import ProviderError
        with pytest.raises(ProviderError):
            await provider.embeddings(embed_request)

    @pytest.mark.asyncio
    async def test_stream_chat(self, chat_request):
        provider = AnthropicProvider(api_key="test-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.aiter_lines = MagicMock(return_value=AsyncIter([
                'data: {"type":"content_block_delta","message_id":"m1","delta":{"type":"text_delta","text":"hello"}}',
            ]))
            mock_context = MagicMock()
            mock_context.__aenter__.return_value = mock_response
            mock_client.stream.return_value = mock_context
            mock_get_client.return_value = mock_client
            chunks = []
            async for chunk in provider.stream_chat(chat_request):
                chunks.append(chunk)
            assert len(chunks) == 1


class TestProviderRequestErrors:
    @pytest.mark.asyncio
    async def test_request_retry_on_timeout(self, chat_request):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            from httpx import TimeoutException
            mock_client.request.side_effect = TimeoutException("timeout")
            mock_get_client.return_value = mock_client
            from app.exceptions import ProviderTimeoutError
            with pytest.raises(ProviderTimeoutError):
                await provider._request("POST", "/test")

    @pytest.mark.asyncio
    async def test_request_retry_on_connect_error(self, chat_request):
        provider = OpenAIProvider(api_key="test-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            from httpx import ConnectError
            mock_client.request.side_effect = ConnectError("connection failed")
            mock_get_client.return_value = mock_client
            from app.exceptions import ProviderUnavailableError
            with pytest.raises(ProviderUnavailableError):
                await provider._request("POST", "/test")

    @pytest.mark.asyncio
    async def test_request_401_auth_error(self):
        provider = OpenRouterProvider(api_key="bad-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            from httpx import HTTPStatusError, Request, Response
            mock_request = Request("POST", "http://test.com")
            mock_response = Response(401, request=mock_request)
            mock_client.request.side_effect = HTTPStatusError("unauthorized", request=mock_request, response=mock_response)
            mock_get_client.return_value = mock_client
            from app.exceptions import ProviderAuthError
            with pytest.raises(ProviderAuthError):
                await provider._request("POST", "/test")

    @pytest.mark.asyncio
    async def test_request_429_rate_limit(self):
        provider = OpenRouterProvider(api_key="test-key")
        with patch.object(provider, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            from httpx import HTTPStatusError, Request, Response
            mock_request = Request("POST", "http://test.com")
            mock_response = Response(429, request=mock_request, headers={"Retry-After": "30"})
            mock_client.request.side_effect = HTTPStatusError("rate limit", request=mock_request, response=mock_response)
            mock_get_client.return_value = mock_client
            from app.exceptions import ProviderRateLimitError
            with pytest.raises(ProviderRateLimitError):
                await provider._request("POST", "/test")


class TestProviderClose:
    @pytest.mark.asyncio
    async def test_close_with_client(self):
        provider = OpenRouterProvider(api_key="test-key")
        mock_client = AsyncMock()
        provider._client = mock_client
        await provider.close()
        mock_client.aclose.assert_called_once()
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        provider = OpenRouterProvider(api_key="test-key")
        await provider.close()
