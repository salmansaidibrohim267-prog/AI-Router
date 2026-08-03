"""Pluggable secret management (Strategy pattern).

Backends:

- ``environment`` — secrets sourced from environment variables.
- ``vault``       — HashiCorp Vault KV v2 through an injectable transport.
- ``kubernetes``  — Kubernetes ``Secret`` objects through an injectable transport.
- ``aws``         — AWS Secrets Manager through an injectable client.
- ``azure``       — Azure Key Vault secrets through an injectable client/transport.
- ``google``      — Google Secret Manager through an injectable client.

Every backend exposes the same async API; the ``SecretManager`` facade adds
caching, rotation and audit hooks.
"""

from __future__ import annotations

import base64
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from .config import SecurityConfig
from .exceptions import SecretBackendError, SecretNotFoundError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import Secret, SecretKind, generate_id


class SecretBackend(ABC):
    """Secret backend strategy protocol."""

    name = "base"

    def __init__(self, config: SecurityConfig) -> None:
        self.config = config

    async def start(self) -> None:  # noqa: B027
        """Open any client resources (overridden by HTTP adapters)."""

    async def close(self) -> None:  # noqa: B027
        """Release client resources (overridden by HTTP adapters)."""

    @abstractmethod
    async def get(self, name: str) -> Secret:
        """Fetch a secret by name; raise SecretNotFoundError when absent."""

    @abstractmethod
    async def set(self, secret: Secret) -> Secret:
        """Store a secret."""

    @abstractmethod
    async def delete(self, name: str) -> bool:
        """Delete a secret; return False when it did not exist."""

    @abstractmethod
    async def list(self) -> list[str]:
        """List available secret names."""


class EnvironmentBackend(SecretBackend):
    """Secrets sourced from environment variables (``name`` = env var name)."""

    name = "environment"

    async def get(self, name: str) -> Secret:
        value = os.environ.get(name)
        if value is None:
            raise SecretNotFoundError(f"environment secret {name!r} not found")
        return Secret(
            id=generate_id("secret"),
            name=name,
            kind=SecretKind.OPAQUE,
            value=value,
        )

    async def set(self, secret: Secret) -> Secret:
        os.environ[secret.name] = secret.value
        return secret

    async def delete(self, name: str) -> bool:
        if name not in os.environ:
            return False
        os.environ.pop(name, None)
        return True

    async def list(self) -> list[str]:
        return [name for name in os.environ if name.startswith(self.config.secret_config.get("prefix", "SECRET_"))]


class VaultBackend(SecretBackend):
    """HashiCorp Vault KV v2 backend.

    ``secret_config``: ``address``, ``token``/``token_file``, ``mount``
    (default "secret"), ``namespace``. ``transport(backend, method, url, body=None)``
    is injectable for tests.
    """

    name = "vault"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.secret_config
        self.address = cfg.get("address", "http://127.0.0.1:8200").rstrip("/")
        self.mount = cfg.get("mount", "secret")
        self._headers: dict[str, str] = {}
        token = cfg.get("token") or ""
        if not token:
            token_file = cfg.get("token_file")
            if token_file:
                try:
                    with open(token_file) as handle:
                        token = handle.read().strip()
                except OSError:
                    token = ""
        if token:
            self._headers["X-Vault-Token"] = token
        if cfg.get("namespace"):
            self._headers["X-Vault-Namespace"] = cfg["namespace"]

    async def _url(self, name: str) -> str:
        return f"{self.address}/v1/{self.mount}/data/{name}"

    async def get(self, name: str) -> Secret:
        try:
            body = await self.transport(self, "GET", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"vault read failed: {exc}") from exc
        data = body.get("data", {}).get("data", {}) if isinstance(body, dict) else {}
        if not data:
            raise SecretNotFoundError(f"vault secret {name!r} not found")
        return Secret(
            id=generate_id("secret"),
            name=name,
            kind=SecretKind(data.get("kind", "opaque")) if data.get("kind") else SecretKind.OPAQUE,
            value=str(data.get("value", "")),
            metadata=dict(data.get("metadata", {})),
        )

    async def set(self, secret: Secret) -> Secret:
        payload = {"data": {"value": secret.value, "kind": secret.kind.value, "metadata": dict(secret.metadata)}}
        try:
            await self.transport(self, "POST", await self._url(secret.name), body=payload)
        except Exception as exc:
            raise SecretBackendError(f"vault write failed: {exc}") from exc
        return secret

    async def delete(self, name: str) -> bool:
        try:
            await self.transport(self, "DELETE", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"vault delete failed: {exc}") from exc
        return True

    async def list(self) -> list[str]:
        url = f"{self.address}/v1/{self.mount}/metadata"
        try:
            body = await self.transport(self, "LIST", url)
        except Exception as exc:
            raise SecretBackendError(f"vault list failed: {exc}") from exc
        if not isinstance(body, dict):
            return []
        return list(body.get("data", {}).get("keys", []) or [])


class KubernetesBackend(SecretBackend):
    """Kubernetes Secret objects.

    ``secret_config``: ``api_server``, ``token``/``token_file``, ``namespace``,
    ``verify_tls``. Values are base64 encoded in the API; the transport is
    injectable.
    """

    name = "kubernetes"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.secret_config
        self.api_server = cfg.get("api_server", "https://kubernetes.default.svc").rstrip("/")
        self.namespace = cfg.get("namespace", "default")
        token = cfg.get("token") or ""
        if not token and cfg.get("token_file"):
            try:
                with open(cfg["token_file"]) as handle:
                    token = handle.read().strip()
            except OSError:
                token = ""
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._headers["Content-Type"] = "application/json"

    async def _url(self, name: str) -> str:
        return f"{self.api_server}/api/v1/namespaces/{self.namespace}/secrets/{name}"

    async def get(self, name: str) -> Secret:
        try:
            body = await self.transport(self, "GET", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"kubernetes secret read failed: {exc}") from exc
        if not isinstance(body, dict) or "data" not in body:
            raise SecretNotFoundError(f"kubernetes secret {name!r} not found")
        raw = body.get("data", {})
        value = ""
        encoded = raw.get("value")
        if encoded:
            value = base64.b64decode(encoded.encode()).decode(errors="replace")
        return Secret(id=generate_id("secret"), name=name, kind=SecretKind.OPAQUE, value=value, metadata=dict(raw))

    async def set(self, secret: Secret) -> Secret:
        payload = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret.name, "namespace": self.namespace},
            "stringData": {"value": secret.value, "kind": secret.kind.value},
        }
        try:
            await self.transport(self, "POST", await self._url(secret.name), body=payload)
        except Exception as exc:
            raise SecretBackendError(f"kubernetes secret write failed: {exc}") from exc
        return secret

    async def delete(self, name: str) -> bool:
        try:
            await self.transport(self, "DELETE", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"kubernetes secret delete failed: {exc}") from exc
        return True

    async def list(self) -> list[str]:
        url = f"{self.api_server}/api/v1/namespaces/{self.namespace}/secrets"
        try:
            body = await self.transport(self, "GET", url)
        except Exception as exc:
            raise SecretBackendError(f"kubernetes secret list failed: {exc}") from exc
        if not isinstance(body, dict):
            return []
        return [item.get("metadata", {}).get("name") for item in body.get("items", []) if isinstance(item, dict)]


class AWSSecretsBackend(SecretBackend):
    """AWS Secrets Manager through an injectable boto3-style client.

    ``client`` must expose ``get_secret_value(SecretId=...)``,
    ``create_secret(Name=..., SecretString=...)``, ``delete_secret(SecretId=...)``
    and ``list_secrets()``.
    """

    name = "aws"

    def __init__(self, config: SecurityConfig, client: Any = None) -> None:
        super().__init__(config)
        self.client = client

    async def get(self, name: str) -> Secret:
        if self.client is None:
            raise SecretBackendError("aws backend requires an injected client")
        try:
            response = self.client.get_secret_value(SecretId=name)
        except KeyError as exc:
            raise SecretNotFoundError(f"aws secret {name!r} not found") from exc
        except Exception as exc:
            raise SecretBackendError(f"aws secret read failed: {exc}") from exc
        value = response.get("SecretString") or ""
        if not value:
            raise SecretNotFoundError(f"aws secret {name!r} not found")
        return Secret(id=generate_id("secret"), name=name, kind=SecretKind.OPAQUE, value=value)

    async def set(self, secret: Secret) -> Secret:
        if self.client is None:
            raise SecretBackendError("aws backend requires an injected client")
        try:
            self.client.create_secret(Name=secret.name, SecretString=secret.value)
        except Exception as exc:
            raise SecretBackendError(f"aws secret write failed: {exc}") from exc
        return secret

    async def delete(self, name: str) -> bool:
        if self.client is None:
            raise SecretBackendError("aws backend requires an injected client")
        try:
            self.client.delete_secret(SecretId=name)
        except Exception as exc:
            raise SecretBackendError(f"aws secret delete failed: {exc}") from exc
        return True

    async def list(self) -> list[str]:
        if self.client is None:
            raise SecretBackendError("aws backend requires an injected client")
        try:
            response = self.client.list_secrets()
        except Exception as exc:
            raise SecretBackendError(f"aws secret list failed: {exc}") from exc
        return [item.get("Name") for item in response.get("SecretList", []) if item.get("Name")]


class AzureBackend(SecretBackend):
    """Azure Key Vault secrets.

    ``secret_config``: ``vault_url`` (https://<name>.vault.azure.net),
    ``api_version`` (default "7.4"). ``transport(backend, method, url, body=None)``
    is injectable.
    """

    name = "azure"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.secret_config
        self.vault_url = cfg.get("vault_url", "https://example.vault.azure.net").rstrip("/")
        self.api_version = cfg.get("api_version", "7.4")

    async def _url(self, name: str) -> str:
        return f"{self.vault_url}/secrets/{name}?api-version={self.api_version}"

    async def get(self, name: str) -> Secret:
        try:
            body = await self.transport(self, "GET", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"azure secret read failed: {exc}") from exc
        if not isinstance(body, dict) or "value" not in body:
            raise SecretNotFoundError(f"azure secret {name!r} not found")
        return Secret(id=generate_id("secret"), name=name, kind=SecretKind.OPAQUE, value=str(body.get("value", "")))

    async def set(self, secret: Secret) -> Secret:
        payload = {"value": secret.value}
        try:
            await self.transport(self, "PUT", await self._url(secret.name), body=payload)
        except Exception as exc:
            raise SecretBackendError(f"azure secret write failed: {exc}") from exc
        return secret

    async def delete(self, name: str) -> bool:
        try:
            await self.transport(self, "DELETE", await self._url(name))
        except Exception as exc:
            raise SecretBackendError(f"azure secret delete failed: {exc}") from exc
        return True

    async def list(self) -> list[str]:
        url = f"{self.vault_url}/secrets?api-version={self.api_version}"
        try:
            body = await self.transport(self, "GET", url)
        except Exception as exc:
            raise SecretBackendError(f"azure secret list failed: {exc}") from exc
        if not isinstance(body, dict):
            return []
        return [item.get("id", "").split("/")[-1] for item in body.get("value", []) if isinstance(item, dict)]


class GoogleBackend(SecretBackend):
    """Google Secret Manager.

    ``secret_config``: ``project``, ``version`` (default "latest").
    ``client`` must expose ``access_secret_version(request=...)``,
    ``create_secret(request=...)``, ``add_secret_version(request=...)``,
    ``delete_secret(request=...)`` and ``list_secrets(request=...)`` (requests as
    dicts, responses as dicts).
    """

    name = "google"

    def __init__(self, config: SecurityConfig, client: Any = None) -> None:
        super().__init__(config)
        self.client = client
        cfg = config.secret_config
        self.project = cfg.get("project", "default-project")
        self.version = cfg.get("version", "latest")

    async def get(self, name: str) -> Secret:
        if self.client is None:
            raise SecretBackendError("google backend requires an injected client")
        request = {"name": f"projects/{self.project}/secrets/{name}/versions/{self.version}"}
        try:
            response = self.client.access_secret_version(request=request)
        except Exception as exc:
            raise SecretBackendError(f"google secret read failed: {exc}") from exc
        payload = (response or {}).get("payload") or {}
        encoded = payload.get("data") or ""
        value = base64.b64decode(encoded.encode()).decode(errors="replace")
        return Secret(id=generate_id("secret"), name=name, kind=SecretKind.OPAQUE, value=value)

    async def set(self, secret: Secret) -> Secret:
        if self.client is None:
            raise SecretBackendError("google backend requires an injected client")
        parent = f"projects/{self.project}/secrets/{secret.name}"
        try:
            self.client.create_secret(request={"parent": f"projects/{self.project}", "secret_id": secret.name})
        except Exception:
            pass  # already exists
        try:
            self.client.add_secret_version(
                request={"parent": parent, "payload": {"data": base64.b64encode(secret.value.encode()).decode()}}
            )
        except Exception as exc:
            raise SecretBackendError(f"google secret write failed: {exc}") from exc
        return secret

    async def delete(self, name: str) -> bool:
        if self.client is None:
            raise SecretBackendError("google backend requires an injected client")
        try:
            self.client.delete_secret(request={"name": f"projects/{self.project}/secrets/{name}"})
        except Exception as exc:
            raise SecretBackendError(f"google secret delete failed: {exc}") from exc
        return True

    async def list(self) -> list[str]:
        if self.client is None:
            raise SecretBackendError("google backend requires an injected client")
        try:
            response = self.client.list_secrets(request={"parent": f"projects/{self.project}"})
        except Exception as exc:
            raise SecretBackendError(f"google secret list failed: {exc}") from exc
        secrets = (response or {}).get("secrets", []) if isinstance(response, dict) else []
        return [item.get("name", "").split("/")[-1] for item in secrets if isinstance(item, dict)]


# -- registry + facade ----------------------------------------------------------


class SecretBackendRegistry:
    """Strategy registry mapping backend names to factories."""

    def __init__(self) -> None:
        self._factories: dict[str, Any] = {
            "environment": lambda config, **kw: EnvironmentBackend(config),
            "vault": lambda config, **kw: VaultBackend(config, kw.get("transport")),
            "kubernetes": lambda config, **kw: KubernetesBackend(config, kw.get("transport")),
            "aws": lambda config, **kw: AWSSecretsBackend(config, kw.get("client")),
            "azure": lambda config, **kw: AzureBackend(config, kw.get("transport")),
            "google": lambda config, **kw: GoogleBackend(config, kw.get("client")),
        }

    def register(self, name: str, factory: Any) -> None:
        self._factories[name] = factory

    def create(self, config: SecurityConfig, **overrides: Any) -> SecretBackend:
        backend_name = overrides.pop("backend", None) or config.secret_backend
        factory = self._factories.get(backend_name)
        if factory is None:
            raise SecretBackendError(f"unknown secret backend {backend_name!r}")
        return factory(config, **overrides)


def create_secret_backend(config: SecurityConfig | None = None, **overrides: Any) -> SecretBackend:
    """DI factory for secret backends."""
    config = config or SecurityConfig()
    registry = overrides.pop("registry", None) or SecretBackendRegistry()
    return registry.create(config, **overrides)


class SecretManager:
    """Facade over a secret backend with caching and rotation hooks."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        backend: SecretBackend | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.backend = backend if backend is not None else create_secret_backend(self.config)
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._cache: dict[str, tuple[Secret, float]] = {}
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.backend.start()

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self.backend.close()
        self._cache.clear()

    def _cached(self, name: str) -> Secret | None:
        entry = self._cache.get(name)
        if entry is None:
            return None
        secret, fetched_at = entry
        if time.time() - fetched_at > self.config.secret_cache_ttl:
            self._cache.pop(name, None)
            return None
        return secret

    async def get_secret(self, name: str, bypass_cache: bool = False) -> Secret:
        if not bypass_cache:
            cached = self._cached(name)
            if cached is not None:
                return cached
        secret = await self.backend.get(name)
        self._cache[name] = (secret, time.time())
        self.metrics.record("secret_reads", component="secrets")
        self.logger.log_event("secret_read", name=name)
        return secret

    async def set_secret(
        self,
        name: str,
        value: str,
        kind: SecretKind = SecretKind.OPAQUE,
        metadata: dict[str, Any] | None = None,
    ) -> Secret:
        secret = Secret(id=generate_id("secret"), name=name, kind=kind, value=value, metadata=metadata or {})
        stored = await self.backend.set(secret)
        self._cache[name] = (stored, time.time())
        self.metrics.record("secret_writes", component="secrets")
        self.logger.log_event("secret_set", name=name, kind=kind.value)
        return stored

    async def delete_secret(self, name: str) -> bool:
        removed = await self.backend.delete(name)
        self._cache.pop(name, None)
        if removed:
            self.metrics.record("secret_deletes", component="secrets")
            self.logger.log_event("secret_deleted", name=name)
        return removed

    async def list_secrets(self) -> list[str]:
        names = await self.backend.list()
        self.metrics.record("secret_lists", component="secrets")
        return names

    async def rotate_secret(self, name: str, new_value: str) -> Secret:
        """Rotate a secret in place and mark the old version rotated."""
        try:
            current = await self.get_secret(name, bypass_cache=True)
        except SecretNotFoundError:
            current = None
        secret = Secret(
            id=generate_id("secret"),
            name=name,
            kind=current.kind if current is not None else SecretKind.OPAQUE,
            value=new_value,
            version=(current.version + 1) if current is not None else 1,
            metadata=dict(current.metadata) if current is not None else {},
        )
        stored = await self.backend.set(secret)
        self._cache[name] = (stored, time.time())
        self.metrics.record("secret_rotations", component="secrets")
        self.logger.log_event("secret_rotated", name=name, version=stored.version)
        return stored

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend.name,
            "running": self._running,
            "cache_size": len(self._cache),
            "cache_ttl": self.config.secret_cache_ttl,
        }


def create_secret_manager(config: SecurityConfig | None = None, **overrides: Any) -> SecretManager:
    """DI factory for the secret manager."""
    config = config if config is not None else SecurityConfig()
    backend = overrides.pop("backend", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    if backend is None:
        backend = create_secret_backend(config, **overrides)
    return SecretManager(config, backend, logger, metrics)
