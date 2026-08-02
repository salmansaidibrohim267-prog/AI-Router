# Providers

Direct provider clients. Useful for 1:1 comparisons, offline testing, or
bypassing the router entirely (e.g. local Ollama).

## Run

```bash
# from the repository root
PYTHONPATH=. python examples/providers/main.py ollama
PYTHONPATH=. python examples/providers/main.py openai
PYTHONPATH=. python examples/providers/main.py anthropic
PYTHONPATH=. python examples/providers/main.py google
```

For Ollama, start the server first: `ollama serve && ollama pull llama3.2`.

## Expected output

```
provider: OpenAI  model: gpt-4o-mini
An AI gateway routes requests to the best available model provider.
```
