"""Release Manager: semantic versioning, release candidates, changelog
generation, signed releases, artifact manifests and automated publishing.

The manager keeps an in-memory (optionally file-backed) release history and
walks the canonical flow:

1. ``next_version(bump, rc=...)`` — derive the next version from the latest,
2. ``create_release`` — stamp a version, generate the changelog entry,
3. ``sign`` / ``verify`` — HMAC sign the artifact manifest,
4. ``publish`` — hand artifacts to configured publishers,
5. ``promote`` — RC -> release, or version bump for new release lines.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from .changelog import ChangelogGenerator, CommitEntry, ReleaseEntry
from .config import ReleaseConfig
from .exceptions import ReleaseError, ReleaseLockedError, VersionNotFoundError
from .publishing import Publisher, PublisherRegistry, create_publisher
from .signing import ReleaseSigner, Signature, canonical_json
from .version import SemanticVersion


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactManifest:
    """A versioned, signable manifest of release artifacts."""

    def __init__(
        self,
        version: str,
        artifacts: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.version = version
        self.artifacts: list[dict[str, Any]] = list(artifacts or [])
        self.metadata: dict[str, Any] = dict(metadata or {})

    def add(self, name: str, path: str, digest: str = "") -> None:
        entry = {
            "name": name,
            "path": path,
            "digest": digest or (sha256_file(path) if os.path.exists(path) else ""),
            "size": os.path.getsize(path) if os.path.exists(path) else 0,
        }
        if any(a["name"] == name for a in self.artifacts):
            self.artifacts = [a for a in self.artifacts if a["name"] != name]
        self.artifacts.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "artifacts": [dict(a) for a in self.artifacts],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactManifest":
        return cls(data.get("version", ""), data.get("artifacts", []), data.get("metadata", {}))

    def payload(self) -> dict[str, Any]:
        return {"version": self.version, "artifacts": self.artifacts}

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "artifact_count": len(self.artifacts),
            "total_size": sum(a.get("size", 0) for a in self.artifacts),
        }


class ReleaseManager:
    """Orchestrates the release lifecycle."""

    def __init__(
        self,
        config: ReleaseConfig | None = None,
        signer: ReleaseSigner | None = None,
        changelog: ChangelogGenerator | None = None,
        publishers: dict[str, Publisher] | None = None,
        history_file: str = "",
    ) -> None:
        self.config = config if config is not None else ReleaseConfig()
        self.signer = signer if signer is not None else ReleaseSigner(self.config.signing_key)
        self.changelog = changelog if changelog is not None else ChangelogGenerator(self.config.project_name)
        self.publishers = dict(publishers or {})
        self.history_file = history_file
        self._releases: list[ReleaseEntry] = []
        self._manifests: dict[str, ArtifactManifest] = {}
        self._signatures: dict[str, Signature] = {}
        self._finalised: set[str] = set()
        if history_file and os.path.exists(history_file):
            self._load_history()

    # -- history ---------------------------------------------------------------

    def _load_history(self) -> None:
        try:
            with open(self.history_file) as handle:
                data = json.load(handle)
            self._releases = [
                ReleaseEntry(
                    version=entry["version"],
                    date=entry.get("date", ""),
                    commits=[CommitEntry(**commit) for commit in entry.get("commits", [])],
                )
                for entry in data.get("releases", [])
            ]
            self._finalised = set(data.get("finalised", []))
            for manifest in data.get("manifests", []):
                item = ArtifactManifest.from_dict(manifest)
                self._manifests[item.version] = item
            for signature in data.get("signatures", []):
                version = signature.get("payload", {}).get("version", "")
                if version:
                    self._signatures[version] = Signature(
                        payload=signature.get("payload", {}),
                        signature=signature.get("signature", ""),
                        algorithm=signature.get("algorithm", "hmac-sha256"),
                    )
        except (OSError, ValueError, TypeError, KeyError):
            self._releases = []
            self._finalised = set()

    def save_history(self) -> None:
        if not self.history_file:
            return
        data = {
            "releases": [{"version": r.version, "date": r.date, "commits": [c.to_dict() for c in r.commits]} for r in self._releases],
            "finalised": sorted(self._finalised),
            "manifests": [m.to_dict() for m in self._manifests.values()],
            "signatures": [s.to_dict() for s in self._signatures.values()],
        }
        with open(self.history_file, "w") as handle:
            json.dump(data, handle, indent=2)

    def list_releases(self) -> list[str]:
        return [r.version for r in self._releases]

    def latest_version(self) -> SemanticVersion | None:
        versions = [SemanticVersion.parse(v) for v in self.list_releases()]
        return max(versions) if versions else None

    def get_release(self, version: str) -> ReleaseEntry | None:
        for release in self._releases:
            if release.version == version:
                return release
        return None

    def get_manifest(self, version: str) -> ArtifactManifest | None:
        return self._manifests.get(version)

    def get_signature(self, version: str) -> Signature | None:
        return self._signatures.get(version)

    def is_finalised(self, version: str) -> bool:
        return version in self._finalised

    # -- version derivation ------------------------------------------------------

    def next_version(self, bump: str = "patch", rc: int = 1) -> SemanticVersion:
        latest = self.latest_version()
        if latest is None:
            return SemanticVersion.parse(self.config.initial_version)
        if bump == "rc":
            return latest.as_rc(latest.rc_number() + 1)
        if bump == "release":
            return latest.as_release()
        if latest.is_rc() and latest.rc_number() > 0:
            return latest.as_rc(latest.rc_number() + 1) if bump == "patch" else latest.next(bump, "rc.1")
        return latest.next(bump)

    # -- release creation ----------------------------------------------------------

    def create_release(
        self,
        version: str | None = None,
        commit_lines: list[str] | None = None,
        bump: str = "patch",
        date: str | None = None,
    ) -> ReleaseEntry:
        resolved = SemanticVersion.parse(version) if version else self.next_version(bump)
        version_str = str(resolved)
        if self.get_release(version_str) is not None:
            raise ReleaseError(f"release {version_str} already exists")
        commits = self.changelog.parse_commits(commit_lines or [])
        entry = self.changelog.build_entry(version_str, commits, date)
        self._releases.append(entry)
        self._releases.sort(key=lambda r: SemanticVersion.parse(r.version))
        return entry

    def create_rc(self, rc_number: int | None = None, commit_lines: list[str] | None = None) -> ReleaseEntry:
        latest = self.latest_version()
        if latest is None:
            version = SemanticVersion.parse(self.config.initial_version)
            if rc_number is not None:
                version = SemanticVersion(version.major, version.minor, version.patch, f"rc.{rc_number}")
            return self.create_release(str(version), commit_lines)
        if not latest.is_rc():
            number = rc_number or 1
            version = latest.as_rc(number)
        else:
            number = rc_number or (latest.rc_number() + 1)
            version = latest.as_rc(number)
        return self.create_release(str(version), commit_lines)

    def promote_to_release(self, rc_version: str, commit_lines: list[str] | None = None) -> ReleaseEntry:
        """Promote an RC to a stable release of the same major.minor.patch."""
        rc = SemanticVersion.parse(rc_version)
        if not rc.is_rc():
            raise ReleaseError(f"{rc_version} is not a release candidate")
        release = rc.as_release()
        return self.create_release(str(release), commit_lines)

    # -- changelog output ------------------------------------------------------------

    def changelog_markdown(self) -> str:
        if not self._releases:
            return self.changelog.generate_from_commits(str(self.next_version()), [])
        return self.changelog.generate(self._releases)

    def write_changelog(self, path: str | None = None) -> str:
        path = path or self.config.changelog_file
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        content = self.changelog_markdown()
        with open(path, "w") as handle:
            handle.write(content)
        return path

    # -- signing -------------------------------------------------------------------------

    def sign_manifest(self, version: str) -> Signature:
        manifest = self._manifests.get(version)
        if manifest is None:
            raise ReleaseError(f"no manifest for {version}; add artifacts first")
        signature = self.signer.sign(manifest.payload())
        self._signatures[version] = signature
        return signature

    def verify_manifest(self, version: str) -> bool:
        signature = self._signatures.get(version)
        manifest = self._manifests.get(version)
        if signature is None or manifest is None:
            return False
        return self.signer.verify(signature)

    def export_signature(self, version: str) -> dict[str, Any]:
        signature = self._signatures.get(version)
        if signature is None:
            raise ReleaseError(f"no signature for {version}")
        return signature.to_dict()

    # -- artifacts ----------------------------------------------------------------------

    def add_artifact(self, version: str, name: str, path: str) -> ArtifactManifest:
        if self.is_finalised(version):
            raise ReleaseLockedError(f"release {version} is finalised")
        manifest = self._manifests.setdefault(version, ArtifactManifest(version))
        manifest.add(name, path)
        return manifest

    def build_artifact_manifest(self, version: str, artifacts: dict[str, str]) -> ArtifactManifest:
        if self.is_finalised(version):
            raise ReleaseLockedError(f"release {version} is finalised")
        manifest = self._manifests.setdefault(version, ArtifactManifest(version))
        for name, path in artifacts.items():
            manifest.add(name, path)
        return manifest

    # -- publishing ---------------------------------------------------------------------

    def register_publisher(self, name: str, publisher: Publisher) -> None:
        self.publishers[name] = publisher

    def publish(self, version: str, notes: str = "", names: list[str] | None = None) -> dict[str, Any]:
        names = names or list(self.publishers) or list(self.config.publishers)
        results: dict[str, Any] = {}
        for name in names:
            publisher = self.publishers.get(name)
            if publisher is None:
                if self.config.auto_publish:
                    publisher = create_publisher(self.config, name)
                    self.publishers[name] = publisher
                else:
                    continue
            manifest = self._manifests.get(version)
            paths = [a["path"] for a in manifest.artifacts] if manifest else []
            results[name] = publisher.publish(version, paths, notes)
        return results

    # -- finalisation -----------------------------------------------------------------------

    def finalise(self, version: str) -> bool:
        """Mark a release immutable (locked against further artifact changes)."""
        if self.get_release(version) is None:
            raise VersionNotFoundError(f"release {version} not found")
        self._finalised.add(version)
        return True

    def status(self) -> dict[str, Any]:
        latest = self.latest_version()
        return {
            "project": self.config.project_name,
            "latest_version": str(latest) if latest else None,
            "release_count": len(self._releases),
            "finalised": sorted(self._finalised),
            "signatures": sorted(self._signatures),
            "publishers": sorted(self.publishers),
        }


def create_release_manager(config: ReleaseConfig | None = None, **overrides: Any) -> ReleaseManager:
    config = config if config is not None else ReleaseConfig()
    signer = overrides.pop("signer", None)
    changelog = overrides.pop("changelog", None)
    publishers = overrides.pop("publishers", None)
    history_file = overrides.pop("history_file", "")
    return ReleaseManager(config, signer, changelog, publishers, history_file)
