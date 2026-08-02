from __future__ import annotations

import time
from typing import Any

from app.retrieval.exceptions import FilterError
from app.retrieval.models import MetadataFilter, SearchQuery


class MetadataFilterEngine:
    def apply(
        self,
        query: SearchQuery,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for item in results:
            metadata = item.get("metadata", {})
            if not self._matches_all(query, metadata):
                continue
            filtered.append(item)
        return filtered

    def _matches_all(self, query: SearchQuery, metadata: dict[str, Any]) -> bool:
        for mf in query.metadata_filters:
            if not self._matches(mf, metadata):
                return False
        if query.author is not None:
            if metadata.get("author") != query.author:
                return False
        if query.tags:
            item_tags = metadata.get("tags", [])
            if isinstance(item_tags, str):
                item_tags = [item_tags]
            if not any(t in item_tags for t in query.tags):
                return False
        if query.language is not None:
            if metadata.get("language") != query.language:
                return False
        if query.source is not None:
            if metadata.get("source") != query.source:
                return False
        if query.tenant is not None:
            if metadata.get("tenant") != query.tenant:
                return False
        if query.custom_filters:
            for k, v in query.custom_filters.items():
                if metadata.get(k) != v:
                    return False
        return True

    def _matches(self, mf: MetadataFilter, metadata: dict[str, Any]) -> bool:
        actual = metadata.get(mf.field)
        op = mf.operator
        if op == "eq":
            return actual == mf.value
        elif op == "neq":
            return actual != mf.value
        elif op == "gt":
            return actual is not None and actual > mf.value
        elif op == "gte":
            return actual is not None and actual >= mf.value
        elif op == "lt":
            return actual is not None and actual < mf.value
        elif op == "lte":
            return actual is not None and actual <= mf.value
        elif op == "in":
            return actual in (mf.value or [])
        elif op == "contains":
            return mf.value in (actual or "")
        else:
            raise FilterError(f"Unknown operator: {op}")

    def build_vector_store_filter(
        self,
        query: SearchQuery,
    ) -> dict[str, Any] | None:
        vs_filter: dict[str, Any] = {}
        has_filters = False

        for mf in query.metadata_filters:
            if mf.operator == "eq":
                vs_filter[mf.field] = mf.value
                has_filters = True

        if query.author is not None:
            vs_filter["author"] = query.author
            has_filters = True
        if query.language is not None:
            vs_filter["language"] = query.language
            has_filters = True
        if query.source is not None:
            vs_filter["source"] = query.source
            has_filters = True
        if query.tenant is not None:
            vs_filter["tenant"] = query.tenant
            has_filters = True
        if query.custom_filters:
            vs_filter.update(query.custom_filters)
            has_filters = True

        return vs_filter if has_filters else None
