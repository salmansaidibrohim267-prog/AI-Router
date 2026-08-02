# Changelog

All notable changes to **AI Router** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Future improvements and new features will be documented here.

### Changed

- Documentation improvements.
- Internal refactoring.

### Fixed

- Minor bug fixes and maintenance updates.

---

## [1.0.0] - 2026-07-31

### 🎉 Initial Stable Release

The first production-ready release of **AI Router**.

AI Router is an enterprise-grade AI Gateway that provides unified access to multiple LLM providers with production-ready routing, observability, security, plugin architecture, distributed execution, and Retrieval-Augmented Generation (RAG).

---

### Added

#### Core Router

- Multi-provider AI routing
- Provider abstraction layer
- Request/response normalization
- Streaming responses
- Load balancing
- Retry mechanism
- Circuit breaker
- Provider health checks
- Failover support

#### Supported Providers

- OpenAI
- Anthropic
- Google Gemini
- Ollama
- OpenAI-compatible APIs

#### API Gateway

- FastAPI REST API
- OpenAPI / Swagger UI
- Health endpoint
- Readiness endpoint (`/ready`)
- Metrics endpoint
- Version endpoint

#### Security

- API Key authentication
- Secret management
- Storage encryption
- Audit logging
- Rate limiting
- Request validation

#### Observability

- OpenTelemetry integration
- Prometheus metrics
- Structured logging
- Distributed tracing
- Alert management

#### Plugin System

- Dynamic plugin discovery
- Plugin lifecycle management
- Plugin registry
- Plugin manifest support
- Hook system

#### Distributed Architecture

- Distributed task execution
- Redis-backed queue
- Worker registry
- Distributed scheduler
- Lease manager
- Dead Letter Queue (DLQ)
- Retry policies
- Event bus

#### Knowledge & Intelligence

- Document ingestion pipeline
- Advanced chunking engine
- Embedding abstraction
- Vector store abstraction
- Semantic search
- Hybrid search
- Result reranking
- RAG pipeline
- Prompt context builder
- Vector conversation memory
- Citation engine
- MCP Client
- MCP Integration
- Knowledge evaluation

#### SDK & Examples

- Python SDK
- Simple Chat example
- RAG example
- Provider example
- Plugin example
- MCP example

#### Documentation

- Complete project documentation
- API documentation
- SDK documentation
- Security guide
- Operations guide
- Migration guide
- Upgrade guide
- Contributing guide

#### Community

- MIT License
- Code of Conduct
- Contributing Guide
- Security Policy
- Support Guide
- Issue Templates
- Pull Request Template
- CODEOWNERS
- FUNDING configuration
- Dependabot configuration

#### CI/CD

- GitHub Actions
- Automated testing
- Security scanning
- Benchmark workflow
- Release workflow
- Docker image build
- SBOM generation
- Provenance attestation

#### Docker & Deployment

- Multi-stage Docker build
- Production Dockerfile
- Non-root container
- Health checks
- OCI labels
- STOPSIGNAL support
- Docker Compose
- Traefik integration

---

### Changed

- Repository reorganized for production readiness.
- Documentation consolidated into a comprehensive README.
- Improved Docker images and deployment configuration.
- Improved CI/CD workflows.
- Added concurrency protection to GitHub Actions.
- Improved release pipeline.
- Improved observability dashboards.
- Updated `.gitignore` to exclude runtime artifacts.
- Updated API version handling.
- Improved readiness endpoint behavior.
- Enhanced alert handling.
- Improved test coverage.

---

### Fixed

- Corrected API version reporting.
- Fixed duplicate version fields.
- Fixed readiness endpoint behavior.
- Fixed Docker image metadata.
- Fixed GitHub Actions signing workflow.
- Fixed Prometheus dashboard metrics.
- Fixed documentation inconsistencies.
- Fixed stale test counts in documentation.
- Fixed broken documentation links.
- Fixed runtime artifact tracking (`memory.db`).

---

### Repository Statistics

- 4,477 automated tests passing
- 21 tests skipped
- Production-ready architecture
- Multi-provider AI Gateway
- Distributed Architecture
- RAG & Knowledge Engine
- Plugin System
- MCP Integration
- Enterprise Security
- OpenTelemetry Observability

---

### Notes

This release represents the first stable production version of **AI Router** and is intended for self-hosted, enterprise, and cloud-native deployments.

Subsequent improvements and new features will be tracked under the **Unreleased** section following Semantic Versioning.

---

[Unreleased]: https://github.com/salmansaidibrohim267-prog/AI-Router/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/salmansaidibrohim267-prog/AI-Router/releases/tag/v1.0.0
