"""Schema migration tooling (Stage 10.10).

Upgrade / rollback / downgrade / dry-run with SQLite and in-memory version
tracking, file-based migration discovery and advisory locking.
"""

from .config import MigrationConfig
from .exceptions import (
    MigrationConflictError,
    MigrationError,
    MigrationFailureError,
    MigrationLockedError,
    MigrationNotFoundError,
    MigrationVersionError,
)
from .manager import MigrationManager, create_migration_manager
from .repository import (
    AppliedMigration,
    MemoryMigrationStore,
    Migration,
    MigrationLock,
    MigrationStore,
    SqliteMigrationStore,
)

__all__ = [
    "MigrationConfig",
    "Migration",
    "AppliedMigration",
    "MigrationStore",
    "MemoryMigrationStore",
    "SqliteMigrationStore",
    "MigrationLock",
    "MigrationManager",
    "create_migration_manager",
    "MigrationError",
    "MigrationNotFoundError",
    "MigrationConflictError",
    "MigrationVersionError",
    "MigrationLockedError",
    "MigrationFailureError",
]
