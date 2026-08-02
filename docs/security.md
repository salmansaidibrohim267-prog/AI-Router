# Security

Security hardening overview for the AI Router gateway.

## Transport & access

- TLS terminated at Traefik (Let's Encrypt) with HSTS-friendly headers.
- Rate limiting middleware (default 100 requests per 60-second window per
  client, token-bucket with burst) at the edge.
- API keys required on gateway endpoints; providers are invoked with their
  own secrets injected via environment/secret store.

## Secrets

- `app/security/` implements a secret store with AES-GCM envelope encryption
  and optional KMS/HSM-backed key management (`StorageEncryption`,
  `KeyManager` with `HSMAdapter` / `KMSAdapter` adapters).
- Secrets are never logged; `as_dict()` omits private material.
- `SecretNotFoundError` is raised distinctly before generic error handling.

## Audit

- Every sensitive operation appends an immutable audit chain record
  (hash-linked, pruned records re-linked and re-signed).
- Chain hash covers the payload excluding volatile `signature`/`hash` fields.

## Releases

- Artifact manifests are HMAC-SHA256 signed (`app/release/signing.py`);
  tampering breaks verification.
- `Ed25519StyleSigner` adapter simulates a key split so verifiers can check
  without the signing half.
- Container images are cosign-signed in `build-sign.yml`.

## Dependency & image scanning

- `bandit` static scan on `app/` (CI, non-blocking).
- `pip-audit` for known vulnerabilities in requirements.
- Trivy scans the built image for HIGH/CRITICAL CVEs.
- syft generates an SPDX SBOM per build.

## Runtime hardening

- Non-root user (`ai-router`, uid 1000), no shell.
- Read-only root filesystem, `allowPrivilegeEscalation: false`, all
  capabilities dropped (k8s).
- Immutable image tags in production; `latest` rejected by the GitOps
  validator.

## Incident response

1. Verify signatures first (`ReleaseSigner.verify_or_raise`).
2. Rotate secrets; KMS/HSM key rotation supported by the security package.
3. Roll back via `scripts/rollback.sh` / `kubectl rollout undo`.
4. Audit the chain via `app/security` tools to reconstruct activity.
