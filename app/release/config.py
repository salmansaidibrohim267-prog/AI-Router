"""Release configuration (Stage 10.10).

Constructor defaults plus ``from_env()`` reading ``REL_*`` environment
variables, mirroring the other subsystem configs.
"""

from __future__ import annotations

import os
from typing import Any


class ReleaseConfig:
    """Runtime configuration for release management."""

    def __init__(self, **kwargs: Any) -> None:
        self.project_name: str = kwargs.pop("project_name", "ai-router")
        self.initial_version: str = kwargs.pop("initial_version", "1.0.0-rc.1")
        self.main_branch: str = kwargs.pop("main_branch", "main")
        self.registry: str = kwargs.pop("registry", "ghcr.io/anomalyco")
        self.image_name: str = kwargs.pop("image_name", "ai-router")
        self.sbom_enabled: bool = bool(kwargs.pop("sbom_enabled", True))
        self.signing_enabled: bool = bool(kwargs.pop("signing_enabled", True))
        self.signing_key: str = kwargs.pop("signing_key", "release-signing-key")
        self.changelog_file: str = kwargs.pop("changelog_file", "CHANGELOG.md")
        self.artifacts_dir: str = kwargs.pop("artifacts_dir", "dist/release")
        self.auto_publish: bool = bool(kwargs.pop("auto_publish", False))
        self.publishers: list[str] = list(kwargs.pop("publishers", ["github"]) or [])
        self.pre_release_tags: list[str] = list(kwargs.pop("pre_release_tags", ["rc", "beta", "alpha"]) or [])
        self._reject_unknown(kwargs)

    def _reject_unknown(self, kwargs: dict[str, Any]) -> None:
        if kwargs:
            raise TypeError(f"unexpected release config: {sorted(kwargs)}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "ReleaseConfig":
        kwargs: dict[str, Any] = {
            "project_name": os.environ.get("REL_PROJECT_NAME", "ai-router"),
            "initial_version": os.environ.get("REL_INITIAL_VERSION", "1.0.0-rc.1"),
            "main_branch": os.environ.get("REL_MAIN_BRANCH", "main"),
            "registry": os.environ.get("REL_REGISTRY", "ghcr.io/anomalyco"),
            "image_name": os.environ.get("REL_IMAGE_NAME", "ai-router"),
            "sbom_enabled": os.environ.get("REL_SBOM_ENABLED", "true").lower() in ("1", "true", "yes"),
            "signing_enabled": os.environ.get("REL_SIGNING_ENABLED", "true").lower() in ("1", "true", "yes"),
            "signing_key": os.environ.get("REL_SIGNING_KEY", "release-signing-key"),
            "changelog_file": os.environ.get("REL_CHANGELOG_FILE", "CHANGELOG.md"),
            "artifacts_dir": os.environ.get("REL_ARTIFACTS_DIR", "dist/release"),
            "auto_publish": os.environ.get("REL_AUTO_PUBLISH", "false").lower() in ("1", "true", "yes"),
            "publishers": [p.strip() for p in os.environ.get("REL_PUBLISHERS", "github").split(",") if p.strip()],
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in vars(self).items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[name] = value
            else:
                result[name] = list(value) if isinstance(value, (list, tuple)) else str(value)
        return result
