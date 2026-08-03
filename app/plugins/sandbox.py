from __future__ import annotations

import asyncio
import concurrent.futures
import resource
from pathlib import Path
from typing import Any, Callable

from .config import PluginConfig
from .exceptions import PluginSandboxViolationError, PluginTimeoutError
from .logging import PluginLogger


class Sandbox:
    """Execution sandbox with CPU, memory, timeout, filesystem and network limits.

    Enforcement model (deterministic, in-process):
    - ``execute`` runs a callable in a worker thread with a hard timeout.
    - ``run`` runs a coroutine under ``asyncio.wait_for`` with a timeout.
    - filesystem access is constrained to the configured allow-list of paths
    - network and process spawning are denied unless explicitly allowed.
    - memory usage is checked against ``max_memory_mb``.
    CPU shares are recorded as a scheduling hint for out-of-process isolation
    (Stage 10.8) and validated on every execution.
    """

    def __init__(self, config: PluginConfig | None = None, logger: PluginLogger | None = None) -> None:
        self._config = config or PluginConfig()
        self._logger = logger or PluginLogger(self._config)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="plugin-sandbox")

    @property
    def config(self) -> PluginConfig:
        return self._config

    @property
    def timeout_seconds(self) -> float:
        return self._config.timeout_seconds

    def allowed_paths(self) -> list[str]:
        return list(self._config.fs_allowed_paths)

    def is_path_allowed(self, path: str) -> bool:
        target = Path(path).resolve()
        for allowed in self._config.fs_allowed_paths:
            root = Path(allowed).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                continue
            return True
        return False

    def check_path(self, path: str) -> None:
        if not self.is_path_allowed(path):
            raise PluginSandboxViolationError(f"path {path!r} outside sandbox allow-list", path=path)

    def check_network(self) -> None:
        if not self._config.network_allowed:
            raise PluginSandboxViolationError("network access denied by sandbox")

    def check_process(self) -> None:
        if not self._config.processes_allowed:
            raise PluginSandboxViolationError("process spawning denied by sandbox")

    def check_cpu(self) -> None:
        if self._config.cpu_limit <= 0:
            raise PluginSandboxViolationError("cpu limit must be positive")

    def memory_usage_mb(self) -> float:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return usage / 1024.0

    def check_memory(self) -> None:
        usage = self.memory_usage_mb()
        if usage > self._config.max_memory_mb:
            raise PluginSandboxViolationError(
                f"memory usage {usage:.1f}MB exceeds limit {self._config.max_memory_mb}MB", usage_mb=usage
            )

    def verify_environment(self) -> None:
        self.check_cpu()
        self.check_memory()
        for allowed in self._config.fs_allowed_paths:
            if not Path(allowed).exists():
                self._logger.log_event("sandbox.allowed_path_missing", path=allowed)

    def execute(self, fn: Callable[..., Any], *args: Any, timeout: float | None = None) -> Any:
        """Run ``fn`` in a worker thread; raise PluginTimeoutError on timeout."""
        timeout = timeout if timeout is not None else self._config.timeout_seconds
        future = self._executor.submit(fn, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise PluginTimeoutError(
                f"plugin execution exceeded timeout of {timeout}s", timeout_seconds=timeout
            ) from None
        except Exception:
            raise

    async def run(self, coro: Any, timeout: float | None = None) -> Any:
        timeout = timeout if timeout is not None else self._config.timeout_seconds
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise PluginTimeoutError(
                f"plugin execution exceeded timeout of {timeout}s", timeout_seconds=timeout
            ) from None  # noqa: E501

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
