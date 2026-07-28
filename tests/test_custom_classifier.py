"""Tests for the custom classifier SDK."""

import pytest

from app.classifier import (
    BaseClassifier,
    ClassificationResult,
    ClassifierManager,
    TaskClassifier,
)
from app.models import TaskType


class TestClassifierBase:
    def test_classification_result_defaults(self):
        r = ClassificationResult(task=TaskType.CHAT)
        assert r.task == TaskType.CHAT
        assert r.confidence == 0.0
        assert r.matched_keywords == {}
        assert r.metadata == {}

    def test_classification_result_full(self):
        r = ClassificationResult(
            task=TaskType.CODING,
            confidence=0.95,
            matched_keywords={"coding": ["python"]},
            metadata={"source": "test"},
        )
        assert r.task == TaskType.CODING
        assert r.confidence == 0.95
        assert r.matched_keywords == {"coding": ["python"]}
        assert r.metadata == {"source": "test"}

    def test_base_classifier_raises_notimplemented(self):
        class InvalidClassifier(BaseClassifier):
            pass

        with pytest.raises(TypeError):
            InvalidClassifier()

    def test_concrete_classifier(self):
        class TestClassifier(BaseClassifier):
            name = "test"
            description = "Test classifier"

            def classify(self, prompt):
                return TaskType.CHAT

        c = TestClassifier()
        assert c.classify("hello") == TaskType.CHAT
        info = c.get_info()
        assert info["name"] == "test"
        assert info["description"] == "Test classifier"

    def test_classify_with_confidence_default(self):
        class TestClassifier(BaseClassifier):
            name = "test"

            def classify(self, prompt):
                return TaskType.CODING

        c = TestClassifier()
        result = c.classify_with_confidence("write code")
        assert result.task == TaskType.CODING
        assert result.confidence == 0.0


class TestClassifierManager:
    def test_init_with_default(self):
        mgr = ClassifierManager(TaskClassifier())
        assert mgr.active is not None
        assert mgr.classify("hello") == TaskType.CHAT

    def test_switch_classifier(self):
        class CustomClassifier(BaseClassifier):
            name = "custom"
            def classify(self, prompt):
                return TaskType.ANALYSIS

        mgr = ClassifierManager(TaskClassifier())
        mgr.set_classifier(CustomClassifier())
        assert mgr.active.name == "custom"
        assert mgr.classify("anything") == TaskType.ANALYSIS

    def test_discover_custom_classifiers(self):
        mgr = ClassifierManager(TaskClassifier())
        classifiers = mgr.discover_custom()
        assert "embedding" in classifiers
        assert issubclass(classifiers["embedding"], BaseClassifier)

    def test_get_info(self):
        mgr = ClassifierManager(TaskClassifier())
        info = mgr.get_info()
        assert "name" in info
        assert "active" in info
        assert "available" in info

    def test_forwarded_methods(self):
        mgr = ClassifierManager(TaskClassifier())
        mgr.add_keywords(TaskType.CODING, ["customkeyword"])
        assert "customkeyword" in mgr.get_rules()["coding"]

    def test_removed_keywords(self):
        mgr = ClassifierManager(TaskClassifier())
        mgr.remove_keywords(TaskType.CHAT, ["tell me"])
        assert "tell me" not in mgr.get_rules()["chat"]

    def test_default_task_override(self):
        mgr = ClassifierManager(TaskClassifier())
        mgr.set_default_task(TaskType.CODING)
        result = mgr.classify_with_confidence("")
        assert result.task == TaskType.CODING

    def test_classify_with_confidence(self):
        mgr = ClassifierManager(TaskClassifier())
        result = mgr.classify_with_confidence("write python code")
        assert result.task == TaskType.CODING
        assert result.confidence > 0
