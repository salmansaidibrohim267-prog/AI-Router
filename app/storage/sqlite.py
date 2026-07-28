"""SQLite storage backend for persistent provider statistics."""

from __future__ import annotations

import time
from pathlib import Path

from app.storage import ProviderStats, StorageBackend


def _get_aiosqlite():
    """Lazy import aiosqlite to avoid hard dependency."""
    import aiosqlite
    return aiosqlite


class SQLiteStorage(StorageBackend):
    """SQLite-backed persistent storage for provider statistics.

    Stores one row per provider. Uses UPSERT semantics.
    Requires 'aiosqlite' package at runtime.
    """

    def __init__(self, db_path: str = "data/provider_stats.db"):
        self._db_path = db_path
        self._conn = None

    async def _ensure_db(self):
        if self._conn is None:
            aiosqlite = _get_aiosqlite()
            parent = Path(self._db_path).parent
            parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_stats (
                    name TEXT PRIMARY KEY,
                    total_requests INTEGER DEFAULT 0,
                    successful_requests INTEGER DEFAULT 0,
                    failed_requests INTEGER DEFAULT 0,
                    total_latency REAL DEFAULT 0.0,
                    ewma_latency REAL DEFAULT 0.0,
                    total_cost REAL DEFAULT 0.0,
                    total_prompt_tokens INTEGER DEFAULT 0,
                    total_completion_tokens INTEGER DEFAULT 0,
                    uptime_seconds REAL DEFAULT 0.0,
                    first_seen REAL DEFAULT 0.0,
                    last_seen REAL DEFAULT 0.0,
                    consecutive_failures INTEGER DEFAULT 0,
                    consecutive_success INTEGER DEFAULT 0
                )
            """)
            await self._conn.commit()
        return self._conn

    async def load_provider(self, name: str) -> ProviderStats | None:
        conn = await self._ensure_db()
        cursor = await conn.execute(
            "SELECT * FROM provider_stats WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ProviderStats(
            name=row["name"],
            total_requests=row["total_requests"],
            successful_requests=row["successful_requests"],
            failed_requests=row["failed_requests"],
            total_latency=row["total_latency"],
            ewma_latency=row["ewma_latency"],
            total_cost=row["total_cost"],
            total_prompt_tokens=row["total_prompt_tokens"],
            total_completion_tokens=row["total_completion_tokens"],
            uptime_seconds=row["uptime_seconds"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            consecutive_failures=row["consecutive_failures"],
            consecutive_success=row["consecutive_success"],
        )

    async def save_provider(self, stats: ProviderStats) -> None:
        conn = await self._ensure_db()
        await conn.execute("""
            INSERT INTO provider_stats (
                name, total_requests, successful_requests, failed_requests,
                total_latency, ewma_latency, total_cost,
                total_prompt_tokens, total_completion_tokens,
                uptime_seconds, first_seen, last_seen,
                consecutive_failures, consecutive_success
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                total_requests = excluded.total_requests,
                successful_requests = excluded.successful_requests,
                failed_requests = excluded.failed_requests,
                total_latency = excluded.total_latency,
                ewma_latency = excluded.ewma_latency,
                total_cost = excluded.total_cost,
                total_prompt_tokens = excluded.total_prompt_tokens,
                total_completion_tokens = excluded.total_completion_tokens,
                uptime_seconds = excluded.uptime_seconds,
                first_seen = excluded.first_seen,
                last_seen = excluded.last_seen,
                consecutive_failures = excluded.consecutive_failures,
                consecutive_success = excluded.consecutive_success
        """, (
            stats.name, stats.total_requests, stats.successful_requests,
            stats.failed_requests, stats.total_latency, stats.ewma_latency,
            stats.total_cost, stats.total_prompt_tokens,
            stats.total_completion_tokens, stats.uptime_seconds,
            stats.first_seen, stats.last_seen,
            stats.consecutive_failures, stats.consecutive_success,
        ))
        await conn.commit()

    async def load_all_providers(self) -> list[ProviderStats]:
        conn = await self._ensure_db()
        cursor = await conn.execute("SELECT * FROM provider_stats")
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            results.append(ProviderStats(
                name=row["name"],
                total_requests=row["total_requests"],
                successful_requests=row["successful_requests"],
                failed_requests=row["failed_requests"],
                total_latency=row["total_latency"],
                ewma_latency=row["ewma_latency"],
                total_cost=row["total_cost"],
                total_prompt_tokens=row["total_prompt_tokens"],
                total_completion_tokens=row["total_completion_tokens"],
                uptime_seconds=row["uptime_seconds"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                consecutive_failures=row["consecutive_failures"],
                consecutive_success=row["consecutive_success"],
            ))
        return results

    async def delete_provider(self, name: str) -> None:
        conn = await self._ensure_db()
        await conn.execute("DELETE FROM provider_stats WHERE name = ?", (name,))
        await conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
