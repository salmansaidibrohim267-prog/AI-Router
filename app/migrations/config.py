"""Migration tooling configuration (Stage 10.10)."""

from __future__ import annotations

import os
from typing import Any


class MigrationConfig:
    """Runtime configuration for schema migrations."""

    def __init__(self, **kwargs: Any) -> None:
        self.migrations_dir: str = kwargs.pop("migrations_dir", "config/migrations")
        self.schema_table: str = kwargs.pop("schema_table", "schema_versions")
        self.driver: str = kwargs.pop("driver", "memory")
        self.database_path: str = kwargs.pop("database_path", "")
        self.auto_migrate: bool = bool(kwargs.pop("auto_migrate", False))
        self.lock_timeout_seconds: int = int(kwargs.pop("lock_timeout_seconds", 30))
        self._reject_unknown(kwargs)

    def _reject_unknown(self, kwargs: dict[str, Any]) -> None:
        if kwargs:
            raise TypeError(f"unexpected migration config: {sorted(kwargs)}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "MigrationConfig":
        kwargs: dict[str, Any] = {
            "migrations_dir": os.environ.get("MIG_MIGRATIONS_DIR", "config/migrations"),
            "schema_table": os.environ.get("MIG_SCHEMA_TABLE", "schema_versions"),
            "driver": os.environ.get("MIG_DRIVER", "memory"),
            "database_path": os.environ.get("MIG_DATABASE_PATH", ""),
            "auto_migrate": os.environ.get("MIG_AUTO_MIGRATE", "false").lower() in ("1", "true", "yes"),
            "lock_timeout_seconds": int(os.environ.get("MIG_LOCK_TIMEOUT_SECONDS", "30")),
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        return {name: value for name, value in vars(self).items()}
