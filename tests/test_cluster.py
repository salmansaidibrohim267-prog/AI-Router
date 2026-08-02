"""Tests for the app.cluster package (Stage 10.8)."""

from __future__ import annotations

import asyncio
import base64
import time
from datetime import datetime

import pytest

from app.cluster.autoscale import (
    Autoscaler,
    CpuCollector,
    MemoryCollector,
    MetricCollector,
    QueueLengthCollector,
    RequestRateCollector,
    TokenThroughputCollector,
)
from app.cluster.cluster import ClusterManager, create_cluster_manager
from app.cluster.config import ClusterConfig
from app.cluster.deployments import DeploymentManager, DeploymentSpec
from app.cluster.discovery import (
    ConsulDiscovery,
    DNSDiscovery,
    DiscoveryRegistry,
    EtcdDiscovery,
    KubernetesDiscovery,
    StaticDiscovery,
    _b64_or_str,
    _default_transport,
    create_discovery,
)
from app.cluster.election import (
    ElectionRegistry,
    KubernetesLeaseElection,
    LeaseElection,
    RedisElection,
    create_elector,
)
from app.cluster.exceptions import (
    AutoscaleError,
    BackupError,
    ClusterError,
    ClusterNotStartedError,
    DeploymentError,
    DiscoveryError,
    DRFailoverError,
    ElectionError,
    JobNotFoundError,
    NodeAlreadyJoinedError,
    RestoreError,
    SchedulerError,
)
from app.cluster.failover import FailoverManager
from app.cluster.health import HealthMonitor
from app.cluster.logging import ClusterLogger
from app.cluster.metrics import ClusterMetricsTracker
from app.cluster.models import (
    AutoscaleDecision,
    BackupRecord,
    BackupStatus,
    DeploymentState,
    DeploymentStrategy,
    Heartbeat,
    JobRun,
    JobSpec,
    JobState,
    JobType,
    NodeInfo,
    NodeRole,
    NodeState,
    RebalanceReason,
    RebalanceReport,
    ReplicationRecord,
    ReplicationState,
    generate_id,
)
from app.cluster.replication import BackupManager, DisasterRecovery, ReplicationManager
from app.cluster.repository import (
    BackupStore,
    JobStore,
    LeaseStore,
    NodeStore,
    SnapshotStore,
)
from app.cluster.scheduler import CronExpression, DistributedScheduler


def make_config(**kwargs):
    return ClusterConfig(**{"node_id": "node-test", "node_name": "test-node", **kwargs})


def make_node(node_id="node-a", **kwargs):
    return NodeInfo(id=node_id, name=node_id, address="127.0.0.1", port=8000, **kwargs)


async def wait_until(predicate, timeout=1.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


class TestClusterConfig:
    def test_defaults(self):
        config = ClusterConfig(node_id="n1")
        assert config.node_id == "n1"
        assert config.discovery_type == "static"
        assert config.election_strategy == "lease"
        assert config.autoscale_enabled is True
        assert config.replication_enabled is True
        assert config.min_replicas == 1
        assert config.max_replicas == 16

    def test_unknown_option_raises(self):
        with pytest.raises(TypeError):
            ClusterConfig(bogus_option=1)

    def test_node_id_defaults(self):
        config = ClusterConfig()
        assert config.node_id.startswith("node-")

    def test_as_dict_serialisable(self):
        config = make_config(labels={"tier": "blue"})
        data = config.as_dict()
        assert data["node_id"] == "node-test"
        assert data["labels"] == {"tier": "blue"}
        assert data["discovery_config"] == {}
        assert isinstance(data["node_port"], int)

    def test_from_env_full(self, monkeypatch):
        values = {
            "CL_NODE_ID": "env-node",
            "CL_NODE_PORT": "9000",
            "CL_DISCOVERY_PEERS": "10.0.0.1:8000, 10.0.0.2",
            "CL_HEARTBEAT_TIMEOUT": "3.5",
            "CL_AUTOSCALE_ENABLED": "false",
            "CL_MIN_REPLICAS": "2",
            "CL_ELECTION_STRATEGY": "redis",
        }
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        config = ClusterConfig.from_env()
        assert config.node_id == "env-node"
        assert config.node_port == 9000
        assert config.discovery_config == {"peers": ["10.0.0.1:8000", "10.0.0.2"]}
        assert config.heartbeat_timeout == 3.5
        assert config.autoscale_enabled is False
        assert config.min_replicas == 2
        assert config.election_strategy == "redis"

    def test_from_env_overrides(self, monkeypatch):
        monkeypatch.setenv("CL_NODE_ID", "env-node")
        config = ClusterConfig.from_env(node_id="explicit")
        assert config.node_id == "explicit"


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class TestModels:
    def test_generate_id(self):
        first = generate_id("job")
        second = generate_id("job")
        assert first.startswith("job-")
        assert first != second

    def test_node_info_roundtrip(self):
        node = make_node(labels={"a": "b"})
        node.role = NodeRole.LEADER
        node.leader_epoch = 3
        restored = NodeInfo.from_dict(node.to_dict())
        assert restored.id == node.id
        assert restored.role == NodeRole.LEADER
        assert restored.leader_epoch == 3
        assert restored.labels == {"a": "b"}
        assert restored.state == NodeState.JOINING

    def test_node_info_from_dict_defaults(self):
        restored = NodeInfo.from_dict({"id": "x", "address": "1.2.3.4"})
        assert restored.name == "x"
        assert restored.role == NodeRole.FOLLOWER
        assert restored.capacity == 1

    def test_job_spec_to_dict(self):
        spec = JobSpec(name="j", type=JobType.CRON, cron="0 0 * * *")
        data = spec.to_dict()
        assert data["type"] == "cron"
        assert data["cron"] == "0 0 * * *"
        assert data["singleton"] is False

    def test_job_run_to_dict(self):
        run = JobRun(job_id="j", job_name="n", state=JobState.RUNNING)
        data = run.to_dict()
        assert data["state"] == "running"
        assert data["attempts"] == 1

    def test_deployment_to_dict(self):
        from app.cluster.models import Deployment

        deployment = Deployment(spec=DeploymentSpec(name="svc", version="2.0"))
        data = deployment.to_dict()
        assert data["name"] == "svc"
        assert data["version"] == "2.0"
        assert data["state"] == "pending"
        assert data["traffic"] == {}

    def test_backup_and_replication_to_dict(self):
        backup = BackupRecord(name="b1")
        assert backup.to_dict()["status"] == "pending"
        replication = ReplicationRecord(snapshot_id="s1", replica_id="r1")
        assert replication.to_dict()["replica_id"] == "r1"

    def test_autoscale_decision_to_dict(self):
        decision = AutoscaleDecision(
            component="c", metric="cpu", current=90.0, threshold=70.0, desired=3, previous=1, reason="load"
        )
        data = decision.to_dict()
        assert data["desired"] == 3
        assert data["metric"] == "cpu"

    def test_rebalance_report_to_dict(self):
        report = RebalanceReport(reason=RebalanceReason.MANUAL)
        data = report.to_dict()
        assert data["reason"] == "manual"

    def test_enums(self):
        assert JobType.RECURRING.value == "recurring"
        assert NodeState.FAILED.value == "failed"
        assert DeploymentStrategy.BLUE_GREEN.value == "blue_green"
        assert ReplicationState.REPLICATED.value == "replicated"
        assert BackupStatus.OK.value == "ok"


# ---------------------------------------------------------------------------
# logging / metrics
# ---------------------------------------------------------------------------


class TestObservability:
    def test_logger_events_ring_and_log(self):
        config = make_config()
        logger = ClusterLogger(config)
        logger.log_event("node_joined", node="n1")
        logger.log_event("node_left", node="n1")
        assert len(logger.events) == 2
        assert logger.events[0]["event"] == "cluster_node_joined"
        assert logger.events[0]["data"]["node"] == "n1"

    def test_logger_capped(self):
        config = make_config()
        logger = ClusterLogger(config)
        for index in range(1100):
            logger.log_event("heartbeat", index=index)
        assert len(logger.events) <= 1000
        assert logger.events[-1]["data"]["index"] == 1099

    def test_logger_disabled(self):
        logger = ClusterLogger(make_config(log_events=False))
        logger.log_event("test")
        assert logger.events == []

    def test_metrics_tracker(self):
        metrics = ClusterMetricsTracker(make_config())
        metrics.record("leader_elections", component="cluster")
        metrics.record("leader_elections", component="cluster")
        metrics.record("failovers", component="failover")
        assert metrics.counts()["leader_elections"] == 2
        assert metrics.for_component("cluster") == {"leader_elections": 2}
        summary = metrics.summary()
        assert summary["total_events"] == 3
        assert "cluster" in summary["components"]

    def test_metrics_disabled(self):
        metrics = ClusterMetricsTracker(make_config(track_metrics=False))
        metrics.record("x")
        assert metrics.counts() == {}


# ---------------------------------------------------------------------------
# repository
# ---------------------------------------------------------------------------


class TestNodeStore:
    def test_crud(self):
        store = NodeStore()
        node = make_node()
        store.register(node)
        assert store.get(node.id) is node
        assert len(store) == 1
        store.update(node.id, state=NodeState.HEALTHY)
        assert store.get(node.id).state == NodeState.HEALTHY
        assert store.remove(node.id) is None
        assert len(store) == 0
        assert store.get(node.id) is None

    def test_require_unknown(self):
        store = NodeStore()
        with pytest.raises(KeyError):
            store.require("missing")
        with pytest.raises(KeyError):
            store.update("missing", state=NodeState.HEALTHY)

    def test_update_unknown_attr(self):
        store = NodeStore()
        store.register(make_node())
        with pytest.raises(AttributeError):
            store.update("node-a", bogus=True)

    def test_by_state_and_alive(self):
        store = NodeStore()
        store.register(make_node("a"))
        store.register(make_node("b"))
        store.mark("a", NodeState.HEALTHY)
        store.update("b", state=NodeState.FAILED)
        assert [n.id for n in store.by_state(NodeState.FAILED)] == ["b"]
        assert [n.id for n in store.alive()] == ["a"]
        store.update("b", state=NodeState.LEFT)
        assert [n.id for n in store.alive()] == ["a"]

    def test_history_and_mark(self):
        store = NodeStore()
        store.register(make_node("a"))
        store.remove("a")
        assert [n.id for n in store.history()] == ["a"]
        store.register(make_node("b"))
        store.mark("b", NodeState.HEALTHY)
        assert store.get("b").state == NodeState.HEALTHY

    def test_touch_and_heartbeats(self):
        store = NodeStore()
        store.register(make_node("a"))
        store.touch("a", load=0.5)
        assert store.get("a").state == NodeState.HEALTHY
        assert store.last_heartbeat("a").load == 0.5
        heartbeat = Heartbeat(node_id="a", timestamp=123.0)
        store.record_heartbeat(heartbeat)
        assert store.get("a").last_seen == 123.0
        assert store.last_heartbeat("a").timestamp == 123.0
        assert store.last_heartbeat("missing") is None

    def test_leader_and_epoch(self):
        store = NodeStore()
        store.register(make_node("a"))
        store.register(make_node("b"))
        assert store.leader() is None
        assert store.next_epoch() == 1
        store.set_leader("a")
        assert store.leader().id == "a"
        assert store.leader().leader_epoch == 1
        store.set_leader("b", epoch=5)
        assert store.leader().id == "b"
        assert store.get("a").role == NodeRole.FOLLOWER
        assert store.next_epoch() == 6

    def test_snapshot(self):
        store = NodeStore()
        store.register(make_node("a", labels={"k": "v"}))
        snapshot = store.snapshot()
        assert snapshot[0]["id"] == "a"
        assert snapshot[0]["labels"] == {"k": "v"}


class TestJobStore:
    def test_crud(self):
        store = JobStore()
        job = JobSpec(name="j")
        store.add(job)
        assert store.get(job.id) is job
        assert len(store) == 1
        assert store.remove(job.id) is True
        assert store.remove(job.id) is False
        assert len(store) == 0
        with pytest.raises(KeyError):
            store.require("missing")
        with pytest.raises(KeyError):
            store.update("missing", owner="x")

    def test_due(self):
        store = JobStore()
        job = JobSpec(name="j", next_run=100.0)
        store.add(job)
        assert store.due(200.0) == [job]
        assert store.due(50.0) == []
        assert store.due() is not None

    def test_owner_and_orphans(self):
        store = JobStore()
        owned = JobSpec(name="o", failover=True, owner="node-a")
        orphan = JobSpec(name="x", failover=True, owner=None)
        regular = JobSpec(name="r", failover=False, owner=None)
        for job in (owned, orphan, regular):
            store.add(job)
        assert len(store.by_owner("node-a")) == 1
        assert [j.id for j in store.orphaned()] == [orphan.id]
        assert store.claim(orphan.id, "node-b") is True
        assert orphan.owner == "node-b"
        assert store.claim(orphan.id, "node-c") is False
        assert store.claim(owned.id, "node-c") is False

    def test_runs(self):
        store = JobStore()
        run = JobRun(job_id="j", job_name="n")
        store.add_run(run)
        assert store.get_run(run.id) is run
        assert store.runs() == [run]
        assert store.runs("j") == [run]
        assert store.runs("other") == []
        assert store.runs("j", limit=0) == []


class TestLeaseStore:
    def test_acquire_renew_release(self):
        store = LeaseStore()
        assert store.acquire("lock", "a", ttl=10.0) is True
        assert store.acquire("lock", "b", ttl=10.0) is False
        assert store.renew("lock", "a", ttl=10.0) is True
        assert store.renew("lock", "b", ttl=10.0) is False
        assert store.release("lock", "b") is False
        assert store.release("lock", "a") is True
        assert store.release("lock", "a") is False
        assert store.get("lock") is None

    def test_ttl_expiry(self):
        store = LeaseStore()
        store.acquire("lock", "a", ttl=0.001)
        time.sleep(0.005)
        assert store.get("lock") is None
        assert store.acquire("lock", "b", ttl=10.0) is True
        assert store.renew("lock", "b", ttl=0.001)
        time.sleep(0.005)
        assert store.renew("lock", "b", ttl=10.0) is False
        assert store.get("lock") is None

    def test_snapshot(self):
        store = LeaseStore()
        store.acquire("lock", "a", ttl=10.0)
        snapshot = store.snapshot()
        assert snapshot["lock"][0] == "a"


class TestBackupStore:
    def test_crud(self):
        store = BackupStore()
        record = BackupRecord(name="b1")
        store.save(record)
        assert store.get(record.id) is record
        assert store.list() == [record]
        assert store.require(record.id) is record
        with pytest.raises(KeyError):
            store.require("missing")
        assert store.remove(record.id) is True
        assert store.remove(record.id) is False

    def test_list_order(self):
        store = BackupStore()
        first = BackupRecord(name="a", created_at=100.0)
        second = BackupRecord(name="b", created_at=200.0)
        store.save(first)
        store.save(second)
        assert store.list() == [second, first]


class TestSnapshotStore:
    def test_snapshots(self):
        store = SnapshotStore()
        store.save_snapshot("s1", {"a": 1})
        store.save_snapshot("s2", {"b": 2})
        assert store.list_snapshots() == ["s1", "s2"]
        assert store.get_snapshot("s1") == {"a": 1}
        assert store.get_snapshot("missing") is None

    def test_records_and_lag(self):
        store = SnapshotStore()
        store.save_record(ReplicationRecord(snapshot_id="s1", replica_id="r1", state=ReplicationState.REPLICATED, lag_seconds=1.0))
        store.save_record(ReplicationRecord(snapshot_id="s1", replica_id="r2", state=ReplicationState.PENDING, lag_seconds=0.0))
        assert store.latest_lag() == 1.0
        assert len(store.records("s1")) == 2
        assert len(store.records()) == 2
        store.update_record("missing", state=ReplicationState.FAILED) if False else None
        record = store.records()[0]
        updated = store.update_record(record.id, error="boom")
        assert updated.error == "boom"
        with pytest.raises(KeyError):
            store.update_record("missing", error="x")

    def test_lag_empty(self):
        assert SnapshotStore().latest_lag() == float("inf")


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


class TestStaticDiscovery:
    def test_discover_peers(self):
        config = make_config(discovery_config={"peers": ["10.0.0.1:8001", "10.0.0.2"]})
        backend = StaticDiscovery(config)
        nodes = asyncio.run(backend.discover())
        assert [n.address for n in nodes] == ["10.0.0.1", "10.0.0.2"]
        assert nodes[0].port == 8001
        assert nodes[1].port == 8000
        assert nodes[0].state == NodeState.JOINED
        assert nodes[0].region == "default"

    def test_parse_peer_no_port(self):
        node_id, address, port = StaticDiscovery._parse_peer("10.1.1.1")
        assert address == "10.1.1.1"
        assert port == 8000
        assert node_id.startswith("node-")


class TestDNSDiscovery:
    async def test_discover_with_resolver(self):
        config = make_config(
            discovery_config={
                "hostname": "svc.local",
                "port": 8000,
                "prefix": "router",
                "resolver": lambda hostname: asyncio.coroutine(lambda: ["1.2.3.4", "5.6.7.8"])(),
            }
        )

        async def fake_resolver(hostname):
            return ["1.2.3.4", "5.6.7.8"]

        config.discovery_config["resolver"] = fake_resolver
        backend = DNSDiscovery(config)
        nodes = await backend.discover()
        assert [n.address for n in nodes] == ["1.2.3.4", "5.6.7.8"]
        assert nodes[0].id == "router-0"
        assert nodes[0].name == "svc.local#0"

    async def test_discover_missing_hostname(self):
        backend = DNSDiscovery(make_config(discovery_config={}))
        with pytest.raises(DiscoveryError):
            await backend.discover()

    async def test_discover_resolution_error(self):
        config = make_config(discovery_config={"hostname": "svc.local"})

        async def broken(hostname):
            raise OSError("no route")

        config.discovery_config["resolver"] = broken
        backend = DNSDiscovery(config)
        with pytest.raises(DiscoveryError):
            await backend.discover()

    async def test_default_resolver_uses_loop(self, monkeypatch):
        config = make_config(discovery_config={"hostname": "svc.local"})
        backend = DNSDiscovery(config)
        loop = asyncio.get_running_loop()
        calls = []

        async def fake_getaddrinfo(*args, **kwargs):
            calls.append(args)
            return [(2, 1, 6, "", ("10.0.0.9", 0)), (2, 1, 6, "", ("10.0.0.9", 0))]

        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        nodes = await backend.discover()
        assert [n.address for n in nodes] == ["10.0.0.9"]
        assert calls


class TestKubernetesDiscovery:
    async def test_discover_pods(self):
        config = make_config(
            discovery_config={
                "api_server": "https://k8s.example",
                "namespace": "prod",
                "label_selector": "app=ai-router",
            }
        )

        async def fake_transport(backend, method, url):
            assert method == "GET"
            assert "labelSelector=app=ai-router" in url
            return {
                "items": [
                    {
                        "metadata": {
                            "uid": "pod-1",
                            "name": "router-abc",
                            "labels": {"app": "ai-router", "topology.kubernetes.io/region": "us-east"},
                        },
                        "status": {"podIP": "10.244.0.1"},
                    },
                    {"metadata": {"uid": "pod-2", "name": "router-def"}, "status": {"podIP": ""}},
                ]
            }

        backend = KubernetesDiscovery(config, transport=fake_transport)
        nodes = await backend.discover()
        assert len(nodes) == 1
        assert nodes[0].id == "pod-1"
        assert nodes[0].address == "10.244.0.1"
        assert nodes[0].region == "us-east"
        assert nodes[0].labels["app"] == "ai-router"

    async def test_transport_failure(self):
        async def failing(backend, method, url):
            raise ConnectionError("boom")

        backend = KubernetesDiscovery(make_config(), transport=failing)
        with pytest.raises(DiscoveryError):
            await backend.discover()


class TestConsulDiscovery:
    async def test_discover_instances(self):
        config = make_config(discovery_config={"address": "http://consul:8500", "service": "router"})

        async def fake_transport(backend, method, url):
            assert method == "GET"
            assert "passing=true" in url
            return [
                {
                    "Node": {"ID": "node-1", "Address": "10.0.0.5"},
                    "Service": {"ID": "svc-1", "Service": "router", "Address": "10.0.0.6", "Port": 9000, "Meta": {"tier": "gold"}},
                },
                {"Node": {"ID": "node-2", "Address": "10.0.0.7"}, "Service": {"Service": "router", "Address": "", "Port": 9000}},
            ]

        backend = ConsulDiscovery(config, transport=fake_transport)
        nodes = await backend.discover()
        assert len(nodes) == 2
        assert nodes[0].address == "10.0.0.6"
        assert nodes[0].port == 9000
        assert nodes[0].labels == {"tier": "gold"}
        assert nodes[1].address == "10.0.0.7"  # falls back to Node.Address

    async def test_register_and_deregister(self):
        config = make_config(discovery_config={"address": "http://consul:8500", "service": "router", "tag": "blue"})
        seen = {}

        async def fake_transport(backend, method, url):
            seen["method"] = method
            seen["url"] = url

        backend = ConsulDiscovery(config, transport=fake_transport)
        await backend.register(make_node("local"))
        assert seen["method"] == "PUT"
        assert "register" in seen["url"]
        await backend.deregister("local")
        assert "deregister/local" in seen["url"]

    async def test_transport_failure(self):
        async def failing(backend, method, url):
            raise ConnectionError("boom")

        backend = ConsulDiscovery(make_config(), transport=failing)
        with pytest.raises(DiscoveryError):
            await backend.discover()


class TestEtcdDiscovery:
    async def test_discover_keys(self):
        config = make_config(
            discovery_config={"endpoints": ["http://etcd:2379"], "prefix": "/ai-router/nodes/"}
        )

        def b64(text):
            return base64.b64encode(text.encode()).decode()

        async def fake_transport(backend, method, url):
            assert method == "POST"
            return {
                "kvs": [
                    {"key": b64("/ai-router/nodes/node-1"), "value": b64("10.0.0.1:8001")},
                    {"key": b64("/other/prefix"), "value": b64("10.0.0.9:8001")},
                ]
            }

        backend = EtcdDiscovery(config, transport=fake_transport)
        nodes = await backend.discover()
        assert len(nodes) == 1
        assert nodes[0].id == "node-1"
        assert nodes[0].address == "10.0.0.1"
        assert nodes[0].port == 8001

    async def test_discover_value_without_port(self):
        config = make_config(discovery_config={"endpoints": ["http://etcd:2379"]})

        def b64(text):
            return base64.b64encode(text.encode()).decode()

        async def fake_transport(backend, method, url):
            return {"kvs": [{"key": b64("/ai-router/nodes/n2"), "value": b64("10.0.0.2")}]}

        backend = EtcdDiscovery(config, transport=fake_transport)
        nodes = await backend.discover()
        assert nodes[0].address == "10.0.0.2"
        assert nodes[0].port == 8000

    async def test_register_and_deregister(self):
        config = make_config(discovery_config={"endpoints": ["http://etcd:2379"]})
        calls = []

        async def fake_transport(backend, method, url):
            calls.append((method, url))

        backend = EtcdDiscovery(config, transport=fake_transport)
        await backend.register(make_node("n1"))
        assert calls[-1][1].endswith("/v3/kv/put")
        await backend.deregister("n1")
        assert calls[-1][1].endswith("/v3/kv/deleterange")

    async def test_transport_failure(self):
        async def failing(backend, method, url):
            raise ConnectionError("boom")

        backend = EtcdDiscovery(make_config(), transport=failing)
        with pytest.raises(DiscoveryError):
            await backend.discover()


class TestDiscoveryRegistry:
    def test_b64_or_str(self):
        assert _b64_or_str(123) == ""
        assert _b64_or_str("plain-value") == "plain-value"
        import base64 as _b64

        encoded = _b64.b64encode(b"10.0.0.1:8001").decode()
        assert _b64_or_str(encoded) == "10.0.0.1:8001"

    def test_create_backends(self):
        registry = DiscoveryRegistry()
        for discovery_type, expected in (
            ("static", StaticDiscovery),
            ("dns", DNSDiscovery),
            ("kubernetes", KubernetesDiscovery),
            ("consul", ConsulDiscovery),
            ("etcd", EtcdDiscovery),
        ):
            backend = registry.create(make_config(discovery_type=discovery_type))
            assert isinstance(backend, expected)

    def test_unknown_type(self):
        with pytest.raises(DiscoveryError):
            DiscoveryRegistry().create(make_config(discovery_type="nope"))

    def test_register_custom(self):
        class CustomBackend(StaticDiscovery):
            pass

        registry = DiscoveryRegistry()
        registry.register("custom", CustomBackend)
        backend = registry.create(make_config(discovery_type="custom"))
        assert isinstance(backend, CustomBackend)

    def test_create_discovery_overrides(self):
        with pytest.raises(TypeError):
            create_discovery(make_config(), bogus=1)


    async def test_close_and_http_ensure(self):
        import httpx

        backend = KubernetesDiscovery(make_config(discovery_config={"token": "secret-token"}))
        await backend.start()
        assert backend.client is not None
        assert "Bearer secret-token" in backend.client.headers.get("Authorization", "")
        await backend.close()
        assert backend.client is None
        await backend.close()  # idempotent

    async def test_k8s_token_file_fallback(self, tmp_path):
        import httpx

        token_file = tmp_path / "token"
        token_file.write_text("file-token")
        backend = KubernetesDiscovery(
            make_config(discovery_config={"token_file": str(token_file)})
        )
        await backend.start()
        assert "Bearer file-token" in backend.client.headers.get("Authorization", "")
        await backend.close()

    async def test_k8s_token_file_missing(self):
        import httpx

        backend = KubernetesDiscovery(
            make_config(discovery_config={"token_file": "/nonexistent/token"})
        )
        await backend.start()
        assert backend.client is not None
        await backend.close()

    async def test_discover_datacenter_and_skips(self):
        config = make_config(
            discovery_config={"address": "http://consul:8500", "service": "router", "datacenter": "dc1"}
        )

        async def fake_transport(backend, method, url):
            assert "&dc=dc1" in url
            return [
                {"Node": {"ID": "n1", "Address": "10.0.0.1"}, "Service": {"ID": "s1", "Service": "router", "Port": 9000}},
                {"Node": {"ID": "n2", "Address": ""}, "Service": {"Service": "router"}},
            ]

        backend = ConsulDiscovery(config, transport=fake_transport)
        nodes = await backend.discover()
        assert [n.id for n in nodes] == ["s1"]

    async def test_consul_register_deregister_errors(self):
        async def failing(backend, method, url):
            raise ConnectionError("boom")

        backend = ConsulDiscovery(make_config(), transport=failing)
        with pytest.raises(DiscoveryError):
            await backend.register(make_node("x"))
        with pytest.raises(DiscoveryError):
            await backend.deregister("x")

    async def test_etcd_register_deregister_errors(self):
        async def failing(backend, method, url):
            raise ConnectionError("boom")

        backend = EtcdDiscovery(make_config(), transport=failing)
        with pytest.raises(DiscoveryError):
            await backend.register(make_node("x"))
        with pytest.raises(DiscoveryError):
            await backend.deregister("x")


class TestDefaultTransport:
    async def test_http_error(self):
        import httpx

        backend = ConsulDiscovery(make_config())
        backend.client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        )
        with pytest.raises(DiscoveryError):
            await _default_transport(backend, "GET", "http://example.test/v1")
        await backend.client.aclose()

    async def test_http_success(self):
        import httpx

        backend = ConsulDiscovery(make_config())
        backend.client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"ok": True})
            )
        )
        body = await _default_transport(backend, "GET", "http://example.test/v1")
        assert body == {"ok": True}
        await backend.client.aclose()


# ---------------------------------------------------------------------------
# election
# ---------------------------------------------------------------------------


class FakeKV:
    def __init__(self):
        self._data = {}

    async def set_nx(self, key, value, ttl):
        if key in self._data:
            return False
        self._data[key] = (value, time.time() + ttl)
        return True

    async def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires <= time.time():
            return None
        return value

    async def expire(self, key, ttl):
        if key in self._data:
            value, _ = self._data[key]
            self._data[key] = (value, time.time() + ttl)
            return True
        return False

    async def delete(self, key):
        return self._data.pop(key, None) is not None


class TestLeaseElection:
    async def test_acquire_and_leadership(self):
        node = make_node("node-a")
        elector = LeaseElection(make_config(), node, ClusterLogger(make_config()))
        assert await elector.elect() is True
        assert elector.is_leader
        assert elector.current_leader == "node-a"

    async def test_conflict_and_observer(self):
        config = make_config()
        logger = ClusterLogger(config)
        store = LeaseStore()
        first = LeaseElection(config, make_node("node-a"), logger, store)
        second = LeaseElection(config, make_node("node-b"), logger, store)
        changes = []
        first.on_change(lambda leader, epoch: _collect(changes, leader, epoch))
        assert await first.elect() is True
        assert await second.elect() is False
        assert second.current_leader == "node-a"
        assert second.is_leader is False
        assert changes == [("node-a", 1)]

    async def test_observer_unsubscribe(self):
        config = make_config()
        elector = LeaseElection(config, make_node("node-a"), ClusterLogger(config))
        changes = []
        unsubscribe = elector.on_change(lambda leader, epoch: changes.append(leader))
        unsubscribe()
        await elector.elect()
        assert changes == []

    async def test_renew_and_step_down(self):
        config = make_config()
        elector = LeaseElection(config, make_node("node-a"), ClusterLogger(config))
        await elector.elect()
        changes = []
        elector.on_change(lambda leader, epoch: changes.append(leader))
        assert await elector.elect() is True  # renew
        assert changes == []
        assert await elector.step_down() is True
        assert changes == [None]
        assert elector.is_leader is False
        assert await elector.step_down() is False

    async def test_expired_lease_reacquired(self):
        config = make_config()
        logger = ClusterLogger(config)
        store = LeaseStore()
        first = LeaseElection(config, make_node("a"), logger, store)
        second = LeaseElection(config, make_node("b"), logger, store)
        await first.elect()
        # force expiry of the lease held by a
        store.acquire("cluster-leader", "a", ttl=0.001)
        time.sleep(0.005)
        assert await second.elect() is True
        assert second.is_leader

    async def test_start_stop_loop(self):
        config = make_config(election_retry_interval=0.01)
        node = make_node("node-a")
        elector = LeaseElection(config, node, ClusterLogger(config))
        await elector.start()
        assert await wait_until(lambda: elector.is_leader)
        await elector.stop()
        assert elector.current_leader == "node-a"

    async def test_start_stop_idempotent(self):
        elector = LeaseElection(make_config(), make_node("a"), ClusterLogger(make_config()))
        await elector.start()
        await elector.start()
        await elector.stop()
        await elector.stop()

    async def test_loop_survives_election_error(self):
        class FlakyElector(LeaseElection):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.failures = 0

            async def elect(self):
                if self.failures < 1:
                    self.failures += 1
                    raise RuntimeError("transient")
                return await super().elect()

        config = make_config(election_retry_interval=0.005)
        logger = ClusterLogger(config)
        elector = FlakyElector(config, make_node("a"), logger)
        await elector.start()
        assert await wait_until(lambda: elector.is_leader)
        await elector.stop()
        assert any("election_error" in e["event"] for e in logger.events)


async def _collect(changes, leader, epoch):
    changes.append((leader, epoch))


class TestRedisElection:
    async def test_acquire_renew_release(self):
        kv = FakeKV()
        config = make_config()
        node = make_node("node-a")
        elector = RedisElection(config, node, ClusterLogger(config), kv)
        assert await elector.elect() is True
        assert elector.is_leader
        assert await elector.elect() is True
        assert await elector.step_down() is True
        assert elector.is_leader is False
        assert await elector.step_down() is False

    async def test_conflict(self):
        kv = FakeKV()
        config = make_config()
        logger = ClusterLogger(config)
        first = RedisElection(config, make_node("a"), logger, kv)
        second = RedisElection(config, make_node("b"), logger, kv)
        await first.elect()
        assert await second.elect() is False
        assert second.current_leader == "a"
        await first.step_down()
        assert await second.elect() is True

    async def test_observer_on_change(self):
        kv = FakeKV()
        config = make_config()
        elector = RedisElection(config, make_node("a"), ClusterLogger(config), kv)
        changes = []
        elector.on_change(lambda leader, epoch: changes.append(leader))
        await elector.elect()
        assert changes == ["a"]

    async def test_loop(self):
        kv = FakeKV()
        elector = RedisElection(
            make_config(election_retry_interval=0.005), make_node("a"), ClusterLogger(make_config()), kv
        )
        await elector.start()
        assert await wait_until(lambda: elector.is_leader)
        await elector.stop()


class TestKubernetesLeaseElection:
    async def test_acquire_renew_release(self):
        calls = []

        async def fake_transport(backend, method, url, body=None):
            calls.append((method, url))
            if method == "GET":
                return {"spec": {"holderIdentity": "node-a"}}
            return {}

        config = make_config(discovery_config={"api_server": "https://k8s", "lease_name": "leader"})
        elector = KubernetesLeaseElection(config, make_node("node-a"), ClusterLogger(config), fake_transport)
        assert await elector.elect() is True
        assert elector.is_leader
        assert await elector.elect() is True
        assert len([m for m, _ in calls if m == "PUT"]) == 2  # renew each round
        assert await elector.step_down() is True
        assert elector.is_leader is False
        assert "DELETE" in [m for m, _ in calls]

    async def test_acquire_when_unheld(self):
        async def fake_transport(backend, method, url, body=None):
            if method == "GET":
                return {"spec": {}}
            return {}

        config = make_config(discovery_config={"api_server": "https://k8s"})
        elector = KubernetesLeaseElection(config, make_node("node-a"), ClusterLogger(config), fake_transport)
        assert await elector.elect() is True
        assert elector.is_leader

    async def test_conflict(self):
        async def fake_transport(backend, method, url, body=None):
            if method == "GET":
                return {"spec": {"holderIdentity": "someone-else"}}
            return {}

        config = make_config(discovery_config={"api_server": "https://k8s"})
        elector = KubernetesLeaseElection(config, make_node("node-a"), ClusterLogger(config), fake_transport)
        assert await elector.elect() is False
        assert elector.current_leader == "someone-else"

    async def test_read_failure_is_caught(self):
        async def fake_transport(backend, method, url, body=None):
            raise ConnectionError("boom")

        config = make_config(discovery_config={"api_server": "https://k8s"})
        logger = ClusterLogger(config)
        elector = KubernetesLeaseElection(config, make_node("node-a"), logger, fake_transport)
        assert await elector.elect() is False
        assert any("election_error" in e["event"] for e in logger.events)

    async def test_acquire_failure_raises(self):
        calls = {"get": 0}

        async def fake_transport(backend, method, url, body=None):
            if method == "GET":
                return {"spec": {}}
            raise ConnectionError("boom")

        config = make_config(discovery_config={"api_server": "https://k8s"})
        elector = KubernetesLeaseElection(config, make_node("node-a"), ClusterLogger(config), fake_transport)
        with pytest.raises(ElectionError):
            await elector.elect()

    async def test_step_down_release_error(self):
        async def fake_transport(backend, method, url, body=None):
            if method == "GET":
                return {"spec": {"holderIdentity": "node-a"}}
            if method == "DELETE":
                raise ConnectionError("boom")
            return {}

        config = make_config(discovery_config={"api_server": "https://k8s"})
        elector = KubernetesLeaseElection(config, make_node("node-a"), ClusterLogger(config), fake_transport)
        await elector.elect()
        with pytest.raises(ElectionError):
            await elector.step_down()


class TestElectionRegistry:
    def test_lease_strategy(self):
        config = make_config()
        registry = ElectionRegistry()
        elector = registry.create(config, make_node("a"), ClusterLogger(config), store=LeaseStore())
        assert isinstance(elector, LeaseElection)

    def test_redis_strategy(self):
        config = make_config(election_strategy="redis")
        elector = ElectionRegistry().create(config, make_node("a"), ClusterLogger(config), kv=FakeKV())
        assert isinstance(elector, RedisElection)

    def test_redis_requires_kv(self):
        config = make_config(election_strategy="redis")
        with pytest.raises(ElectionError):
            ElectionRegistry().create(config, make_node("a"), ClusterLogger(config))

    def test_kubernetes_strategy(self):
        config = make_config(election_strategy="kubernetes")
        elector = ElectionRegistry().create(
            config, make_node("a"), ClusterLogger(config), transport=lambda *a, **k: {}
        )
        assert isinstance(elector, KubernetesLeaseElection)

    def test_kubernetes_requires_transport(self):
        config = make_config(election_strategy="kubernetes")
        with pytest.raises(ElectionError):
            ElectionRegistry().create(config, make_node("a"), ClusterLogger(config))

    def test_unknown_strategy(self):
        config = make_config(election_strategy="consul-raffle")
        with pytest.raises(ElectionError):
            ElectionRegistry().create(config, make_node("a"), ClusterLogger(config))

    def test_extra_overrides_rejected(self):
        config = make_config()
        with pytest.raises(TypeError):
            ElectionRegistry().create(config, make_node("a"), ClusterLogger(config), store=LeaseStore(), kv=FakeKV())

    def test_create_elector_factory(self):
        elector = create_elector(make_config(), make_node("a"), ClusterLogger(make_config()))
        assert isinstance(elector, LeaseElection)
        with pytest.raises(TypeError):
            create_elector(make_config(), bogus=1)


# ---------------------------------------------------------------------------
# scheduler + cron
# ---------------------------------------------------------------------------


class TestCronExpression:
    def test_every_minute(self):
        cron = CronExpression("* * * * *")
        assert cron.matches(datetime(2026, 8, 1, 10, 30))
        nxt = cron.next_after(datetime(2026, 8, 1, 10, 30, 59))
        assert nxt == datetime(2026, 8, 1, 10, 31)

    def test_step(self):
        cron = CronExpression("*/15 * * * *")
        assert cron.matches(datetime(2026, 8, 1, 10, 30))
        assert not cron.matches(datetime(2026, 8, 1, 10, 31))
        assert cron.next_after(datetime(2026, 8, 1, 10, 31)) == datetime(2026, 8, 1, 10, 45)

    def test_range_and_list(self):
        cron = CronExpression("0 9-10 * * 1-5")
        assert cron.matches(datetime(2026, 8, 4, 9, 0))  # Tuesday (dow 1)
        assert not cron.matches(datetime(2026, 8, 2, 9, 0))  # Sunday (dow 6)
        cron = CronExpression("5,10 * * * *")
        assert cron.matches(datetime(2026, 8, 1, 1, 5))
        assert not cron.matches(datetime(2026, 8, 1, 1, 6))

    def test_dom_dow_either(self):
        cron = CronExpression("0 0 13 * 5")
        assert cron.matches(datetime(2026, 8, 15, 0, 0))  # Saturday (dow 5)
        assert cron.matches(datetime(2026, 8, 13, 0, 0))  # the 13th (Thursday)

    def test_month_rollover(self):
        cron = CronExpression("0 0 1 * *")
        assert cron.next_after(datetime(2026, 8, 31, 12)) == datetime(2026, 9, 1, 0, 0)

    def test_day_rollover(self):
        cron = CronExpression("30 14 * * *")
        assert cron.next_after(datetime(2026, 8, 1, 15)) == datetime(2026, 8, 2, 14, 30)

    def test_invalid_expressions(self):
        with pytest.raises(ValueError):
            CronExpression("* * * *")
        with pytest.raises(ValueError):
            CronExpression("*/0 * * * *")
        with pytest.raises(ValueError):
            CronExpression("foo * * * *")
        with pytest.raises(ValueError):
            CronExpression("70 * * * *")
        with pytest.raises(ValueError):
            CronExpression("1-5-9 * * * *")
        with pytest.raises(ValueError):
            CronExpression("", )

    def test_step_range(self):
        cron = CronExpression("30-59/5 * * * *")
        assert cron.matches(datetime(2026, 8, 1, 10, 35))
        assert not cron.matches(datetime(2026, 8, 1, 10, 32))

    def test_no_future_match(self):
        cron = CronExpression("0 0 30 2 *")
        with pytest.raises(ValueError):
            cron.next_after(datetime(2026, 1, 1))


class TestScheduler:
    async def test_add_job_next_run(self):
        scheduler = DistributedScheduler(make_config())
        recurring = JobSpec(name="r", interval=60.0)
        delayed = JobSpec(name="d", type=JobType.DELAYED, delay=5.0)
        cron = JobSpec(name="c", type=JobType.CRON, cron="* * * * *")
        now = time.time()
        scheduler.add_job(recurring)
        scheduler.add_job(delayed)
        scheduler.add_job(cron)
        assert recurring.next_run - now >= 59
        assert delayed.next_run - now >= 4
        assert cron.next_run > now

    async def test_add_cron_without_expression(self):
        scheduler = DistributedScheduler(make_config())
        with pytest.raises(SchedulerError):
            scheduler.add_job(JobSpec(name="c", type=JobType.CRON))

    async def test_schedule_type_inference(self):
        scheduler = DistributedScheduler(make_config())
        by_cron = scheduler.schedule("a", lambda p: None, cron="0 0 * * *")
        by_delay = scheduler.schedule("b", lambda p: None, delay=10)
        by_singleton = scheduler.schedule("c", lambda p: None, singleton=True)
        by_failover = scheduler.schedule("d", lambda p: None, failover=True)
        by_default = scheduler.schedule("e", lambda p: None)
        assert by_cron.type == JobType.CRON
        assert by_delay.type == JobType.DELAYED
        assert by_singleton.type == JobType.SINGLETON
        assert by_failover.type == JobType.FAILOVER
        assert by_default.type == JobType.RECURRING
        assert "a" in scheduler.handlers

    async def test_run_sync_handler(self):
        scheduler = DistributedScheduler(make_config())
        ran = []
        job = scheduler.schedule("t", lambda payload: ran.append(payload.get("x")) or "ok", payload={"x": 1}, timeout=5)
        run = await scheduler.run_now(job.id)
        assert ran == [1]
        assert run.state == JobState.SUCCEEDED
        assert run.result == "ok"
        assert job.last_run > 0

    async def test_run_async_handler(self):
        scheduler = DistributedScheduler(make_config())

        async def handler(payload):
            await asyncio.sleep(0.01)
            return "async-ok"

        job = scheduler.schedule("a", handler, timeout=5)
        run = await scheduler.run_now(job.id)
        assert run.result == "async-ok"

    async def test_tick_executes_due(self):
        scheduler = DistributedScheduler(make_config())
        ran = []
        job = scheduler.schedule("t", lambda payload: ran.append(1), interval=1, timeout=5)
        job.next_run = time.time() - 60
        started = await scheduler.tick(time.time())
        assert started == 1
        assert await wait_until(lambda: len(ran) == 1)
        assert job.next_run > 0
        assert scheduler.status()["executed"] == 1

    async def test_delayed_job_removed_after_success(self):
        scheduler = DistributedScheduler(make_config())
        job = scheduler.schedule("d", lambda payload: "done", delay=1, timeout=5)
        job.next_run = time.time() - 60
        await scheduler.tick(time.time())
        assert await wait_until(lambda: scheduler.store.get(job.id) is None)
        runs = scheduler.runs(job.id)
        assert runs and runs[0].state == JobState.SUCCEEDED

    async def test_cron_job_rescheduled(self):
        scheduler = DistributedScheduler(make_config())
        job = scheduler.schedule("c", lambda payload: None, cron="* * * * *", timeout=5)
        job.next_run = time.time() - 60
        await scheduler.tick(time.time())
        assert await wait_until(lambda: job.last_run > 0)
        assert job.next_run > 0
        assert scheduler.get_job(job.id) is job

    async def test_missing_handler(self):
        scheduler = DistributedScheduler(make_config())
        job = JobSpec(name="unregistered", interval=1)
        scheduler.add_job(job)
        run = await scheduler.run_now(job.id)
        assert run.state == JobState.FAILED
        assert "no handler" in run.error
        assert scheduler.metrics.counts().get("job_failures") == 1

    async def test_handler_raises(self):
        scheduler = DistributedScheduler(make_config())

        def broken(payload):
            raise ValueError("nope")

        job = scheduler.schedule("b", broken, timeout=5)
        run = await scheduler.run_now(job.id)
        assert run.state == JobState.FAILED
        assert run.error == "nope"

    async def test_retry_then_success(self):
        scheduler = DistributedScheduler(make_config())
        attempts = {"count": 0}

        def flaky(payload):
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise RuntimeError("flaky")
            return "recovered"

        job = scheduler.schedule("f", flaky, interval=0.01, metadata={"retries": 2}, timeout=5)
        first = await scheduler.run_now(job.id)
        assert first.state == JobState.PENDING
        second = await scheduler.run_now(job.id)
        assert second.state == JobState.SUCCEEDED
        assert second.attempts == 2
        assert attempts["count"] == 2

    async def test_retries_exhausted(self):
        scheduler = DistributedScheduler(make_config())

        def always_broken(payload):
            raise RuntimeError("always")

        job = scheduler.schedule("x", always_broken, interval=0.01, metadata={"retries": 1}, timeout=5)
        first = await scheduler.run_now(job.id)
        assert first.state == JobState.PENDING
        second = await scheduler.run_now(job.id)
        assert second.state == JobState.FAILED
        assert job.next_run == 0

    async def test_timeout(self):
        scheduler = DistributedScheduler(make_config())

        async def slow(payload):
            await asyncio.sleep(5)

        job = scheduler.schedule("s", slow, timeout=0.05)
        run = await scheduler.run_now(job.id)
        assert run.state == JobState.FAILED
        assert "timed out" in run.error

    async def test_singleton_leader_only(self):
        scheduler = DistributedScheduler(make_config())
        ran = []
        job = scheduler.schedule("s", lambda payload: ran.append(1), singleton=True, timeout=5)
        scheduler.set_leader_check(lambda: False)
        job.next_run = time.time() - 60
        started = await scheduler.tick(time.time())
        assert started == 0
        scheduler.set_leader_check(lambda: True)
        job.next_run = time.time() - 60
        started = await scheduler.tick(time.time())
        assert started == 1
        assert await wait_until(lambda: len(ran) == 1)

    async def test_failover_claim(self):
        scheduler = DistributedScheduler(make_config())
        scheduler.set_node_id("node-b")
        ran = []
        job = scheduler.schedule("f", lambda payload: ran.append(1), failover=True, interval=1, timeout=5)
        job.owner = "node-a"
        job.next_run = time.time() - 60
        assert await scheduler.tick(time.time()) == 0  # owned elsewhere
        job.owner = None
        job.next_run = time.time() - 60
        assert await scheduler.tick(time.time()) == 1  # claimed
        assert job.owner == "node-b"
        assert await wait_until(lambda: len(ran) == 1)

    async def test_claim_rejected(self):
        scheduler = DistributedScheduler(make_config())
        job = scheduler.schedule("f", lambda payload: None, failover=True, timeout=5)
        job.owner = "node-a"
        job.next_run = time.time() - 60
        scheduler.set_node_id("node-b")
        assert await scheduler.tick(time.time()) == 0

    async def test_remove_and_get(self):
        scheduler = DistributedScheduler(make_config())
        job = scheduler.schedule("r", lambda payload: None, timeout=5)
        assert scheduler.remove_job(job.id) is True
        assert scheduler.remove_job(job.id) is False
        with pytest.raises(JobNotFoundError):
            scheduler.get_job(job.id)

    async def test_pause_resume(self):
        scheduler = DistributedScheduler(make_config(scheduler_interval=0.005))
        ran = []
        job = scheduler.schedule("p", lambda payload: ran.append(1), interval=1, timeout=5)
        scheduler.pause()
        assert scheduler.is_paused
        job.next_run = time.time() - 60
        await scheduler.start()
        await asyncio.sleep(0.05)
        assert ran == []
        scheduler.resume()
        assert not scheduler.is_paused
        job.next_run = time.time() - 60
        assert await wait_until(lambda: len(ran) == 1)
        await scheduler.stop()

    async def test_handlers_registration(self):
        scheduler = DistributedScheduler(make_config())
        scheduler.register_handler("h", lambda p: None)
        assert "h" in scheduler.handlers
        assert scheduler.unregister_handler("h") is True
        assert scheduler.unregister_handler("h") is False

    async def test_runs_and_status(self):
        scheduler = DistributedScheduler(make_config())
        job = scheduler.schedule("s", lambda payload: None, timeout=5)
        await scheduler.run_now(job.id)
        assert len(scheduler.runs()) == 1
        assert len(scheduler.runs(job.id)) == 1
        status = scheduler.status()
        assert status["total_jobs"] == 1
        assert status["by_type"]["recurring"] == 1

    async def test_loop_start_stop(self):
        scheduler = DistributedScheduler(make_config(scheduler_interval=0.01))
        await scheduler.start()
        assert await wait_until(lambda: scheduler.last_tick > 0)
        await scheduler.stop()
        await scheduler.stop()

    async def test_loop_survives_tick_error(self):
        class FlakyScheduler(DistributedScheduler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.failures = 0

            async def tick(self, now=None):
                if self.failures < 1:
                    self.failures += 1
                    raise RuntimeError("tick boom")
                return await super().tick(now)

        logger = ClusterLogger(make_config())
        scheduler = FlakyScheduler(make_config(scheduler_interval=0.005), logger=logger)
        await scheduler.start()
        assert await wait_until(lambda: scheduler.last_tick > 0)
        await scheduler.stop()
        assert any("scheduler_tick_error" in e["event"] for e in logger.events)

    async def test_run_now_unknown(self):
        scheduler = DistributedScheduler(make_config())
        with pytest.raises(JobNotFoundError):
            await scheduler.run_now("missing")

    async def test_cancel_reschedules(self):
        scheduler = DistributedScheduler(make_config())

        async def never(payload):
            await asyncio.sleep(60)

        job = scheduler.schedule("n", never, interval=1, timeout=0)
        task = asyncio.create_task(scheduler.run_now(job.id))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert scheduler.runs(job.id)[0].state == JobState.FAILED
        assert scheduler.runs(job.id)[0].error == "cancelled"
        assert job.next_run > 0

    async def test_concurrent_limit(self):
        scheduler = DistributedScheduler(make_config(scheduler_max_concurrent=1))
        active = {"now": 0, "max": 0}

        async def holder(payload):
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
            await asyncio.sleep(0.05)
            active["now"] -= 1

        a = scheduler.schedule("a", holder, timeout=5)
        b = scheduler.schedule("b", holder, timeout=5)
        await asyncio.gather(scheduler.run_now(a.id), scheduler.run_now(b.id))
        assert active["max"] == 1


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_heartbeat_tracking(self):
        monitor = HealthMonitor(make_config(), store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        heartbeat = monitor.send_heartbeat("a", load=0.3)
        assert heartbeat.node_id == "a"
        assert store.last_heartbeat("a").load == 0.3
        monitor.receive_heartbeat(Heartbeat(node_id="a", timestamp=500.0))
        assert monitor.last_seen("a") == 500.0
        assert monitor.last_seen("missing") == 0.0
        assert not monitor.is_stale("a", now=505.0)
        assert monitor.is_stale("a", now=600.0)

    def test_check_healthy_and_stale(self):
        config = make_config(heartbeat_timeout=5.0)
        monitor = HealthMonitor(config, store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.touch("a")
        report = monitor.check(store.get("a"), now=time.time() + 1)
        assert report.healthy
        assert report.checks["heartbeat_fresh"]
        store.update("a", last_seen=time.time() - 10)
        report = monitor.check(store.get("a"), now=time.time())
        assert not report.healthy
        assert report.last_seen > 0

    def test_custom_checks(self):
        monitor = HealthMonitor(make_config(), store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.touch("a")
        monitor.register_check("disk", lambda node: node.labels.get("disk_ok") == "yes")
        report = monitor.check(store.get("a"))
        assert not report.healthy
        assert report.checks["disk"] is False
        monitor.register_check("raising", lambda node: (_ for _ in ()).throw(RuntimeError("boom")))
        report = monitor.check(store.get("a"))
        assert report.checks["raising"] is False

    async def test_evaluate_failure_and_recovery(self):
        config = make_config(heartbeat_timeout=5.0)
        monitor = HealthMonitor(config, store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.touch("a")
        transitions = []
        monitor.subscribe(lambda node_id, prev, new: _collect_transition(transitions, node_id, prev, new))
        # stale -> SUSPECTED (not healthy before)
        store.update("a", last_seen=time.time() - 10)
        store.mark("a", NodeState.JOINING)
        got = await monitor.evaluate(now=time.time())
        assert any(state == NodeState.SUSPECTED for _, _, state in got)
        # stale from healthy -> FAILED
        store.mark("a", NodeState.HEALTHY)
        store.update("a", last_seen=time.time() - 10)
        got = await monitor.evaluate(now=time.time())
        assert any(state == NodeState.FAILED for _, _, state in got)
        assert store.get("a").state == NodeState.FAILED
        assert transitions
        assert monitor.metrics.counts().get("node_failures") == 1
        # failed stays failed (no auto-revive)
        got = await monitor.evaluate(now=time.time())
        assert got == []
        assert store.get("a").state == NodeState.FAILED
        # suspected recovers to healthy when fresh again
        store.mark("a", NodeState.SUSPECTED)
        store.update("a", last_seen=time.time())
        got = await monitor.evaluate(now=time.time())
        assert any(state == NodeState.HEALTHY for _, _, state in got)
        assert monitor.metrics.counts().get("node_recoveries") == 1

    async def test_evaluate_skips_left_failed(self):
        config = make_config(heartbeat_timeout=5.0)
        monitor = HealthMonitor(config, store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.mark("a", NodeState.LEFT)
        assert await monitor.evaluate(now=time.time()) == []
        store.register(make_node("b"))
        store.update("b", last_seen=0.0)
        store.mark("b", NodeState.FAILED)
        assert await monitor.evaluate(now=time.time()) == []

    async def test_observer_error_isolated(self):
        config = make_config(heartbeat_timeout=5.0)
        logger = ClusterLogger(config)
        monitor = HealthMonitor(config, store=NodeStore(), logger=logger)
        store = monitor.store
        store.register(make_node("a"))

        async def bad_observer(node_id, prev, new):
            raise RuntimeError("observer boom")

        store.mark("a", NodeState.HEALTHY)
        store.update("a", last_seen=time.time() - 10)
        monitor.subscribe(bad_observer)
        await monitor.evaluate(now=time.time())
        assert any("health_observer_error" in e["event"] for e in logger.events)

    async def test_subscribe_unsubscribe(self):
        monitor = HealthMonitor(make_config(), store=NodeStore())
        observer = lambda n, p, s: None
        unsubscribe = monitor.subscribe(observer)
        assert monitor.unsubscribe(observer) is True
        unsubscribe()
        assert monitor.unsubscribe(observer) is False

    async def test_start_stop_idempotent_and_loop_survives(self):
        logger = ClusterLogger(make_config())
        monitor = HealthMonitor(make_config(), store=NodeStore(), logger=logger)
        await monitor.start()
        await monitor.start()  # no-op guard
        assert monitor._running
        await monitor.stop()
        await monitor.stop()  # no-op guard
        assert not monitor._running

    async def test_loop_error_survives(self):
        logger = ClusterLogger(make_config(heartbeat_interval=0.005))
        monitor = HealthMonitor(make_config(heartbeat_interval=0.005), store=NodeStore(), logger=logger)

        async def boom(*args):
            raise RuntimeError("evaluate boom")

        monitor.evaluate = boom
        await monitor.start()
        assert await wait_until(lambda: any("health_eval_error" in e["event"] for e in logger.events))
        await monitor.stop()

    async def test_observer_cancelled_reraises(self):
        monitor = HealthMonitor(make_config(), store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.update("a", last_seen=time.time() - 10)

        async def cancelling_observer(node_id, prev, new):
            raise asyncio.CancelledError

        monitor.subscribe(cancelling_observer)
        with pytest.raises(asyncio.CancelledError):
            await monitor.evaluate(now=time.time())

    async def test_reports_and_lists(self):
        config = make_config(heartbeat_timeout=5.0)
        monitor = HealthMonitor(config, store=NodeStore())
        store = monitor.store
        store.register(make_node("a"))
        store.touch("a")
        store.register(make_node("b"))
        store.update("b", last_seen=time.time() - 10)
        store.mark("b", NodeState.FAILED)
        reports = monitor.reports()
        assert len(reports) == 2
        assert [r.node_id for r in monitor.reports()][0] == "a"
        assert [n.id for n in monitor.healthy_nodes()] == ["a"]
        assert [n.id for n in monitor.dead_nodes()] == ["b"]
        status = monitor.status()
        assert status["healthy"] == 1
        assert status["unhealthy"] == 1
        assert status["total"] == 2

    async def test_loop_start_stop(self):
        monitor = HealthMonitor(make_config(heartbeat_interval=0.01), store=NodeStore())
        monitor.store.register(make_node("a"))
        await monitor.start()
        await asyncio.sleep(0.03)
        await monitor.stop()
        await monitor.stop()
        await monitor.start()
        await monitor.stop()


# ---------------------------------------------------------------------------
# failover
# ---------------------------------------------------------------------------


async def _collect_transition(changes, node_id, prev, new):
    changes.append((node_id, prev, new))


class TestFailover:
    async def test_reassign(self):
        config = make_config()
        store = NodeStore()
        jobs = JobStore()
        failover = FailoverManager(config, store=store, jobs=jobs)
        store.register(make_node("dead-node"))
        owned = JobSpec(name="o", failover=True, owner="dead-node")
        non_failover = JobSpec(name="n", failover=False, owner="dead-node")
        jobs.add(owned)
        jobs.add(non_failover)
        reassigned = await failover.reassign("dead-node")
        assert reassigned == 1
        assert owned.owner is None
        assert non_failover.owner == "dead-node"
        assert len(failover.history()) == 1
        assert failover.history()[0]["jobs_reassigned"] == 1
        assert failover.metrics.counts().get("failovers") == 1

    async def test_reassign_unknown_node(self):
        failover = FailoverManager(make_config(), store=NodeStore(), jobs=JobStore())
        assert await failover.reassign("ghost") == 0

    async def test_health_subscription(self):
        config = make_config(heartbeat_timeout=5.0)
        store = NodeStore()
        jobs = JobStore()
        monitor = HealthMonitor(config, store=store)
        failover = FailoverManager(config, store=store, jobs=jobs, health=monitor)
        store.register(make_node("dead-node"))
        job = JobSpec(name="j", failover=True, owner="dead-node")
        jobs.add(job)
        await failover.start()
        await failover.start()  # idempotent
        store.touch("dead-node")
        store.mark("dead-node", NodeState.HEALTHY)
        store.update("dead-node", last_seen=time.time() - 10)
        await monitor.evaluate(now=time.time())
        assert store.get("dead-node").state == NodeState.FAILED
        assert job.owner is None
        assert len(failover.history()) == 1
        await failover.stop()
        await failover.stop()

    async def test_reassign_orphans(self):
        failover = FailoverManager(make_config(), store=NodeStore(), jobs=JobStore())
        failover.jobs.add(JobSpec(name="o", failover=True, owner=None))
        assert failover.reassign_orphans() == 1

    async def test_status(self):
        failover = FailoverManager(make_config(), store=NodeStore(), jobs=JobStore())
        status = failover.status()
        assert status["failovers"] == 0
        assert status["orphaned_jobs"] == 0
        assert status["last_failover"] is None

    async def test_other_state_changes_ignored(self):
        config = make_config()
        failover = FailoverManager(config, store=NodeStore(), jobs=JobStore())
        assert await failover._on_health_change("a", NodeState.HEALTHY, NodeState.SUSPECTED) is None
        assert failover.history() == []


# ---------------------------------------------------------------------------
# autoscale
# ---------------------------------------------------------------------------


class TestCollectors:
    def test_collector_window_and_sample(self):
        collector = CpuCollector(source=lambda: 42.0, window=2)
        assert collector.sample() == 42.0
        collector.record(50.0)
        collector.record(60.0)
        collector.record(70.0)  # trims window to [60, 70]
        assert collector.last() == 70.0
        assert collector.sample() == (70.0 + 42.0) / 2  # source sampled into trimmed window
        collector.reset()
        assert collector.last() == 0.0
        assert collector.sample() == 42.0  # live source sampled after reset

    def test_collector_types(self):
        assert CpuCollector().name == "cpu"
        assert MemoryCollector().name == "memory"
        assert QueueLengthCollector().name == "queue_length"
        assert RequestRateCollector().name == "request_rate"
        assert TokenThroughputCollector().name == "token_throughput"
        assert MetricCollector().sample() == 0.0
        assert TokenThroughputCollector.default_threshold == 100000.0


class TestAutoscaler:
    async def test_disabled(self):
        autoscaler = Autoscaler(make_config(autoscale_enabled=False))
        assert await autoscaler.evaluate() is None

    async def test_cooldown_skips(self):
        autoscaler = Autoscaler(
            make_config(autoscale_cooldown=1000.0),
            collectors={"cpu": CpuCollector(source=lambda: 95.0)},
        )
        autoscaler.record("cpu", 95.0)
        first = await autoscaler.evaluate(now=time.time() + 5000)
        assert first is not None
        assert await autoscaler.evaluate(now=time.time() + 5001) is None

    async def test_scale_up(self):
        decisions = []
        applied = []
        autoscaler = Autoscaler(
            make_config(min_replicas=1, max_replicas=10, autoscale_cooldown=0),
            collectors={"cpu": CpuCollector()},
            apply_scale=lambda component, replicas: applied.append((component, replicas)),
        )
        autoscaler.set_component("node-1")
        autoscaler.subscribe(lambda decision: decisions.append(decision))
        autoscaler.record("cpu", 140.0)
        decision = await autoscaler.evaluate(now=time.time())
        assert decision is not None
        assert decision.desired > 1
        assert decision.metric == "cpu"
        assert autoscaler.replicas == decision.desired
        assert decisions == [decision]
        assert applied == [("node-1", decision.desired)]
        assert autoscaler.metrics.counts().get("scale_decisions") == 1

    async def test_scale_down(self):
        autoscaler = Autoscaler(
            make_config(min_replicas=1, max_replicas=10, autoscale_cooldown=0),
            collectors={"cpu": CpuCollector()},
        )
        autoscaler.set_replicas(4)
        autoscaler.record("cpu", 20.0)
        decision = await autoscaler.evaluate(now=time.time())
        assert decision is not None
        assert decision.desired == 1
        assert "scale-down" in decision.reason

    async def test_no_decision_when_unchanged(self):
        autoscaler = Autoscaler(
            make_config(min_replicas=1, max_replicas=10, autoscale_cooldown=0),
            collectors={"cpu": CpuCollector()},
        )
        autoscaler.set_replicas(1)
        autoscaler.record("cpu", 10.0)  # below thresholds
        assert await autoscaler.evaluate(now=time.time()) is None

    async def test_unknown_metric(self):
        autoscaler = Autoscaler(make_config())
        with pytest.raises(AutoscaleError):
            autoscaler.record("gpu", 100.0)

    async def test_status_and_decisions(self):
        autoscaler = Autoscaler(
            make_config(min_replicas=1, max_replicas=10, autoscale_cooldown=0),
            collectors={"cpu": CpuCollector()},
        )
        autoscaler.record("cpu", 150.0)
        await autoscaler.evaluate(now=time.time())
        assert len(autoscaler.decisions()) == 1
        status = autoscaler.status()
        assert status["enabled"] is True
        assert "cpu" in status["metrics"]
        assert status["decisions"][0]["desired"] >= 1

    async def test_loop(self):
        autoscaler = Autoscaler(make_config(autoscale_interval=0.01))
        await autoscaler.start()
        await autoscaler.start()
        await asyncio.sleep(0.03)
        await autoscaler.stop()
        await autoscaler.stop()

    async def test_loop_survives_evaluate_error(self):
        class FlakyAutoscaler(Autoscaler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.failures = 0

            async def evaluate(self, now=None):
                if self.failures < 1:
                    self.failures += 1
                    raise RuntimeError("eval boom")
                return None

        logger = ClusterLogger(make_config())
        autoscaler = FlakyAutoscaler(make_config(autoscale_interval=0.005), logger=logger)
        await autoscaler.start()
        assert await wait_until(lambda: autoscaler.failures >= 1)
        await autoscaler.stop()
        assert any("autoscale_error" in e["event"] for e in logger.events)

    async def test_set_replicas(self):
        autoscaler = Autoscaler(make_config())
        autoscaler.set_replicas(7)
        assert autoscaler.replicas == 7
        autoscaler.set_replicas(0)
        assert autoscaler.replicas == 1

    async def test_observer_error_isolated(self):
        autoscaler = Autoscaler(
            make_config(min_replicas=1, max_replicas=10, autoscale_cooldown=0),
            collectors={"cpu": CpuCollector(source=lambda: 130.0)},
        )

        async def bad(decision):
            raise RuntimeError("boom")

        autoscaler.subscribe(bad)
        autoscaler.record("cpu", 130.0)
        decision = await autoscaler.evaluate(now=time.time() + 5000)
        assert decision is not None


# ---------------------------------------------------------------------------
# deployments
# ---------------------------------------------------------------------------


def make_deployment_manager(**kwargs):
    store = NodeStore()
    store.register(make_node("n1"))
    store.register(make_node("n2"))
    store.register(make_node("n3"))
    return DeploymentManager(make_config(), store=store, **kwargs)


class TestDeploymentManager:
    async def test_rolling_full_lifecycle(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.ROLLING, batch_size=1)
        deployment = manager.deploy(spec)
        assert deployment.state == DeploymentState.PENDING
        await manager.poll()
        assert deployment.state == DeploymentState.PREPARING
        await manager.poll()
        assert deployment.state == DeploymentState.DEPLOYING
        await manager.poll()
        assert deployment.state == DeploymentState.DEPLOYING
        assert len(deployment.deployed_nodes) == 1
        assert 0 < deployment.progress < 100
        await manager.poll()
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED
        assert deployment.progress == 100.0
        assert manager.current_version("svc") == "2.0"
        assert manager.traffic_weights("svc") == {"2.0": 100.0}
        assert manager.metrics.counts().get("deployments_completed") == 1

    async def test_rolling_failure_rolls_back(self):
        manager = make_deployment_manager(checker=lambda version, node_id: False)
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.ROLLING, batch_size=1, previous_version="1.0")
        deployment = manager.deploy(spec)
        await manager.poll()
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.ROLLED_BACK
        assert "health check" in deployment.error
        assert deployment.failed_nodes
        assert manager.traffic_weights("svc") == {"1.0": 100.0}
        assert manager.metrics.counts().get("deployments_rolled_back") == 1

    async def test_blue_green_lifecycle(self):
        applied = []
        manager = make_deployment_manager(apply_version=lambda name, version, target: applied.append((name, version, target)))
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.BLUE_GREEN, previous_version="1.0")
        deployment = manager.deploy(spec)
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.DEPLOYING
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.HEALTHY
        assert deployment.traffic == {"2.0": 100.0, "1.0": 0.0}
        await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED
        assert manager.current_version("svc") == "2.0"
        assert manager.traffic_weights("svc") == {"2.0": 100.0}
        assert ("svc", "2.0", "green") in applied

    async def test_blue_green_rollback_after_complete(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.BLUE_GREEN, previous_version="1.0")
        deployment = manager.deploy(spec)
        for _ in range(5):
            await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED
        await manager.rollback(deployment.spec.id)
        assert deployment.state == DeploymentState.ROLLED_BACK
        assert manager.traffic_weights("svc") == {"1.0": 100.0}

    async def test_canary_lifecycle(self):
        applied = []
        manager = make_deployment_manager(apply_version=lambda name, version, target: applied.append((name, version, target)))
        spec = DeploymentSpec(
            name="svc", version="2.0", strategy=DeploymentStrategy.CANARY, canary_percentage=10.0, previous_version="1.0"
        )
        deployment = manager.deploy(spec)
        await manager.poll()
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.HEALTHY
        assert deployment.traffic == {"2.0": 10.0, "1.0": 90.0}
        await manager.promote(deployment.spec.id)
        assert deployment.state == DeploymentState.COMPLETED
        assert deployment.progress == 100.0
        assert manager.traffic_weights("svc") == {"2.0": 100.0}
        assert ("svc", "2.0", "100%") in applied

    async def test_canary_rollback(self):
        manager = make_deployment_manager(checker=lambda version, node_id: False)
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.CANARY, previous_version="1.0")
        deployment = manager.deploy(spec)
        await manager.poll()
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.ROLLED_BACK

    async def test_promote_requires_healthy(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0")
        deployment = manager.deploy(spec)
        with pytest.raises(DeploymentError):
            await manager.promote(deployment.spec.id)

    async def test_rollback_cancelled_raises(self):
        manager = make_deployment_manager()
        deployment = manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        deployment.state = DeploymentState.CANCELLED
        with pytest.raises(DeploymentError):
            await manager.rollback(deployment.spec.id)

    async def test_deploy_validations(self):
        manager = make_deployment_manager()
        with pytest.raises(DeploymentError):
            manager.deploy(DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.CANARY, canary_percentage=150))
        with pytest.raises(DeploymentError):
            manager.deploy(DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.ROLLING, batch_size=0))
        spec = DeploymentSpec(name="svc", version="2.0")
        manager.deploy(spec)
        with pytest.raises(DeploymentError):
            manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        with pytest.raises(DeploymentError):
            manager.deploy(DeploymentSpec(name="svc", version="3.0"))

    async def test_deploy_previous_version_auto(self):
        manager = make_deployment_manager()
        first = manager.deploy(DeploymentSpec(name="svc", version="1.0"))
        for _ in range(6):
            await manager.poll()
        assert first.state == DeploymentState.COMPLETED
        second = manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        assert second.spec.previous_version == "1.0"

    async def test_deploy_same_version_raises(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0")
        manager.deploy(spec)
        manager._versions["svc"] = "2.0"
        with pytest.raises(DeploymentError):
            manager.deploy(DeploymentSpec(name="svc", version="2.0"))

    async def test_blue_green_green_check_rollback(self):
        manager = make_deployment_manager(checker=lambda version, node_id: version == "2.0" and node_id != "green")
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.BLUE_GREEN, previous_version="1.0")
        deployment = manager.deploy(spec)
        for _ in range(3):
            await manager.poll()  # PENDING -> PREPARING -> DEPLOYING -> deploy all nodes
        await manager.poll()  # green env check fails
        assert deployment.state == DeploymentState.ROLLED_BACK
        assert "green environment" in deployment.error

    async def test_blue_green_partial_checker_failure(self):
        manager = make_deployment_manager(checker=lambda version, node_id: node_id != "n2")
        spec = DeploymentSpec(name="svc", version="2.0", strategy=DeploymentStrategy.BLUE_GREEN, previous_version="1.0")
        deployment = manager.deploy(spec)
        for _ in range(3):
            await manager.poll()
        assert deployment.deployed_nodes == ["n1", "n3"]
        assert deployment.failed_nodes == ["n2"]
        assert deployment.state == DeploymentState.DEPLOYING

    async def test_canary_poll_finalizes_completed(self):
        applied = []
        manager = make_deployment_manager(apply_version=lambda name, version, target: applied.append((name, version, target)))
        spec = DeploymentSpec(
            name="svc", version="2.0", strategy=DeploymentStrategy.CANARY, canary_percentage=10.0, previous_version="1.0"
        )
        deployment = manager.deploy(spec)
        for _ in range(3):
            await manager.poll()
        assert deployment.state == DeploymentState.HEALTHY
        await manager.poll()  # healthy canary finalizes via _finalize
        assert deployment.state == DeploymentState.COMPLETED
        assert deployment.progress == 100.0
        assert ("svc", "2.0", "100%") in applied
        assert manager.current_version("svc") == "2.0"

    async def test_rollback_without_previous_version(self):
        manager = make_deployment_manager()
        deployment = manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        await manager.rollback(deployment.spec.id)
        assert deployment.state == DeploymentState.ROLLED_BACK
        assert manager.traffic_weights("svc") == {}

    async def test_start_stop_idempotent(self):
        manager = make_deployment_manager()
        await manager.start()
        await manager.start()  # no-op guard
        await manager.stop()
        await manager.stop()  # no-op guard
        assert not manager._running

    async def test_get_and_list(self):
        manager = make_deployment_manager()
        with pytest.raises(DeploymentError):
            manager.get("missing")
        deployment = manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        assert manager.get(deployment.spec.id) is deployment
        assert manager.list() == [deployment]
        assert manager.active() == [deployment]

    async def test_pause_resume(self):
        manager = make_deployment_manager()
        deployment = manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        manager.pause(deployment.spec.id)
        await manager.poll()
        assert deployment.state == DeploymentState.PENDING
        manager.resume_deployment(deployment.spec.id)
        await manager.poll()
        assert deployment.state == DeploymentState.PREPARING
        manager.pause("missing") if False else None
        with pytest.raises(DeploymentError):
            manager.pause("missing")

    async def test_rolling_with_apply_and_weights_during(self):
        applied = []
        manager = make_deployment_manager(apply_version=lambda name, version, target: applied.append((name, version, target)))
        spec = DeploymentSpec(name="svc", version="2.0", previous_version="1.0", batch_size=2)
        deployment = manager.deploy(spec)
        for _ in range(3):
            await manager.poll()
        assert len(deployment.deployed_nodes) == 2
        assert ("svc", "2.0", "n1") in applied
        assert manager.traffic_weights("svc") == {"1.0": 100.0}  # old version still serves
        await manager.poll()
        await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED

    async def test_target_nodes_filter(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0", nodes=["n1"])
        deployment = manager.deploy(spec)
        for _ in range(4):
            await manager.poll()
        assert deployment.deployed_nodes == ["n1"]
        assert deployment.state == DeploymentState.COMPLETED

    async def test_target_nodes_empty(self):
        manager = DeploymentManager(make_config(), store=NodeStore())
        spec = DeploymentSpec(name="svc", version="2.0")
        deployment = manager.deploy(spec)
        for _ in range(4):
            await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED

    async def test_loop_start_stop(self):
        manager = make_deployment_manager()
        await manager.start()
        await asyncio.sleep(0.03)
        await manager.stop()
        await manager.stop()

    async def test_loop_survives_error(self):
        class FlakyDeployments(DeploymentManager):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.failures = 0

            async def poll(self):
                if self.failures < 1:
                    self.failures += 1
                    raise RuntimeError("poll boom")
                return await super().poll()

        logger = ClusterLogger(make_config())
        manager = FlakyDeployments(make_config(), store=NodeStore(), logger=logger)
        await manager.start()
        assert await wait_until(lambda: manager.failures >= 1)
        await manager.stop()
        assert any("deployment_loop_error" in e["event"] for e in logger.events)

    async def test_status(self):
        manager = make_deployment_manager()
        manager.deploy(DeploymentSpec(name="svc", version="2.0"))
        status = manager.status()
        assert len(status["active"]) == 1
        assert status["versions"] == {}

    async def test_poll_healthy_finalizes_rolling(self):
        manager = make_deployment_manager()
        spec = DeploymentSpec(name="svc", version="2.0", previous_version="1.0")
        deployment = manager.deploy(spec)
        for _ in range(6):
            await manager.poll()
        assert deployment.state == DeploymentState.COMPLETED
        assert manager.traffic_weights("svc") == {"2.0": 100.0}


# ---------------------------------------------------------------------------
# replication / backup / DR
# ---------------------------------------------------------------------------


class TestBackupManager:
    def test_create_backup(self):
        provider_calls = []
        manager = BackupManager(
            make_config(backup_prune_max=0),
            state_provider=lambda: provider_calls.append(1) or {"a": 1, "b": 2},
        )
        record = manager.create_backup(name="nightly")
        assert record.name == "nightly"
        assert record.entries == 2
        assert record.size > 0
        assert record.checksum
        assert record.status == BackupStatus.OK
        assert provider_calls == [1]
        assert len(manager.list_backups()) == 1

    def test_create_backup_non_dict(self):
        manager = BackupManager(make_config(), state_provider=lambda: [1, 2])
        with pytest.raises(BackupError):
            manager.create_backup()

    def test_restore(self):
        restored = []
        manager = BackupManager(
            make_config(backup_prune_max=0),
            state_provider=lambda: {"key": "value"},
            restore_target=lambda data: restored.append(data),
        )
        record = manager.create_backup()
        result = manager.restore(record.id)
        assert restored == [{"key": "value"}]
        assert result.restored_at is not None

    def test_restore_checksum_mismatch(self):
        manager = BackupManager(
            make_config(backup_prune_max=0),
            state_provider=lambda: {"key": "value"},
        )
        record = manager.create_backup()
        record.data["key"] = "tampered"
        with pytest.raises(RestoreError):
            manager.restore(record.id)

    def test_restore_target_raises(self):
        manager = BackupManager(
            make_config(backup_prune_max=0),
            state_provider=lambda: {"key": "value"},
            restore_target=lambda data: (_ for _ in ()).throw(RuntimeError("disk full")),
        )
        record = manager.create_backup()
        with pytest.raises(RestoreError):
            manager.restore(record.id)

    def test_restore_failed_status(self):
        manager = BackupManager(make_config(), state_provider=lambda: {})
        record = manager.create_backup()
        record.status = BackupStatus.FAILED
        with pytest.raises(RestoreError):
            manager.restore(record.id)

    def test_get_delete_prune(self):
        manager = BackupManager(make_config(), state_provider=lambda: {"k": 1})
        first = manager.create_backup()
        with pytest.raises(BackupError):
            manager.get("missing")
        assert manager.delete("missing") is False
        assert manager.delete(first.id) is True
        assert len(manager.list_backups()) == 0

    def test_prune_keeps_newest(self):
        manager = BackupManager(
            make_config(backup_prune_max=0),
            state_provider=lambda: {"k": 1},
        )
        backups = [manager.create_backup() for _ in range(5)]
        removed = manager.prune(2)
        assert removed == 3
        remaining = manager.list_backups()
        assert len(remaining) == 2
        assert remaining[0].id == backups[-1].id
        assert manager.prune(100) == 0

    def test_auto_prune_on_create(self):
        manager = BackupManager(
            make_config(backup_prune_max=2),
            state_provider=lambda: {"k": 1},
        )
        for _ in range(4):
            manager.create_backup()
        assert len(manager.list_backups()) == 2

    def test_status(self):
        manager = BackupManager(make_config(), state_provider=lambda: {"k": 1})
        manager.create_backup()
        status = manager.status()
        assert status["count"] == 1
        assert status["latest"]["name"].startswith("backup-")


class TestReplicationManager:
    async def test_replicate_success(self):
        delivered = []
        async def transport(manager, replica, snapshot):
            delivered.append((replica, snapshot))

        manager = ReplicationManager(
            make_config(),
            replicas=["r1", "r2"],
            transport=transport,
        )
        records = await manager.replicate({"a": 1}, snapshot_id="snap-1")
        assert len(records) == 2
        assert all(r.state == ReplicationState.REPLICATED for r in records)
        assert [d[0] for d in delivered] == ["r1", "r2"]
        assert manager.store.get_snapshot("snap-1") == {"a": 1}
        assert manager.lag() >= 0
        assert manager.metrics.counts().get("replications") == 2

    async def test_replicate_failure_isolated(self):
        def failing_transport(manager, replica, snapshot):
            if replica == "bad":
                raise ConnectionError("down")
            return None

        async def failing(manager, replica, snapshot):
            return failing_transport(manager, replica, snapshot)

        manager = ReplicationManager(make_config(), replicas=["bad", "good"], transport=failing)
        records = await manager.replicate({"a": 1})
        by_replica = {r.replica_id: r for r in records}
        assert by_replica["bad"].state == ReplicationState.FAILED
        assert "down" in by_replica["bad"].error
        assert by_replica["good"].state == ReplicationState.REPLICATED

    async def test_default_transport_and_replicas(self):
        manager = ReplicationManager(make_config())
        records = await manager.replicate({"a": 1})
        assert records == []
        manager.add_replica("r1")
        manager.add_replica("r1")
        assert manager.replicas == ["r1"]
        assert manager.remove_replica("r1") is True
        assert manager.remove_replica("r1") is False
        records = await manager.replicate({"a": 2})
        assert records == []
        assert manager.snapshots() == ["snapshot-"] or len(manager.snapshots()) == 2

    async def test_status_and_records(self):
        manager = ReplicationManager(make_config(), replicas=["r1"])
        await manager.replicate({"a": 1}, snapshot_id="s1")
        status = manager.status()
        assert status["replicated"] == 1
        assert status["replicas"] == ["r1"]
        assert len(manager.records()) == 1
        assert len(manager.records("s1")) == 1
        assert manager.lag() >= 0


class TestDisasterRecovery:
    def test_promote_standby(self):
        store = NodeStore()
        store.register(make_node("a", region="eu"))
        store.update("a", role=NodeRole.STANDBY)
        dr = DisasterRecovery(make_config(), store=store)
        node = dr.promote_standby("a")
        assert node.role == NodeRole.FOLLOWER
        assert node.state == NodeState.HEALTHY
        assert dr.metrics.counts().get("standby_promotions") == 1

    def test_promote_errors(self):
        store = NodeStore()
        store.register(make_node("a"))
        dr = DisasterRecovery(make_config(), store=store)
        with pytest.raises(DRFailoverError):
            dr.promote_standby("missing")
        store.update("a", state=NodeState.FAILED)
        with pytest.raises(DRFailoverError):
            dr.promote_standby("a")
        store.update("a", state=NodeState.HEALTHY, role=NodeRole.LEADER)
        with pytest.raises(DRFailoverError):
            dr.promote_standby("a")
        # follower can be "promoted" (no-op)
        store.update("a", state=NodeState.HEALTHY, role=NodeRole.FOLLOWER)
        dr.promote_standby("a")

    def test_demote(self):
        store = NodeStore()
        store.register(make_node("a"))
        dr = DisasterRecovery(make_config(), store=store)
        node = dr.demote("a")
        assert node.role == NodeRole.STANDBY
        with pytest.raises(DRFailoverError):
            dr.demote("missing")

    async def test_failover_region(self):
        store = NodeStore()
        store.register(make_node("a", region="us-east"))
        store.register(make_node("b", region="us-east"))
        store.register(make_node("c", region="us-west"))
        store.update("c", role=NodeRole.STANDBY)
        dr = DisasterRecovery(make_config(), store=store)
        promoted = await dr.failover_region("us-east", standby_region="us-west")
        assert promoted == 2
        assert store.get("a").state == NodeState.FAILED
        assert store.get("b").state == NodeState.FAILED
        assert store.get("c").role == NodeRole.FOLLOWER
        assert dr.metrics.counts().get("region_failovers") == 1

    async def test_failover_region_errors(self):
        dr = DisasterRecovery(make_config(), store=NodeStore())
        with pytest.raises(DRFailoverError):
            await dr.failover_region("nowhere")
        store = NodeStore()
        store.register(make_node("a", region="us-east"))
        dr = DisasterRecovery(make_config(), store=store)
        with pytest.raises(DRFailoverError):
            await dr.failover_region("us-east", standby_region="empty")

    async def test_failover_region_self(self):
        store = NodeStore()
        store.register(make_node("a", region="us-east"))
        store.register(make_node("b", region="us-west"))
        store.update("b", role=NodeRole.STANDBY)
        config = make_config(node_id="a")
        dr = DisasterRecovery(config, store=store)
        await dr.failover_region("us-east", standby_region="us-west")
        assert store.get("a").role == NodeRole.STANDBY

    async def test_dr_status(self):
        store = NodeStore()
        store.register(make_node("a", region="eu"))
        store.update("a", role=NodeRole.STANDBY)
        dr = DisasterRecovery(make_config(), store=store)
        status = dr.dr_status()
        assert status["standbys"] == 1
        assert status["regions"] == ["eu"]
        assert len(status["nodes"]) == 1


# ---------------------------------------------------------------------------
# ClusterManager
# ---------------------------------------------------------------------------


class TestClusterManager:
    async def test_create_factory(self):
        manager = create_cluster_manager(make_config())
        assert isinstance(manager, ClusterManager)
        assert manager.elector is not None
        assert manager.scheduler is not None
        assert manager.health is not None
        assert manager.failover is not None
        assert manager.autoscaler is not None
        assert manager.deployments is not None
        assert manager.backup is not None
        assert manager.replication is not None
        assert manager.dr is not None
        with pytest.raises(TypeError):
            create_cluster_manager(make_config(), bogus=1)

    async def test_factory_shared_stores(self):
        node_store = NodeStore()
        job_store = JobStore()
        lease_store = LeaseStore()
        manager = create_cluster_manager(
            make_config(),
            store=node_store,
            job_store=job_store,
            lease_store=lease_store,
        )
        assert manager.scheduler.store is job_store
        assert manager.store is node_store
        assert manager.elector.store is lease_store

    async def test_join_leave(self):
        config = make_config(election_retry_interval=0.05)
        manager = create_cluster_manager(config)
        assert not manager.running
        await manager.join()
        assert manager.running
        assert manager.store.get(config.node_id).state == NodeState.JOINED
        assert manager.node.state == NodeState.JOINED
        status = await manager.status()
        assert status["cluster"]["running"] is True
        await manager.leave()
        assert not manager.running
        assert manager.store.get(config.node_id).state == NodeState.LEFT

    async def test_join_twice_raises(self):
        manager = create_cluster_manager(make_config())
        await manager.join()
        with pytest.raises(NodeAlreadyJoinedError):
            await manager.join()
        await manager.shutdown()

    async def test_leave_without_join_raises(self):
        manager = create_cluster_manager(make_config())
        with pytest.raises(ClusterNotStartedError):
            await manager.leave()

    async def test_shutdown_idempotent(self):
        manager = create_cluster_manager(make_config())
        await manager.shutdown()
        await manager.shutdown()

    async def test_elected_leader_updates_store(self):
        config = make_config(election_retry_interval=0.01)
        manager = create_cluster_manager(config)
        await manager.join()
        assert await wait_until(lambda: manager.elector.is_leader)
        assert manager.store.leader().id == config.node_id
        assert manager.node.role == NodeRole.LEADER
        assert manager.metrics.counts().get("leader_elections") == 1
        await manager.shutdown()

    async def test_leave_steps_down(self):
        config = make_config(election_retry_interval=0.01)
        manager = create_cluster_manager(config)
        await manager.join()
        assert await wait_until(lambda: manager.elector.is_leader)
        await manager.leave()
        assert not manager.elector.is_leader
        assert manager.elector.current_leader is None

    async def test_discover_registers_members(self):
        peers = ["10.0.0.1:8000", "10.0.0.2:8000"]
        manager = create_cluster_manager(
            make_config(discovery_type="static", discovery_config={"peers": peers})
        )
        await manager.join()
        nodes = await manager.discover()
        assert len(nodes) == 2
        assert manager.store.get(nodes[0].id) is not None
        await manager.shutdown()

    async def test_discover_without_backend(self):
        manager = ClusterManager(make_config(), discovery=None)
        assert await manager.discover() == []

    async def test_rebalance_not_started(self):
        manager = create_cluster_manager(make_config())
        with pytest.raises(ClusterNotStartedError):
            await manager.rebalance()

    async def test_rebalance_reassigns_dead(self):
        config = make_config()
        manager = create_cluster_manager(config)
        store = manager.store
        job_store = manager.scheduler.store
        await manager.join()
        store.register(make_node("dead-node"))
        job = JobSpec(name="j", failover=True, owner="dead-node")
        job_store.add(job)
        store.mark("dead-node", NodeState.FAILED)
        report = await manager.rebalance()
        assert report.failed_nodes == ["dead-node"]
        assert report.reassigned_jobs == 1
        assert job.owner == config.node_id  # claimed by the rebalancing node
        await manager.shutdown()

    async def test_rebalance_claims_orphans(self):
        manager = create_cluster_manager(make_config())
        await manager.join()
        job = JobSpec(name="o", failover=True, owner=None)
        manager.scheduler.store.add(job)
        report = await manager.rebalance()
        assert report.orphaned_jobs == 0  # all claimed
        assert job.owner == manager.node.id
        await manager.shutdown()

    async def test_rebalance_reelects_after_leader_loss(self):
        config = make_config()
        store = NodeStore()
        lease_store = LeaseStore()
        manager = create_cluster_manager(
            config, store=store, lease_store=lease_store
        )
        await manager.join()
        # simulate another node holding the lease and being dead
        store.register(make_node("old-leader"))
        store.mark("old-leader", NodeState.FAILED)
        lease_store.acquire("cluster-leader", "old-leader", ttl=100)
        await manager.elector.elect()
        assert manager.elector.current_leader == "old-leader"
        report = await manager.rebalance()
        assert report.elected_leader is True
        assert report.leader == config.node_id
        await manager.shutdown()

    async def test_rebalance_leader_alive_no_reelection(self):
        config = make_config()
        store = NodeStore()
        lease_store = LeaseStore()
        manager = create_cluster_manager(config, store=store, lease_store=lease_store)
        await manager.join()
        store.register(make_node("alive-leader"))
        lease_store.acquire("cluster-leader", "alive-leader", ttl=100)
        await manager.elector.elect()
        report = await manager.rebalance()
        assert report.elected_leader is False
        assert report.leader == "alive-leader"
        await manager.shutdown()

    async def test_watch_leader_failover_reelects(self):
        config = make_config(election_retry_interval=0.02)
        store = NodeStore()
        lease_store = LeaseStore()
        manager = create_cluster_manager(config, store=store, lease_store=lease_store)
        await manager.join()
        store.register(make_node("old-leader"))
        store.mark("old-leader", NodeState.FAILED)
        lease_store.acquire("cluster-leader", "old-leader", ttl=100)
        await manager.elector.elect()
        assert manager.elector.current_leader == "old-leader"
        assert await wait_until(lambda: manager.elector.is_leader, timeout=2.0)
        await manager.shutdown()

    async def test_status_sections(self):
        manager = create_cluster_manager(make_config(election_retry_interval=0.01))
        await manager.join()
        assert await wait_until(lambda: manager.elector.is_leader)
        status = await manager.status()
        for key in ("cluster", "membership", "leadership", "scheduler", "health", "autoscale", "deployments", "backups", "replication", "dr", "observability"):
            assert key in status, key
        assert status["membership"]["total"] == 1
        assert status["leadership"]["is_leader"] is True
        await manager.shutdown()

    async def test_status_components_optional(self):
        manager = ClusterManager(make_config())
        status = await manager.status()
        assert status["cluster"]["running"] is False
        assert "leadership" not in status
        assert "scheduler" not in status

    async def test_join_elected_leader_and_singleton_scheduler(self):
        config = make_config(election_retry_interval=0.01)
        manager = create_cluster_manager(config)
        await manager.join()
        ran = []
        job = manager.scheduler.schedule("leader-only", lambda p: ran.append(1), singleton=True, interval=0.01, timeout=5)
        assert await wait_until(lambda: manager.elector.is_leader)
        job.next_run = time.time() - 60
        await manager.scheduler.tick(time.time())
        assert await wait_until(lambda: len(ran) == 1)
        await manager.shutdown()

    async def test_end_to_end_failover(self):
        """Two managers sharing stores: leader dies, follower takes over work."""
        config = make_config(heartbeat_timeout=0.05, election_retry_interval=0.01)
        node_store = NodeStore()
        job_store = JobStore()
        lease_store = LeaseStore()

        leader = create_cluster_manager(
            config,
            node_id="leader-node",
            store=node_store,
            job_store=job_store,
            lease_store=lease_store,
        )
        follower = create_cluster_manager(
            config,
            node_id="follower-node",
            store=node_store,
            job_store=job_store,
            lease_store=lease_store,
        )
        await leader.join()
        assert await wait_until(lambda: leader.elector.is_leader)
        await follower.join()
        ran = []
        job = follower.scheduler.schedule(
            "failover-task", lambda p: ran.append(p), failover=True, interval=0.05, timeout=5
        )
        job.owner = "leader-node"
        job.next_run = time.time() - 60
        # leader dies: its process stops, then membership marks it failed
        await leader.shutdown()
        node_store.mark("leader-node", NodeState.FAILED)
        await follower.health.evaluate(now=time.time())
        await follower.rebalance()
        assert job.owner == "follower-node"
        # scheduler claims and runs it
        await follower.scheduler.tick(time.time())
        assert await wait_until(lambda: len(ran) == 1)
        assert follower.store.leader().id == "follower-node"
        await follower.shutdown()

    async def test_join_deregisters_on_leave(self):
        deregistered = []

        class TrackingDiscovery(StaticDiscovery):
            async def deregister(self, node_id):
                deregistered.append(node_id)

        discovery = TrackingDiscovery(
            make_config(discovery_type="static", discovery_config={"peers": []})
        )
        manager = ClusterManager(make_config(), discovery=discovery)
        await manager.join()
        await manager.leave()
        assert deregistered == [manager.node.id]

    async def test_join_without_election_components(self):
        manager = ClusterManager(make_config())
        await manager.join()
        assert manager.running
        await manager.leave()

    async def test_rebalance_leader_lost_reason(self):
        manager = create_cluster_manager(make_config())
        await manager.join()
        report = await manager.rebalance(reason=RebalanceReason.LEADER_LOST)
        assert report.reason == RebalanceReason.LEADER_LOST
        await manager.shutdown()


class TestClusterErrors:
    def test_hierarchy(self):
        assert issubclass(ClusterNotStartedError, ClusterError)
        assert issubclass(NodeAlreadyJoinedError, ClusterError)
        assert issubclass(DiscoveryError, ClusterError)
        assert issubclass(ElectionError, ClusterError)
        assert issubclass(SchedulerError, ClusterError)
        assert issubclass(DeploymentError, ClusterError)
        assert issubclass(AutoscaleError, ClusterError)
        assert issubclass(BackupError, ClusterError)
        assert issubclass(RestoreError, ClusterError)
        assert issubclass(DRFailoverError, ClusterError)
