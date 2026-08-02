"""Request routing, version negotiation, and route registry for the API Gateway."""

from __future__ import annotations

import re
import threading
from typing import Any

from .config import GatewayConfig
from .exceptions import (
    MethodNotAllowedError,
    RouteNotFoundError,
    VersionDeprecatedError,
    VersionNotSupportedError,
)
from .logging import GatewayLogger
from .models import Route, RouteMethod, VersionInfo


def compile_pattern(pattern: str) -> tuple[str, list[str]]:
    """Compile a route pattern into a regex and named parameter list.

    Supports ``{param}`` and ``:param`` styles, e.g. ``/users/{user_id}/posts``.
    """
    names: list[str] = []
    chunks: list[str] = []
    for chunk in pattern.split("/"):
        if not chunk:
            chunks.append("")
            continue
        if chunk.startswith("{") and chunk.endswith("}"):
            name = chunk[1:-1]
            names.append(name)
            chunks.append(r"(?P<" + name + r">[^/]+)")
        elif chunk.startswith(":") and len(chunk) > 1:
            name = chunk[1:]
            names.append(name)
            chunks.append(r"(?P<" + name + r">[^/]+)")
        else:
            chunks.append(re.escape(chunk))
    return "^" + "/".join(chunks) + "/?$", names


class VersionNegotiator:
    """Negotiates the API version from URL prefix or header."""

    def __init__(self, config: GatewayConfig):
        self._config = config

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def strip_version_prefix(self, path: str) -> tuple[str, str]:
        """Return ``(clean_path, version)`` when the path begins with a supported version."""
        first = path.split("/", 2)
        if len(first) < 2 or not first[1]:
            return path, ""
        candidate = first[1]
        if candidate in self._config.supported_versions:
            rest = "/" + first[2] if len(first) > 2 and first[2] else "/"
            return rest, candidate
        return path, ""

    def negotiate(self, path: str, headers: dict[str, str] | None = None, *, url_version: str = "", query: dict[str, Any] | None = None) -> VersionInfo:
        """Resolve the effective version, honoring header priority."""
        headers = headers or {}
        query = query or {}
        header_value = self._header_version(headers)
        url_value = url_version
        query_value = str(query.get("version") or "") if "version" in query else ""

        candidate = ""
        source = ""
        if self._config.version_header_priority:
            for value, src in ((header_value, "header"), (url_value, "url"), (query_value, "query")):
                if value:
                    candidate, source = value, src
                    break
        else:
            for value, src in ((url_value, "url"), (header_value, "header"), (query_value, "query")):
                if value:
                    candidate, source = value, src
                    break

        if not candidate:
            default = self._config.default_version
            deprecated = default in self._config.deprecated_versions
            return VersionInfo(
                version=default,
                source="default",
                deprecated=deprecated,
                sunset=self._sunset(default),
            )

        if candidate not in self._config.supported_versions:
            raise VersionNotSupportedError(candidate, list(self._config.supported_versions))

        deprecated = candidate in self._config.deprecated_versions
        return VersionInfo(
            version=candidate,
            source=source,
            deprecated=deprecated,
            sunset=self._sunset(candidate),
        )

    def _header_version(self, headers: dict[str, str]) -> str:
        if not self._config.allow_header_versioning:
            return ""
        value = headers.get(self._config.version_header, "")
        if not value:
            accept = headers.get("Accept", "")
            for part in accept.split(","):
                part = part.strip()
                if part.startswith("application/vnd.") and "+json" in part:
                    return part.split(".")[-1].split("+")[0]
        return value

    def _sunset(self, version: str) -> str:
        if version not in self._config.deprecated_versions:
            return ""
        index = self._config.deprecated_versions.index(version)
        return f"sunset-after-{index + 1}-deprecation-cycles"

    def deprecation_headers(self, info: VersionInfo) -> dict[str, str]:
        if not info.deprecated:
            return {}
        return {
            self._config.deprecation_warning_header: f'Deprecated version "{info.version}"',
            "Deprecation": f'version="{info.version}"',
            "Sunset": info.sunset,
        }

    def enforce_deprecation(self, info: VersionInfo) -> None:
        if info.deprecated and self._config.deprecated_versions.count(info.version) > 0 and getattr(self._config, "_hard_deprecation", False):
            raise VersionDeprecatedError(info.version)


class RouteRegistry:
    """Thread-safe registry of routes with pattern matching and versioning.

    A pattern may host multiple routes — one per API version — so the same
    path can evolve across versions with backward compatibility.
    """

    def __init__(self, config: GatewayConfig | None = None, logger: GatewayLogger | None = None):
        self._config = config or GatewayConfig()
        self._logger = logger or GatewayLogger(enabled=False)
        self._lock = threading.RLock()
        self._routes: dict[str, dict[str, Route]] = {}
        self._compiled: dict[str, tuple[str, list[str]]] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision

    def register(self, route: Route) -> None:
        if not route.pattern.startswith("/"):
            raise ValueError("Route patterns must start with '/'")
        with self._lock:
            self._routes.setdefault(route.pattern, {})[route.version] = route
            if route.pattern not in self._compiled:
                self._compiled[route.pattern] = compile_pattern(route.pattern)
            self._revision += 1
        if self._logger.enabled:
            self._logger.route(route.pattern, "registered", version=route.version)

    def unregister(self, pattern: str, version: str = "") -> bool:
        with self._lock:
            versions = self._routes.get(pattern)
            if versions is None:
                return False
            removed: Route | None = None
            if version:
                removed = versions.pop(version, None)
            else:
                removed = versions.popitem()[1] if versions else None
            if removed is None:
                return False
            self._revision += 1
            if not versions:
                self._routes.pop(pattern, None)
                self._compiled.pop(pattern, None)
        if self._logger.enabled:
            self._logger.route(pattern, "unregistered", version=removed.version)
        return True

    def get(self, pattern: str, version: str = "") -> Route | None:
        with self._lock:
            versions = self._routes.get(pattern)
            if versions is None:
                return None
            if version:
                return versions.get(version)
            return versions.get(self._config.default_version) or next(iter(versions.values()), None)

    def list(self, version: str = "") -> list[Route]:
        with self._lock:
            routes: list[Route] = []
            for versions in self._routes.values():
                for route_version, route in versions.items():
                    if not version or route_version == version:
                        routes.append(route)
            return sorted(routes, key=lambda r: (r.pattern, r.version))

    def reload(self) -> int:
        """Recompile all patterns; returns the new revision."""
        with self._lock:
            for pattern in self._routes:
                self._compiled[pattern] = compile_pattern(pattern)
            self._revision += 1
            return self._revision

    def clear(self) -> None:
        with self._lock:
            self._routes.clear()
            self._compiled.clear()
            self._revision += 1

    def count(self) -> int:
        with self._lock:
            return sum(len(versions) for versions in self._routes.values())

    def resolve(self, path: str, method: str, version: str = "") -> tuple[Route, dict[str, str]]:
        """Find the best route for ``path``/``method`` under ``version``.

        Prefers exact pattern matches, then parameterized matches. Raises
        :class:`RouteNotFoundError` or :class:`MethodNotAllowedError`.
        """
        with self._lock:
            exact_versions = self._routes.get(path)
            if exact_versions is not None:
                exact = self._pick(exact_versions, method, version)
                if exact is not None:
                    return exact, {}

            matched: list[tuple[Route, dict[str, str]]] = []
            for pattern, (regex, names) in self._compiled.items():
                if pattern == path:
                    continue
                for route in self._versions_for(pattern):
                    if not route.matches(method, version):
                        continue
                    match = re.match(regex, path)
                    if match:
                        params = {name: match.group(name) for name in names if match.groupdict().get(name) is not None}
                        matched.append((route, params))

            if not matched:
                if self._has_any_route(path, version):
                    raise MethodNotAllowedError(path, method, self._allowed_methods(path, version))
                raise RouteNotFoundError(path, method)

            matched.sort(key=lambda item: (self._static_score(item[0].pattern), item[0].pattern, item[0].version))
            return matched[0]

    def _pick(self, versions: dict[str, Route], method: str, version: str) -> Route | None:
        if version:
            route = versions.get(version)
            if route is not None and route.matches(method, version):
                return route
            return None
        candidates = sorted(versions.values(), key=lambda r: r.version)
        for route in candidates:
            if route.matches(method, ""):
                return route
        return None

    def _versions_for(self, pattern: str) -> list[Route]:
        return list(self._routes.get(pattern, {}).values())

    def _static_score(self, pattern: str) -> int:
        return sum(1 for chunk in pattern.split("/") if chunk and not chunk.startswith(("{", ":")))

    def _has_any_route(self, path: str, version: str) -> bool:
        for pattern, (regex, _names) in self._compiled.items():
            for route in self._versions_for(pattern):
                if version and route.version != version:
                    continue
                if re.match(regex, path):
                    return True
        return False

    def _allowed_methods(self, path: str, version: str) -> list[str]:
        allowed: list[str] = []
        for pattern, route_versions in self._routes.items():
            regex, _names = self._compiled.get(pattern, compile_pattern(pattern))
            if not re.match(regex, path):
                continue
            for route in route_versions.values():
                if version and route.version != version:
                    continue
                if RouteMethod.ANY.value in route.methods:
                    return [RouteMethod.ANY.value]
                allowed.extend(route.methods)
        return sorted(set(allowed))
