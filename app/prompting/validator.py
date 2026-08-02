from __future__ import annotations

from app.prompting.config import PromptingConfig
from app.prompting.exceptions import PromptValidationError
from app.prompting.models import PromptBuildResult


class PromptValidator:
    def __init__(self, config: PromptingConfig | None = None):
        self._config = config or PromptingConfig()

    def validate(self, result: PromptBuildResult) -> list[str]:
        warnings: list[str] = []
        if not result.text.strip():
            warnings.append("Prompt text is empty")
        if result.truncated:
            warnings.append("Prompt was truncated to fit token budget")
        if result.sections and "user" not in result.sections and "user_query" not in result.sections:
            warnings.append("No user query section present")
        if not result.sections:
            warnings.append("Prompt has no sections")
        return warnings

    def validate_request(
        self,
        user_query: str = "",
        template: str = "",
    ) -> None:
        if not template.strip():
            raise PromptValidationError("Template must not be empty")
        if not user_query.strip():
            raise PromptValidationError("User query must not be empty")
