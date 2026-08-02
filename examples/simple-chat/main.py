"""Simple chat with AI Router — REST, SDK, and streaming.

Run from the repository root:

    PYTHONPATH=. python examples/simple-chat/main.py
"""

import asyncio
import os

import httpx

from app.models import ChatRequest, Message, MessageRole
from app.router import AIRouter

ROUTER_URL = os.getenv("AI_ROUTER_URL", "http://localhost:8000")
MODEL = os.getenv("AI_ROUTER_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("AI_ROUTER_API_KEY", "test-key")


async def rest_chat(question: str) -> str:
    """1) Plain REST call to the running AI Router gateway."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ROUTER_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": question}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def sdk_chat(question: str) -> None:
    """2) Direct SDK call — routing, retries, fallback and circuit breaking included."""
    router = AIRouter()
    await router.initialize()
    response = await router.chat(
        ChatRequest(
            model=MODEL,
            messages=[Message(role=MessageRole.USER, content=question)],
            max_tokens=512,
        )
    )
    print(f"model: {response.model}  id: {response.id}")
    print(f"usage: {response.usage}")
    print(response.choices[0].message.content)


async def sdk_stream(question: str) -> None:
    """3) Streaming — tokens arrive chunk by chunk."""
    router = AIRouter()
    await router.initialize()
    chunks = []
    async for chunk in router.stream_chat(
        ChatRequest(
            model=MODEL,
            messages=[Message(role=MessageRole.USER, content=question)],
            stream=True,
        )
    ):
        delta = chunk.choices[0].delta or {}
        text = delta.get("content", "")
        if text:
            print(text, end="", flush=True)
            chunks.append(text)
    print()
    print(f"streamed {len(''.join(chunks))} characters")


async def main() -> None:
    question = "Explain the difference between routing and load balancing in one sentence."
    answer = await rest_chat(question)
    print(f"REST -> {answer}\n")

    await sdk_chat(question)
    print()
    await sdk_stream(question)


if __name__ == "__main__":
    asyncio.run(main())
