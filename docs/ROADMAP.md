# Roadmap

AI Router v1.0.0 is feature complete and production ready. This roadmap
reflects the maintainers' direction for upcoming releases.

## Legend

| Mark | Meaning |
| --- | --- |
| ✅ | Shipped (v1.0.0) |
| 🚧 | In progress |
| 📋 | Planned |
| 💡 | Backlog / idea |

## v1.0.x — Maintenance & hardening (current)

- ✅ Multi-provider routing, health checks, circuit breakers, failover
- ✅ RAG: ingestion, chunking, embedding, vector stores, reranking, citations
- ✅ MCP SDK and integration surfaces
- ✅ Plugin SDK with signing, sandboxing and lifecycle
- ✅ Multi-tenancy, billing and admin console
- ✅ Enterprise security: audit chains, secret store, KMS/HSM, zero trust
- ✅ Distributed workers, scheduler, leader election, event bus
- ✅ Observability: Prometheus, Grafana, Loki, OpenTelemetry, SLOs
- ✅ CI/CD, GHCR image publishing, signed GitHub releases with SBOM
- 🚧 Flaky-test elimination and CI stability
- 🚧 Release-process automation polish

## v1.1 — Quality of life

- 📋 Streaming observability (token-level traces)
- 📋 Smarter cost-aware routing (budget-aware provider selection)
- 📋 Expanded plugin marketplace samples
- 📋 More vector store backends
- 📋 Windows / macOS native demo packaging

## v1.2 — Enterprise features

- 📋 SSO / OIDC identity federation
- 📋 Multi-region active-active routing
- 📋 Advanced compliance exports (SOC 2, ISO 27001 ready reports)
- 📋 Audit-chain export/archive tooling
- 💡 Policy-as-code provider guardrails

## v2.0 — Platform expansion

- 💡 Built-in model fine-tuning / evaluation loop integration
- 💡 Multi-cluster federation via a control plane
- 💡 Plugin marketplace hosting + remote install
- 💡 Webhook/event-driven integrations catalog

## Known limitations

See [`release/KNOWN_LIMITATIONS.md`](../release/KNOWN_LIMITATIONS.md) for
the current list of known limitations and their planned resolutions.

## How to influence the roadmap

- Vote and discuss in [GitHub Discussions](https://github.com/salmansaidibrohim267-prog/AI-Router/discussions)
- Open feature requests via the issue templates
- Contribute — see [CONTRIBUTING.md](../CONTRIBUTING.md)