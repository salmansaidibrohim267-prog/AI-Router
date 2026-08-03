"""Publishing adapters for release artifacts.

``Publisher`` is the strategy interface; GitHub Releases (via injectable
``git_client`` / HTTP transport), container registry (image tag push) and a
local filesystem publisher are provided. A registry maps names to factories.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from abc import ABC, abstractmethod
from typing import Any, Callable

from .config import ReleaseConfig
from .exceptions import PublishError
from .signing import ReleaseSigner, Signature

Transport = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
"""transport(method, url, headers, body) -> response dict (injectable)."""


class Publisher(ABC):
    """Release publishing strategy."""

    name = "base"

    def __init__(self, config: ReleaseConfig) -> None:
        self.config = config

    @abstractmethod
    def publish(self, version: str, artifact_paths: list[str], notes: str = "") -> dict[str, Any]:
        """Publish artifacts; returns a result summary."""


class GitHubPublisher(Publisher):
    """Publishes a GitHub Release (injectable transport for tests)."""

    name = "github"

    def __init__(self, config: ReleaseConfig, transport: Transport | None = None, token: str = "") -> None:
        super().__init__(config)
        self.transport = transport
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo = "salmansaidibrohim267-prog/AI-Router"
        self.api_url = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def publish(self, version: str, artifact_paths: list[str], notes: str = "") -> dict[str, Any]:
        if self.transport is None:
            raise PublishError("github publisher requires an injected transport")
        url = f"{self.api_url}/repos/{self.repo}/releases"
        body = {
            "tag_name": f"v{version}",
            "name": f"v{version}",
            "body": notes,
            "draft": False,
            "prerelease": "-" in version,
        }
        try:
            response = self.transport("POST", url, self._headers(), body)
        except Exception as exc:
            raise PublishError(f"github release creation failed: {exc}") from exc
        release_id = (response or {}).get("id")
        uploads: list[dict[str, Any]] = []
        for path in artifact_paths:
            if not os.path.exists(path):
                continue
            upload = self._upload_asset(release_id, path)
            if upload:
                uploads.append(upload)
        return {"publisher": self.name, "release_id": release_id, "uploads": uploads, "url": url}

    def _upload_asset(self, release_id: Any, path: str) -> dict[str, Any] | None:
        if self.transport is None or release_id is None:
            return None
        name = os.path.basename(path)
        url = f"{self.api_url}/repos/{self.repo}/releases/{release_id}/assets?name={name}"
        try:
            with open(path, "rb") as handle:
                content = handle.read()
            response = self.transport(
                "POST", url, {**self._headers(), "Content-Type": "application/octet-stream"}, {"body": content}
            )
        except Exception as exc:
            raise PublishError(f"github asset upload failed for {name}: {exc}") from exc
        return {"name": name, "asset_id": (response or {}).get("id"), "size": os.path.getsize(path)}


class ContainerRegistryPublisher(Publisher):
    """Publishes container image tags to a registry (manifest-only simulation)."""

    name = "registry"

    def __init__(self, config: ReleaseConfig, transport: Transport | None = None, token: str = "") -> None:
        super().__init__(config)
        self.transport = transport
        self.token = token or os.environ.get("REGISTRY_TOKEN", "")

    def publish(self, version: str, artifact_paths: list[str], notes: str = "") -> dict[str, Any]:
        if self.transport is None:
            raise PublishError("registry publisher requires an injected transport")
        image = f"{self.config.registry}/{self.config.image_name}"
        tags = [version]
        if "-" not in version:
            tags.extend(["latest", version.rsplit(".", 1)[0]])
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        results: list[dict[str, Any]] = []
        for tag in tags:
            url = f"https://registry.example.com/v2/{image}/tags"
            try:
                response = self.transport("PUT", url, headers, {"tag": tag, "digest": notes or version})
            except Exception as exc:
                raise PublishError(f"registry tag push failed for {tag}: {exc}") from exc
            results.append({"tag": tag, "accepted": bool((response or {}).get("accepted", True))})
        return {"publisher": self.name, "image": image, "tags": results}


class LocalPublisher(Publisher):
    """Copies artifacts into a local release directory (CI artifact staging)."""

    name = "local"

    def __init__(self, config: ReleaseConfig, output_dir: str | None = None) -> None:
        super().__init__(config)
        self.output_dir = output_dir or config.artifacts_dir

    def publish(self, version: str, artifact_paths: list[str], notes: str = "") -> dict[str, Any]:
        target = os.path.join(self.output_dir, version)
        os.makedirs(target, exist_ok=True)
        copied: list[dict[str, Any]] = []
        for path in artifact_paths:
            if not os.path.exists(path):
                continue
            destination = os.path.join(target, os.path.basename(path))
            shutil.copy2(path, destination)
            copied.append({"name": os.path.basename(path), "path": destination})
        manifest_path = os.path.join(target, "manifest.json")
        with open(manifest_path, "w") as handle:
            json.dump({"version": version, "artifacts": copied, "notes": notes}, handle, indent=2)
        return {"publisher": self.name, "directory": target, "artifacts": copied}


class PublisherRegistry:
    """Strategy registry for publishers."""

    def __init__(self) -> None:
        self._factories: dict[str, Any] = {
            "github": lambda config, **kw: GitHubPublisher(config, kw.get("transport"), kw.get("token", "")),
            "registry": lambda config, **kw: ContainerRegistryPublisher(config, kw.get("transport"), kw.get("token", "")),
            "local": lambda config, **kw: LocalPublisher(config, kw.get("output_dir")),
        }

    def register(self, name: str, factory: Any) -> None:
        self._factories[name] = factory

    def create(self, config: ReleaseConfig, name: str, **overrides: Any) -> Publisher:
        factory = self._factories.get(name)
        if factory is None:
            raise PublishError(f"unknown publisher {name!r}")
        return factory(config, **overrides)


def create_publisher(config: ReleaseConfig, name: str, **overrides: Any) -> Publisher:
    registry = overrides.pop("registry", None) or PublisherRegistry()
    return registry.create(config, name, **overrides)
