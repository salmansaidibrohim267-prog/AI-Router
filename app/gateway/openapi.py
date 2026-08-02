"""OpenAPI 3.0 documentation generation for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .models import Route, RouteMethod, RouteProtocol, RouteVisibility


def _extract_path_params(pattern: str) -> list[str]:
    return re.findall(r"\{(?P<name>[^}]+)\}", pattern)


def _path_item(route: Route) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": f"{route.methods[0].lower()}_{route.pattern.replace('/', '_')}",
        "responses": {"200": {"description": "Successful response"}},
        "tags": route.tags or ["default"],
    }
    if route.deprecated:
        operation["deprecated"] = True
    if route.description:
        operation["description"] = route.description
    security = []
    if route.visibility == RouteVisibility.PUBLIC:
        security.append({})
    else:
        security.append({"bearerAuth": []})
    operation["security"] = security
    return operation


def generate_openapi_spec(gateway: Any) -> dict[str, Any]:
    """Build the full OpenAPI 3.0 spec document from registered routes."""
    config = gateway.config
    paths: dict[str, dict[str, Any]] = {}
    for version in config.supported_versions:
        for route in gateway.router.list(version):
            paths.setdefault(route.pattern, {})
            methods = [m for m in route.methods if m != RouteMethod.ANY.value] or ["get"]
            for method in methods:
                lower = method.lower()
                if lower in paths[route.pattern]:
                    continue
                operation = _path_item(route)
                for param in _extract_path_params(route.pattern):
                    operation.setdefault("parameters", []).append(
                        {"name": param, "in": "path", "required": True, "schema": {"type": "string"}}
                    )
                if route.protocol == RouteProtocol.SSE:
                    operation["responses"]["200"]["content"] = {"text/event-stream": {"schema": {"type": "string"}}}
                elif route.protocol == RouteProtocol.STREAM:
                    operation["responses"]["200"]["content"] = {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}
                else:
                    operation["responses"]["200"]["content"] = {"application/json": {"schema": {"type": "object"}}}
                paths[route.pattern][lower] = operation

    spec: dict[str, Any] = {
        "openapi": config.openapi_version,
        "info": {"title": config.openapi_title, "version": config.default_version, "description": "AI Router Gateway"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            }
        },
    }
    if config.openapi_servers:
        spec["servers"] = [{"url": server} for server in config.openapi_servers]
    return spec


def generate_openapi(gateway: Any, format: str = "json") -> str:
    """Render the OpenAPI document as JSON or YAML."""
    spec = generate_openapi_spec(gateway)
    if format == "yaml":
        return yaml.safe_dump(spec, sort_keys=False)
    return json.dumps(spec, indent=2)
