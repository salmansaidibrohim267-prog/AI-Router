"""Zero-downtime deployments (Strategy pattern).

Strategies:

- ``rolling``   — deploy to batches of nodes; each batch must pass the
  health check before the next batch; failure rolls back.
- ``blue_green`` — full ``green`` version deployed and validated before
  traffic switches; the old ``blue`` version is retained for rollback.
- ``canary``    — new version receives a small traffic percentage, is
  validated, then promoted (or rolled back).

Traffic weights are exposed via :meth:`DeploymentManager.traffic_weights`
so a load balancer can route without downtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from .config import ClusterConfig
from .exceptions import DeploymentError
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import Deployment, DeploymentSpec, DeploymentState, DeploymentStrategy, NodeInfo, NodeState
from .repository import NodeStore

HealthChecker = Callable[[str, str], bool]
"""checker(version, node_id) -> healthy"""


class DeploymentManager:
    """Orchestrates rolling, blue-green and canary deployments."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: NodeStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        checker: HealthChecker | None = None,
        apply_version: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else NodeStore()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.checker = checker or (lambda version, node_id: True)
        self._apply_version = apply_version
        self._deployments: dict[str, Deployment] = {}
        self._versions: dict[str, str] = {}  # component -> active version
        self._traffic: dict[str, dict[str, float]] = {}  # component -> {version: weight}
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._paused: set[str] = set()

    # -- lifecycle ---------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="cluster-deployments")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - deployment loop survives
                self.logger.log_event("deployment_loop_error", error=str(exc))
            await asyncio.sleep(0.5)

    # -- deployment lifecycle ------------------------------------------------------

    def deploy(self, spec: DeploymentSpec) -> Deployment:
        """Start a new deployment; raises if one is already active."""
        for existing in self._deployments.values():
            if existing.spec.name == spec.name and existing.state in (
                DeploymentState.PENDING,
                DeploymentState.PREPARING,
                DeploymentState.DEPLOYING,
                DeploymentState.HEALTHY,
            ):
                raise DeploymentError(f"deployment already active for {spec.name!r}")
        if spec.strategy == DeploymentStrategy.CANARY and not 0 < spec.canary_percentage <= 100:
            raise DeploymentError("canary_percentage must be in (0, 100]")
        if spec.strategy == DeploymentStrategy.ROLLING and spec.batch_size < 1:
            raise DeploymentError("batch_size must be >= 1")
        current = self._versions.get(spec.name)
        if current and current == spec.version:
            raise DeploymentError(f"version {spec.version!r} already active for {spec.name!r}")
        if current:
            spec.previous_version = spec.previous_version or current
        if spec.name not in self._traffic:
            self._traffic[spec.name] = {spec.previous_version or spec.version: 100.0}
        deployment = Deployment(spec=spec, state=DeploymentState.PENDING)
        self._deployments[spec.id] = deployment
        self.logger.log_event(
            "deployment_started",
            id=spec.id,
            name=spec.name,
            version=spec.version,
            strategy=spec.strategy.value,
        )
        return deployment

    def get(self, deployment_id: str) -> Deployment:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            raise DeploymentError(f"unknown deployment {deployment_id!r}")
        return deployment

    def list(self) -> list[Deployment]:
        return sorted(self._deployments.values(), key=lambda d: d.created_at, reverse=True)

    def active(self) -> list[Deployment]:
        return [
            d
            for d in self.list()
            if d.state in (DeploymentState.PENDING, DeploymentState.PREPARING, DeploymentState.DEPLOYING, DeploymentState.HEALTHY)
        ]

    def traffic_weights(self, name: str) -> dict[str, float]:
        """Traffic split per version (zero-downtime switching)."""
        return dict(self._traffic.get(name, {}))

    def current_version(self, name: str) -> str | None:
        return self._versions.get(name)

    def _target_nodes(self, spec: DeploymentSpec) -> list[NodeInfo]:
        if spec.nodes:
            nodes = [self.store.get(nid) for nid in spec.nodes]
            return [n for n in nodes if n is not None]
        return [n for n in self.store.alive() if n.state != NodeState.LEAVING]

    # -- strategy state machine -------------------------------------------------------

    async def poll(self) -> None:
        """Advance all in-flight deployments one step."""
        for deployment in list(self._deployments.values()):
            if deployment.spec.id in self._paused:
                continue
            await self._advance(deployment)

    async def _advance(self, deployment: Deployment) -> None:
        if deployment.state == DeploymentState.PENDING:
            deployment.state = DeploymentState.PREPARING
            deployment.updated_at = time.time()
            deployment.traffic = self._traffic_for(deployment, 0.0)
            return
        if deployment.state == DeploymentState.PREPARING:
            deployment.state = DeploymentState.DEPLOYING
            deployment.updated_at = time.time()
            return
        if deployment.state == DeploymentState.DEPLOYING:
            await self._deploy_step(deployment)
            return
        if deployment.state == DeploymentState.HEALTHY:
            await self._finalize(deployment)
            return

    def _traffic_for(self, deployment: Deployment, current_weight: float) -> dict[str, float]:
        if deployment.spec.strategy == DeploymentStrategy.CANARY:
            green_weight = deployment.spec.canary_percentage
        else:
            green_weight = 100.0 if deployment.state in (DeploymentState.HEALTHY, DeploymentState.COMPLETED) else 0.0
        weights = {deployment.spec.version: green_weight}
        if deployment.spec.previous_version:
            weights[deployment.spec.previous_version] = max(0.0, 100.0 - green_weight)
        return weights

    async def _deploy_step(self, deployment: Deployment) -> None:
        spec = deployment.spec
        targets = self._target_nodes(spec)
        if deployment.state != DeploymentState.DEPLOYING:
            return
        if spec.strategy == DeploymentStrategy.ROLLING:
            await self._rolling_step(deployment, targets)
        elif spec.strategy == DeploymentStrategy.BLUE_GREEN:
            await self._blue_green_step(deployment, targets)
        else:
            await self._canary_step(deployment, targets)

    async def _rolling_step(self, deployment: Deployment, targets: list[NodeInfo]) -> None:
        spec = deployment.spec
        batch = [n for n in targets if n.id not in deployment.deployed_nodes][: spec.batch_size]
        if not batch:
            deployment.progress = 100.0
            deployment.traffic = self._traffic_for(deployment, 100.0)
            await self._mark_completed(deployment)
            return
        healthy = True
        for node in batch:
            if not self.checker(deployment.spec.version, node.id):
                deployment.failed_nodes.append(node.id)
                healthy = False
        if not healthy:
            await self._rollback(deployment, f"health check failed for {len(deployment.failed_nodes)} node(s)")
            return
        for node in batch:
            if self._apply_version is not None:
                self._apply_version(deployment.spec.name, deployment.spec.version, node.id)
            deployment.deployed_nodes.append(node.id)
        deployment.progress = len(deployment.deployed_nodes) / max(1, len(targets)) * 100.0
        deployment.updated_at = time.time()

    async def _blue_green_step(self, deployment: Deployment, targets: list[NodeInfo]) -> None:
        if len(deployment.deployed_nodes) >= len(targets):
            if not self.checker(deployment.spec.version, "green"):
                await self._rollback(deployment, "green environment failed health check")
                return
            deployment.state = DeploymentState.HEALTHY
            deployment.progress = 100.0
            deployment.traffic = self._traffic_for(deployment, 100.0)
            if self._apply_version is not None:
                self._apply_version(deployment.spec.name, deployment.spec.version, "green")
            deployment.updated_at = time.time()
            return
        pending = [n for n in targets if n.id not in deployment.deployed_nodes]
        for node in pending:
            if not self.checker(deployment.spec.version, node.id):
                deployment.failed_nodes.append(node.id)
                continue
            deployment.deployed_nodes.append(node.id)
        deployment.progress = len(deployment.deployed_nodes) / max(1, len(targets)) * 100.0
        deployment.updated_at = time.time()

    async def _canary_step(self, deployment: Deployment, targets: list[NodeInfo]) -> None:
        if not self.checker(deployment.spec.version, "canary"):
            await self._rollback(deployment, "canary failed health check")
            return
        deployment.state = DeploymentState.HEALTHY
        deployment.progress = deployment.spec.canary_percentage
        deployment.traffic = self._traffic_for(deployment, deployment.spec.canary_percentage)
        deployment.updated_at = time.time()

    async def _finalize(self, deployment: Deployment) -> None:
        if deployment.spec.strategy == DeploymentStrategy.BLUE_GREEN:
            deployment.state = DeploymentState.COMPLETED
            self._versions[deployment.spec.name] = deployment.spec.version
            self._traffic[deployment.spec.name] = {deployment.spec.version: 100.0}
            self.logger.log_event("deployment_completed", id=deployment.spec.id, name=deployment.spec.name)
        elif deployment.spec.strategy == DeploymentStrategy.CANARY:
            deployment.state = DeploymentState.COMPLETED
            deployment.progress = 100.0
            self._versions[deployment.spec.name] = deployment.spec.version
            self._traffic[deployment.spec.name] = {deployment.spec.version: 100.0}
            if self._apply_version is not None:
                self._apply_version(deployment.spec.name, deployment.spec.version, "100%")
            self.logger.log_event("deployment_completed", id=deployment.spec.id, name=deployment.spec.name)
        else:
            self._versions[deployment.spec.name] = deployment.spec.version
            self._traffic[deployment.spec.name] = {deployment.spec.version: 100.0}
            deployment.state = DeploymentState.COMPLETED
            self.logger.log_event("deployment_completed", id=deployment.spec.id, name=deployment.spec.name)
        self.metrics.record("deployments_completed", component="deployments")

    async def _mark_completed(self, deployment: Deployment) -> None:
        await self._finalize(deployment)

    # -- promotion / rollback ------------------------------------------------------------

    async def promote(self, deployment_id: str) -> Deployment:
        """Promote a healthy deployment (canary/blue-green) to full traffic."""
        deployment = self.get(deployment_id)
        if deployment.state != DeploymentState.HEALTHY:
            raise DeploymentError("only healthy deployments can be promoted")
        deployment.state = DeploymentState.COMPLETED
        deployment.progress = 100.0
        self._versions[deployment.spec.name] = deployment.spec.version
        self._traffic[deployment.spec.name] = {deployment.spec.version: 100.0}
        if self._apply_version is not None:
            self._apply_version(deployment.spec.name, deployment.spec.version, "100%")
        deployment.updated_at = time.time()
        self.metrics.record("deployments_promoted", component="deployments")
        self.logger.log_event("deployment_promoted", id=deployment.spec.id, name=deployment.spec.name)
        return deployment

    async def rollback(self, deployment_id: str) -> Deployment:
        """Roll back to the previous version (zero-downtime switch)."""
        deployment = self.get(deployment_id)
        if deployment.state == DeploymentState.CANCELLED:
            raise DeploymentError("cancelled deployments cannot be rolled back")
        previous = deployment.spec.previous_version
        deployment.state = DeploymentState.ROLLED_BACK
        deployment.error = "rolled back on demand"
        deployment.progress = 0.0
        if previous:
            self._traffic[deployment.spec.name] = {previous: 100.0}
            if self._apply_version is not None:
                self._apply_version(deployment.spec.name, previous, "100%")
        elif deployment.spec.name in self._traffic:
            self._traffic[deployment.spec.name] = {}
        deployment.updated_at = time.time()
        self.metrics.record("deployments_rolled_back", component="deployments")
        self.logger.log_event("deployment_rolled_back", id=deployment.spec.id, name=deployment.spec.name)
        return deployment

    async def _rollback(self, deployment: Deployment, error: str) -> None:
        deployment.state = DeploymentState.ROLLING_BACK
        deployment.error = error
        deployment.updated_at = time.time()
        previous = deployment.spec.previous_version
        if previous:
            self._traffic[deployment.spec.name] = {previous: 100.0}
            if self._apply_version is not None:
                self._apply_version(deployment.spec.name, previous, "100%")
        deployment.state = DeploymentState.ROLLED_BACK
        self.metrics.record("deployments_rolled_back", component="deployments")
        self.logger.log_event(
            "deployment_rolled_back", id=deployment.spec.id, name=deployment.spec.name, error=error
        )

    # -- management ------------------------------------------------------------------------

    def pause(self, deployment_id: str) -> None:
        self.get(deployment_id)
        self._paused.add(deployment_id)

    def resume_deployment(self, deployment_id: str) -> None:
        self.get(deployment_id)
        self._paused.discard(deployment_id)

    def status(self) -> dict[str, Any]:
        return {
            "active": [d.to_dict() for d in self.active()],
            "history": [d.to_dict() for d in self.list()],
            "versions": dict(self._versions),
            "traffic": {name: dict(weights) for name, weights in self._traffic.items()},
        }
