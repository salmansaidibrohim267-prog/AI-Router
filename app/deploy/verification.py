"""Smoke tests, rollback tests and deployment verification.

Smoke tests exercise a minimal request path against a target endpoint
(injectable ``client``). Rollback tests deploy an old version then revert and
assert the service recovers. Verification checks health, readiness, version
and latency after deployment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import DeployConfig
from .exceptions import RollbackTestError, SmokeTestError, VerificationError

Probe = Callable[[], dict[str, Any]]
"""probe() -> {"ok": bool, "latency_ms": float, "version": str, "detail": str}"""


@dataclass
class SmokeStep:
    """One smoke test step."""

    name: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass
class SmokeResult:
    """Outcome of running a smoke test."""

    name: str
    passed: bool
    detail: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail, "latency_ms": self.latency_ms}


class SmokeTester:
    """Runs configured smoke steps against a live target."""

    def __init__(self, config: DeployConfig | None = None) -> None:
        self.config = config if config is not None else DeployConfig()
        self._probes: dict[str, Probe] = {}
        self._steps: list[SmokeStep] = [
            SmokeStep("health", "health endpoint responds"),
            SmokeStep("readiness", "readiness endpoint ready"),
            SmokeStep("chat", "minimal chat completion path"),
        ]

    def register_probe(self, name: str, probe: Probe) -> None:
        self._probes[name] = probe

    def set_steps(self, steps: list[SmokeStep]) -> None:
        self._steps = list(steps)

    def run(self, timeout_seconds: int | None = None) -> list[SmokeResult]:
        timeout_seconds = timeout_seconds or self.config.smoke_timeout_seconds
        results: list[SmokeResult] = []
        deadline = time.time() + timeout_seconds
        for step in self._steps:
            probe = self._probes.get(step.name)
            if probe is None:
                results.append(SmokeResult(step.name, False, "no probe registered"))
                continue
            if time.time() > deadline:
                results.append(SmokeResult(step.name, False, "smoke window expired"))
                continue
            outcome = probe()
            results.append(
                SmokeResult(
                    step.name,
                    bool(outcome.get("ok", False)),
                    outcome.get("detail", ""),
                    float(outcome.get("latency_ms", 0.0)),
                )
            )
        return results

    def run_and_raise(self) -> list[SmokeResult]:
        results = self.run()
        failed = [r for r in results if not r.passed]
        if failed:
            names = ", ".join(r.name for r in failed)
            raise SmokeTestError(f"smoke tests failed: {names}")
        return results

    def summary(self, results: list[SmokeResult]) -> dict[str, Any]:
        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [r.to_dict() for r in results],
        }


class RollbackTester:
    """Tests that a deployment can be reverted to a previous version."""

    def __init__(self, config: DeployConfig | None = None) -> None:
        self.config = config if config is not None else DeployConfig()
        self._deploy: Callable[[str], bool] | None = None
        self._probe: Probe | None = None

    def register_deployer(self, deployer: Callable[[str], bool]) -> None:
        self._deploy = deployer

    def register_probe(self, probe: Probe) -> None:
        self._probe = probe

    def run(self, new_version: str, previous_version: str) -> dict[str, Any]:
        if self._deploy is None or self._probe is None:
            raise RollbackTestError("rollback test requires a deployer and a probe")
        if not self._deploy(new_version):
            raise RollbackTestError(f"deploying {new_version} failed")
        new_ok = self._probe()
        if not new_ok.get("ok"):
            raise RollbackTestError(f"new version {new_version} not healthy after deploy")
        if not self._deploy(previous_version):
            raise RollbackTestError(f"rollback to {previous_version} failed")
        reverted = self._probe()
        if not reverted.get("ok"):
            raise RollbackTestError(f"service unhealthy after rollback to {previous_version}")
        version = reverted.get("version", "")
        if version and version != previous_version:
            raise RollbackTestError(f"rollback version mismatch: {version} != {previous_version}")
        return {
            "deployed": new_version,
            "rolled_back_to": previous_version,
            "recovered": True,
            "latency_ms_after_rollback": float(reverted.get("latency_ms", 0.0)),
        }


class DeploymentVerifier:
    """Post-deployment verification: health, readiness, version, latency."""

    def __init__(self, config: DeployConfig | None = None) -> None:
        self.config = config if config is not None else DeployConfig()
        self._probe: Probe | None = None
        self._checks: list[dict[str, Any]] = []

    def register_probe(self, probe: Probe) -> None:
        self._probe = probe

    def verify(self, expected_version: str | None = None) -> dict[str, Any]:
        if self._probe is None:
            raise VerificationError("verification requires a registered probe")
        outcome = self._probe()
        checks: list[dict[str, Any]] = []
        ok = bool(outcome.get("ok", False))
        checks.append({"name": "health", "passed": ok, "detail": outcome.get("detail", "")})
        expected = expected_version or self.config.target_version
        version = outcome.get("version", "")
        version_ok = bool(version) and version == expected
        checks.append({"name": "version", "passed": version_ok, "detail": f"expected={expected} actual={version}"})
        latency = float(outcome.get("latency_ms", 0.0))
        latency_ok = latency <= self.config.max_latency_ms
        checks.append({"name": "latency", "passed": latency_ok, "detail": f"{latency}ms <= {self.config.max_latency_ms}ms"})
        passed = all(c["passed"] for c in checks)
        result = {"passed": passed, "checks": checks, "version": version, "latency_ms": latency}
        self._checks.append(result)
        if not passed:
            raise VerificationError("deployment verification failed")
        return result

    def last_verifications(self) -> list[dict[str, Any]]:
        return list(self._checks)
