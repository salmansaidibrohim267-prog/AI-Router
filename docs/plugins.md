# Plugins

AI Router supports plugins for custom providers, tools and routing policies.

## Provider plugins

Drop a module into `providers/` implementing the provider interface and
register it in `config/providers.yaml`. The router discovers providers at
startup and includes them in health checks and routing.

## Tool plugins (builtin tools)

Builtin tools live in `app/tools/builtins/` and are registered through the
tool registry (`app/tools/registry.py`). Each tool:

- implements the `Tool` interface (`name`, `description`, `execute`),
- declares a permission level, and
- is validated by `app/tools/permission.py` before execution.

Examples: `calculator_tool.py`, `filesystem_tool.py`, `http_tool.py`,
`search_tool.py`.

## Benchmarks

Benchmark suites are plugins in their own right: implement the `Suite`
interface (a `run(target)` returning `SuiteResult`) and register it with
`SuiteRunner`:

```python
from benchmarks.suites import SuiteRunner, SuiteResult

class CustomSuite:
    name = "custom"

    def run(self, target):
        target()
        return SuiteResult(name="custom", metrics={"ok": 1.0})

runner = SuiteRunner(target=lambda: None)
runner.register("custom", CustomSuite())
report = runner.run(["custom"])
```

## Publisher plugins

Extend `app.release.publishing.Publisher` and register a factory in
`PublisherRegistry` to push releases to new channels:

```python
from app.release import Publisher, PublisherRegistry

class SlackPublisher(Publisher):
    name = "slack"

    def publish(self, version, artifact_paths, notes=""):
        return {"publisher": self.name, "channel": "releases"}

registry = PublisherRegistry()
registry.register("slack", lambda config, **kw: SlackPublisher(config))
```
