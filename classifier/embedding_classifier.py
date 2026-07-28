from app.classifier import BaseClassifier, ClassificationResult
from app.models import TaskType


class EmbeddingClassifier(BaseClassifier):
    name = "embedding"
    description = "Embedding-based task classifier (stub)"

    def classify(self, prompt: str) -> TaskType:
        return TaskType.CHAT

    def classify_with_confidence(self, prompt: str) -> ClassificationResult:
        return ClassificationResult(task=TaskType.CHAT, confidence=0.5)
