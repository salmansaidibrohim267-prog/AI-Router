from __future__ import annotations

import base64
import json
from typing import Any

from app.retrieval.exceptions import PaginationError
from app.retrieval.models import SearchQuery, SearchResultItem


class Paginator:
    def __init__(self, max_limit: int = 100):
        self._max_limit = max_limit

    def apply(self, query: SearchQuery, all_results: list[SearchResultItem]) -> list[SearchResultItem]:
        offset = query.offset
        limit = min(query.limit, self._max_limit) if query.limit else 10
        limit = max(limit, 1)

        if query.cursor:
            offset = self._decode_cursor(query.cursor)
            if offset is None:
                raise PaginationError("Invalid cursor")

        if offset >= len(all_results):
            return []

        return all_results[offset:offset + limit]

    def compute_next_cursor(self, query: SearchQuery, results: list[SearchResultItem], total: int) -> str | None:
        new_offset = query.offset + len(results)
        if new_offset >= total:
            return None
        return self._encode_cursor(new_offset)

    def _encode_cursor(self, offset: int) -> str:
        raw = json.dumps({"offset": offset})
        return base64.urlsafe_b64encode(raw.encode()).decode()

    def _decode_cursor(self, cursor: str) -> int | None:
        try:
            raw = base64.urlsafe_b64decode(cursor.encode() + b"==")
            data = json.loads(raw)
            return int(data["offset"])
        except (Exception, ValueError):
            return None
