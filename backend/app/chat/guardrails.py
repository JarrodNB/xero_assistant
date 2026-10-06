"""Purpose: Redact secrets, then screen the user message with Jev before the chat model runs.

Public API:
- redact_text
- chat_guardrails
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic_ai_harness import GuardrailResult, InputGuardrail, ToolGuardrail
from pydantic_ai_harness.guardrails import ToolResultInfo
from pydantic_ai_harness.guardrails.detectors import personal_data, redact_secrets

from app.chat.jev import CHECK_FAILED, REFUSAL, SUPPORT, current_jev

_PERSONAL_DATA = personal_data(only=["us_ssn", "credit_card", "iban"])


def redact_text(value: str) -> str:
    """Remove secrets, card numbers, SSNs, and IBANs from text."""
    cleaned = value
    for detector in (redact_secrets, _PERSONAL_DATA):
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


async def screen_user_message(prompt: str) -> GuardrailResult:
    """Ask Jev about the user message. The assistant reply is not screened."""
    screener = current_jev.get()
    if screener is None or not prompt.strip():
        return GuardrailResult.allow()
    try:
        action = await screener.guard(prompt, "input")
    except Exception:
        return GuardrailResult.block(CHECK_FAILED)
    if action == "pass":
        return GuardrailResult.allow()
    if action == "support":
        return GuardrailResult.block(SUPPORT)
    return GuardrailResult.block(REFUSAL)


def chat_guardrails() -> list[object]:
    """Redact secrets, screen the user message with Jev, and redact tool results."""
    return [
        InputGuardrail(guard=[redact_secrets, _PERSONAL_DATA, screen_user_message]),
        ToolGuardrail(result_guard=_redact_tool_result),
    ]
