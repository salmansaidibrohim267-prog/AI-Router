import pytest
from app.classifier import TaskClassifier
from app.models import TaskType


class TestClassifier:
    def setup_method(self):
        self.classifier = TaskClassifier()

    def test_classify_coding(self):
        prompts = [
            "implement a python function to sort array",
            "fix this bug in javascript code",
            "implement binary search algorithm in python",
            "refactor this class to use async await pattern",
        ]
        for prompt in prompts:
            result = self.classifier.classify(prompt)
            assert result == TaskType.CODING, f"Expected CODING for: {prompt}"

    def test_classify_chat(self):
        prompts = [
            "hello how are you today",
            "tell me a story about dragons",
            "what is the meaning of life",
            "write a poem about nature",
        ]
        for prompt in prompts:
            result = self.classifier.classify(prompt)
            assert result == TaskType.CHAT, f"Expected CHAT for: {prompt}"

    def test_classify_architecture(self):
        prompts = [
            "design a microservices architecture with load balancing",
            "high availability fault tolerance database design",
            "monitoring and observability setup for kubernetes",
        ]
        for prompt in prompts:
            result = self.classifier.classify(prompt)
            assert result == TaskType.ARCHITECTURE, f"Expected ARCHITECTURE for: {prompt}"

    def test_classify_analysis(self):
        prompts = [
            "compare pros and cons of each approach",
            "evaluate trade-offs between different solutions",
            "summarize the findings from the research study",
        ]
        for prompt in prompts:
            result = self.classifier.classify(prompt)
            assert result == TaskType.ANALYSIS, f"Expected ANALYSIS for: {prompt}"

    def test_classify_with_confidence(self):
        result = self.classifier.classify_with_confidence("implement a function to sort array in python")
        assert result.task == TaskType.CODING
        assert result.confidence > 0

    def test_default_to_chat(self):
        result = self.classifier.classify("xyzzy magic unknown words")
        assert result == TaskType.CHAT

    def test_add_keywords(self):
        self.classifier.add_keywords(TaskType.CODING, ["customkeyword"])
        result = self.classifier.classify("customkeyword test")
        assert result == TaskType.CODING

    def test_remove_keywords(self):
        self.classifier.remove_keywords(TaskType.CHAT, ["tell me", "tell"])
        result = self.classifier.classify_with_confidence("tell me a story")
        assert "tell me" not in result.matched_keywords.get("chat", [])

    def test_set_default_task(self):
        self.classifier.set_default_task(TaskType.CODING)
        result = self.classifier.classify("nothing matches here at all")
        assert result == TaskType.CODING

    def test_get_rules(self):
        rules = self.classifier.get_rules()
        assert TaskType.CHAT.value in rules
        assert TaskType.CODING.value in rules
        assert len(rules[TaskType.CHAT.value]) > 0
