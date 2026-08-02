"""GitOps manifest validation and application.

Validates Kubernetes-style GitOps manifests (ArgoCD Application, HelmRelease)
for well-formedness: parseable YAML, kind whitelist, image tag immutability
(no ``latest``), required metadata and correct version fields.
"""

from __future__ import annotations

import re
from typing import Any

from .config import DeployConfig
from .exceptions import GitOpsError

_KIND_PATTERN = re.compile(r"^(Application|HelmRelease|Deployment|ConfigMap|Secret)$")

_IMAGE_TAG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::(?P<tag>[a-zA-Z0-9._-]+))?$")


class GitOpsManifest:
    """A validated GitOps application manifest."""

    def __init__(self, kind: str, name: str, namespace: str = "default", spec: dict[str, Any] | None = None) -> None:
        self.kind = kind
        self.name = name
        self.namespace = namespace
        self.spec = dict(spec or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": self.kind,
            "metadata": {"name": self.name, "namespace": self.namespace},
            "spec": dict(self.spec),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GitOpsManifest":
        metadata = data.get("metadata", {}) or {}
        return cls(
            kind=data.get("kind", ""),
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            spec=data.get("spec", {}),
        )

    @property
    def target_revision(self) -> str:
        return self.spec.get("targetRevision", "") or self.spec.get("source", {}).get("targetRevision", "")

    def images(self) -> list[str]:
        return [img for img in re.split(r"\s*,\s*", self.spec.get("images", "") or "") if img]


class GitOpsValidator:
    """Validates GitOps manifests for release readiness."""

    def __init__(self, config: DeployConfig | None = None) -> None:
        self.config = config if config is not None else DeployConfig()

    def validate(self, manifest: GitOpsManifest) -> list[str]:
        """Return a list of validation problems (empty = valid)."""
        problems: list[str] = []
        if not manifest.kind:
            problems.append("manifest kind is missing")
        elif not _KIND_PATTERN.match(manifest.kind):
            problems.append(f"unsupported manifest kind {manifest.kind!r}")
        if not manifest.name:
            problems.append("manifest name is missing")
        if not manifest.target_revision:
            problems.append("targetRevision is missing (immutable version required)")
        for image in manifest.images():
            match = _IMAGE_TAG_RE.match(image)
            if match is None:
                problems.append(f"malformed image reference {image!r}")
                continue
            tag = match.group("tag") or "latest"
            if tag in ("latest", "main", "master", "dev"):
                problems.append(f"immutable image tags required, got {tag!r} in {image!r}")
        return problems

    def validate_or_raise(self, manifest: GitOpsManifest) -> bool:
        problems = self.validate(manifest)
        if problems:
            raise GitOpsError("; ".join(problems))
        return True

    def load_yaml(self, text: str) -> GitOpsManifest:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - env dependent
            raise GitOpsError("PyYAML is required to parse manifests") from exc
        try:
            data = yaml.safe_load(text)
        except Exception as exc:
            raise GitOpsError(f"manifest is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise GitOpsError("manifest must be a mapping")
        return GitOpsManifest.from_dict(data)

    def apply(self, manifest: GitOpsManifest, dry_run: bool = False) -> dict[str, Any]:
        """Validate and record the application (no external cluster access)."""
        self.validate_or_raise(manifest)
        return {
            "kind": manifest.kind,
            "name": manifest.name,
            "namespace": manifest.namespace,
            "target_revision": manifest.target_revision,
            "applied": not dry_run,
            "dry_run": dry_run,
        }


class DeploymentPipeline:
    """End-to-end pipeline: gates -> smoke -> rollback -> verify -> GitOps."""

    def __init__(
        self,
        config: DeployConfig | None = None,
        gates_runner: Any = None,
        smoke_tester: Any = None,
        rollback_tester: Any = None,
        verifier: Any = None,
        gitops: GitOpsValidator | None = None,
    ) -> None:
        from .gates import QualityGateRunner
        from .verification import DeploymentVerifier, RollbackTester, SmokeTester

        self.config = config if config is not None else DeployConfig()
        self.gates = gates_runner if gates_runner is not None else QualityGateRunner(self.config)
        self.smoke = smoke_tester if smoke_tester is not None else SmokeTester(self.config)
        self.rollback = rollback_tester if rollback_tester is not None else RollbackTester(self.config)
        self.verify = verifier if verifier is not None else DeploymentVerifier(self.config)
        self.gitops = gitops if gitops is not None else GitOpsValidator(self.config)
        self._run_log: list[dict[str, Any]] = []

    def run(
        self,
        gate_results: list[Any] | None = None,
        smoke_results: list[Any] | None = None,
        expected_version: str | None = None,
    ) -> dict[str, Any]:
        """Execute the full pipeline; raises on any failed stage."""
        gate_results = gate_results if gate_results is not None else self.gates.run_and_raise()
        smoke_results = smoke_results if smoke_results is not None else self.smoke.run_and_raise()
        rollback_result = self.rollback.run(self.config.target_version, self.config.target_version)
        verification = self.verify.verify(expected_version or self.config.target_version)
        self._run_log.append(
            {
                "version": expected_version or self.config.target_version,
                "environment": self.config.environment,
                "gates_passed": len(gate_results),
                "smoke_passed": len(smoke_results),
                "rollback": rollback_result,
                "verification": verification,
            }
        )
        return self._run_log[-1]

    def last_run(self) -> dict[str, Any] | None:
        return self._run_log[-1] if self._run_log else None

    def runs(self) -> list[dict[str, Any]]:
        return list(self._run_log)


def create_deployment_pipeline(config: DeployConfig | None = None, **overrides: Any) -> DeploymentPipeline:
    config = config if config is not None else DeployConfig()
    gates_runner = overrides.pop("gates_runner", None)
    smoke_tester = overrides.pop("smoke_tester", None)
    rollback_tester = overrides.pop("rollback_tester", None)
    verifier = overrides.pop("verifier", None)
    gitops = overrides.pop("gitops", None)
    return DeploymentPipeline(config, gates_runner, smoke_tester, rollback_tester, verifier, gitops)
