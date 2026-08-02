from __future__ import annotations

from app.mcp.models import MCPMetrics


class MCPMetricsTracker:
    def __init__(self):
        self._metrics = MCPMetrics()

    def record_connection(self) -> None:
        self._metrics.total_connections += 1

    def record_disconnection(self) -> None:
        self._metrics.total_disconnections += 1

    def record_reconnect(self) -> None:
        self._metrics.total_reconnects += 1

    def record_ping(self, latency_ms: float = 0.0) -> None:
        self._metrics.total_pings += 1
        self._metrics.total_latency_ms += latency_ms

    def record_tool_call(self, latency_ms: float = 0.0) -> None:
        self._metrics.total_tool_calls += 1
        self._metrics.total_latency_ms += latency_ms

    def record_batch_call(self, calls: int) -> None:
        self._metrics.total_batch_calls += 1
        self._metrics.total_tool_calls += calls

    def record_stream_call(self) -> None:
        self._metrics.total_stream_calls += 1

    def record_resources_listed(self) -> None:
        self._metrics.total_resources_listed += 1

    def record_resource_read(self) -> None:
        self._metrics.total_resources_read += 1

    def record_resource_watched(self) -> None:
        self._metrics.total_resources_watched += 1

    def record_prompts_listed(self) -> None:
        self._metrics.total_prompts_listed += 1

    def record_prompt_rendered(self) -> None:
        self._metrics.total_prompts_rendered += 1

    def record_heartbeat(self) -> None:
        self._metrics.heartbeats += 1

    def record_heartbeat_failure(self) -> None:
        self._metrics.heartbeat_failures += 1

    def record_error(self) -> None:
        self._metrics.total_errors += 1

    def get_metrics(self) -> MCPMetrics:
        return self._metrics
