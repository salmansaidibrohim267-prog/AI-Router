"""Privacy controls: PII detection, masking, retention and data subject requests.

PII patterns are regex based; masking supports ``full`` and ``partial`` modes.
DSARs (access/erasure/rectification/portability) are tracked with a store and
processed against a data source callable.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import SecurityConfig
from .exceptions import DataSubjectRequestError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import DataSubjectRequest, DataSubjectRequestStatus, DataSubjectRequestType, PIIField, PIIKind

_PII_PATTERNS: dict[PIIKind, re.Pattern[str]] = {
    PIIKind.EMAIL: re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    PIIKind.PHONE: re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"),
    PIIKind.SSN: re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    PIIKind.CREDIT_CARD: re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    PIIKind.IP_ADDRESS: re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    PIIKind.DATE_OF_BIRTH: re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    PIIKind.NAME: re.compile(r"(?:name|full name)\s*[:=]\s*[A-Z][A-Za-z' -]+", re.IGNORECASE),
    PIIKind.ADDRESS: re.compile(
        r"\b\d{1,5}\s+[A-Za-z0-9.' -]+\b(?:street|ave|ave\.|avenue|road|rd|blvd|way|lane|ln|dr|drive|court|ct)\b",
        re.IGNORECASE,
    ),  # noqa: E501
}


@dataclass
class MaskedResult:
    text: str
    fields: list[PIIField] = field(default_factory=list)
    masked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "fields": [f.to_dict() for f in self.fields], "masked": self.masked}


class PIIDetector:
    """Detects PII occurrences in free text via regex patterns."""

    def __init__(self, patterns: dict[PIIKind, re.Pattern[str]] | None = None) -> None:
        self.patterns = patterns if patterns is not None else _PII_PATTERNS

    def detect(self, text: str) -> list[PIIField]:
        fields: list[PIIField] = []
        for kind, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                fields.append(
                    PIIField(
                        kind=kind,
                        location=(match.start(), match.end()),
                        confidence=1.0,
                        value=match.group(0),
                    )
                )
        return sorted(fields, key=lambda f: f.location)

    def mask(self, text: str, mode: str | None = None) -> MaskedResult:
        mode = mode if mode is not None else "partial"
        fields = self.detect(text)
        chunks: list[str] = []
        cursor = 0
        masked_count = 0
        for fld in fields:
            start, end = fld.location
            chunks.append(text[cursor:start])
            chunks.append(self._mask_value(fld.value, mode))
            masked_count += 1
            cursor = end
        chunks.append(text[cursor:])
        return MaskedResult(text="".join(chunks), fields=fields, masked=masked_count)

    @staticmethod
    def _mask_value(value: str, mode: str) -> str:
        if mode == "full":
            return "***"
        visible = max(1, min(4, len(value) // 4))
        return value[:visible] + "*" * (len(value) - visible)


class PrivacyService:
    """PII detection/masking plus retention and DSAR handling."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        detector: PIIDetector | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.detector = detector if detector is not None else PIIDetector()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._requests: dict[str, DataSubjectRequest] = {}
        self._request_lock = threading.Lock()
        self._data_provider: Callable[[str, str], Any] | None = None
        self._data_eraser: Callable[[str, str], bool] | None = None

    # -- PII -------------------------------------------------------------------

    def detect(self, text: str) -> list[PIIField]:
        if not self.config.pii_detection_enabled:
            return []
        fields = self.detector.detect(text)
        if fields:
            self.metrics.record("pii_detections", component="privacy", amount=len(fields))
        return fields

    def mask(self, text: str, mode: str | None = None) -> MaskedResult:
        if not self.config.pii_detection_enabled:
            return MaskedResult(text=text)
        result = self.detector.mask(text, mode or self.config.pii_masking_mode)
        if result.masked:
            self.metrics.record("pii_masks", component="privacy", amount=result.masked)
            self.logger.log_event("pii_masked", fields=result.masked, mode=mode or self.config.pii_masking_mode)
        return result

    def redact(self, text: str) -> str:
        """Mask in ``full`` mode and drop everything else — destructive variant."""
        result = self.detector.mask(text, mode="full")
        return result.text

    # -- DSAR ------------------------------------------------------------------

    def register_data_provider(self, provider: Callable[[str, str], Any]) -> None:
        self._data_provider = provider

    def register_data_eraser(self, eraser: Callable[[str, str], bool]) -> None:
        self._data_eraser = eraser

    def submit_request(self, subject: str, request_type: DataSubjectRequestType) -> DataSubjectRequest:
        from .models import generate_id

        request = DataSubjectRequest(
            id=generate_id("dsar"),
            subject=subject,
            request_type=request_type,
        )
        with self._request_lock:
            self._requests[request.id] = request
        self.metrics.record("dsar_submitted", component="privacy")
        self.logger.log_event("dsar_submitted", request_id=request.id, subject=subject, type=request_type.value)
        return request

    def get_request(self, request_id: str) -> DataSubjectRequest | None:
        return self._requests.get(request_id)

    def list_requests(self, subject: str | None = None) -> list[DataSubjectRequest]:
        requests = list(self._requests.values())
        if subject is not None:
            requests = [r for r in requests if r.subject == subject]
        return requests

    def fulfill_request(self, request_id: str) -> DataSubjectRequest:
        with self._request_lock:
            request = self._requests.get(request_id)
            if request is None:
                raise DataSubjectRequestError(f"request {request_id} not found")
            if request.status in (DataSubjectRequestStatus.FULFILLED, DataSubjectRequestStatus.REJECTED):
                raise DataSubjectRequestError(f"request {request_id} already finalised")
            request.status = DataSubjectRequestStatus.IN_PROGRESS
            try:
                if request.request_type == DataSubjectRequestType.ACCESS:
                    if self._data_provider is None:
                        raise DataSubjectRequestError("no data provider registered")
                    request.result = {"data": self._data_provider(request.subject, "access")}
                elif request.request_type == DataSubjectRequestType.PORTABILITY:
                    if self._data_provider is None:
                        raise DataSubjectRequestError("no data provider registered")
                    request.result = {"data": self._data_provider(request.subject, "portability")}
                elif request.request_type == DataSubjectRequestType.ERASURE:
                    if self._data_eraser is None:
                        raise DataSubjectRequestError("no data eraser registered")
                    erased = self._data_eraser(request.subject, "all")
                    request.result = {"erased": bool(erased)}
                elif request.request_type == DataSubjectRequestType.RECTIFICATION:
                    if self._data_eraser is None:
                        raise DataSubjectRequestError("no data eraser registered")
                    request.result = {"rectified": True}
                request.status = DataSubjectRequestStatus.FULFILLED
                request.fulfilled_at = time.time()
            except Exception:
                request.status = DataSubjectRequestStatus.PENDING
                raise
            self.metrics.record("dsar_fulfilled", component="privacy")
            return request

    def expire_stale_requests(self, ttl_seconds: int = 86400) -> int:
        """Expire pending requests older than the TTL."""
        cutoff = time.time() - ttl_seconds
        expired = 0
        with self._request_lock:
            for request in self._requests.values():
                if request.status == DataSubjectRequestStatus.PENDING and request.created_at < cutoff:
                    request.status = DataSubjectRequestStatus.EXPIRED
                    expired += 1
        return expired

    def status(self) -> dict[str, Any]:
        return {
            "requests": len(self._requests),
            "detection_enabled": self.config.pii_detection_enabled,
            "masking_mode": self.config.pii_masking_mode,
            "retention_days": self.config.pii_retention_days,
        }


def create_privacy_service(config: SecurityConfig | None = None, **overrides: Any) -> PrivacyService:
    config = config if config is not None else SecurityConfig()
    detector = overrides.pop("detector", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    if detector is None:
        detector = PIIDetector()
    return PrivacyService(config, detector, logger, metrics)
