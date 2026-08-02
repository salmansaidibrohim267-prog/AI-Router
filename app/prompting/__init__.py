from app.prompting.builder import PromptContextBuilder
from app.prompting.config import PromptingConfig
from app.prompting.models import (
    ContextItem,
    ConversationMessage,
    MemoryEntry,
    OutputFormat,
    PromptBuildRequest,
    PromptBuildResult,
    PromptMetrics,
    ToolDefinition,
)


def create_prompt_context_builder(
    config: PromptingConfig | None = None,
    **kwargs,
) -> PromptContextBuilder:
    if config is None:
        config = PromptingConfig.from_env()
    return PromptContextBuilder(config=config, **kwargs)


__all__ = [
    "PromptingConfig",
    "PromptContextBuilder",
    "PromptBuildRequest",
    "PromptBuildResult",
    "PromptMetrics",
    "ContextItem",
    "ConversationMessage",
    "MemoryEntry",
    "ToolDefinition",
    "OutputFormat",
    "create_prompt_context_builder",
]
