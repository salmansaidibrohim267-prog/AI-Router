# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Please do **not** open a public issue for security vulnerabilities.

Report vulnerabilities privately to the maintainers:

- **GitHub Security Advisory:** use the repository's *Security → Report a vulnerability*
  flow, which guarantees a private, maintainer-only thread.
- **Email:** `salmansaidibrohim267-prog@users.noreply.github.com` (maintainer contact)

### What to include

- Affected version(s) and commit hashes if known
- A minimal, self-contained reproduction (config, request, stack trace)
- Impact assessment (data exposed, privilege level, exploitation path)

### Response times

| Stage        | Timeframe                      |
| ------------ | ------------------------------ |
| Acknowledged | Within 48 hours                |
| Triage       | Within 5 business days         |
| Fix + release | As soon as possible, typically within 30 days |

After triage you will receive a status update and, once a fix ships, a CVE
reference and credit in the release notes (if you want it).

## Security posture

AI Router implements the security model documented in `docs/security.md`:
API-key auth with RBAC, secrets management with AES-256-GCM envelope
encryption, an HMAC-chained tamper-evident audit log, PII masking, and a
zero-trust mode (`SEC_ZERO_TRUST_ENFORCE=1`). Report anything that deviates
from that model as a vulnerability.

## Automated security testing

The CI pipeline runs security checks on every push and PR:

| Check | Tool | Scope |
| --- | --- | --- |
| Static analysis | Bandit | `app/` |
| Dependency audit | pip-audit | `requirements.txt` |
| Image scan | Trivy | container image (HIGH/CRITICAL) |
| SBOM | syft (anchore/sbom-action) | container image + source |
| Lint/mypy | ruff, black, flake8, mypy | code quality gates |

Findings are non-blocking where marked; genuine vulnerabilities should be
reported through the private flow above.

## Contributing security improvements

Security fixes and hardening PRs are always welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). If the change affects the security
model, mention `security:` in the commit type so it lands in the changelog
Security section.

This project is licensed under the [MIT License](LICENSE); the security
tooling and practices described here apply to the current supported
versions listed above.
