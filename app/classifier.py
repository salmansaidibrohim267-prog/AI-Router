"""Task classifier for routing prompts to appropriate models."""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models import TaskType


class ClassificationResult:
    """Result of task classification."""

    def __init__(
        self,
        task: TaskType,
        confidence: float = 0.0,
        matched_keywords: dict[str, list[str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.task = task
        self.confidence = confidence
        self.matched_keywords = matched_keywords or {}
        self.metadata = metadata or {}


class BaseClassifier(ABC):
    """Abstract base for all classifiers."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def classify(self, prompt: str) -> TaskType:
        ...

    def classify_with_confidence(self, prompt: str) -> ClassificationResult:
        task = self.classify(prompt)
        return ClassificationResult(task=task, confidence=0.0)

    def get_info(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


class ClassifierManager(BaseClassifier):
    """Classifier manager that delegates to configured classifier."""

    name = "manager"
    description = "Classifier manager that delegates to configured classifier"

    def __init__(self, default_classifier: BaseClassifier):
        self._active: BaseClassifier = default_classifier
        self._custom_dir = Path("classifier")

    @property
    def active(self) -> BaseClassifier:
        return self._active

    def set_classifier(self, classifier: BaseClassifier) -> None:
        self._active = classifier

    def classify(self, prompt: str) -> TaskType:
        return self._active.classify(prompt)

    def classify_with_confidence(self, prompt: str) -> ClassificationResult:
        return self._active.classify_with_confidence(prompt)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._active, name)

    def discover_custom(self) -> dict[str, type[BaseClassifier]]:
        classifiers: dict[str, type[BaseClassifier]] = {}
        if not self._custom_dir.is_dir():
            return classifiers

        for entry in sorted(self._custom_dir.iterdir()):
            if entry.suffix == ".py" and entry.name != "__init__.py":
                try:
                    module_name = f"_custom_classifier_{entry.stem}"
                    spec = importlib.util.spec_from_file_location(module_name, entry)
                    if not spec or not spec.loader:
                        continue

                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseClassifier)
                            and attr is not BaseClassifier
                        ):
                            classifier_name = getattr(attr, "name", entry.stem.lower())
                            classifiers[classifier_name] = attr
                except Exception:
                    import traceback
                    traceback.print_exc()

        return classifiers

    def get_info(self) -> dict[str, Any]:
        return {
            "name": self._active.name,
            "description": self._active.description,
            "active": self._active.name,
            "available": list(self.discover_custom().keys()),
        }


class TaskClassifier(BaseClassifier):
    """Keyword-based task classifier with configurable rules."""

    DEFAULT_RULES = {
        TaskType.CODING: [
            "code", "coding", "program", "function", "api", "fastapi", "docker",
            "bug", "error", "debug", "javascript", "typescript", "python", "rust",
            "go", "java", "c++", "sql", "database", "query", "script", "algorithm",
            "implementation", "refactor", "optimize", "performance", "memory",
            "async", "await", "thread", "concurrent", "parallel", "git", "github",
            "ci/cd", "pipeline", "deploy", "kubernetes", "k8s", "terraform",
            "ansible", "class", "interface", "module", "package", "library",
            "framework", "react", "vue", "angular", "nextjs", "node", "express",
        ],
        TaskType.ARCHITECTURE: [
            "architecture", "design", "system", "infrastructure", "scaling",
            "deployment", "server", "microservices", "monolith", "distributed",
            "load balancing", "caching", "message queue", "event driven",
            "service mesh", "api gateway", "database design", "schema", "orm",
            "capacity planning", "high availability", "fault tolerance",
            "disaster recovery", "backup", "monitoring", "observability",
            "logging", "tracing", "metrics", "alerting", "sla", "slo", "sli",
        ],
        TaskType.ANALYSIS: [
            "analyze", "analysis", "compare", "research", "explain", "evaluate",
            "review", "assess", "investigate", "study", "examine", "explore",
            "understand", "interpret", "summarize", "synthesize", "conclude",
            "recommend", "pros and cons", "trade-offs", "benchmark", "profile",
            "metrics", "kpi", "dashboard", "report", "insight", "pattern",
            "trend", "anomaly", "correlation", "causation", "hypothesis",
        ],
        TaskType.CHAT: [
            "chat", "talk", "discuss", "conversation", "question", "help",
            "how to", "what is", "why", "when", "where", "who", "tell me",
            "show me", "give me", "list", "examples", "ideas", "suggestions",
            "brainstorm", "creative", "write", "story", "poem", "joke",
        ],
    }

    def __init__(self, rules: dict[TaskType, list[str]] | None = None):
        self.rules = rules or self.DEFAULT_RULES.copy()
        self._default_task = TaskType.CHAT

    def classify(self, prompt: str) -> TaskType:
        result = self.classify_with_confidence(prompt)
        return result.task

    def classify_with_confidence(self, prompt: str) -> ClassificationResult:
        text = prompt.lower()
        scores: dict[TaskType, int] = {task: 0 for task in TaskType}
        matched: dict[str, list[str]] = {task.value: [] for task in TaskType}

        for task, keywords in self.rules.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    scores[task] += 1
                    matched[task.value].append(keyword)

        best_task = max(scores, key=scores.get)
        best_score = scores[best_task]
        total_matches = sum(scores.values())
        confidence = best_score / total_matches if total_matches > 0 else 0.0

        if best_score == 0:
            best_task = self._default_task
            confidence = 0.5

        return ClassificationResult(
            task=best_task,
            confidence=confidence,
            matched_keywords=matched,
        )

    def add_keywords(self, task: TaskType, keywords: list[str]) -> None:
        if task not in self.rules:
            self.rules[task] = []
        self.rules[task].extend(keywords)

    def remove_keywords(self, task: TaskType, keywords: list[str]) -> None:
        if task in self.rules:
            self.rules[task] = [k for k in self.rules[task] if k not in keywords]

    def set_default_task(self, task: TaskType) -> None:
        self._default_task = task

    def get_rules(self) -> dict[str, list[str]]:
        return {task.value: keywords for task, keywords in self.rules.items()}


# Global classifier instance (via ClassifierManager for pluggable support)
classifier = ClassifierManager(TaskClassifier())
