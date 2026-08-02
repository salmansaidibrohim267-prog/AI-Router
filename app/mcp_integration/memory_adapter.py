from __future__ import annotations

from typing import Any

from .config import MCPIntegrationConfig
from .exceptions import MCPMemoryAdapterError
from .logging import MCPIntegrationLogger
from .statistics import MCPIntegrationMetricsTracker


class MCPMemoryAdapter:
    def __init__(
        self,
        client: Any,
        config: MCPIntegrationConfig | None = None,
        logger: MCPIntegrationLogger | None = None,
        metrics: MCPIntegrationMetricsTracker | None = None,
    ):
        self._client = client
        self._config = config or MCPIntegrationConfig()
        self._logger = logger or MCPIntegrationLogger()
        self._metrics = metrics or MCPIntegrationMetricsTracker(self._config)

    async def _ensure_connected(self) -> None:
        if not getattr(self._client, "connected", False):
            if hasattr(self._client, "connect"):
                await self._client.connect()
            else:
                raise MCPMemoryAdapterError("MCP client is not connected")

    @staticmethod
    def _memory_item_from_dict(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": data.get("id", data.get("item_id", "")),
            "content": data.get("content", ""),
            "memory_type": data.get("memory_type", "short_term"),
            "category": data.get("category", "general"),
            "importance": data.get("importance", 0.5),
            "confidence": data.get("confidence", 1.0),
            "metadata": data.get("metadata", {}),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    async def store(
        self,
        content: str,
        scope: dict[str, str] | None = None,
        memory_type: str = "short_term",
        category: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "content": content,
            "memory_type": memory_type,
            "category": category,
        }
        if scope:
            arguments[self._config.memory_scope_param] = scope
        if metadata:
            arguments["metadata"] = metadata
        try:
            await self._ensure_connected()
            self._metrics.record_tool_call()
            result = await self._client.call_tool(
                self._config.memory_store_tool,
                arguments,
                timeout=self._config.timeout,
            )
        except MCPMemoryAdapterError:
            raise
        except Exception as exc:
            self._metrics.record_error()
            raise MCPMemoryAdapterError(f"MCP memory store failed: {exc}") from exc
        if getattr(result, "is_error", False):
            self._metrics.record_error()
            raise MCPMemoryAdapterError(
                f"Memory tool {self._config.memory_store_tool!r} returned an error"
            )
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict) and structured.get("item"):
            item = self._memory_item_from_dict(structured["item"])
        else:
            item = self._memory_item_from_dict(
                {"id": "", "content": content, "memory_type": memory_type}
            )
        self._metrics.record_memory_store()
        self._logger.log_event(
            "memory_store",
            memory_type=memory_type,
            category=category,
            scope=scope or {},
        )
        return item

    async def search(
        self,
        query: str = "",
        scope: dict[str, str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        arguments: dict[str, Any] = {"query": query, "top_k": top_k}
        if scope:
            arguments[self._config.memory_scope_param] = scope
        try:
            await self._ensure_connected()
            self._metrics.record_tool_call()
            result = await self._client.call_tool(
                self._config.memory_search_tool,
                arguments,
                timeout=self._config.timeout,
            )
        except MCPMemoryAdapterError:
            raise
        except Exception as exc:
            self._metrics.record_error()
            raise MCPMemoryAdapterError(f"MCP memory search failed: {exc}") from exc
        if getattr(result, "is_error", False):
            self._metrics.record_error()
            raise MCPMemoryAdapterError(
                f"Memory tool {self._config.memory_search_tool!r} returned an error"
            )
        items = self._parse_memory_items(result)
        self._metrics.record_memory_retrieve(len(items))
        self._logger.log_event(
            "memory_search",
            query=query,
            top_k=top_k,
            results=len(items),
        )
        return items

    def _parse_memory_items(self, result: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            raw = (
                structured.get("items")
                or structured.get("results")
                or structured.get("memories")
            )
            if isinstance(raw, list):
                items = [self._memory_item_from_dict(i) for i in raw if isinstance(i, dict)]
        for block in getattr(result, "content", None) or []:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    items.append(self._memory_item_from_dict({"content": text}))
        return items

    async def retrieve(
        self,
        scope: dict[str, str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return await self.search("", scope=scope, top_k=top_k)

    async def delete(self, item_id: str) -> bool:
        try:
            await self._ensure_connected()
            self._metrics.record_tool_call()
            result = await self._client.call_tool(
                self._config.memory_delete_tool,
                {"id": item_id},
                timeout=self._config.timeout,
            )
        except MCPMemoryAdapterError:
            raise
        except Exception as exc:
            self._metrics.record_error()
            raise MCPMemoryAdapterError(f"MCP memory delete failed: {exc}") from exc
        if getattr(result, "is_error", False):
            self._metrics.record_error()
            raise MCPMemoryAdapterError(
                f"Memory tool {self._config.memory_delete_tool!r} returned an error"
            )
        self._logger.log_event("memory_delete", item_id=item_id)
        return True

    @staticmethod
    def to_chunks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for item in items:
            content = item.get("content")
            if not content:
                continue
            chunks.append(
                {
                    "id": item.get("id", "memory"),
                    "content": content,
                    "score": float(item.get("importance", 0.5)),
                    "metadata": {
                        "source": "memory",
                        "memory_type": item.get("memory_type", "short_term"),
                        "category": item.get("category", "general"),
                        **item.get("metadata", {}),
                    },
                }
            )
        return chunks
