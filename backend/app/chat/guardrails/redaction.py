"""Purpose: Keep personal data and secrets out of model prompts, and restore personal data for tools.

Public API:
- prepare_run_input
- protect_prompt
- redact_for_trace
- redact_text
- tool_result_guardrail
- protect_model_history
"""

import json
from copy import deepcopy
from typing import Any

from pydantic_ai.messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart

from pydantic_ai_harness import GuardrailResult, ToolGuardrail
from pydantic_ai_harness.guardrails import ToolCallInfo, ToolResultInfo
from pydantic_ai_harness.guardrails.detectors import redact_secrets

from app.chat.report_history import without_report_figures
from app.chat.guardrails.pii import PiiVault, current_vault, map_strings, rewrite_run_input

_DELEGATE = "delegate_task"


def redact_text(value: str) -> str:
    """Replace personal data with placeholders and remove secrets."""
    vault = current_vault.get()
    if vault is None:
        vault = PiiVault()
    return _without_secrets(vault.protect_text(without_report_figures(value)))


def redact_for_trace(value: str, vault: PiiVault | None = None) -> str:
    """Replace personal data and secrets for a trace, without keeping them for restore."""
    holder = vault if vault is not None else PiiVault()
    return _without_secrets(holder.protect_text(value))


def protect_prompt(prompt: str) -> GuardrailResult:
    """Replace personal data in the latest user prompt before later checks see it."""
    if current_vault.get() is None:
        current_vault.set(PiiVault())
    protected = redact_text(prompt)
    if protected == prompt:
        return GuardrailResult.allow()
    return GuardrailResult.replace(protected)


def prepare_run_input(run_input: object) -> None:
    """Replace personal data and secrets on a chat request before the agent sees it."""
    vault = current_vault.get()
    if vault is None:
        return

    def rewrite(text: str) -> str:
        """Protect one string with the turn vault."""
        return redact_text(text)

    rewrite_run_input(run_input, rewrite)


def protect_model_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Refresh provider history with values learned from tools without changing stored messages."""
    vault = current_vault.get()
    if vault is None:
        return messages
    protected = deepcopy(messages)
    _protect_message_parts(protected, vault)
    _protect_message_parts(protected, vault)
    return protected


def _protect_message_parts(messages: list[ModelMessage], vault: PiiVault) -> None:
    """Protect message values, allowing a second pass to reuse values learned later in history."""
    for message in messages:
        for part in message.parts:
            if isinstance(part, (TextPart, UserPromptPart)) and isinstance(part.content, str):
                part.content = redact_text(part.content)
            elif isinstance(part, ToolCallPart):
                args = part.args_as_dict()
                payload = args.get("payload_json")
                protected_args = _scrub_value({key: value for key, value in args.items() if key != "payload_json"}, vault)
                if isinstance(payload, str):
                    try:
                        protected_args["payload_json"] = json.dumps(_scrub_value(json.loads(payload), vault))
                    except ValueError:
                        protected_args["payload_json"] = redact_text(payload)
                elif "payload_json" in args:
                    protected_args["payload_json"] = _scrub_value(payload, vault)
                part.args = protected_args
            elif isinstance(part, ToolReturnPart):
                part.content = _scrub_value(_without_internal_ids(part.content), vault)


def _without_internal_ids(value: Any) -> Any:
    """Remove private routing and line identities from provider history, preserving UI events."""
    if isinstance(value, dict):
        return {key: _without_internal_ids(item) for key, item in value.items()
                if key not in {"action_id", "line_item_id", "removed_line_item_ids"}}
    if isinstance(value, list):
        return [_without_internal_ids(item) for item in value]
    return value


def _restore_tool_args(info: ToolCallInfo) -> GuardrailResult:
    """Restore placeholders in tool arguments, leaving a delegated task tokenized."""
    if info.name == _DELEGATE:
        return GuardrailResult.allow()
    vault = current_vault.get()
    if vault is None:
        return GuardrailResult.allow()
    args = dict(info.args)
    restored = _restore_args(args, vault)
    if restored == args:
        return GuardrailResult.allow()
    return GuardrailResult.replace(restored)


def _protect_tool_result(info: ToolResultInfo) -> GuardrailResult:
    """Replace personal data and secrets in a tool result before the model reads it."""
    vault = current_vault.get()
    if vault is None:
        vault = PiiVault()
        current_vault.set(vault)
    cleaned = _scrub_value(info.result, vault)
    if cleaned == info.result:
        return GuardrailResult.allow()
    return GuardrailResult.replace(cleaned)


def tool_result_guardrail() -> ToolGuardrail:
    """Restore tool arguments and protect tool results before the model reads them."""
    return ToolGuardrail(guard=_restore_tool_args, result_guard=_protect_tool_result)


def _scrub_value(value: Any, vault: PiiVault) -> Any:
    """Replace personal data and secrets in nested text."""

    def rewrite(text: str) -> str:
        """Protect one string with this vault."""
        return _without_secrets(vault.protect_text(text))

    return map_strings(value, rewrite)


def _restore_args(args: dict[str, Any], vault: PiiVault) -> dict[str, Any]:
    """Restore tool arguments, parsing a proposal payload before values are put back."""
    payload = args.get("payload_json")
    if not isinstance(payload, str):
        restored = vault.restore_value(args)
        return restored if isinstance(restored, dict) else args
    restored = vault.restore_value({key: value for key, value in args.items() if key != "payload_json"})
    if not isinstance(restored, dict):
        return args
    restored["payload_json"] = _restore_payload_json(payload, vault)
    return restored


def _restore_payload_json(payload: str, vault: PiiVault) -> str:
    """Restore placeholders inside a JSON object, then serialize it again."""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return vault.restore_text(payload)
    if not isinstance(parsed, (dict, list)):
        return vault.restore_text(payload)
    return json.dumps(vault.restore_value(parsed), ensure_ascii=False)


def _without_secrets(value: str) -> str:
    """Remove API keys and private keys. Those replacements are not restored."""
    verdict = redact_secrets(value)
    if verdict.action == "replace" and isinstance(verdict.replacement, str):
        return verdict.replacement
    return value
