"""Purpose: Redact secrets and payment details before a model reads them.

Public API:
- PERSONAL_DATA
- redact_text
- tool_result_guardrail
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic_ai_harness import GuardrailResult, ToolGuardrail
from pydantic_ai_harness.guardrails import ToolResultInfo
from pydantic_ai_harness.guardrails.detectors import personal_data, redact_secrets

PERSONAL_DATA = personal_data(only=["us_ssn", "credit_card", "iban"])


def redact_text(value: str) -> str:
    """Remove secrets, card numbers, SSNs, and IBANs from text."""
    cleaned = value
    for detector in (redact_secrets, PERSONAL_DATA):
        verdict = detector(cleaned)
        if verdict.action == "replace" and isinstance(verdict.replacement, str):
            cleaned = verdict.replacement
    return cleaned


def _redact_value(value: Any) -> tuple[Any, bool]:
    """Redact strings nested in a tool result."""
    if isinstance(value, str):
        cleaned = redact_text(value)
        return cleaned, cleaned != value
    if isinstance(value, Mapping):
        changed = False
        cleaned_mapping: dict[Any, Any] = {}
        for key, item in value.items():
            cleaned_item, item_changed = _redact_value(item)
            cleaned_mapping[key] = cleaned_item
            changed = changed or item_changed
        return cleaned_mapping, changed
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        changed = False
        cleaned_items = []
        for item in value:
            cleaned_item, item_changed = _redact_value(item)
            cleaned_items.append(cleaned_item)
            changed = changed or item_changed
        return cleaned_items, changed
    return value, False


def _redact_tool_result(info: ToolResultInfo) -> GuardrailResult:
    """Redact secret-bearing text in a tool result before the model reads it."""
    cleaned, changed = _redact_value(info.result)
    if changed:
        return GuardrailResult.replace(cleaned)
    return GuardrailResult.allow()


def tool_result_guardrail() -> ToolGuardrail:
    """Redact secrets in a tool result before the model reads it."""
    return ToolGuardrail(result_guard=_redact_tool_result)
