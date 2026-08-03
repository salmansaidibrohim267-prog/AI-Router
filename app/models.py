"""Pydantic models for AI Router."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Supported task types for routing."""

    CHAT = "chat"
    CODING = "coding"
    ARCHITECTURE = "architecture"
    ANALYSIS = "analysis"
    UNKNOWN = "unknown"


class ProviderStatus(str, Enum):
    """Provider health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


class MessageRole(str, Enum):
    """Message roles for chat."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """Chat message."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    """Chat completion request."""

    model: str
    messages: list[Message]
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float | None = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(default=0.0, ge=-2.0, le=2.0)
    stop: list[str] | str | None = None
    stream: bool = False
    user: str | None = None
    metadata: dict[str, Any] | None = None
    prompt_token_estimate: int | None = None


class ChatChoice(BaseModel):
    """Chat completion choice."""

    index: int
    message: Message
    finish_reason: str | None = None


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_tokens: int = 0
    reasoning_tokens: int = 0


class ChatResponse(BaseModel):
    """Chat completion response."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: list[ChatChoice]
    usage: Usage | None = None
    system_fingerprint: str | None = None


class StreamChoice(BaseModel):
    """Stream chunk choice."""

    index: int
    delta: dict
    finish_reason: str | None = None


class StreamChunk(BaseModel):
    """Streaming response chunk."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: list[StreamChoice]
    system_fingerprint: str | None = None
    usage: Usage | None = None
    metadata: dict[str, Any] | None = None


class EmbeddingRequest(BaseModel):
    """Embedding request."""

    model: str
    input: str | list[str]
    user: str | None = None
    dimensions: int | None = None
    encoding_format: Literal["float", "base64"] = "float"


class EmbeddingData(BaseModel):
    """Embedding data."""

    object: Literal["embedding"] = "embedding"
    embedding: list[float]
    index: int


class EmbeddingResponse(BaseModel):
    """Embedding response."""

    object: Literal["list"] = "list"
    data: list[EmbeddingData]
    model: str
    usage: Usage


class ModelInfo(BaseModel):
    """Model information."""

    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str
    provider: str
    display_name: str | None = None
    description: str | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    supports_streaming: bool = True
    supports_embeddings: bool = False
    supports_functions: bool = False
    pricing: dict[str, float] | None = None


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: ProviderStatus
    provider: str
    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=datetime.now)
    details: dict[str, Any] | None = None
    error: str | None = None


class ProviderConfig(BaseModel):
    """Provider configuration."""

    name: str
    display_name: str
    model: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 3
    enabled: bool = True
    priority: int = 100
    models: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class TaskConfig(BaseModel):
    """Task routing configuration."""

    primary: ProviderConfig
    fallback: list[ProviderConfig] = Field(default_factory=list)


class RouterConfig(BaseModel):
    """Router configuration."""

    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    default_task: str = "chat"
    scoring: dict[str, dict[str, int]] = Field(default_factory=dict)
    cache_ttl: int = 300
    rate_limit: int = 100
    rate_limit_window: int = 60
    health_check_interval: int = 30
    timeout: float = 60.0


class LogEntry(BaseModel):
    """Structured log entry."""

    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: str
    response_id: str | None = None
    provider: str
    model: str
    task: str
    latency_ms: float
    success: bool
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    status_code: int = 200
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatsSummary(BaseModel):
    """Statistics summary."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    provider_usage: dict[str, int] = Field(default_factory=dict)
    model_usage: dict[str, int] = Field(default_factory=dict)
    task_usage: dict[str, int] = Field(default_factory=dict)
    provider_ranking: list[dict] = Field(default_factory=list)
    model_ranking: list[dict] = Field(default_factory=list)


class CacheEntry(BaseModel):
    """Cache entry."""

    key: str
    value: Any
    created_at: float = 0.0
    expires_at: float | None = None
    ttl: int = 300


class ReloadConfigResponse(BaseModel):
    """Config reload response."""

    success: bool
    message: str
    config_hash: str
    loaded_at: datetime = Field(default_factory=datetime.now)


class BenchmarkRequest(BaseModel):
    """Benchmark run request."""

    model: str = "gpt-4o-mini"
    provider: str | None = None
    num_requests: int = 10
    concurrency: int = 5
    stream: bool = False
    prompt: str = "Say hello in one word"


class BenchmarkResponse(BaseModel):
    """Benchmark run response."""

    target: str = "internal"
    num_requests: int
    concurrency: int
    stream: bool
    duration_seconds: float
    average_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_reqs_per_sec: float
    success_rate: float
    errors: int
    fallback_count: int
    provider_success: dict[str, int] = Field(default_factory=dict)
    provider_failure: dict[str, int] = Field(default_factory=dict)
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
