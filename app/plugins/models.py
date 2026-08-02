from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def generate_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class PluginStatus(Enum):
    DRAFT = "draft"
    INSTALLING = "installing"
    INSTALLED = "installed"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    ENABLING = "enabling"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UPDATING = "updating"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    UNINSTALLING = "uninstalling"
    UNINSTALLED = "uninstalled"
    FAILED = "failed"


class ExtensionKind(Enum):
    TOOL = "tool"
    ROUTE = "route"
    MCP_PROVIDER = "mcp_provider"
    LLM_PROVIDER = "llm_provider"
    EMBEDDING_MODEL = "embedding_model"
    SCHEDULER = "scheduler"
    CLI_COMMAND = "cli_command"
    EVENT_LISTENER = "event_listener"


class PermissionResource(Enum):
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PROCESS = "process"
    EVENT_BUS = "event_bus"
    PROVIDER = "provider"
    SECRETS = "secrets"


@dataclass
class PluginSpec:
    """Installed plugin identity plus runtime metadata."""

    name: str
    version: str
    entry: str = "create_plugin"
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    requires_router: str = ""
    permissions: list[dict[str, Any]] = field(default_factory=list)
    signature: str = ""
    installed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "entry": self.entry,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "requires_router": self.requires_router,
            "permissions": self.permissions,
            "signature": self.signature,
            "installed_at": self.installed_at,
        }


@dataclass
class PluginInfo:
    """Runtime view of an installed plugin."""

    name: str
    version: str
    status: PluginStatus = PluginStatus.INSTALLED
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    signature: str = ""
    extensions: dict[str, list[str]] = field(default_factory=dict)
    error: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "status": self.status.value,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "signature": self.signature,
            "extensions": {kind: list(names) for kind, names in self.extensions.items()},
            "error": self.error,
            "updated_at": self.updated_at,
        }


@dataclass
class Extension:
    """A capability registered by a plugin (tool, route, provider, ...)."""

    kind: ExtensionKind
    name: str
    handler: Any
    plugin: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "plugin": self.plugin,
            "metadata": self.metadata,
        }


@dataclass
class Signature:
    algorithm: str = "hmac-sha256"
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"algorithm": self.algorithm, "digest": self.digest}


@dataclass
class Rating:
    entry_id: str
    user: str
    score: int
    comment: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "user": self.user,
            "score": self.score,
            "comment": self.comment,
            "created_at": self.created_at,
        }


@dataclass
class SchedulerSpec:
    interval_seconds: float
    cron: str = ""
    max_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_seconds": self.interval_seconds,
            "cron": self.cron,
            "max_runs": self.max_runs,
        }
