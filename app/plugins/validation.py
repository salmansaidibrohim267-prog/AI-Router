from __future__ import annotations

import re
from typing import Any

from .exceptions import PluginCompatibilityError, PluginInvalidError
from .models import PermissionResource
from .versioning import version_meets

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

_REQUIRED_FIELDS = ("name", "version", "entry")

_PERMISSION_RESOURCES = {resource.value for resource in PermissionResource}

_PERMISSION_ACTIONS = {"read", "write", "execute", "listen", "emit", "call", "access"}


class ManifestValidator:
    """Validates plugin manifests/specs and reports all problems at once."""

    def validate(self, spec: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(spec, dict):
            return ["manifest must be a mapping"]
        for field in _REQUIRED_FIELDS:
            if field not in spec:
                errors.append(f"missing required field {field!r}")
        name = spec.get("name", "")
        if not isinstance(name, str) or not _NAME_PATTERN.match(name):
            errors.append(f"invalid plugin name {name!r}")
        version = spec.get("version", "")
        from .versioning import is_valid_version

        if not isinstance(version, str) or not is_valid_version(version):
            errors.append(f"invalid semver version {version!r}")
        entry = spec.get("entry", "")
        if not isinstance(entry, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", entry):
            errors.append(f"invalid entry point {entry!r}")
        permissions = spec.get("permissions", [])
        if not isinstance(permissions, list):
            errors.append("permissions must be a list")
        else:
            for index, permission in enumerate(permissions):
                if not isinstance(permission, dict):
                    errors.append(f"permissions[{index}] must be a mapping")
                    continue
                resource = permission.get("resource")
                if resource not in _PERMISSION_RESOURCES:
                    errors.append(f"permissions[{index}] unknown resource {resource!r}")
                actions = permission.get("actions", [])
                if not isinstance(actions, list) or not actions or not set(actions) <= _PERMISSION_ACTIONS:
                    errors.append(f"permissions[{index}] invalid actions {actions!r}")
        if "signature" in spec and not isinstance(spec["signature"], str):
            errors.append("signature must be a string")
        return errors

    def validate_or_raise(self, spec: dict[str, Any]) -> None:
        errors = self.validate(spec)
        if errors:
            raise PluginInvalidError("; ".join(errors), errors=errors)


class CompatibilityChecker:
    """Checks router/API compatibility before install or upgrade."""

    def __init__(self, router_version: str = "2.0.0", max_extensions: int = 500) -> None:
        self._router_version = router_version
        self._max_extensions = max_extensions

    def check(self, spec: dict[str, Any], extension_count: int = 0) -> list[str]:
        issues: list[str] = []
        requires = spec.get("requires_router", "")
        if requires and not version_meets(self._router_version, requires):
            issues.append(f"requires router {requires}, running {self._router_version}")
        tags = spec.get("tags", [])
        if not isinstance(tags, list):
            issues.append("tags must be a list")
        if "deprecated" in tags:
            issues.append("plugin is marked deprecated")
        if extension_count and extension_count > self._max_extensions:
            issues.append(f"extension count {extension_count} exceeds limit {self._max_extensions}")
        return issues

    def check_or_raise(self, spec: dict[str, Any], extension_count: int = 0) -> None:
        issues = self.check(spec, extension_count=extension_count)
        if issues:
            raise PluginCompatibilityError("; ".join(issues), issues=issues)
