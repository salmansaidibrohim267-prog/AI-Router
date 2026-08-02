"""Leader election (Strategy pattern).

Pluggable strategies:

- ``lease``  — TTL lease through a ``LeaseStore`` (Repository pattern).
- ``redis``  — atomic SET-NX-EX style election through an injectable KV client.
- ``kubernetes`` — coordination.k8s.io ``Lease`` objects through the K8s API
  transport (same injectable transport as discovery).

Every elector exposes the same async API and notifies observers on
leadership change.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from .config import ClusterConfig
from .exceptions import ElectionError, LeadershipError
from .logging import ClusterLogger
from .models import NodeInfo, NodeState
from .repository import LeaseStore, NodeStore

Observer = Callable[[str | None, int], Awaitable[None]]
"""observer(leader_node_id_or_None, epoch)"""


class Elector:
    """Leader election strategy protocol."""

    name = "base"

    def __init__(self, config: ClusterConfig, node: NodeInfo, logger: ClusterLogger) -> None:
        self.config = config
        self.node = node
        self.logger = logger
        self._observers: list[Observer] = []
        self._leader: str | None = None
        self._epoch = 0
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"cluster-elect-{self.node.id}")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - teardown swallow
                pass
            self._task = None

    @property
    def is_leader(self) -> bool:
        return self._leader == self.node.id

    @property
    def current_leader(self) -> str | None:
        return self._leader

    @property
    def epoch(self) -> int:
        return self._epoch

    def on_change(self, observer: Observer) -> Callable[[], None]:
        """Register an observer; returns an unsubscribe callable."""
        self._observers.append(observer)

        def unsubscribe() -> None:
            if observer in self._observers:
                self._observers.remove(observer)

        return unsubscribe

    async def elect(self) -> bool:
        """Attempt to become leader now (non-blocking)."""
        raise NotImplementedError

    async def step_down(self) -> bool:
        """Relinquish leadership."""
        raise NotImplementedError

    async def _run(self) -> None:
        while self._running:
            try:
                await self.elect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - election must not die
                self.logger.log_event("election_error", node=self.node.id, error=str(exc))
            await asyncio.sleep(self.config.election_retry_interval)

    async def _changed(self, leader: str | None, epoch: int) -> None:
        if leader == self._leader and epoch == self._epoch:
            return
        self._leader = leader
        self._epoch = epoch
        self.logger.log_event(
            "leader_change",
            node=self.node.id,
            leader=leader,
            epoch=epoch,
            is_leader=(leader == self.node.id),
        )
        for observer in list(self._observers):
            result = observer(leader, epoch)
            if asyncio.iscoroutine(result):
                await result


class LeaseElection(Elector):
    """TTL lease election over a LeaseStore."""

    name = "lease"

    def __init__(
        self,
        config: ClusterConfig,
        node: NodeInfo,
        logger: ClusterLogger,
        store: LeaseStore | None = None,
        nodes: NodeStore | None = None,
    ) -> None:
        super().__init__(config, node, logger)
        self.store = store if store is not None else LeaseStore()
        self.nodes = nodes
        self._lease_name = "cluster-leader"

    async def _acquire_or_renew(self) -> bool:
        if self.is_leader:
            return self.store.renew(self._lease_name, self.node.id, self.config.lease_ttl)
        if await self._try_acquire():
            return True
        holder = self.store.get(self._lease_name)
        if holder is not None:
            await self._changed(holder[0], self._epoch)
        return False

    async def _try_acquire(self) -> bool:
        acquired = self.store.acquire(self._lease_name, self.node.id, self.config.lease_ttl)
        if acquired:
            await self._changed(self.node.id, self.node.leader_epoch + 1)
        return acquired

    async def elect(self) -> bool:
        async with self._lock:
            if await self._acquire_or_renew():
                return True
            return False

    async def step_down(self) -> bool:
        async with self._lock:
            released = self.store.release(self._lease_name, self.node.id)
            if released:
                await self._changed(None, self._epoch)
            return released


class RedisElection(Elector):
    """Distributed election via atomic key creation on a KV client.

    ``kv`` must expose ``set_nx(key, value, ttl) -> bool``, ``get(key)``,
    ``delete(key)``, ``expire(key, ttl)``.
    """

    name = "redis"

    def __init__(self, config: ClusterConfig, node: NodeInfo, logger: ClusterLogger, kv: Any) -> None:
        super().__init__(config, node, logger)
        self.kv = kv
        self._key = "cluster:leader"

    async def elect(self) -> bool:
        async with self._lock:
            if self.is_leader:
                renewed = await self.kv.expire(self._key, self.config.lease_ttl)
                if renewed:
                    return True
                await self._changed(None, self._epoch)
                return False
            acquired = await self.kv.set_nx(self._key, self.node.id, self.config.lease_ttl)
            if acquired:
                await self._changed(self.node.id, self.node.leader_epoch + 1)
                return True
            holder = await self.kv.get(self._key)
            if holder is not None:
                await self._changed(holder, self._epoch)
            return False

    async def step_down(self) -> bool:
        async with self._lock:
            if not self.is_leader:
                return False
            deleted = await self.kv.delete(self._key)
            if deleted:
                await self._changed(None, self._epoch)
            return deleted


class KubernetesLeaseElection(Elector):
    """Election using coordination.k8s.io Lease resources.

    Uses the injectable ``transport(backend, method, url, body=None)``.
    ``discovery_config``-style ``election`` config: ``api_server``,
    ``token``/``token_file``, ``namespace``, ``name`` (lease name),
    ``lease_duration`` seconds.
    """

    name = "kubernetes"

    def __init__(
        self,
        config: ClusterConfig,
        node: NodeInfo,
        logger: ClusterLogger,
        transport: Any,
    ) -> None:
        super().__init__(config, node, logger)
        self.transport = transport
        self._cfg = config.discovery_config
        self._name = self._cfg.get("lease_name", "ai-router-leader")
        self._namespace = self._cfg.get("namespace", "default")
        self._duration = int(self._cfg.get("lease_duration", 15))
        self._url = (
            f"{self._cfg.get('api_server', 'https://kubernetes.default.svc')}"
            f"/apis/coordination.k8s.io/v1/namespaces/{self._namespace}/leases/{self._name}"
        )
        self._lease: dict[str, Any] | None = None

    def _holder(self) -> str | None:
        if self._lease is None:
            return None
        spec = self._lease.get("spec", {})
        return spec.get("holderIdentity")

    def _renewed_lease(self, holder: str, epoch: int) -> dict[str, Any]:
        now = time.time()
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {"name": self._name, "namespace": self._namespace},
            "spec": {
                "holderIdentity": holder,
                "leaseDurationSeconds": self._duration,
                "acquireTime": f"{now:.0f}",
                "renewTime": f"{now:.0f}",
                "leaseTransitions": epoch,
            },
        }

    async def _get_lease(self) -> None:
        try:
            body = await self.transport(self, "GET", self._url)
        except Exception as exc:
            raise ElectionError(f"kubernetes lease read failed: {exc}") from exc
        self._lease = body if isinstance(body, dict) else None

    async def elect(self) -> bool:
        async with self._lock:
            try:
                await self._get_lease()
            except ElectionError as exc:
                self.logger.log_event("election_error", node=self.node.id, error=str(exc))
                return False
            holder = self._holder()
            if holder == self.node.id:
                await self.transport(
                    self, "PUT", self._url, body=self._renewed_lease(self.node.id, self._epoch)
                )
                await self._changed(self.node.id, self._epoch)
                return True
            if holder is None:
                try:
                    await self.transport(
                        self,
                        "POST",
                        self._url,
                        body=self._renewed_lease(self.node.id, self._epoch + 1),
                    )
                except Exception as exc:
                    raise ElectionError(f"kubernetes lease acquire failed: {exc}") from exc
                self._lease = self._renewed_lease(self.node.id, self._epoch + 1)
                await self._changed(self.node.id, self._epoch + 1)
                return True
            await self._changed(holder, self._epoch)
            return False

    async def step_down(self) -> bool:
        async with self._lock:
            if not self.is_leader:
                return False
            try:
                await self.transport(self, "DELETE", self._url)
            except Exception as exc:
                raise ElectionError(f"kubernetes lease release failed: {exc}") from exc
            self._lease = None
            await self._changed(None, self._epoch)
            return True


class ElectionRegistry:
    """Strategy registry mapping election strategy names to factories."""

    def create(self, config: ClusterConfig, node: NodeInfo, logger: ClusterLogger, **overrides: Any) -> Elector:
        strategy = config.election_strategy
        if strategy == "lease":
            store = overrides.pop("store", None)
            nodes = overrides.pop("nodes", None)
            if overrides:
                raise TypeError(f"unexpected election overrides: {sorted(overrides)}")
            return LeaseElection(config, node, logger, store, nodes)
        if strategy == "redis":
            kv = overrides.pop("kv", None)
            if overrides:
                raise TypeError(f"unexpected election overrides: {sorted(overrides)}")
            if kv is None:
                raise ElectionError("redis election requires an injected kv client")
            return RedisElection(config, node, logger, kv)
        if strategy == "kubernetes":
            transport = overrides.pop("transport", None)
            if overrides:
                raise TypeError(f"unexpected election overrides: {sorted(overrides)}")
            if transport is None:
                raise ElectionError("kubernetes election requires an injected transport")
            return KubernetesLeaseElection(config, node, logger, transport)
        raise ElectionError(f"unknown election strategy {strategy!r}")


def create_elector(
    config: ClusterConfig | None = None,
    node: NodeInfo | None = None,
    logger: ClusterLogger | None = None,
    **overrides: Any,
) -> Elector:
    """DI factory for leader election strategies."""
    config = config or ClusterConfig()
    node = node or NodeInfo(
        id=config.node_id,
        name=config.node_name,
        address=config.node_address,
        port=config.node_port,
        region=config.region,
        zone=config.zone,
        labels=config.labels,
        version=config.version,
    )
    logger = logger or ClusterLogger(config)
    registry = overrides.pop("registry", None) or ElectionRegistry()
    return registry.create(config, node, logger, **overrides)
