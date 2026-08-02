from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import PluginConfig
from .exceptions import PluginMarketplaceError, PluginRatingError, PluginSignatureError
from .logging import PluginLogger
from .models import Rating
from .signing import verify_payload
from .validation import CompatibilityChecker, ManifestValidator
from .versioning import compare_versions, parse_version


@dataclass
class MarketplaceEntry:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    requires_router: str = ""
    entry: str = "create_plugin"
    plugin_code: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    downloads: int = 0
    ratings: list[Rating] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        rating_data = [rating.to_dict() for rating in self.ratings]
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "requires_router": self.requires_router,
            "downloads": self.downloads,
            "average_rating": self.average_rating,
            "rating_count": len(self.ratings),
            "ratings": rating_data,
        }

    @property
    def average_rating(self) -> float:
        if not self.ratings:
            return 0.0
        return round(sum(rating.score for rating in self.ratings) / len(self.ratings), 2)

    @property
    def rating_count(self) -> int:
        return len(self.ratings)


class Marketplace:
    """Plugin catalog with search, install, updates, ratings and signing.

    Entries are installed by materializing their manifest + plugin source
    into the target plugins directory (Factory pattern for installable
    packages).
    """

    def __init__(
        self,
        config: PluginConfig | None = None,
        logger: PluginLogger | None = None,
        validator: ManifestValidator | None = None,
        compatibility: CompatibilityChecker | None = None,
    ) -> None:
        self._config = config or PluginConfig()
        self._logger = logger or PluginLogger(self._config)
        self._validator = validator or ManifestValidator()
        self._compatibility = compatibility or CompatibilityChecker()
        self._entries: dict[str, MarketplaceEntry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- catalog

    def add(self, entry: MarketplaceEntry) -> MarketplaceEntry:
        with self._lock:
            self._entries[entry.id] = entry
        self._logger.log_event("marketplace.entry_added", entry_id=entry.id, name=entry.name, version=entry.version)
        return entry

    def remove(self, entry_id: str) -> bool:
        with self._lock:
            if entry_id not in self._entries:
                return False
            del self._entries[entry_id]
        return True

    def get(self, entry_id: str) -> MarketplaceEntry:
        with self._lock:
            entry = self._entries.get(entry_id)
        if entry is None:
            raise PluginMarketplaceError(f"marketplace entry {entry_id!r} not found", entry_id=entry_id)
        return entry

    def list(self) -> list[MarketplaceEntry]:
        with self._lock:
            return list(self._entries.values())

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------- search

    def search(self, query: str = "", tag: str = "", limit: int = 20) -> list[MarketplaceEntry]:
        query = query.strip().lower()
        results: list[MarketplaceEntry] = []
        for entry in self.list():
            if tag and tag not in entry.tags:
                continue
            if query:
                haystack = " ".join([entry.name, entry.description, entry.author, " ".join(entry.tags)]).lower()
                if query not in haystack:
                    continue
            results.append(entry)
        return results[:limit]

    def search_by_name(self, name: str) -> list[MarketplaceEntry]:
        return [entry for entry in self.list() if entry.name == name]

    # ------------------------------------------------------------- updates

    def latest(self, name: str) -> MarketplaceEntry | None:
        matches = [entry for entry in self.list() if entry.name == name]
        if not matches:
            return None
        matches.sort(key=lambda entry: parse_version(entry.version), reverse=True)
        return matches[0]

    def update_available(self, name: str, installed_version: str) -> str | None:
        latest = self.latest(name)
        if latest is None:
            return None
        if compare_versions(latest.version, installed_version) > 0:
            return latest.version
        return None

    def compatible_with(self, router_version: str, entry_id: str | None = None) -> list[MarketplaceEntry]:
        checker = CompatibilityChecker(router_version=router_version)
        results: list[MarketplaceEntry] = []
        for entry in self.list():
            if entry_id and entry.id != entry_id:
                continue
            if not checker.check(self._manifest_for(entry)):
                results.append(entry)
        return results

    def _manifest_for(self, entry: MarketplaceEntry) -> dict[str, Any]:
        return {
            "name": entry.name,
            "version": entry.version,
            "entry": entry.entry,
            "requires_router": entry.requires_router,
            "tags": entry.tags,
            **entry.manifest,
        }

    # ------------------------------------------------------------- ratings

    def rate(self, entry_id: str, user: str, score: int, comment: str = "") -> Rating:
        if score < 1 or score > 5:
            raise PluginRatingError(f"score must be between 1 and 5, got {score}", score=score)
        entry = self.get(entry_id)
        rating = Rating(entry_id=entry_id, user=user, score=score, comment=comment)
        with self._lock:
            entry.ratings = [existing for existing in entry.ratings if existing.user != user]
            entry.ratings.append(rating)
        return rating

    def ratings(self, entry_id: str) -> list[Rating]:
        return list(self.get(entry_id).ratings)

    def average(self, entry_id: str) -> float:
        return self.get(entry_id).average_rating

    # ------------------------------------------------------------- install

    def install_entry(
        self,
        entry_id: str,
        target_dir: str,
        require_signature: bool | None = None,
        verify_compatibility: bool = True,
    ) -> dict[str, Any]:
        entry = self.get(entry_id)
        target = Path(target_dir)
        plugin_dir = target / entry.name
        if plugin_dir.exists():
            raise PluginMarketplaceError(f"plugin {entry.name!r} already exists at {plugin_dir}", plugin=entry.name)

        manifest = self._manifest_for(entry)
        issues = self._validator.validate(manifest)
        if issues:
            raise PluginMarketplaceError(f"invalid marketplace entry {entry_id!r}: {'; '.join(issues)}", issues=issues)
        if verify_compatibility:
            self._compatibility.check_or_raise(manifest)
        secret = self._config.signature_secret
        if require_signature is None:
            require_signature = self._config.require_signatures
        if entry.signature:
            if not verify_payload(manifest, entry.signature, secret):
                raise PluginSignatureError(f"signature invalid for {entry.name!r}", plugin=entry.name)
        elif require_signature:
            raise PluginSignatureError(f"entry {entry.name!r} is not signed", plugin=entry.name)

        target.mkdir(parents=True, exist_ok=True)
        plugin_dir.mkdir()
        import yaml

        with open(plugin_dir / "manifest.yaml", "w") as fh:
            yaml.safe_dump(manifest, fh, sort_keys=True)
        with open(plugin_dir / "plugin.py", "w") as fh:
            fh.write(entry.plugin_code)
        with open(plugin_dir / "metadata.json", "w") as fh:
            json.dump(entry.to_dict(), fh, indent=2)

        with self._lock:
            entry.downloads += 1
        self._logger.log_event("marketplace.entry_installed", entry_id=entry_id, plugin=entry.name, version=entry.version)
        return {
            "plugin": entry.name,
            "version": entry.version,
            "path": str(plugin_dir),
            "signature_verified": bool(entry.signature) and bool(secret),
        }
