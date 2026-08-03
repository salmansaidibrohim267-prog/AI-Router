from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPTransportType(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    WEBSOCKET = "websocket"
    SSE = "sse"


class MCPAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    CUSTOM_HEADERS = "custom_headers"


class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class MCPEventType(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    RECONNECTED = "reconnected"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_FAILED = "heartbeat_failed"
    TOOL_CALLED = "tool_called"
    TOOL_FAILED = "tool_failed"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_WATCHED = "resource_watched"
    RESOURCE_UNWATCHED = "resource_unwatched"
    PROMPT_RENDERED = "prompt_rendered"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    ERROR = "error"


@dataclass
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPTool:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            input_schema=dict(data.get("inputSchema", data.get("input_schema", {}))),
            annotations=dict(data.get("annotations", {})),
        )


@dataclass
class MCPResource:
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "text/plain"
    text: str = ""
    blob: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
            "text": self.text[:200],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPResource:
        return cls(
            uri=str(data.get("uri", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            mime_type=str(data.get("mimeType", data.get("mime_type", "text/plain"))),
            text=str(data.get("text", "")),
            blob=str(data.get("blob", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class MCPPrompt:
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": list(self.arguments),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPPrompt:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            arguments=list(data.get("arguments", [])),
        )


@dataclass
class MCPPromptMessage:
    role: str = "user"
    content: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class MCPRenderedPrompt:
    name: str
    description: str = ""
    messages: list[MCPPromptMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPRenderedPrompt:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            messages=[
                MCPPromptMessage(
                    role=str(m.get("role", "user")),
                    content=dict(m.get("content", {})),
                )
                for m in data.get("messages", [])
            ],
        )


@dataclass
class MCPCapabilities:
    tools: bool = False
    resources: bool = False
    prompts: bool = False
    streaming: bool = False
    logging: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": self.tools,
            "resources": self.resources,
            "prompts": self.prompts,
            "streaming": self.streaming,
            "logging": self.logging,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPCapabilities:
        return cls(
            tools=bool(data.get("tools", False)),
            resources=bool(data.get("resources", False)),
            prompts=bool(data.get("prompts", False)),
            streaming=bool(data.get("streaming", False)),
            logging=bool(data.get("logging", False)),
        )


@dataclass
class MCPServerInfo:
    server_name: str = ""
    server_version: str = ""
    protocol_version: str = ""
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)
    instructions: str = ""
    discovered_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "server_version": self.server_version,
            "protocol_version": self.protocol_version,
            "capabilities": self.capabilities.to_dict(),
            "instructions": self.instructions,
            "discovered_at": self.discovered_at,
        }


@dataclass
class MCPCallResult:
    tool_name: str
    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    structured_content: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        parts: list[str] = []
        for block in self.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                text = str(block["text"])
                if block.get("type") == "text" or not parts:
                    parts.append(text)
                else:
                    parts[-1] += text
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "content": list(self.content),
            "is_error": self.is_error,
            "structured_content": self.structured_content,
        }


@dataclass
class MCPStreamEvent:
    event_type: str
    tool_name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    is_final: bool = False

    @property
    def text(self) -> str:
        return str(self.data.get("text", ""))


@dataclass
class MCPConnectionHealth:
    name: str = ""
    connected: bool = False
    state: MCPConnectionState = MCPConnectionState.DISCONNECTED
    latency_ms: float = 0.0
    last_error: str = ""
    tool_count: int = 0
    resource_count: int = 0
    prompt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "state": self.state.value,
            "latency_ms": round(self.latency_ms, 4),
            "last_error": self.last_error,
            "tool_count": self.tool_count,
            "resource_count": self.resource_count,
            "prompt_count": self.prompt_count,
        }


@dataclass
class MCPMetrics:
    total_connections: int = 0
    total_disconnections: int = 0
    total_reconnects: int = 0
    total_pings: int = 0
    total_tool_calls: int = 0
    total_batch_calls: int = 0
    total_stream_calls: int = 0
    total_resources_listed: int = 0
    total_resources_read: int = 0
    total_resources_watched: int = 0
    total_prompts_listed: int = 0
    total_prompts_rendered: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0
    heartbeats: int = 0
    heartbeat_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_connections": self.total_connections,
            "total_disconnections": self.total_disconnections,
            "total_reconnects": self.total_reconnects,
            "total_pings": self.total_pings,
            "total_tool_calls": self.total_tool_calls,
            "total_batch_calls": self.total_batch_calls,
            "total_stream_calls": self.total_stream_calls,
            "total_resources_listed": self.total_resources_listed,
            "total_resources_read": self.total_resources_read,
            "total_resources_watched": self.total_resources_watched,
            "total_prompts_listed": self.total_prompts_listed,
            "total_prompts_rendered": self.total_prompts_rendered,
            "total_errors": self.total_errors,
            "total_latency_ms": round(self.total_latency_ms, 4),
            "heartbeats": self.heartbeats,
            "heartbeat_failures": self.heartbeat_failures,
        }
