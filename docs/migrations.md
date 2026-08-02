# Migrations

Schema and data migrations are managed by `app/migrations`. Migrations are
versioned, reversible, and tracked in a `schema_versions` table.

## Writing a migration

Create `config/migrations/<version>_<name>.py` with `upgrade(ctx)` and
`downgrade(ctx)`:

```python
def upgrade(ctx):
    ctx["db"].execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")

def downgrade(ctx):
    ctx["db"].execute("DROP TABLE users")
```

Numeric versions (zero-padded) order deterministically: `0001` < `0002` <
`0003`.

## Running

```python
from app.migrations import MigrationConfig, MigrationManager

manager = MigrationManager(
    MigrationConfig(driver="sqlite", database_path="app.db"),
    migrations_dir="config/migrations",
)
manager.load_from_dir()

manager.upgrade()                 # apply pending
manager.upgrade(dry_run=True)     # preview without applying
manager.rollback(1)               # revert the last migration
manager.downgrade_to("0001")      # revert everything above a target
manager.status()                  # applied / pending / total
```

Environment configuration (`MIG_*`):

| Variable | Default |
| --- | --- |
| `MIG_DRIVER` | `memory` (`memory` or `sqlite`) |
| `MIG_DATABASE_PATH` | `:memory:` (sqlite) |
| `MIG_SCHEMA_TABLE` | `schema_versions` |
| `MIG_MIGRATIONS_DIR` | `config/migrations` |
| `MIG_AUTO_MIGRATE` | `false` |
| `MIG_LOCK_TIMEOUT_SECONDS` | `30` |

## Safety

- A lock (`BEGIN IMMEDIATE` on SQLite, advisory in-memory) prevents concurrent
  migrators.
- Failed steps raise `MigrationFailureError` and stop the run; records are
  only written after the step succeeds.
- Duplicate versions raise `MigrationVersionError` at registration.
- Rollback skips versions recorded in the store but unknown to code.

## CI

`test.yml` dry-runs migrations against SQLite on every push.
