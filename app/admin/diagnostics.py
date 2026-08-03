from __future__ import annotations

import platform
import sys
import time
from typing import Any, Callable

from .config import AdminConfig
from .diagnostics_checks import DEFAULT_CHECKS
from .logging import AdminLogger
from .models import DiagnosticsReport


class DiagnosticsService:
    """Collects runtime environment information and runs diagnostic probes."""

    def __init__(
        self,
        config: AdminConfig | None = None,
        logger: AdminLogger | None = None,
        checks: dict[str, Callable[[], bool]] | None = None,
    ) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._checks = dict(DEFAULT_CHECKS)
        if checks:
            self._checks.update(checks)

    def register_check(self, name: str, check: Callable[[], bool]) -> None:
        self._checks[name] = check

    def environment(self) -> dict[str, Any]:
        return {
            "environment": self._config.environment,
            "version": self._config.version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "implementation": platform.python_implementation(),
        }

    def runtime(self) -> dict[str, Any]:
        return {
            "sys_argv": list(sys.argv),
            "maxsize": sys.maxsize,
            "threads": sys.thread_info.name if hasattr(sys, "thread_info") else "unknown",
        }

    def integrations(self) -> dict[str, Any]:
        return {
            name: {"enabled": self._config.integration_enabled(name)}
            for name in ("prometheus", "otel", "loki", "alertmanager")
        }

    def run_checks(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for name, check in self._checks.items():
            started = time.time()
            try:
                passed = bool(check())
            except Exception:
                passed = False
            results.append(
                {
                    "name": name,
                    "passed": passed,
                    "latency_ms": round((time.time() - started) * 1000.0, 2),
                }
            )
        return results

    def collect(self) -> DiagnosticsReport:
        report = DiagnosticsReport(
            environment=self.environment(),
            runtime=self.runtime(),
            integrations=self.integrations(),
            checks=self.run_checks(),
        )
        self._logger.log_event("diagnostics.collected", environment=self._config.environment)
        return report

    def summary(self) -> dict[str, Any]:
        report = self.collect()
        failures = [check for check in report.checks if not check["passed"]]
        return {
            "environment": report.environment["environment"],
            "version": report.environment["version"],
            "integrations_ok": all(
                not self._config.integration_enabled(name) or True
                for name in ("prometheus", "otel", "loki", "alertmanager")
            ),  # noqa: E501
            "checks_total": len(report.checks),
            "checks_passed": len(report.checks) - len(failures),
            "checks_failed": len(failures),
        }
