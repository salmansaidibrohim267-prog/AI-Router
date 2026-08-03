# AI Router — Sample Knowledge Document

This document is a factual primer about the AI Router platform. It is
shipped as a sample dataset for the knowledge/RAG examples.

---

## What AI Router is

AI Router is an open-source gateway that sits between applications and LLM
providers. Every request is routed to the best model and provider based on
capability match, cost, latency, reliability, and current load.

## Key capabilities

### Routing engine
The routing engine scores candidate providers across multiple dimensions.
Optimization modes (quality, balanced, cheapest, fastest) adjust the weight
of each dimension. Provider priority and user preference can override the
ranking.

### Circuit breaker
When a provider fails repeatedly, the circuit opens and traffic is diverted
to the next candidate. The circuit recovers automatically after a cooldown
period, with a half-open state that probes the provider with a limited
number of requests.

### Health monitoring
Each provider exposes liveness and readiness state. The gateway's `/ready`
endpoint returns 200 only when the configuration is loaded and at least one
provider is healthy.

### Knowledge and RAG
Documents are ingested, chunked, embedded, and stored in a vector store.
Queries are processed with semantic and hybrid search, reranked, and
assembled into a grounded context before the answer is generated.

### Plugin system
Plugins hook into the request lifecycle: before request, before routing,
before and after provider calls, and before/after response. Plugins are
auto-discovered from the `plugins/` directory using a manifest.

### MCP support
The Model Context Protocol client connects to MCP servers over stdio or
HTTP, discovers tools, resources, and prompts, and executes tool calls.

### Security
API keys are validated per request. RBAC applies an explicit-deny model.
Secrets are stored with AES-256-GCM envelope encryption. All audit events
are chained with HMAC signatures, making the log tamper-evident.

### Observability
Prometheus metrics, OpenTelemetry traces, structured logs, and Grafana
dashboards provide end-to-end visibility. SLO targets and burn-rate alerts
warn before the service-level objective is breached.

## Deployment

AI Router runs as a single process for development and scales horizontally
with a distributed profile backed by Redis. Official assets cover Docker
Compose, Kubernetes, Helm, Terraform, Ansible, and GitOps.

## Example request

A chat completion request is OpenAI-compatible:

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Explain routing."}]
}
```

---

*Sample dataset for AI Router examples. Replace or extend for your own demos.*
