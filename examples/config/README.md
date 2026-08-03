# Example Configurations

Copy-paste configuration templates for AI Router.

| File | Purpose |
| --- | --- |
| `providers.yaml.example` | Example provider registry (openrouter, ollama, openai, anthropic, google) |

## Usage

```bash
cp examples/config/providers.yaml.example config/providers.yaml
# set at least one provider key in .env or the shell, then:
curl -X POST http://localhost:8000/reload-config -H "Authorization: Bearer test-key"
```

Field names match the repository's `config/providers.yaml` exactly —
compare with the real file before overriding it.
