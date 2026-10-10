"""Purpose: Swap personal data for numbered placeholders and restore it on the way out.

Public API:
- OutboundRestorer
- PiiVault
- current_vault
- rewrite_run_input
"""

import json
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

ENTITY_LABELS = {
    "EMAIL_ADDRESS": "email",
    "PHONE_NUMBER": "phone",
    "PERSON": "person",
    "LOCATION": "location",
    "CREDIT_CARD": "credit_card",
    "IBAN_CODE": "iban",
    "CRYPTO": "crypto",
    "IP_ADDRESS": "ip",
    "US_SSN": "ssn",
    "US_BANK_NUMBER": "bank_account",
    "US_DRIVER_LICENSE": "driver_license",
    "US_ITIN": "itin",
    "US_PASSPORT": "passport",
    "MEDICAL_LICENSE": "medical_license",
    "AU_TFN": "tfn",
    "AU_ABN": "abn",
    "AU_ACN": "acn",
    "AU_MEDICARE": "medicare",
}

_PLACEHOLDER = re.compile(r"\[redacted_[a-z0-9_]+:\d+\]")
_PLACEHOLDER_PREFIX = "[redacted_"
_PLACEHOLDER_LABEL = re.compile(r"[a-z0-9_]*")
_FIELD_LABEL = re.compile(r"\b(?:reference|invoice|inv-\d+|po-\d+)\b", re.IGNORECASE)
_LETTERS = re.compile(r"[^\W\d_]+", re.UNICODE)
_MASK = "\ue000{index}\ue001"
_TEXT_FIELDS = ("input", "output", "error_text", "raw_input", "title")

_analyzer: AnalyzerEngine | None = None

current_vault: ContextVar["PiiVault | None"] = ContextVar("current_vault", default=None)


def analyzer() -> AnalyzerEngine:
    """Return the process-wide Presidio engine, loading the small English model once."""
    global _analyzer
    if _analyzer is None:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                "ner_model_configuration": {
                    "labels_to_ignore": ["MONEY", "CARDINAL", "ORDINAL", "QUANTITY", "PERCENT"],
                },
            }
        )
        engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        engine.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="PHONE_NUMBER",
                supported_language="en",
                patterns=[
                    Pattern(
                        "nanp_phone",
                        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)",
                        0.6,
                    )
                ],
            )
        )
        _analyzer = engine
    return _analyzer


class PiiVault:
    """Map each personal value seen in one turn to one stable placeholder."""

    def __init__(self) -> None:
        """Start an empty mapping for this turn."""
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_token: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def protect_text(self, value: str) -> str:
        """Replace personal data in one string, reusing a placeholder for the same value."""
        if not value or _PLACEHOLDER.fullmatch(value):
            return value
        masked, hidden = _mask_placeholders(value)
        spans = [span for span in _resolve_overlaps(_detections(masked)) if _keep_span(masked, span)]
        updated = masked
        for span in sorted(spans, key=lambda item: item.start, reverse=True):
            raw = masked[span.start : span.end]
            if not raw or "\ue000" in raw:
                continue
            token = self._token(span.entity_type, raw)
            updated = updated[: span.start] + token + updated[span.end :]
        return _unmask(updated, hidden)

    def restore_text(self, value: str) -> str:
        """Put the original personal data back into one string."""
        if not value or "[" not in value:
            return value

        def repl(match: re.Match[str]) -> str:
            """Swap one known placeholder for the value it stands for."""
            raw = self._by_token.get(match.group(0))
            if raw is None:
                return match.group(0)
            return raw

        return _PLACEHOLDER.sub(repl, value)

    def protect_value(self, value: Any) -> Any:
        """Replace personal data in nested strings."""
        return map_strings(value, self.protect_text)

    def restore_value(self, value: Any) -> Any:
        """Restore personal data in nested strings."""
        return map_strings(value, self.restore_text)

    def _token(self, entity: str, raw: str) -> str:
        """Return the placeholder for one detected value, creating it on first use."""
        label = ENTITY_LABELS.get(entity, entity.casefold())
        key = (label, raw)
        existing = self._by_value.get(key)
        if existing is not None:
            return existing
        self._counts[label] = self._counts.get(label, 0) + 1
        token = f"[redacted_{label}:{self._counts[label]}]"
        self._by_value[key] = token
        self._by_token[token] = raw
        return token


def map_strings(value: Any, rewrite: Callable[[str], str]) -> Any:
    """Apply one string rewrite to nested text, leaving other values as they are."""
    if isinstance(value, str):
        return rewrite(value)
    if isinstance(value, Mapping):
        return {key: map_strings(item, rewrite) for key, item in value.items()}
    if isinstance(value, list):
        return [map_strings(item, rewrite) for item in value]
    if isinstance(value, tuple):
        return tuple(map_strings(item, rewrite) for item in value)
    return value


def rewrite_run_input(run_input: object, rewrite: Callable[[str], str]) -> None:
    """Rewrite user and assistant text on a Vercel AI run input in place."""
    messages = getattr(run_input, "messages", None)
    if not isinstance(messages, list):
        return
    for message in messages:
        parts = getattr(message, "parts", None)
        if not isinstance(parts, list):
            continue
        for part in parts:
            _rewrite_part(part, rewrite)


class OutboundRestorer:
    """Restore placeholders in server-sent events, holding a token split across deltas."""

    def __init__(self, vault: PiiVault) -> None:
        """Restore with the vault that created the placeholders."""
        self._vault = vault
        self._pending = ""
        self._held = ""
        self._shell: dict[str, Any] | None = None
        self._delta_field = "delta"

    def push(self, chunk: str) -> str:
        """Restore complete events in this chunk and keep a trailing partial event."""
        self._pending += chunk
        pieces: list[str] = []
        while True:
            event, separator = _next_event(self._pending)
            if event is None or separator is None:
                break
            self._pending = self._pending[len(event) + len(separator) :]
            restored = self._restore_event(event)
            if restored:
                pieces.append(restored + separator)
        return "".join(pieces)

    def finish(self) -> str:
        """Restore whatever is still buffered at the end of the stream."""
        pending = self._pending
        self._pending = ""
        pieces: list[str] = []
        if pending:
            restored = self._restore_event(pending)
            if restored:
                pieces.append(restored)
        flushed = self._flush_held()
        if flushed:
            pieces.append(flushed)
        return "".join(pieces)

    def _restore_event(self, event: str) -> str:
        """Restore one SSE event, or return it unchanged when it has no placeholders."""
        payload, prefix = _data_payload(event)
        if payload is None:
            return event
        field = _delta_field(payload)
        if field is not None:
            return self._restore_delta(event, payload, field)
        flushed = self._flush_held()
        restored = map_strings(payload, self._vault.restore_text)
        if restored == payload:
            return f"{flushed}{event}" if flushed else event
        body = "data: " + json.dumps(restored, ensure_ascii=False)
        return f"{flushed}{prefix}{body}" if prefix else f"{flushed}{body}"

    def _restore_delta(self, event: str, payload: dict[str, Any], field: str) -> str:
        """Restore one text delta, keeping an unfinished placeholder for the next chunk."""
        original = payload[field]
        if not isinstance(original, str):
            return event
        held_before = self._held
        ready, self._held = _split_hold(held_before + original)
        self._shell = payload
        self._delta_field = field
        if not ready:
            return ""
        restored = self._vault.restore_text(ready)
        if not held_before and not self._held and restored == original:
            return event
        updated = dict(payload)
        updated[field] = restored
        return "data: " + json.dumps(updated, ensure_ascii=False)

    def _flush_held(self) -> str:
        """Emit a held fragment when the next event is not another text delta."""
        if not self._held or self._shell is None:
            self._held = ""
            return ""
        updated = dict(self._shell)
        updated[self._delta_field] = self._vault.restore_text(self._held)
        self._held = ""
        return "data: " + json.dumps(updated, ensure_ascii=False) + "\n\n"


def _keep_span(text: str, span: RecognizerResult) -> bool:
    """Drop a person hit that is only an invoice field label, such as a reference."""
    if span.entity_type != "PERSON":
        return True
    return not _is_only_field_label(text[span.start : span.end])


def _is_only_field_label(raw: str) -> bool:
    """Return whether the hit has no name left once invoice labels are removed."""
    without_labels = _FIELD_LABEL.sub(" ", raw)
    return _LETTERS.search(without_labels) is None


def _detections(text: str) -> list[RecognizerResult]:
    """Return Presidio hits for the entities this app treats as personal data."""
    engine = analyzer()
    supported = set(engine.get_supported_entities(language="en"))
    entities = [entity for entity in ENTITY_LABELS if entity in supported]
    if not entities:
        return []
    return list(engine.analyze(text=text, language="en", entities=entities))


def _resolve_overlaps(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Keep the higher score, then the longer span, when two hits cover the same text."""
    ordered = sorted(results, key=lambda item: (-item.score, -(item.end - item.start), item.start))
    chosen: list[RecognizerResult] = []
    for result in ordered:
        if any(result.start < other.end and other.start < result.end for other in chosen):
            continue
        chosen.append(result)
    return chosen


def _mask_placeholders(value: str) -> tuple[str, list[str]]:
    """Hide existing placeholders so a second pass does not analyze them."""
    hidden: list[str] = []

    def repl(match: re.Match[str]) -> str:
        """Store one placeholder and put a private-use marker in its place."""
        hidden.append(match.group(0))
        return _MASK.format(index=len(hidden) - 1)

    return _PLACEHOLDER.sub(repl, value), hidden


def _unmask(value: str, hidden: list[str]) -> str:
    """Put masked placeholders back after analysis."""
    restored = value
    for index, token in enumerate(hidden):
        restored = restored.replace(_MASK.format(index=index), token)
    return restored


def _rewrite_part(part: object, rewrite: Callable[[str], str]) -> None:
    """Rewrite text and tool fields on one UI message part."""
    text = getattr(part, "text", None)
    if isinstance(text, str):
        rewritten = rewrite(text)
        if rewritten != text:
            setattr(part, "text", rewritten)
    for field in _TEXT_FIELDS:
        if not hasattr(part, field):
            continue
        current = getattr(part, field)
        updated = map_strings(current, rewrite)
        if updated != current:
            setattr(part, field, updated)


def _data_payload(event: str) -> tuple[dict[str, Any] | None, str]:
    """Return the JSON object from one SSE data line, plus any prefix before it."""
    marker = "data:"
    start = event.find(marker)
    if start < 0:
        return None, ""
    raw = event[start + len(marker) :].strip()
    if not raw or raw == "[DONE]":
        return None, ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, ""
    if not isinstance(payload, dict):
        return None, ""
    return payload, event[:start]


def _delta_field(payload: dict[str, Any]) -> str | None:
    """Return the streamed text field on a text or reasoning delta."""
    if payload.get("type") not in {"text-delta", "reasoning-delta"}:
        return None
    if isinstance(payload.get("delta"), str):
        return "delta"
    if isinstance(payload.get("textDelta"), str):
        return "textDelta"
    return None


def _split_hold(text: str) -> tuple[str, str]:
    """Split a trailing unfinished placeholder off text that is safe to restore."""
    start = text.rfind("[")
    if start < 0:
        return text, ""
    candidate = text[start:]
    if not _is_placeholder_prefix(candidate):
        return text, ""
    return text[:start], candidate


def _is_placeholder_prefix(value: str) -> bool:
    """Return whether text can become a placeholder when more characters arrive."""
    if _PLACEHOLDER.fullmatch(value):
        return False
    if len(value) <= len(_PLACEHOLDER_PREFIX):
        return _PLACEHOLDER_PREFIX.startswith(value)
    if not value.startswith(_PLACEHOLDER_PREFIX):
        return False
    remainder = value[len(_PLACEHOLDER_PREFIX) :]
    if ":" not in remainder:
        return _PLACEHOLDER_LABEL.fullmatch(remainder) is not None
    label, digits = remainder.split(":", 1)
    return (
        bool(label)
        and _PLACEHOLDER_LABEL.fullmatch(label) is not None
        and (not digits or digits.isdigit())
    )


def _next_event(pending: str) -> tuple[str | None, str | None]:
    """Split the next complete SSE event from the buffer."""
    for separator in ("\r\n\r\n", "\n\n"):
        index = pending.find(separator)
        if index >= 0:
            return pending[:index], separator
    return None, None
