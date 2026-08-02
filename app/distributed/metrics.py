from prometheus_client import Counter, Gauge, Histogram

tasks_total = Counter(
    "dist_tasks_total",
    "Total tasks created",
    ["task_type", "state"],
)

tasks_running = Gauge(
    "dist_tasks_running",
    "Currently running tasks",
)

tasks_completed = Counter(
    "dist_tasks_completed",
    "Total completed tasks",
    ["task_type"],
)

tasks_failed = Counter(
    "dist_tasks_failed",
    "Total failed tasks",
    ["task_type", "error_type"],
)

tasks_retry = Counter(
    "dist_tasks_retry",
    "Total task retries",
    ["task_type"],
)

worker_online = Gauge(
    "dist_worker_online",
    "Number of online workers",
)

worker_offline = Gauge(
    "dist_worker_offline",
    "Number of offline workers",
)

queue_length = Gauge(
    "dist_queue_length",
    "Queue length by priority",
    ["priority"],
)

queue_latency_seconds = Histogram(
    "dist_queue_latency_seconds",
    "Time tasks spend in queue",
    ["task_type"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

scheduler_leader = Gauge(
    "dist_scheduler_leader",
    "Scheduler leader status (1=leader, 0=not)",
)

tool_calls = Counter(
    "dist_tool_calls",
    "Tool call count",
    ["tool_name", "success"],
)

approval_pending = Gauge(
    "dist_approval_pending",
    "Number of pending approvals",
)

workflow_running = Gauge(
    "dist_workflow_running",
    "Number of running workflows",
)

lease_expired_total = Counter(
    "dist_lease_expired_total",
    "Total lease expirations",
)

dlq_size = Gauge(
    "dist_dlq_size",
    "Dead letter queue size",
)

idempotency_hit = Counter(
    "dist_idempotency_hit",
    "Idempotency key hits (duplicates prevented)",
)
