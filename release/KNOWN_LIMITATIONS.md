# Known Limitations — v1.0.0

Honest, verified limitations of the current release. These are candidates
for future releases and are not defects hidden from users.

## Product

- **API-only product.** There is no built-in web UI; interaction happens via
  the REST API and Swagger UI (`/docs`). Dashboards are Grafana-based.
- **Streaming is SSE/OpenAI-compatible only** on the chat endpoint; no
  WebSocket transport.
- **Single-node by default.** The base deployment is one gateway process.
  Horizontal scaling requires the distributed profile (Redis 7.2+,
  `DISTRIBUTED_MODE=1`, worker/scheduler processes).
- **Default persistence is local SQLite** (`memory.db`). No sharding;
  scale persistence via the vector store backends and Redis for distributed
  state.
- **Rate limiting is per-key, windowed** (default 100 requests / 60 s,
  configurable). Not distributed across nodes in single-node mode.
- **MCP stdio transport** requires the MCP server process to run on the same
  host; HTTP transport is the recommended remote option.

## Deployment

- **Traefik, Helm and k8s ingress hosts ship with `*.example.com`
  placeholders** — replace them with real domains before going live.
- **GHCR is the configured registry.** Docker Hub publishing is not
  configured and would require a Docker Hub account.
- **Helm chart is not published** to a chart registry; it is consumed from
  the repository.
- **Grafana dashboards require the monitoring profile/provisioning** to be
  imported; SLO burn-rate alerts depend on `otel-collector` metrics.

## Configuration

- **No bundled API keys.** `config/providers.yaml` must be populated with
  real provider credentials or environment variables before routing works.
- **Traefik middleware rate limits** (average 100, burst 50) are separate
  from the application rate limiter — both apply when the Traefik profile
  is used.

## Cosmetic / environmental

- On FastAPI 0.140.x (non-stable build), the OpenAPI `info.license` field is
  not emitted by the framework; `contact` is emitted. Stable FastAPI
  releases render both.
- Some example outputs in the documentation reflect specific provider
  responses and may differ across providers.

## Operations

- **Audit retention** default is 365 days (`SEC_AUDIT_RETENTION_DAYS`);
  retained logs require storage planning at scale.
- **Backup scripts** cover config, Grafana provisioning, and named volumes
  — external object storage is not bundled.
