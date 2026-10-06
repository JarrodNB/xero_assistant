"""Purpose: Tests for credential redaction before traces leave the process.

Public API:
- test_span_processor_scrubs_before_export
- test_redact_value_hides_secrets_and_keeps_invoice_amounts
"""

from app.observability import RedactingSpanProcessor, looks_sensitive, redact_value


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


def test_redact_value_hides_secrets_and_keeps_invoice_amounts() -> None:
    """Invoice amounts stay visible, and tokens, passwords, and argon2 hashes do not."""
    assert redact_value("total", 55) == 55
    assert redact_value("contact_name", "Bob's Construction") == "Bob's Construction"
    assert redact_value("authorization", "Bearer token-123") == "[redacted]"
    assert redact_value("app_password_hash", "$argon2id$v=19$secret") == "[redacted]"
    assert looks_sensitive("note", "Bearer abc") is True
    assert looks_sensitive("invoice_number", "INV-1") is False
