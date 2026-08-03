"""Node discovery backends (Strategy pattern).

Adapters: static configuration, DNS, Kubernetes, Consul, etcd. External
systems are reached through an injectable ``transport`` (async callable)
so tests run without infrastructure; the default transport is a shared
``httpx.AsyncClient``.
"""

from __future__ import annotations

import asyncio
import base64
import socket
from typing import Any, Awaitable, Callable

from .config import ClusterConfig
from .exceptions import DiscoveryError
from .models import NodeInfo, NodeRole, NodeState, generate_id

Transport = Callable[["DiscoveryBackend", str, str], Awaitable[Any]]
"""transport(backend, method, url) -> response body"""


async def _default_transport(backend: "DiscoveryBackend", method: str, url: str) -> Any:
    try:
        import httpx  # noqa: F401 - availability gate
    except ImportError:  # pragma: no cover - httpx is a project dependency
        raise DiscoveryError("httpx is required for HTTP discovery backends") from None
    client = backend.client
    response = await client.request(method, url)
    if response.status_code >= 400:
        raise DiscoveryError(f"{backend.type} returned HTTP {response.status_code}")
    return response.json()


class DiscoveryBackend:
    """Base class for discovery adapters."""

    type = "base"

    def __init__(self, config: ClusterConfig | None = None, transport: Transport | None = None) -> None:
        self.config = config or ClusterConfig()
        self.client: Any = None
        self.transport = transport or _default_transport

    async def start(self) -> None:
        """Open any client resources. Overridden by HTTP adapters."""

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.aclose()
            except Exception:  # pragma: no cover - defensive
                pass
            self.client = None

    async def register(self, node: NodeInfo) -> None:
        """Advertise the local node. Optional per backend."""

    async def deregister(self, node_id: str) -> None:
        """Remove the local node. Optional per backend."""

    async def discover(self) -> list[NodeInfo]:
        raise NotImplementedError

    def _node(
        self,
        node_id: str,
        address: str,
        port: int,
        *,
        name: str = "",
        region: str = "",
        zone: str = "",
        labels: dict[str, str] | None = None,
        version: str = "",
        capacity: int = 1,
    ) -> NodeInfo:
        return NodeInfo(
            id=node_id or generate_id("node"),
            name=name or node_id or address,
            address=address,
            port=int(port or 0),
            role=NodeRole.FOLLOWER,
            state=NodeState.JOINED,
            region=region or self.config.region,
            zone=zone or self.config.zone,
            labels=dict(labels or {}),
            version=version or self.config.version,
            capacity=int(capacity or 1),
        )


class StaticDiscovery(DiscoveryBackend):
    """Discovery from a static peer list (``discovery_config.peers``)."""

    type = "static"

    async def discover(self) -> list[NodeInfo]:
        peers = self.config.discovery_config.get("peers", [])
        nodes: list[NodeInfo] = []
        for peer in peers:
            node_id, address, port = self._parse_peer(peer)
            nodes.append(self._node(node_id, address, port))
        return nodes

    @staticmethod
    def _parse_peer(peer: str) -> tuple[str, str, int]:
        host_part, _, port_part = peer.rpartition(":")
        host_part = host_part or peer
        port = int(port_part) if port_part.isdigit() else 8000
        node_id = host_part.replace(".", "-").replace("/", "-") or "peer"
        return f"node-{node_id}-{port}", host_part, port


class DNSDiscovery(DiscoveryBackend):
    """Discovery by resolving a hostname into member addresses.

    ``discovery_config``: ``hostname`` (required), ``port`` (default 8000),
    ``prefix`` (node id prefix), ``resolver`` (injectable resolve callable).
    """

    type = "dns"

    def __init__(self, config: ClusterConfig | None = None, transport: Transport | None = None) -> None:
        super().__init__(config, transport)
        self._resolver: Callable[[str], Awaitable[list[str]]] | None = self.config.discovery_config.get("resolver")

    async def _resolve(self, hostname: str) -> list[str]:
        if self._resolver is not None:
            return await self._resolver(hostname)
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        addresses: list[str] = []
        for info in infos:
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)
        return addresses or [hostname]

    async def discover(self) -> list[NodeInfo]:
        hostname = self.config.discovery_config.get("hostname")
        if not hostname:
            raise DiscoveryError("dns discovery requires discovery_config.hostname")
        port = int(self.config.discovery_config.get("port", 8000))
        prefix = self.config.discovery_config.get("prefix", "node")
        try:
            addresses = await self._resolve(hostname)
        except OSError as exc:
            raise DiscoveryError(f"dns resolution failed for {hostname}: {exc}") from exc
        nodes: list[NodeInfo] = []
        for index, address in enumerate(addresses):
            node_id = f"{prefix}-{index}"
            nodes.append(self._node(node_id, address, port, name=f"{hostname}#{index}"))
        return nodes


class KubernetesDiscovery(DiscoveryBackend):
    """Discovers pods by label selector through the Kubernetes API.

    ``discovery_config``: ``api_server`` (default https://kubernetes.default.svc),
    ``token`` (bearer token, default read from token file),
    ``namespace`` (default "default"), ``label_selector`` (default
    "app=ai-router"), ``port`` (container port).
    """

    type = "kubernetes"

    async def start(self) -> None:
        if self.client is None:
            await self._ensure_http()

    async def _ensure_http(self) -> None:
        import httpx

        cfg = self.config.discovery_config
        headers: dict[str, str] = {}
        token = cfg.get("token")
        if token is None:
            token_file = cfg.get("token_file", "/var/run/secrets/kubernetes.io/serviceaccount/token")
            try:
                with open(token_file) as handle:  # noqa: PTH123 - system path
                    token = handle.read().strip()
            except OSError:
                token = ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.AsyncClient(
            verify=bool(cfg.get("verify_tls", False)),
            headers=headers,
        )

    async def discover(self) -> list[NodeInfo]:
        await self.start()
        cfg = self.config.discovery_config
        api_server = cfg.get("api_server", "https://kubernetes.default.svc")
        namespace = cfg.get("namespace", "default")
        label_selector = cfg.get("label_selector", "app=ai-router")
        port = int(cfg.get("port", 8000))
        url = f"{api_server}/api/v1/namespaces/{namespace}/pods?labelSelector={label_selector}"
        try:
            body = await self.transport(self, "GET", url)
        except Exception as exc:
            raise DiscoveryError(f"kubernetes discovery failed: {exc}") from exc
        nodes: list[NodeInfo] = []
        for pod in body.get("items", []):
            metadata = pod.get("metadata", {})
            status = pod.get("status", {})
            node_id = metadata.get("uid") or metadata.get("name") or generate_id("pod")
            pod_ip = status.get("podIP") or ""
            if not pod_ip:
                continue
            nodes.append(
                self._node(
                    node_id,
                    pod_ip,
                    port,
                    name=metadata.get("name", node_id),
                    region=metadata.get("labels", {}).get("topology.kubernetes.io/region", ""),
                    zone=metadata.get("labels", {}).get("topology.kubernetes.io/zone", ""),
                    labels=dict(metadata.get("labels", {})),
                )
            )
        return nodes


class ConsulDiscovery(DiscoveryBackend):
    """Discovers service instances through the Consul health API.

    ``discovery_config``: ``address`` (default http://127.0.0.1:8500),
    ``service`` (default "ai-router"), ``datacenter`` (optional),
    ``tag`` (optional filter).
    """

    type = "consul"

    async def start(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.AsyncClient()

    async def discover(self) -> list[NodeInfo]:
        await self.start()
        cfg = self.config.discovery_config
        address = cfg.get("address", "http://127.0.0.1:8500")
        service = cfg.get("service", "ai-router")
        url = f"{address}/v1/health/service/{service}?passing=true"
        if cfg.get("datacenter"):
            url += f"&dc={cfg['datacenter']}"
        try:
            body = await self.transport(self, "GET", url)
        except Exception as exc:
            raise DiscoveryError(f"consul discovery failed: {exc}") from exc
        nodes: list[NodeInfo] = []
        for entry in body:
            service_info = entry.get("Service", {})
            node_info = entry.get("Node", {})
            address = service_info.get("Address") or node_info.get("Address") or ""
            port = int(service_info.get("Port") or 8000)
            if not address:
                continue
            node_id = service_info.get("ID") or node_info.get("ID") or generate_id("consul")
            nodes.append(
                self._node(
                    node_id,
                    address,
                    port,
                    name=service_info.get("Service") or node_id,
                    labels=dict(service_info.get("Meta", {}) or {}),
                )
            )
        return nodes

    async def register(self, node: NodeInfo) -> None:
        await self.start()
        cfg = self.config.discovery_config
        address = cfg.get("address", "http://127.0.0.1:8500")
        service = cfg.get("service", "ai-router")
        payload = {
            "ID": node.id,
            "Name": service,
            "Address": node.address,
            "Port": node.port,
            "Tags": [cfg["tag"]] if cfg.get("tag") else [],
            "Meta": dict(node.labels),
        }
        try:
            await self.transport(self, "PUT", f"{address}/v1/agent/service/register")
        except Exception as exc:
            raise DiscoveryError(f"consul register failed: {exc}") from exc
        self._last_register = payload

    async def deregister(self, node_id: str) -> None:
        await self.start()
        cfg = self.config.discovery_config
        address = cfg.get("address", "http://127.0.0.1:8500")
        try:
            await self.transport(self, "PUT", f"{address}/v1/agent/service/deregister/{node_id}")
        except Exception as exc:
            raise DiscoveryError(f"consul deregister failed: {exc}") from exc


class EtcdDiscovery(DiscoveryBackend):
    """Discovers member endpoints from an etcd v3 keyspace.

    ``discovery_config``: ``endpoints`` (list, default ["http://127.0.0.1:2379"]),
    ``prefix`` (default "/ai-router/nodes/"), ``port`` (node port),
    ``username``/``password`` (basic auth, optional).
    """

    type = "etcd"

    async def start(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.AsyncClient()

    async def discover(self) -> list[NodeInfo]:
        await self.start()
        cfg = self.config.discovery_config
        endpoints = cfg.get("endpoints") or ["http://127.0.0.1:2379"]
        prefix = cfg.get("prefix", "/ai-router/nodes/")
        port = int(cfg.get("port", 8000))
        nodes: list[NodeInfo] = []
        for endpoint in endpoints:
            url = f"{endpoint}/v3/kv/range"
            try:
                body = await self.transport(self, "POST", url)
            except Exception as exc:
                raise DiscoveryError(f"etcd discovery failed: {exc}") from exc
            # Accept both a raw response and a body carrying a "result" field.
            payload = body if "kvs" in (body or {}) else (body or {}).get("result", {})
            kvs = payload.get("kvs", []) if isinstance(payload, dict) else []
            for kv in kvs:
                raw_key = kv.get("key", "")
                raw_value = kv.get("value", "")
                key_text = _b64_or_str(raw_key)
                if not key_text.startswith(prefix):
                    continue
                node_id = key_text[len(prefix) :] or generate_id("etcd")
                value_text = _b64_or_str(raw_value)
                address, _, port_part = value_text.rpartition(":")
                if not address or not port_part.isdigit():
                    address, port = value_text, port
                else:
                    port = int(port_part)
                nodes.append(self._node(node_id, address, port))
        return nodes

    async def register(self, node: NodeInfo) -> None:
        await self.start()
        cfg = self.config.discovery_config
        endpoints = cfg.get("endpoints") or ["http://127.0.0.1:2379"]
        prefix = cfg.get("prefix", "/ai-router/nodes/")
        key = base64.b64encode(f"{prefix}{node.id}".encode()).decode()
        value = base64.b64encode(f"{node.address}:{node.port}".encode()).decode()
        for endpoint in endpoints:
            url = f"{endpoint}/v3/kv/put"
            try:
                await self.transport(self, "POST", url)
            except Exception as exc:
                raise DiscoveryError(f"etcd register failed: {exc}") from exc
        self._last_register = {"key": key, "value": value}

    async def deregister(self, node_id: str) -> None:
        await self.start()
        cfg = self.config.discovery_config
        endpoints = cfg.get("endpoints") or ["http://127.0.0.1:2379"]
        for endpoint in endpoints:
            url = f"{endpoint}/v3/kv/deleterange"
            try:
                await self.transport(self, "POST", url)
            except Exception as exc:
                raise DiscoveryError(f"etcd deregister failed: {exc}") from exc


def _b64_or_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        decoded = base64.b64decode(value).decode()
        if all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789./-_:" for c in decoded):
            return decoded
    except Exception:  # pragma: no cover - defensive
        pass
    return value


class DiscoveryRegistry:
    """Strategy registry mapping discovery types to backend factories."""

    _backends: dict[str, type[DiscoveryBackend]] = {
        "static": StaticDiscovery,
        "dns": DNSDiscovery,
        "kubernetes": KubernetesDiscovery,
        "consul": ConsulDiscovery,
        "etcd": EtcdDiscovery,
    }

    def register(self, name: str, backend: type[DiscoveryBackend]) -> None:
        self._backends[name] = backend

    def create(self, config: ClusterConfig, transport: Transport | None = None) -> DiscoveryBackend:
        backend_type = self._backends.get(config.discovery_type)
        if backend_type is None:
            raise DiscoveryError(f"unknown discovery type {config.discovery_type!r}")
        return backend_type(config, transport)


def create_discovery(config: ClusterConfig | None = None, **overrides: Any) -> DiscoveryBackend:
    """DI factory for discovery backends."""
    config = config or ClusterConfig()
    registry = overrides.pop("registry", None) or DiscoveryRegistry()
    transport = overrides.pop("transport", None)
    if overrides:
        raise TypeError(f"unexpected discovery overrides: {sorted(overrides)}")
    return registry.create(config, transport)
