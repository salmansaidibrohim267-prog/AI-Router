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
