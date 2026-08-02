# Plugins

Custom hooks inside the routing pipeline. The example plugin logs every
request before and after routing.

## Install

```bash
mkdir -p plugins/request-logger
cp examples/plugin/plugin.py examples/plugin/manifest.yaml plugins/request-logger/
```

Plugins are auto-discovered from `plugins/` (each subdirectory needs
`plugin.py` + `manifest.yaml`).

## Run

```bash
PYTHONPATH=. python examples/plugin/main.py
```

## Expected output

```
[plugin:request-logger] initialized
[plugin:request-logger] before_request: 32 chars
[plugin:request-logger] routing -> openai/gpt-4o-mini
[plugin:request-logger] after_response: 27 chars

answer: Hello! How can I help?
loaded plugins: ['request-logger']
```

See `docs/plugins.md` for the full hook reference and the plugin lifecycle.
