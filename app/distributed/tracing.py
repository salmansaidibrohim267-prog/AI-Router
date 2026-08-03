from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

TRACER: Any = None
TRACER_PROVIDER: Any = None

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    trace = None


def init_tracing(
    service_name: str = "ai-router",
    exporter_endpoint: str = "",
    enabled: bool = True,
) -> None:
    global TRACER, TRACER_PROVIDER

    if not enabled or not HAS_OTEL:
        logger.info("OpenTelemetry disabled")
        return

    try:
        endpoint = exporter_endpoint or os.environ.get(
            "OTEL_EXPORTER_ENDPOINT",
            "http://localhost:4318/v1/traces",
        )
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        TRACER_PROVIDER = provider
        TRACER = trace.get_tracer(service_name)
        logger.info(f"OpenTelemetry initialized: {endpoint}")
    except Exception as e:
        logger.warning(f"OpenTelemetry init failed: {e}")


def get_tracer() -> Any:
    global TRACER
    if TRACER is None and HAS_OTEL:
        TRACER = trace.get_tracer("ai-router")
    return TRACER


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as span:
        if attributes:
            span.set_attributes(attributes)
        yield span


def set_span_attribute(key: str, value: Any) -> None:
    if HAS_OTEL:
        span = trace.get_current_span()
        if span:
            span.set_attribute(key, str(value))


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    if HAS_OTEL:
        span = trace.get_current_span()
        if span:
            span.add_event(name, attributes or {})
