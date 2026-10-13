"""Purpose: Send agent traces to Langfuse without credentials or personal data.

Public API:
- looks_sensitive
- redact_value
- configure_observability
- conversation_pseudonym
- trace_ai_work
"""

import base64
import hashlib
import hmac
from contextlib import contextmanager
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry import trace
from opentelemetry.trace import Status

from app.chat.guardrails.pii import PiiVault
from app.chat.guardrails.redaction import redact_for_trace
from app.config import Settings

SENSITIVE_KEYS = ("password", "secret", "token", "authorization", "api_key", "credential")
_METADATA_KEYS = {
    "ledger.use_case", "ledger.environment", "ledger.outcome", "ledger.session",
    "ledger.requests", "ledger.tools", "ledger.input_tokens", "ledger.output_tokens", "ledger.cost_available",
    "ledger.prompt_version.chat", "ledger.prompt_version.summary", "ledger.prompt_version.guardrail",
    "gen_ai.request.model", "gen_ai.response.model", "gen_ai.system", "gen_ai.provider.name",
    "gen_ai.tool.name", "tool_name", "agent_name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens", "gen_ai.usage.cache_read_input_tokens", "gen_ai.usage.cache_write_input_tokens",
}


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
        try:
            _scrub_span(span)
        except Exception:
            return
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
            from opentelemetry.sdk.resources import Resource
            vault = PiiVault()
            attributes = {key: _scrub_attribute(key, value, vault) for key, value in (span.attributes or {}).items()
                          if key in _METADATA_KEYS}
            safe = ReadableSpan(
                name=span.name if span.name in {"chat", "summary", "guardrail"} else "ai_operation",
                context=span.context, parent=span.parent, kind=span.kind,
                resource=Resource({"service.name": "ledger"}), attributes=attributes,
                events=(), links=(), status=Status(span.status.status_code),
                start_time=span.start_time, end_time=span.end_time,
                instrumentation_scope=span.instrumentation_scope,
            )
        except Exception:
            return
        self._downstream.on_end(safe)

    def shutdown(self) -> None:
        """Shut down the wrapped processor."""
        self._downstream.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the wrapped processor."""
        return self._downstream.force_flush(timeout_millis)


def configure_observability(settings: Settings) -> TracerProvider | None:
    """Export agent traces to Langfuse when both keys are set."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
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
    provider = TracerProvider(sampler=ParentBased(TraceIdRatioBased(settings.trace_sample_ratio)))
    provider.add_span_processor(RedactingSpanProcessor(BatchSpanProcessor(exporter)))
    set_tracer_provider(provider)
    from pydantic_ai.models.instrumented import InstrumentationSettings
    Agent.instrument_all(InstrumentationSettings(include_content=False))
    return provider


def conversation_pseudonym(conversation_id: str, secret: str) -> str:
    """HMAC the conversation identifier so export cannot expose the original value."""
    return hmac.new(secret.encode(), conversation_id.encode(), hashlib.sha256).hexdigest()[:24]


@contextmanager
def trace_ai_work(use_case: str, settings: Settings, pseudonym: str, versions: dict[str, str]):
    """Trace only AI workflow metadata, never application request or invoice content."""
    with trace.get_tracer("ledger.ai").start_as_current_span(use_case, record_exception=False,
                                                          set_status_on_exception=False) as span:
        span.set_attribute("ledger.use_case", use_case)
        span.set_attribute("ledger.session", pseudonym)
        span.set_attribute("ledger.environment", settings.environment)
        for name, value in versions.items():
            span.set_attribute(f"ledger.prompt_version.{name}", value)
        span.set_attribute("ledger.cost_available", False)
        yield span


def _keep_span(span: Any) -> bool:
    """Drop FastAPI request spans. Jev and model generations stay."""
    scope = getattr(span, "instrumentation_scope", None)
    scope_name = str(getattr(scope, "name", "") or "")
    if scope_name == "fastapi" or scope_name.startswith("opentelemetry.instrumentation.fastapi"):
        return False
    return not scope_name or scope_name in {"ledger.ai", "pydantic-ai", "pydantic_ai"}


def _scrub_span(span: Any) -> None:
    """Rewrite sensitive attributes on a span when the SDK allows it."""
    attributes = getattr(span, "attributes", None)
    attributes = attributes or {}
    vault = PiiVault()
    for key, value in list(attributes.items()):
        cleaned = _scrub_attribute(str(key), value, vault)
        if cleaned == value:
            continue
        if hasattr(span, "set_attribute"):
            span.set_attribute(key, cleaned)
        private = getattr(span, "_attributes", None)
        if private is not None:
            private[key] = cleaned


def _scrub_attribute(key: str, value: object, vault: PiiVault) -> object:
    """Hide a credential or personal data inside one span attribute."""
    numeric_metadata = key.startswith("gen_ai.usage.") or key in {
        "ledger.requests", "ledger.tools", "ledger.input_tokens", "ledger.output_tokens", "ledger.cost_available",
    }
    if numeric_metadata and isinstance(value, (int, float, bool)):
        return value
    if looks_sensitive(key, value):
        return "[redacted]"
    if key.startswith(("ledger.prompt_version.", "ledger.session")):
        return value if isinstance(value, str) and all(char in "0123456789abcdef" for char in value) else "[redacted]"
    if key in {"ledger.use_case", "ledger.environment", "ledger.outcome", "gen_ai.request.model", "gen_ai.response.model", "gen_ai.system", "gen_ai.provider.name", "gen_ai.tool.name", "tool_name", "agent_name"}:
        return _scrub_content(value, vault)
    return "[redacted]"


def _scrub_content(value: object, vault: PiiVault) -> object:
    """Replace personal data in a string attribute or a sequence of them."""
    if isinstance(value, str):
        return redact_for_trace(value, vault)
    if isinstance(value, tuple):
        return tuple(_scrub_content(item, vault) for item in value)
    if isinstance(value, list):
        return [_scrub_content(item, vault) for item in value]
    return value
