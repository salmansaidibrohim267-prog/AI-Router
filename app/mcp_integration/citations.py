from __future__ import annotations

from typing import Any

from .config import MCPIntegrationConfig
from .exceptions import MCPCitationResolverError
from .logging import MCPIntegrationLogger
from .models import MCPRetrievalResult
from .statistics import MCPIntegrationMetricsTracker


class MCPCitationResolver:
    def __init__(
        self,
        client: Any,
        config: MCPIntegrationConfig | None = None,
        logger: MCPIntegrationLogger | None = None,
        metrics: MCPIntegrationMetricsTracker | None = None,
        engine: Any | None = None,
    ):
        self._client = client
        self._config = config or MCPIntegrationConfig()
        self._logger = logger or MCPIntegrationLogger()
        self._metrics = metrics or MCPIntegrationMetricsTracker(self._config)
        self._engine = engine

    async def resolve_async(
        self, sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for source in sources:
            uri = source.get("uri") or source.get("mcp_uri")
            if not uri:
                continue
            if self._config.citation_resource_prefix and not str(uri).startswith(
                self._config.citation_resource_prefix
            ):
                continue
            try:
                self._metrics.record_resource_read()
                resource = await self._client.read_resource(uri)
            except Exception as exc:
                raise MCPCitationResolverError(
                    f"MCP citation source resolution failed for {uri}: {exc}"
                ) from exc
            text = getattr(resource, "text", None)
            if not isinstance(text, str):
                text = ""
            resolved.append(
                {
                    "source_id": source.get("source_id", str(uri)),
                    "uri": str(uri),
                    "title": source.get("title", ""),
                    "author": source.get("author", ""),
                    "content": text,
                    "retrieval_score": source.get("retrieval_score", 0.5),
                }
            )
        self._logger.log_event(
            "citation_resolve",
            requested=len(sources),
            resolved=len(resolved),
        )
        return resolved

    async def cite_async(
        self,
        text: str,
        chunks: list[MCPRetrievalResult],
        citation_format: str | None = None,
        include_resources: bool = True,
    ) -> dict[str, Any]:
        if self._engine is None:
            raise MCPCitationResolverError(
                "Citation engine is not configured; cannot generate citations"
            )
        sources: list[dict[str, Any]] = []
        for chunk in chunks:
            sources.append(
                {
                    "source_id": chunk.id or chunk.metadata.get("uri", "chunk"),
                    "uri": chunk.metadata.get("uri", ""),
                    "content": chunk.content,
                    "retrieval_score": chunk.score,
                    "title": chunk.metadata.get("title", ""),
                    "author": chunk.metadata.get("author", ""),
                }
            )
        local = [s for s in sources if not s.get("uri")]
        remote = [s for s in sources if s.get("uri")]
        resolved: list[dict[str, Any]] = list(local)
        if include_resources and remote:
            try:
                resolved.extend(await self.resolve_async(remote))
            except MCPCitationResolverError:
                resolved.extend(remote)
        try:
            result = await self._engine.generate_async(
                text=text,
                sources=resolved,
                citation_format=citation_format or self._config.citation_format,
            )
        except MCPCitationResolverError:
            raise
        except Exception as exc:
            self._metrics.record_error()
            raise MCPCitationResolverError(
                f"MCP citation generation failed: {exc}"
            ) from exc
        self._metrics.record_citation()
        rendered = getattr(result, "rendered", "")
        verified = bool(getattr(result, "verified", False))
        errors = list(getattr(result, "errors", []))
        self._logger.log_event(
            "citation_generated",
            sources=len(sources),
            verified=verified,
            errors=errors,
        )
        return {
            "text": getattr(result, "text", text),
            "rendered": rendered,
            "format": getattr(result, "format", citation_format or self._config.citation_format),
            "verified": verified,
            "errors": errors,
            "sources": [getattr(s, "to_dict", lambda: dict(s))() for s in getattr(result, "sources", [])],
        }
