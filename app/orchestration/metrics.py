from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

orchestrator_requests_total = Counter(
    "orchestrator_requests_total",
    "Total orchestration requests",
    ["mode"],
)

planner_latency_seconds = Histogram(
    "orchestrator_planner_latency_seconds",
    "Planner execution latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

execution_latency_seconds = Histogram(
    "orchestrator_execution_latency_seconds",
    "Execution engine latency",
    ["mode"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

agent_latency_seconds = Histogram(
    "orchestrator_agent_latency_seconds",
    "Per-agent execution latency",
    ["agent"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

reflection_retry_total = Counter(
    "orchestrator_reflection_retry_total",
    "Number of reflection-triggered retries",
)

consensus_count_total = Counter(
    "orchestrator_consensus_count_total",
    "Number of consensus executions",
    ["strategy"],
)

debate_count_total = Counter(
    "orchestrator_debate_count_total",
    "Number of debate executions",
)

workflow_count_total = Counter(
    "orchestrator_workflow_count_total",
    "Number of workflow executions",
)

orchestrator_active_requests = Gauge(
    "orchestrator_active_requests",
    "Active orchestration requests",
    ["mode"],
)

task_queue_depth = Gauge(
    "orchestrator_task_queue_depth",
    "Task queue depth by state",
    ["state"],
)

worker_utilization = Gauge(
    "orchestrator_worker_utilization",
    "Worker utilization",
    ["worker_id"],
)

task_duration_seconds = Histogram(
    "orchestrator_task_duration_seconds",
    "Task execution duration",
    ["task_type", "state"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

memory_usage_bytes = Gauge(
    "orchestrator_memory_usage_bytes",
    "Memory store usage in bytes",
    ["store_type"],
)

compression_ratio = Gauge(
    "orchestrator_compression_ratio",
    "Context compression ratio",
)

budget_remaining = Gauge(
    "orchestrator_budget_remaining",
    "Remaining budget in USD",
)

budget_tokens_remaining = Gauge(
    "orchestrator_budget_tokens_remaining",
    "Remaining token budget",
)

approval_waiting_total = Gauge(
    "orchestrator_approval_waiting_total",
    "Number of pending approval checkpoints",
)

execution_graph_count = Gauge(
    "orchestrator_execution_graph_count",
    "Number of execution graphs generated",
)

tool_call_total = Counter(
    "orchestrator_tool_call_total",
    "Tool call count",
    ["tool_name", "success"],
)

compression_count_total = Counter(
    "orchestrator_compression_count_total",
    "Context compression count",
)
