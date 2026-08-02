from __future__ import annotations


class PromptingError(Exception):
    pass


class PromptTemplateError(PromptingError):
    def __init__(self, msg: str = "Template error"):
        super().__init__(msg)


class PromptValidationError(PromptingError):
    def __init__(self, msg: str = "Prompt validation failed"):
        super().__init__(msg)


class PromptBudgetError(PromptingError):
    def __init__(self, msg: str = "Token budget error"):
        super().__init__(msg)


class PromptFormattingError(PromptingError):
    def __init__(self, msg: str = "Prompt formatting failed"):
        super().__init__(msg)


class PromptOptimizerError(PromptingError):
    def __init__(self, msg: str = "Context optimization failed"):
        super().__init__(msg)


class PromptBuildError(PromptingError):
    def __init__(self, msg: str = "Prompt build failed"):
        super().__init__(msg)
