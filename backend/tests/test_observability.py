"""Purpose: Tests for credential redaction before traces leave the process.

Public API:
- test_span_processor_scrubs_before_export
- test_fastapi_spans_are_not_exported
- test_redact_value_hides_secrets_and_keeps_invoice_amounts
- test_real_spans_drop_content_events_and_sensitive_status
"""

from app.observability import RedactingSpanProcessor, looks_sensitive, redact_value
from app.observability import conversation_pseudonym


def test_span_processor_scrubs_before_export() -> None:
    """Ending a span redacts credentials and still notifies the exporter."""
    class FakeSpan:
        """Minimal span with mutable attributes."""

        def __init__(self) -> None:
            """Store one secret and one invoice amount."""
            self.attributes = {"authorization": "Bearer secret", "total": 55}
            self._attributes = dict(self.attributes)

        def set_attribute(self, key: str, value: object) -> None:
            """Update both attribute views."""
            self.attributes[key] = value
            self._attributes[key] = value

    class Downstream:
        """Record that the span was forwarded."""

        def __init__(self) -> None:
            """Start with no forwarded span."""
            self.ended = False

        def _on_ending(self, span: FakeSpan) -> None:
            """Mark the span as forwarded."""
            self.ended = span.attributes["authorization"] == "[redacted]"

        def on_end(self, span: FakeSpan) -> None:
            """Ignore the later export hook in this test."""

        def on_start(self, span: FakeSpan, parent_context: object = None) -> None:
            """Ignore span start."""

        def shutdown(self) -> None:
            """Ignore shutdown."""

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            """Report a successful flush."""
            return True

    downstream = Downstream()
    processor = RedactingSpanProcessor(downstream)
    processor._on_ending(FakeSpan())
    assert downstream.ended is True


def test_fastapi_spans_are_not_exported() -> None:
    """HTTP spans from FastAPI never reach the exporter. A generation span does."""

    class Scope:
        """Name of the library that created a span."""

        def __init__(self, name: str) -> None:
            """Store the instrumentation scope name."""
            self.name = name

    class FakeSpan:
        """Minimal span with a scope and mutable attributes."""

        def __init__(self, scope_name: str) -> None:
            """Store the scope and one secret attribute."""
            self.instrumentation_scope = Scope(scope_name)
            self.attributes = {"authorization": "Bearer secret"}
            self._attributes = dict(self.attributes)

        def set_attribute(self, key: str, value: object) -> None:
            """Update both attribute views."""
            self.attributes[key] = value
            self._attributes[key] = value

    class Downstream:
        """Count spans that were forwarded."""

        def __init__(self) -> None:
            """Start with no forwarded spans."""
            self.ended: list[str] = []

        def _on_ending(self, span: FakeSpan) -> None:
            """Record a forwarded span."""
            self.ended.append(span.instrumentation_scope.name)

        def on_end(self, span: FakeSpan) -> None:
            """Ignore the later export hook in this test."""

        def on_start(self, span: FakeSpan, parent_context: object = None) -> None:
            """Ignore span start."""

        def shutdown(self) -> None:
            """Ignore shutdown."""

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            """Report a successful flush."""
            return True

    downstream = Downstream()
    processor = RedactingSpanProcessor(downstream)
    processor._on_ending(FakeSpan("fastapi"))
    processor.on_end(FakeSpan("opentelemetry.instrumentation.fastapi"))
    processor._on_ending(FakeSpan("pydantic-ai"))
    assert downstream.ended == ["pydantic-ai"]


def test_redact_value_hides_secrets_and_keeps_invoice_amounts() -> None:
    """Invoice amounts stay visible, and tokens, passwords, and argon2 hashes do not."""
    assert redact_value("total", 55) == 55
    assert redact_value("contact_name", "Bob's Construction") == "Bob's Construction"
    assert redact_value("authorization", "Bearer token-123") == "[redacted]"
    assert redact_value("app_password_hash", "$argon2id$v=19$secret") == "[redacted]"
    assert looks_sensitive("note", "Bearer abc") is True
    assert looks_sensitive("invoice_number", "INV-1") is False


def test_real_spans_drop_content_events_and_sensitive_status() -> None:
    """SDK spans export only useful metadata, without prompt bodies or exception diagnostics."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import Status, StatusCode

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    with provider.get_tracer("pydantic-ai").start_as_current_span("model") as span:
        span.set_attribute("metadata.customer", "private@example.com")
        span.set_attribute("customer_phone", 123456789)
        span.set_attribute("gen_ai.input.messages", "private@example.com and sk-private")
        span.set_attribute("gen_ai.usage.input_tokens", 20)
        span.set_attribute("gen_ai.request.model", "gpt-4.1-mini")
        span.set_attribute("ledger.session", conversation_pseudonym("private@example.com", "secret"))
        span.add_event("exception", {"exception.message": "private@example.com"})
        span.set_status(Status(StatusCode.ERROR, "private@example.com provider-secret"))
    exported = exporter.get_finished_spans()
    assert len(exported) == 1
    assert "private@example.com" not in str(exported[0].attributes)
    assert "customer_phone" not in exported[0].attributes
    assert exported[0].attributes["gen_ai.usage.input_tokens"] == 20
    assert not exported[0].events
    assert exported[0].status.description is None
    provider.shutdown()
