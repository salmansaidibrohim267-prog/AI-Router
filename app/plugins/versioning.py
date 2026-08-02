from __future__ import annotations

import re

_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")


def is_valid_version(version: str) -> bool:
    return bool(_SEMVER.match(version))


def parse_version(version: str) -> tuple[int, int, int, str]:
    if not is_valid_version(version):
        raise ValueError(f"invalid version {version!r}")
    core, sep, rest = version.partition("-")
    suffix = rest if sep else version.partition("+")[2]
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch, suffix)


def compare_versions(a: str, b: str) -> int:
    """Return -1/0/1: a < b, a == b, a > b."""
    pa, pb = parse_version(a), parse_version(b)
    if pa[:3] < pb[:3]:
        return -1
    if pa[:3] > pb[:3]:
        return 1
    if pa[3] == pb[3]:
        return 0
    return -1 if pa[3] else 1


def version_meets(version: str, requirement: str) -> bool:
    """Check version against a requirement like '>=2.0.0' or '^1.2.0'."""
    requirement = requirement.strip()
    if not requirement:
        return True
    if requirement.startswith("^"):
        base = parse_version(requirement[1:])
        target = parse_version(version)
        if target[:3] < base[:3]:
            return False
        return target[0] == base[0]
    if requirement.startswith(">="):
        return parse_version(version) >= parse_version(requirement[2:])
    if requirement.startswith("<="):
        return parse_version(version) <= parse_version(requirement[2:])
    if requirement.startswith(">"):
        return parse_version(version) > parse_version(requirement[1:])
    if requirement.startswith("<"):
        return parse_version(version) < parse_version(requirement[1:])
    if requirement.startswith("~"):
        base = parse_version(requirement[1:])
        target = parse_version(version)
        if target[:3] < base[:3]:
            return False
        return target[:2] == base[:2]
    return parse_version(version) == parse_version(requirement)
