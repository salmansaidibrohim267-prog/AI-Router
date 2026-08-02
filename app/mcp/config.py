from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MCPConfig:
    transport: str = "stdio"
    url: str = ""
    command: str = ""
    args: list[str] = None  # type: ignore[assignment]
    env: dict[str, str] = None  # type: ignore[assignment]
    timeout: float = 30.0
    request_timeout: float = 30.0
    connect_timeout: float = 10.0
    heartbeat_interval: float = 30.0
    heartbeat_timeout: float = 5.0
    reconnect_enabled: bool = True
    reconnect_max_attempts: int = 5
    reconnect_base_delay: float = 0.5
    reconnect_max_delay: float = 30.0
    retry_enabled: bool = True
    retry_max_attempts: int = 3
    retry_base_delay: float = 0.25
    auth_type: str = "none"
    api_key: str = ""
    api_key_header: str = "X-API-Key"
    bearer_token: str = ""
    oauth2_token: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_token_url: str = ""
    custom_headers: dict[str, str] = None  # type: ignore[assignment]
    protocol_version: str = "2025-03-26"
    client_name: str = "ai-router"
    client_version: str = "0.1.0"
    discover_on_connect: bool = True
    log_events: bool = True
    track_metrics: bool = True
    max_batch_size: int = 50

    def __post_init__(self) -> None:
        if self.args is None:
            self.args = []
        if self.env is None:
            self.env = {}
        if self.custom_headers is None:
            self.custom_headers = {}

    @classmethod
    def from_env(cls) -> MCPConfig:
        return cls(
            transport=os.getenv("MCP_TRANSPORT", "stdio"),
            url=os.getenv("MCP_URL", ""),
            command=os.getenv("MCP_COMMAND", ""),
            args=[a for a in os.getenv("MCP_ARGS", "").split(",") if a],
            timeout=float(os.getenv("MCP_TIMEOUT", "30")),
            request_timeout=float(os.getenv("MCP_REQUEST_TIMEOUT", "30")),
            connect_timeout=float(os.getenv("MCP_CONNECT_TIMEOUT", "10")),
            heartbeat_interval=float(os.getenv("MCP_HEARTBEAT_INTERVAL", "30")),
            reconnect_enabled=os.getenv("MCP_RECONNECT_ENABLED", "1") == "1",
            reconnect_max_attempts=int(os.getenv("MCP_RECONNECT_MAX_ATTEMPTS", "5")),
            retry_enabled=os.getenv("MCP_RETRY_ENABLED", "1") == "1",
            retry_max_attempts=int(os.getenv("MCP_RETRY_MAX_ATTEMPTS", "3")),
            auth_type=os.getenv("MCP_AUTH_TYPE", "none"),
            api_key=os.getenv("MCP_API_KEY", ""),
            api_key_header=os.getenv("MCP_API_KEY_HEADER", "X-API-Key"),
            bearer_token=os.getenv("MCP_BEARER_TOKEN", ""),
            oauth2_token=os.getenv("MCP_OAUTH2_TOKEN", ""),
            custom_headers={
                k.split("MCP_CUSTOM_HEADER_", 1)[1].replace("_", "-").title(): v
                for k, v in os.environ.items()
                if k.startswith("MCP_CUSTOM_HEADER_")
            },
            protocol_version=os.getenv("MCP_PROTOCOL_VERSION", "2025-03-26"),
            client_name=os.getenv("MCP_CLIENT_NAME", "ai-router"),
            discover_on_connect=os.getenv("MCP_DISCOVER_ON_CONNECT", "1") == "1",
            log_events=os.getenv("MCP_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("MCP_TRACK_METRICS", "1") == "1",
        )
