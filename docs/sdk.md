# SDK

The `app` package is organized as importable subsystems so it can be used as a
library as well as a service.

## Installation

```bash
pip install -e .          # editable install from the repo
```

## Routing

```python
from app.router import AIRouter
from app.models import ChatRequest

router = AIRouter()
await router.initialize()

response = await router.chat(ChatRequest(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
))
print(response.model, response.choices[0].message.content)

await router.close()
```

The module also exposes a ready-to-use singleton: `from app.router import
router`. Embeddings are available via `router.embeddings(...)`.

## Costs

```python
from app.costs import TokenAccounting

accounting = TokenAccounting()
usage = accounting.record("openai", "gpt-4o", 1000, 500)
print(usage.estimated_cost)
print(accounting.get_summary())
```

## Release management

```python
from app.release import ReleaseManager, ReleaseConfig

manager = ReleaseManager(ReleaseConfig(history_file="history.json"))
version = manager.next_version("rc")
manager.create_release(str(version), ["feat: shipped v1"])
manager.write_changelog()
manager.save_history()
```

## Migrations

```python
from app.migrations import MigrationConfig, MigrationManager

manager = MigrationManager(
    MigrationConfig(driver="sqlite", database_path="app.db"),
    migrations_dir="config/migrations",
)
manager.load_from_dir()
manager.upgrade()          # or manager.upgrade(dry_run=True)
manager.rollback(1)        # revert the last migration
```

## Observability

```python
from app.observability import SliCollector, SloDefinition, AlertEngine, BurnRateAlertBuilder

collector = SliCollector()
collector.define(SloDefinition("api", target=99.9))
collector.record_good("api")
collector.record_bad("api")
collector.burn_rate("api")

engine = AlertEngine()
engine.add_rules(BurnRateAlertBuilder().build(SloDefinition("api")))
fired = engine.evaluate({"burn_rate_api": 2.5})
```

## Deployment pipeline

```python
from app.deploy import DeploymentPipeline

pipeline = DeploymentPipeline()
pipeline.gates.register("coverage", lambda: {"passed": True, "value": 98.0})
pipeline.smoke.register_probe("health", lambda: {"ok": True, "latency_ms": 5.0})
pipeline.rollback.register_deployer(lambda v: True)
pipeline.rollback.register_probe(lambda: {"ok": True, "version": "1.0.0-rc.1"})
pipeline.verify.register_probe(lambda: {"ok": True, "version": "1.0.0-rc.1", "latency_ms": 5.0})
pipeline.run()
```
