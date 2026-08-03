"""Migration manager: discover, plan, upgrade, downgrade, rollback and dry-run.

Ordering is lexicographic on version strings (zero-padded numeric versions
recommended). ``upgrade`` applies pending migrations in order; ``rollback``
reverts the most recent ``steps`` applied migrations in reverse order;
``downgrade_to`` reverts everything above a target version. Dry-runs return
the plan without executing it.
"""

from __future__ import annotations

import os
from typing import Any

from .config import MigrationConfig
from .exceptions import (
    MigrationFailureError,
    MigrationLockedError,
    MigrationVersionError,
)
from .repository import (
    AppliedMigration,
    MemoryMigrationStore,
    Migration,
    MigrationLock,
    MigrationStore,
    SqliteMigrationStore,
)


class MigrationManager:
    """Applies and tracks schema migrations."""

    def __init__(
        self,
        config: MigrationConfig | None = None,
        store: MigrationStore | None = None,
        migrations: list[Migration] | None = None,
        migrations_dir: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.config = config if config is not None else MigrationConfig()
        self.store = store if store is not None else self._make_store()
        self.migrations_dir = migrations_dir or self.config.migrations_dir
        self.context = dict(context or {})
        self._migrations: dict[str, Migration] = {}
        for migration in migrations or []:
            self.register(migration)
        self._lock = MigrationLock(self.store)

    def _make_store(self) -> MigrationStore:
        if self.config.driver == "sqlite":
            return SqliteMigrationStore(self.config.database_path, self.config.schema_table)
        return MemoryMigrationStore()

    # -- registration / discovery --------------------------------------------------------

    def register(self, migration: Migration) -> None:
        if migration.version in self._migrations:
            raise MigrationVersionError(f"duplicate migration version {migration.version}")
        if not migration.version:
            raise MigrationVersionError("migration version must not be empty")
        self._migrations[migration.version] = migration

    def register_many(self, migrations: list[Migration]) -> None:
        for migration in migrations:
            self.register(migration)

    def get(self, version: str) -> Migration | None:
        return self._migrations.get(version)

    def migrations(self) -> list[Migration]:
        return [self._migrations[v] for v in sorted(self._migrations)]

    def load_from_dir(self, directory: str | None = None) -> list[Migration]:
        """Load ``<version>_<name>.py`` modules exposing ``upgrade(ctx)``/``downgrade(ctx)``."""
        directory = directory or self.migrations_dir
        loaded: list[Migration] = []
        if not os.path.isdir(directory):
            return loaded
        import importlib.util

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py"):
                continue
            base = filename[:-3]
            if "_" not in base:
                continue
            version, name = base.split("_", 1)
            if not version or any(not (part.isdigit() or part == ".") for part in version):
                continue
            path = os.path.join(directory, filename)
            spec = importlib.util.spec_from_file_location(f"migration_{version}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            up = getattr(module, "upgrade", None)
            down = getattr(module, "downgrade", None)
            if up is None:
                up = lambda ctx: None  # noqa: E731
            if down is None:
                down = lambda ctx: None  # noqa: E731
            migration = Migration(version=version, name=name, up=up, down=down)
            self.register(migration)
            loaded.append(migration)
        return loaded

    # -- planning ---------------------------------------------------------------------------

    def applied_versions(self) -> list[str]:
        return self.store.applied_versions()

    def pending(self) -> list[Migration]:
        applied = set(self.applied_versions())
        return [m for m in self.migrations() if m.version not in applied]

    def is_applied(self, version: str) -> bool:
        return self.store.is_applied(version)

    def plan(self) -> list[Migration]:
        return self.pending()

    def plan_rollback(self, steps: int = 1) -> list[Migration]:
        applied = [v for v in self.store.applied_versions() if v in self._migrations]
        ordered = sorted(applied, key=lambda v: _version_key(v))
        selected = ordered[-steps:] if steps > 0 else []
        return [self._migrations[v] for v in reversed(selected)]

    def plan_downgrade_to(self, target: str) -> list[Migration]:
        applied = [v for v in self.store.applied_versions() if v in self._migrations]
        ordered = sorted(applied, key=lambda v: _version_key(v))
        target_key = _version_key(target)
        to_revert = [v for v in ordered if _version_key(v) > target_key]
        return [self._migrations[v] for v in reversed(to_revert)]

    # -- execution ---------------------------------------------------------------------------

    def _execute_up(self, migration: Migration, dry_run: bool = False) -> None:
        if not dry_run and migration.up is not None:
            try:
                migration.up(self.context)
            except Exception as exc:
                raise MigrationFailureError(f"migration {migration.version} up failed: {exc}") from exc
        if not dry_run:
            self.store.record(AppliedMigration(version=migration.version, name=migration.name))
        self.context.setdefault("_log", []).append(("up", migration.version, dry_run))

    def _execute_down(self, migration: Migration, dry_run: bool = False) -> None:
        if not dry_run and migration.down is not None:
            try:
                migration.down(self.context)
            except Exception as exc:
                raise MigrationFailureError(f"migration {migration.version} down failed: {exc}") from exc
        if not dry_run:
            self.store.unrecord(migration.version)
        self.context.setdefault("_log", []).append(("down", migration.version, dry_run))

    def upgrade(self, dry_run: bool = False) -> list[Migration]:
        if not dry_run:
            acquired = self._lock.acquire(self.config.lock_timeout_seconds)
            if not acquired:
                raise MigrationLockedError("schema is locked by another migrator")
        try:
            applied: list[Migration] = []
            for migration in self.pending():
                self._execute_up(migration, dry_run)
                applied.append(migration)
            return applied
        finally:
            if not dry_run:
                self._lock.release()

    def migrate(self) -> list[Migration]:
        """Alias for ``upgrade`` used by CI and entrypoints."""
        return self.upgrade()

    def downgrade_to(self, target: str, dry_run: bool = False) -> list[Migration]:
        if not dry_run:
            acquired = self._lock.acquire(self.config.lock_timeout_seconds)
            if not acquired:
                raise MigrationLockedError("schema is locked by another migrator")
        try:
            reverted: list[Migration] = []
            for migration in self.plan_downgrade_to(target):
                self._execute_down(migration, dry_run)
                reverted.append(migration)
            return reverted
        finally:
            if not dry_run:
                self._lock.release()

    def rollback(self, steps: int = 1, dry_run: bool = False) -> list[Migration]:
        """Revert the most recent ``steps`` applied migrations (reverse order)."""
        if steps <= 0:
            return []
        if not dry_run:
            acquired = self._lock.acquire(self.config.lock_timeout_seconds)
            if not acquired:
                raise MigrationLockedError("schema is locked by another migrator")
        try:
            reverted: list[Migration] = []
            for migration in self.plan_rollback(steps):
                self._execute_down(migration, dry_run)
                reverted.append(migration)
            return reverted
        finally:
            if not dry_run:
                self._lock.release()

    def status(self) -> dict[str, Any]:
        return {
            "applied": self.applied_versions(),
            "pending": [m.version for m in self.pending()],
            "total": len(self._migrations),
            "driver": self.config.driver,
            "migrations_dir": self.migrations_dir,
        }


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def create_migration_manager(config: MigrationConfig | None = None, **overrides: Any) -> MigrationManager:
    config = config if config is not None else MigrationConfig()
    store = overrides.pop("store", None)
    migrations = overrides.pop("migrations", None)
    migrations_dir = overrides.pop("migrations_dir", "")
    context = overrides.pop("context", None)
    return MigrationManager(config, store, migrations, migrations_dir, context)
