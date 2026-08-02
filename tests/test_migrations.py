"""Tests for the migrations subsystem (Stage 10.10)."""

import os

import pytest

from app.migrations import (
    AppliedMigration,
    MemoryMigrationStore,
    Migration,
    MigrationConfig,
    MigrationConflictError,
    MigrationFailureError,
    MigrationLockedError,
    MigrationManager,
    MigrationNotFoundError,
    MigrationStore,
    MigrationVersionError,
    SqliteMigrationStore,
    create_migration_manager,
)


def _migration(version, name="m", up=None, down=None):
    return Migration(version=version, name=name, up=up, down=down)


class TestMigrationConfig:
    def test_defaults(self):
        config = MigrationConfig()
        assert config.migrations_dir == "config/migrations"
        assert config.schema_table == "schema_versions"
        assert config.driver == "memory"
        assert config.lock_timeout_seconds == 30

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MIG_DRIVER", "sqlite")
        monkeypatch.setenv("MIG_AUTO_MIGRATE", "true")
        config = MigrationConfig.from_env()
        assert config.driver == "sqlite"
        assert config.auto_migrate is True

    def test_unknown_kwarg_raises(self):
        with pytest.raises(TypeError):
            MigrationConfig(bogus=1)


class TestStores:
    def test_memory_record_and_unrecord(self):
        store = MemoryMigrationStore()
        assert store.applied_versions() == []
        assert store.is_applied("1") is False
        store.record(AppliedMigration("1", "a"))
        assert store.is_applied("1") is True
        assert store.applied_versions() == ["1"]
        store.unrecord("1")
        assert store.is_applied("1") is False

    def test_memory_record_conflict(self):
        store = MemoryMigrationStore()
        store.record(AppliedMigration("1", "a"))
        with pytest.raises(MigrationConflictError):
            store.record(AppliedMigration("1", "b"))

    def test_memory_initial_applied(self):
        store = MemoryMigrationStore(applied=[AppliedMigration("1", "a")])
        assert store.applied_versions() == ["1"]

    def test_sqlite_roundtrip(self):
        store = SqliteMigrationStore(":memory:")
        store.record(AppliedMigration("1", "a", 123.0))
        assert store.applied_versions() == ["1"]
        assert store.is_applied("1")
        store.unrecord("1")
        assert store.applied_versions() == []
        store.close()

    def test_sqlite_conflict(self):
        store = SqliteMigrationStore(":memory:")
        store.record(AppliedMigration("1", "a"))
        with pytest.raises(MigrationConflictError):
            store.record(AppliedMigration("1", "b"))
        store.close()

    def test_sqlite_file_persistence(self, tmp_path):
        path = str(tmp_path / "db.sqlite")
        store = SqliteMigrationStore(path)
        store.record(AppliedMigration("1", "a"))
        store.close()
        store2 = SqliteMigrationStore(path)
        assert store2.is_applied("1")
        store2.close()

    def test_sqlite_empty_path_uses_memory(self):
        store = SqliteMigrationStore("")
        assert store.database_path == ":memory:"
        store.close()

    def test_migration_to_dict(self):
        migration = _migration("1", "init", up=lambda ctx: None)
        data = migration.to_dict()
        assert data["version"] == "1"
        assert data["has_up"] is True
        assert data["has_down"] is False

    def test_applied_migration_to_dict(self):
        data = AppliedMigration("1", "a", 5.0).to_dict()
        assert data == {"version": "1", "name": "a", "applied_at": 5.0}


class TestMigrationManager:
    def test_register_and_get(self):
        manager = MigrationManager()
        manager.register(_migration("1", "init"))
        assert manager.get("1") is not None
        assert manager.get("2") is None
        assert [m.version for m in manager.migrations()] == ["1"]

    def test_register_duplicate_raises(self):
        manager = MigrationManager()
        manager.register(_migration("1"))
        with pytest.raises(MigrationVersionError):
            manager.register(_migration("1"))

    def test_register_empty_version_raises(self):
        manager = MigrationManager()
        with pytest.raises(MigrationVersionError):
            manager.register(_migration(""))

    def test_register_many_and_ordering(self):
        manager = MigrationManager()
        manager.register_many([_migration("2"), _migration("10"), _migration("1")])
        assert [m.version for m in manager.migrations()] == ["1", "10", "2"]

    def test_upgrade_applies_in_order(self):
        log = []

        def up(ctx):
            log.append("up")

        manager = MigrationManager(migrations=[_migration("1", "a", up=up), _migration("2", "b", up=up)])
        applied = manager.upgrade()
        assert [m.version for m in applied] == ["1", "2"]
        assert log == ["up", "up"]
        assert manager.is_applied("1")
        assert manager.is_applied("2")

    def test_upgrade_idempotent(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2")])
        manager.upgrade()
        assert manager.upgrade() == []

    def test_dry_run_does_not_apply(self):
        log = []

        def up(ctx):
            log.append(1)

        manager = MigrationManager(migrations=[_migration("1", up=up)])
        applied = manager.upgrade(dry_run=True)
        assert applied == [m for m in manager.migrations()]
        assert log == []
        assert manager.is_applied("1") is False

    def test_dry_run_logs_entries(self):
        manager = MigrationManager(migrations=[_migration("1")])
        manager.upgrade(dry_run=True)
        assert ("up", "1", True) in manager.context["_log"]

    def test_up_failure_raises(self):
        def up(ctx):
            raise RuntimeError("boom")

        manager = MigrationManager(migrations=[_migration("1", up=up)])
        with pytest.raises(MigrationFailureError):
            manager.upgrade()

    def test_rollback(self):
        log = []

        def down(ctx):
            log.append("down")

        manager = MigrationManager(migrations=[_migration("1", down=down), _migration("2", down=down)])
        manager.upgrade()
        reverted = manager.rollback(steps=1)
        assert reverted == [manager.get("2")]
        assert log == ["down"]
        assert manager.is_applied("2") is False
        assert manager.is_applied("1") is True

    def test_rollback_all_and_zero(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2")])
        manager.upgrade()
        assert [m.version for m in manager.rollback(steps=2)] == ["2", "1"]
        assert manager.rollback(steps=0) == []
        assert manager.rollback(steps=-1) == []

    def test_rollback_skips_unregistered(self):
        store = MemoryMigrationStore(applied=[AppliedMigration("ghost", "x")])
        manager = MigrationManager(store=store, migrations=[_migration("1")])
        assert manager.plan_rollback(1) == []

    def test_downgrade_to(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2"), _migration("3")])
        manager.upgrade()
        reverted = manager.downgrade_to("1")
        assert [m.version for m in reverted] == ["3", "2"]
        assert manager.is_applied("3") is False
        assert manager.is_applied("2") is False
        assert manager.is_applied("1") is True

    def test_downgrade_to_target_equal_applied(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2")])
        manager.upgrade()
        assert manager.downgrade_to("2") == []

    def test_downgrade_dry_run(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2")])
        manager.upgrade()
        reverted = manager.downgrade_to("1", dry_run=True)
        assert len(reverted) == 1
        assert manager.is_applied("2") is True

    def test_down_failure_raises(self):
        def down(ctx):
            raise RuntimeError("boom")

        manager = MigrationManager(migrations=[_migration("1", down=down)])
        manager.upgrade()
        with pytest.raises(MigrationFailureError):
            manager.rollback(1)

    def test_plan_and_pending(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2")])
        assert len(manager.plan()) == 2
        manager.upgrade()
        assert manager.plan() == []

    def test_plan_rollback_order(self):
        manager = MigrationManager(migrations=[_migration("1"), _migration("2"), _migration("3")])
        manager.upgrade()
        assert [m.version for m in manager.plan_rollback(2)] == ["3", "2"]

    def test_load_from_dir(self, tmp_path):
        os.makedirs(tmp_path / "migrations")
        (tmp_path / "migrations" / "0001_init.py").write_text("def upgrade(ctx):\n    ctx['ran'] = True\n")
        (tmp_path / "migrations" / "0002_add_table.py").write_text("def downgrade(ctx):\n    ctx['reverted'] = True\n")
        (tmp_path / "migrations" / "not_a_migration.py").write_text("x = 1\n")
        (tmp_path / "migrations" / "0003_no_fns.py").write_text("y = 2\n")

        manager = MigrationManager(migrations_dir=str(tmp_path / "migrations"))
        loaded = manager.load_from_dir()
        assert [m.version for m in loaded] == ["0001", "0002", "0003"]
        assert loaded[0].name == "init"

        manager.upgrade()
        assert manager.context["ran"] is True
        assert manager.is_applied("0002")
        manager.rollback(2)
        assert manager.context["reverted"] is True
        assert manager.is_applied("0002") is False

    def test_load_from_dir_missing(self):
        manager = MigrationManager(migrations_dir="/nonexistent")
        assert manager.load_from_dir() == []

    def test_migrate_alias(self):
        manager = MigrationManager(migrations=[_migration("1")])
        assert len(manager.migrate()) == 1

    def test_status(self):
        manager = MigrationManager(migrations=[_migration("1")])
        manager.upgrade()
        status = manager.status()
        assert status["applied"] == ["1"]
        assert status["pending"] == []
        assert status["total"] == 1
        assert status["driver"] == "memory"

    def test_sqlite_manager(self, tmp_path):
        config = MigrationConfig(driver="sqlite", database_path=str(tmp_path / "m.sqlite"))
        manager = MigrationManager(config=config, migrations=[_migration("1"), _migration("2")])
        manager.upgrade()
        assert manager.is_applied("1")
        manager.rollback(1)
        assert manager.is_applied("2") is False
        assert manager.is_applied("1") is True
        manager.store.close()

    def test_factory(self):
        manager = create_migration_manager(MigrationConfig(), migrations=[_migration("1")])
        assert isinstance(manager, MigrationManager)
        assert manager.get("1") is not None
