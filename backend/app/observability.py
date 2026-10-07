"""Purpose: Send agent traces to Langfuse without sending credentials.

Public API:
- looks_sensitive
- redact_value
- configure_observability
"""

import base64
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter

from app.config import Settings

SENSITIVE_KEYS = ("password", "secret", "token", "authorization", "api_key", "credential")


def looks_sensitive(key: str, value: object) -> bool:
    """Return whether a span attribute could carry a credential."""
    lowered = key.casefold()
    if any(part in lowered for part in SENSITIVE_KEYS):
        return True
    if isinstance(value, str) and ("bearer " in value.casefold() or value.startswith("$argon2")):
        return True
    return False


def redact_value(key: str, value: object) -> object:
    """Replace credential-like values and leave invoice data unchanged."""
    if looks_sensitive(key, value):
        return "[redacted]"
    return value


class RedactingSpanProcessor:
    """Scrub credential attributes before they reach the exporter."""

    def __init__(self, downstream: Any) -> None:
        """Wrap the processor that actually exports spans."""
        self._downstream = downstream

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        """Scrub attributes known at the start of a span."""
        if not _keep_span(span):
            return
        _scrub_span(span)
        self._downstream.on_start(span, parent_context)

    def _on_ending(self, span: Any) -> None:
        """Scrub credentials while the span is still mutable."""
        if not _keep_span(span):
            return
        try:
            _scrub_span(span)
        except Exception:
            return
        ending = getattr(self._downstream, "_on_ending", None)
        if ending is not None:
            ending(span)

    def on_end(self, span: ReadableSpan) -> None:
        """Forward the finished span after redaction."""
        if not _keep_span(span):
            return
        try:
            _scrub_span(span)
        except Exception:
            pass
        self._downstream.on_end(span)

    def shutdown(self) -> None:
        """Shut down the wrapped processor."""
        self._downstream.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the wrapped processor."""
        return self._downstream.force_flush(timeout_millis)


def configure_observability(settings: Settings) -> None:
    """Export agent traces to Langfuse when both keys are set."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import set_tracer_provider
    from pydantic_ai import Agent

    auth = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()
    host = settings.langfuse_host.rstrip("/")
    exporter: SpanExporter = OTLPSpanExporter(
        endpoint=f"{host}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}"},
    )
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(BatchSpanProcessor(exporter)))
    set_tracer_provider(provider)
    Agent.instrument_all()


def _keep_span(span: Any) -> bool:
    """Drop FastAPI request spans. Jev and model generations stay."""
    scope = getattr(span, "instrumentation_scope", None)
    scope_name = str(getattr(scope, "name", "") or "")
    if scope_name == "fastapi" or scope_name.startswith("opentelemetry.instrumentation.fastapi"):
        return False
    return True


def _scrub_span(span: Any) -> None:
    """Rewrite sensitive attributes on a span when the SDK allows it."""
    attributes = getattr(span, "attributes", None)
    if not attributes:
        return
    for key, value in list(attributes.items()):
        if looks_sensitive(str(key), value) and hasattr(span, "set_attribute"):
            span.set_attribute(key, "[redacted]")
        private = getattr(span, "_attributes", None)
        if private is not None and looks_sensitive(str(key), value):
            private[key] = "[redacted]"
