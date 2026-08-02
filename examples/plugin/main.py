"""Run a chat through the router with the request-logger plugin enabled.

Make sure the plugin is installed first (see plugin.py docstring):

    mkdir -p plugins/request-logger
    cp examples/plugin/plugin.py examples/plugin/manifest.yaml plugins/request-logger/
"""

import asyncio

from app.models import ChatRequest, Message, MessageRole
from app.router import AIRouter


async def main() -> None:
    router = AIRouter()
    await router.initialize()

    response = await router.chat(
        ChatRequest(
            model="gpt-4o-mini",
            messages=[
                Message(
                    role=MessageRole.USER,
                    content="Say hello in exactly three words.",
                )
            ],
            max_tokens=32,
        )
    )
    print("\nanswer:", response.choices[0].message.content)

    plugin = router.plugin_registry.get("request-logger")
    print("plugin loaded:", plugin is not None)


if __name__ == "__main__":
    asyncio.run(main())
