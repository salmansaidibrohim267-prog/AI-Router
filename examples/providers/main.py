"""Direct provider clients — Ollama, OpenAI, Anthropic, Google.

Bypasses routing and talks to a single provider. Use this when you want to
compare providers 1:1, or when routing is not needed (e.g. local Ollama).

Run from the repository root:

    PYTHONPATH=. python examples/providers/main.py [ollama|openai|anthropic|google]
"""

import asyncio
import os
import sys

from app.models import ChatRequest, Message, MessageRole
from app.providers.anthropic import AnthropicProvider
from app.providers.google import GoogleProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider

QUESTION = "Explain what an AI gateway is in one sentence."

PROVIDERS = {
    "ollama": lambda: OllamaProvider(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        timeout=120.0,
    ),
    "openai": lambda: OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY")),
    "anthropic": lambda: AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY")),
    "google": lambda: GoogleProvider(api_key=os.getenv("GOOGLE_API_KEY")),
}

MODELS = {
    "ollama": os.getenv("OLLAMA_MODEL", "llama3.2"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
    "google": os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
}


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "ollama"
    if name not in PROVIDERS:
        print(f"usage: python main.py [{'|'.join(PROVIDERS)}]")
        sys.exit(1)

    provider = PROVIDERS[name]()
    response = await provider.chat(
        ChatRequest(
            model=MODELS[name],
            messages=[Message(role=MessageRole.USER, content=QUESTION)],
            max_tokens=128,
        )
    )
    print(f"provider: {provider.display_name}  model: {response.model}")
    print(response.choices[0].message.content)


if __name__ == "__main__":
    asyncio.run(main())
