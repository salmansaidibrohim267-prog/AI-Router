"""Migration model and repositories for version tracking.

``Migration`` pairs an ``up`` and ``down`` callable with a version and name.
Repositories track applied versions: an in-memory store plus a SQLite driver
for real persistence. All drivers share the same ``MigrationStore`` protocol.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .exceptions import MigrationConflictError

StepFn = Callable[[dict[str, Any]], None]


@dataclass
class Migration:
    """A reversible schema migration step."""

    version: str
    name: str
    up: StepFn | None = None
    down: StepFn | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "has_up": self.up is not None,
            "has_down": self.down is not None,
            "metadata": dict(self.metadata),
        }


@dataclass
class AppliedMigration:
    """Record of a successfully applied migration."""

    version: str
    name: str
    applied_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "name": self.name, "applied_at": self.applied_at}


class MigrationStore(Protocol):
    """Protocol for version-tracking storage."""

    def applied_versions(self) -> list[str]: ...

    def is_applied(self, version: str) -> bool: ...

    def record(self, migration: AppliedMigration) -> None: ...

    def unrecord(self, version: str) -> None: ...


class MemoryMigrationStore:
    """In-memory store (falsy-safe: uses `is None`, never `or`)."""

    def __init__(self, applied: list[AppliedMigration] | None = None) -> None:
        self._applied: list[AppliedMigration] = list(applied) if applied is not None else []
        self._lock = threading.RLock()

    def applied_versions(self) -> list[str]:
        with self._lock:
            return [m.version for m in self._applied]

    def is_applied(self, version: str) -> bool:
        return version in self.applied_versions()

    def record(self, migration: AppliedMigration) -> None:
        with self._lock:
            if self.is_applied(migration.version):
                raise MigrationConflictError(f"migration {migration.version} already applied")
            self._applied.append(migration)

    def unrecord(self, version: str) -> None:
        with self._lock:
            self._applied = [m for m in self._applied if m.version != version]


class SqliteMigrationStore:
    """SQLite-backed store using a ``schema_versions`` table."""

    def __init__(self, database_path: str = ":memory:", table: str = "schema_versions") -> None:
        if not database_path:
            database_path = ":memory:"
        self.database_path = database_path
        self.table = table
        self._connection = sqlite3.connect(database_path)
        self._connection.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (version TEXT PRIMARY KEY, name TEXT, applied_at REAL)"
        )
        self._connection.commit()
        self._lock = threading.RLock()

    def _all(self) -> list[AppliedMigration]:
        cursor = self._connection.execute(f"SELECT version, name, applied_at FROM {self.table} ORDER BY applied_at")
        return [AppliedMigration(version=row[0], name=row[1], applied_at=row[2]) for row in cursor.fetchall()]

    def applied_versions(self) -> list[str]:
        with self._lock:
            return [m.version for m in self._all()]

    def is_applied(self, version: str) -> bool:
        return version in self.applied_versions()

    def record(self, migration: AppliedMigration) -> None:
        with self._lock:
            if self.is_applied(migration.version):
                raise MigrationConflictError(f"migration {migration.version} already applied")
            self._connection.execute(
                f"INSERT INTO {self.table} (version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.applied_at),
            )
            self._connection.commit()

    def unrecord(self, version: str) -> None:
        with self._lock:
            self._connection.execute(f"DELETE FROM {self.table} WHERE version = ?", (version,))
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class MigrationLock:
    """Advisory lock guarding the schema during migrations."""

    def __init__(self, store: MigrationStore | MemoryMigrationStore | SqliteMigrationStore) -> None:
        self._store = store
        self._held = False

    def acquire(self, timeout_seconds: float = 30.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._try_acquire():
                self._held = True
                return True
            time.sleep(0.01)
        return False

    def _try_acquire(self) -> bool:
        if isinstance(self._store, SqliteMigrationStore):
            try:
                self._store._connection.execute("BEGIN IMMEDIATE")
                return True
            except sqlite3.OperationalError:
                return False
        return True

    def release(self) -> None:
        if not self._held:
            return
        if isinstance(self._store, SqliteMigrationStore):
            try:
                self._store._connection.execute("COMMIT")
            except sqlite3.OperationalError:
                pass
        self._held = False
