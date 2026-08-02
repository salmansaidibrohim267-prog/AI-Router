"""Semantic Versioning 2.0.0 with release-candidate support.

Supports ``major.minor.patch`` plus optional ``-prerelease`` and ``+build``
suffixes, comparison per the semver precedence rules (prerelease < release),
and bumping of each segment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .exceptions import VersionError

_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@dataclass(frozen=True)
class SemanticVersion:
    """An immutable semantic version."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""

    def __post_init__(self) -> None:
        for name, value in (("major", self.major), ("minor", self.minor), ("patch", self.patch)):
            if not isinstance(value, int) or value < 0:
                raise VersionError(f"{name} must be a non-negative integer, got {value!r}")

    # -- parsing / serialisation ----------------------------------------------

    @classmethod
    def parse(cls, text: str) -> "SemanticVersion":
        match = _VERSION_RE.match(str(text).strip())
        if match is None:
            raise VersionError(f"invalid semantic version: {text!r}")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("pre") or "",
            build=match.group("build") or "",
        )

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += f"-{self.prerelease}"
        if self.build:
            value += f"+{self.build}"
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "prerelease": self.prerelease,
            "build": self.build,
            "version": str(self),
        }

    # -- properties -------------------------------------------------------------

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def is_rc(self) -> bool:
        return self.prerelease.startswith("rc")

    def rc_number(self) -> int:
        if not self.is_rc():
            return 0
        suffix = self.prerelease[2:].lstrip(".")
        try:
            return int(suffix) if suffix else 1
        except ValueError:
            return 0

    # -- comparison (semver precedence) ------------------------------------------

    def _pre_key(self) -> list[Any]:
        if not self.prerelease:
            return [1]
        parts: list[Any] = [0]
        for part in self.prerelease.split("."):
            if part.isdigit():
                parts.append(("num", int(part)))
            else:
                parts.append(("str", part))
        return parts

    def _base_key(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def _compare(self, other: "SemanticVersion") -> int:
        base_a, base_b = self._base_key(), other._base_key()
        if base_a != base_b:
            return -1 if base_a < base_b else 1
        key_a, key_b = self._pre_key(), other._pre_key()
        return -1 if key_a < key_b else (1 if key_a > key_b else 0)

    def __lt__(self, other: "SemanticVersion") -> bool:
        return self._compare(other) < 0

    def __le__(self, other: "SemanticVersion") -> bool:
        return self._compare(other) <= 0

    def __gt__(self, other: "SemanticVersion") -> bool:
        return self._compare(other) > 0

    def __ge__(self, other: "SemanticVersion") -> bool:
        return self._compare(other) >= 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._compare(other) == 0

    def __hash__(self) -> int:
        return hash(str(self))

    # -- bumping -------------------------------------------------------------------

    def bump_major(self, prerelease: str = "") -> "SemanticVersion":
        return SemanticVersion(self.major + 1, 0, 0, prerelease)

    def bump_minor(self, prerelease: str = "") -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor + 1, 0, prerelease)

    def bump_patch(self, prerelease: str = "") -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor, self.patch + 1, prerelease)

    def as_release(self) -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor, self.patch)

    def as_rc(self, number: int = 1) -> "SemanticVersion":
        return SemanticVersion(self.major, self.minor, self.patch, f"rc.{number}")

    def next(self, bump: str = "patch", prerelease: str = "") -> "SemanticVersion":
        if bump == "major":
            return self.bump_major(prerelease)
        if bump == "minor":
            return self.bump_minor(prerelease)
        if bump == "patch":
            return self.bump_patch(prerelease)
        if bump == "rc":
            return self.as_rc(self.rc_number() + 1)
        if bump == "release":
            return self.as_release()
        raise VersionError(f"unknown bump type {bump!r}")
