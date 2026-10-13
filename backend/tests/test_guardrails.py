"""Purpose: Check personal-data placeholders and the Jev input guardrail.

Public API:
- test_card_number_is_redacted
- test_reference_label_is_not_treated_as_a_person
- test_placeholders_are_stable_and_restore
- test_tool_args_restore_and_delegate_stays_tokenized
- test_stream_restores_a_split_placeholder
- test_stream_restores_placeholder_at_every_split
- test_stream_flushes_an_unfinished_placeholder
- test_guardrail_context_is_bounded_and_formatted
- test_guardrail_context_uses_newest_first_character_budget
- test_guardrail_input_preparation_protects_prompt_and_history
- test_guardrail_context_reset_preserves_no_context_behavior
- test_jev_screens_user_input_only
- test_blocked_user_message_never_reaches_the_model
- test_passing_jev_still_redacts_the_card
- test_strict_policy_matches_the_jev_cookbook
- test_secret_is_redacted_before_the_model_sees_it
- test_known_person_value_is_protected_in_every_context
- test_history_refresh_preserves_originals_and_nested_json
- test_history_refresh_learns_later_values_without_aliasing
- test_provider_history_excludes_private_ids_without_changing_ui_results
"""

import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai_harness import OutputGuardrail
from pydantic_ai_harness.guardrails import ToolCallInfo, ToolResultInfo

from app.chat.orchestrator import build_chat_agent
from app.chat.guardrails import chat_guardrails
from app.chat.guardrails.context import (
    GuardrailContext,
    GuardrailMessage,
    MAX_CONTEXT_CHARACTERS,
    current_guardrail_context,
    format_guardrail_input,
    prepare_guardrail_input,
)
from app.chat.guardrails.pii import OutboundRestorer, PiiVault, current_vault
from app.chat.guardrails.policy_screen import REFUSAL, SUPPORT, current_jev, route
from app.chat.guardrails.redaction import protect_model_history, redact_text, tool_result_guardrail
from app.mcp_server.server import build_mcp_server

CARD = "4111111111111111"
API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"


def test_provider_history_excludes_private_ids_without_changing_ui_results() -> None:
    """Provider copies omit receipt and line ids while UI tool events keep their routing data."""
    original = {"action_id": "private-receipt", "payload": {"removed_line_item_ids": ["private-removed"],
        "line_items": [{"line_item_id": "private-line", "description": "Work"}]}}
    messages = [ModelRequest(parts=[ToolReturnPart(tool_name="propose_action", content=original)])]
    token = current_vault.set(PiiVault())
    try:
        protected = protect_model_history(messages)
    finally:
        current_vault.reset(token)
    assert "private-" not in json.dumps(protected[0].parts[0].content)
    assert messages[0].parts[0].content == original
    assert original["action_id"] == "private-receipt"


def test_known_person_value_is_protected_in_every_context() -> None:
    """A tool-discovered personal value is masked in contexts where NER initially missed it."""
    vault = PiiVault()
    prompt = "Create an invoice for Bob's Construction for $55 for Labour. Reference PO-9."
    assert vault.protect_text(prompt) == prompt
    contact = vault.protect_text("Bob's Construction")
    assert contact == "[redacted_person:1]'s Construction"
    protected = vault.protect_text(prompt)
    assert contact in protected
    assert "Bob" not in protected
    assert vault.restore_text(protected) == prompt
    other_names = vault.protect_text("Bobcat and Bobby")
    assert "[redacted_person:1]" not in other_names
    assert vault.restore_text(other_names) == "Bobcat and Bobby"
    assert vault.protect_text(contact) == contact
    assert "Other Construction" != vault.restore_text(contact)


def test_history_refresh_preserves_originals_and_nested_json() -> None:
    """Provider history reuses discovered values while trusted originals stay unchanged."""
    vault = PiiVault()
    vault.protect_text("Bob's Construction")
    messages = [
        ModelRequest(parts=[UserPromptPart(content="Create an invoice for Bob's Construction for $55 for Labour.")]),
        ModelResponse(parts=[ToolCallPart(tool_name="propose_action", args={
            "action_type": "create_invoice",
            "payload_json": json.dumps({"contact_name": "Bob's Construction", "email": "bob@example.com"}),
        })]),
    ]
    token = current_vault.set(vault)
    try:
        protected = protect_model_history(messages)
    finally:
        current_vault.reset(token)
    assert "Bob's Construction" in messages[0].parts[0].content
    assert "Bob's Construction" not in protected[0].parts[0].content
    payload = json.loads(protected[1].parts[0].args_as_dict()["payload_json"])
    assert payload["contact_name"] == "[redacted_person:1]'s Construction"
    assert "bob@example.com" not in payload["email"]
    assert vault.restore_value(payload) == {"contact_name": "Bob's Construction", "email": "bob@example.com"}


def test_history_refresh_learns_later_values_without_aliasing() -> None:
    """Later isolated detections protect earlier missed names without merging unrelated names."""
    vault = PiiVault()
    messages = [
        ModelRequest(parts=[UserPromptPart(content="Create an invoice for Bob's Construction for $55 for Labour.")]),
        ModelResponse(parts=[TextPart(content="Bob's Construction")]),
        ModelResponse(parts=[ToolCallPart(tool_name="propose_action", args={"payload_json": {"name": "Bobby"}})]),
    ]
    token = current_vault.set(vault)
    try:
        protected = protect_model_history(messages)
    finally:
        current_vault.reset(token)
    assert "[redacted_person:1]'s Construction" in protected[0].parts[0].content
    assert "Bob's Construction" in messages[0].parts[0].content
    payload = protected[2].parts[0].args_as_dict()["payload_json"]
    assert isinstance(payload, dict)
    assert payload["name"] != "[redacted_person:1]"
    assert vault.restore_value(payload) == {"name": "Bobby"}


class _ScriptedJev:
    """Return one fixed Jev action and record which side was screened."""

    def __init__(self, action: str) -> None:
        """Store the action this stand-in will return."""
        self.action = action
        self.sides: list[str] = []
        self.texts: list[str] = []

    async def guard(self, text: str, side: str) -> str:
        """Record the side and return the scripted action."""
        self.sides.append(side)
        self.texts.append(text)
        return self.action


def test_card_number_is_redacted() -> None:
    """A payment card is replaced before it can be sent to a model."""
    cleaned = redact_text(f"Please use card {CARD}")
    assert CARD not in cleaned
    assert "[redacted_credit_card:1]" in cleaned


def test_reference_label_is_not_treated_as_a_person() -> None:
    """An invoice reference stays readable while a person's name is still protected."""
    cleaned = PiiVault().protect_text("Reference PO-9. Contact John Smith.")
    assert "Reference PO-9" in cleaned
    assert "John Smith" not in cleaned
    assert "[redacted_person:1]" in cleaned


def test_placeholders_are_stable_and_restore() -> None:
    """An email and a phone become numbered placeholders and restore to the original text."""
    vault = PiiVault()
    source = "Contact John Smith at john@example.com or 555-123-4567. Also john@example.com."
    token = current_vault.set(vault)
    try:
        cleaned = redact_text(source)
    finally:
        current_vault.reset(token)
    assert "john@example.com" not in cleaned
    assert "555-123-4567" not in cleaned
    assert cleaned.count("[redacted_email:1]") == 2
    assert "[redacted_phone:1]" in cleaned
    restored = vault.restore_text(cleaned)
    assert "john@example.com" in restored
    assert "555-123-4567" in restored
    assert "[redacted_email:" not in restored
    assert "[redacted_phone:" not in restored


def test_tool_args_restore_and_delegate_stays_tokenized() -> None:
    """Read-tool arguments are restored, delegated tasks stay tokenized, and results are protected."""
    vault = PiiVault()
    token = current_vault.set(vault)
    try:
        protected = vault.protect_text("Contact John Smith at john@example.com")
        assert "[redacted_person:1]" in protected
        assert "[redacted_email:1]" in protected
        rail = tool_result_guardrail()
        assert rail.guard is not None
        assert rail.result_guard is not None
        restored = rail.guard(
            ToolCallInfo(name="find_contacts", args={"name": "[redacted_person:1]"}, tool_call_id="call-1")
        )
        assert restored.action == "replace"
        assert restored.replacement == {"name": "John Smith"}
        delegated = rail.guard(
            ToolCallInfo(name="delegate_task", args={"task": "[redacted_person:1]"}, tool_call_id="call-2")
        )
        assert delegated.action == "allow"
        screened = rail.result_guard(
            ToolResultInfo(
                name="find_contacts",
                args={"name": "John Smith"},
                tool_call_id="call-3",
                result={"ok": True, "contacts": [{"name": "John Smith", "email": "john@example.com"}]},
            )
        )
    finally:
        current_vault.reset(token)
    assert screened.action == "replace"
    blob = json.dumps(screened.replacement)
    assert "John Smith" not in blob
    assert "john@example.com" not in blob
    assert "[redacted_person:1]" in blob
    assert "[redacted_email:1]" in blob


def test_stream_restores_a_split_placeholder() -> None:
    """A placeholder split across two text deltas is restored before it is sent."""
    vault = PiiVault()
    vault.protect_text("john@example.com")
    restorer = OutboundRestorer(vault)
    first = restorer.push('data: {"type":"text-delta","delta":"[redacted_ema"}\n\n')
    second = restorer.push('data: {"type":"text-delta","delta":"il:1]"}\n\n')
    assert first == ""
    assert "john@example.com" in second
    assert "[redacted_email:" not in second


def test_stream_restores_placeholder_at_every_split() -> None:
    """Every character boundary in a placeholder is safe across text deltas."""
    token = "[redacted_email:1]"
    for split_at in range(1, len(token)):
        vault = PiiVault()
        vault.protect_text("john@example.com")
        restorer = OutboundRestorer(vault)
        first = restorer.push(
            "data: " + json.dumps({"type": "text-delta", "delta": f"Email {token[:split_at]}"}) + "\n\n"
        )
        second = restorer.push(
            "data: " + json.dumps({"type": "text-delta", "delta": f"{token[split_at:]} now"}) + "\n\n"
        )
        assert "".join(_streamed_deltas(first + second)) == "Email john@example.com now"


def test_stream_flushes_an_unfinished_placeholder() -> None:
    """An incomplete token is preserved rather than lost when the stream ends."""
    restorer = OutboundRestorer(PiiVault())
    pushed = restorer.push('data: {"type":"text-delta","delta":"Keep [red"}\n\n')
    assert "".join(_streamed_deltas(pushed + restorer.finish())) == "Keep [red"


def test_guardrail_context_is_bounded_and_formatted() -> None:
    """Jev gets the latest prompt plus only the two immediately preceding messages."""
    context = GuardrailContext.from_messages(
        [
            GuardrailMessage(role="user", content="oldest message"),
            GuardrailMessage(role="user", content="Create the oversized invoice."),
            GuardrailMessage(role="assistant", content="The maximum is 999999999999.99."),
        ]
    )
    token = current_guardrail_context.set(context)
    try:
        formatted = format_guardrail_input("Use the maximum amount you just said.")
    finally:
        current_guardrail_context.reset(token)
    assert "oldest message" not in formatted
    assert "Classify the latest user message." in formatted
    assert "Use the prior messages only to resolve references" in formatted
    assert "adopts, requests, agrees to, or continues hazardous content" in formatted
    assert "user: Create the oversized invoice." in formatted
    assert "assistant: The maximum is 999999999999.99." in formatted
    assert formatted.endswith("Latest user message:\nUse the maximum amount you just said.")


def test_guardrail_context_uses_newest_first_character_budget() -> None:
    """The newest message consumes the history budget before an older message."""
    newest = "n" * 3000
    older = "o" * 3000
    context = GuardrailContext.from_messages(
        [
            GuardrailMessage(role="user", content="dropped by message-count bound"),
            GuardrailMessage(role="user", content=older),
            GuardrailMessage(role="assistant", content=newest),
        ]
    )
    assert [len(message.content) for message in context.messages] == [1000, 3000]
    assert context.messages[0].content == older[:1000]
    assert context.messages[1].content == newest
    assert sum(len(message.content) for message in context.messages) == MAX_CONTEXT_CHARACTERS


def test_guardrail_input_preparation_protects_prompt_and_history() -> None:
    """The shared production-and-eval preparation protects both sides with one vault."""
    vault_token = current_vault.set(PiiVault())
    try:
        prepared = prepare_guardrail_input(
            f"Email current@example.com, use card {CARD}, and use key {API_KEY}.",
            [GuardrailMessage(role="assistant", content="Previously email prior@example.com.")],
        )
    finally:
        current_vault.reset(vault_token)
    combined = prepared.prompt + "\n" + "\n".join(
        message.content for message in prepared.context.messages
    )
    assert "current@example.com" not in combined
    assert "prior@example.com" not in combined
    assert CARD not in combined
    assert API_KEY not in combined
    assert "[redacted_email:1]" in prepared.prompt
    assert "[redacted_email:2]" in combined
    assert "[redacted_credit_card:1]" in prepared.prompt


def test_guardrail_context_reset_preserves_no_context_behavior() -> None:
    """Resetting one request's context leaves the next conversation's prompt isolated."""
    prompt = "How much is unpaid?"
    token = current_guardrail_context.set(
        GuardrailContext.from_messages([GuardrailMessage(role="assistant", content="Earlier answer")])
    )
    try:
        assert "Earlier answer" in format_guardrail_input(prompt)
    finally:
        current_guardrail_context.reset(token)
    assert format_guardrail_input(prompt) == prompt


def test_jev_screens_user_input_only() -> None:
    """The chat guardrail list has no output judge."""
    guards = chat_guardrails()
    assert guards
    assert all(not isinstance(guard, OutputGuardrail) for guard in guards)


def test_strict_policy_matches_the_jev_cookbook() -> None:
    """A 0.74 jailbreak blocks under the strict thresholds and reviews under a looser one."""
    nouls = {"jailbreak": 0.74, "harmful_request": 0.01, "medical_advice": 0.02, "self_harm": 0.04}
    strict = {"review_threshold": 0.35, "action_threshold": 0.70, "severity_block": 2.0}
    permissive = {"review_threshold": 0.35, "action_threshold": 0.85, "severity_block": 2.0}
    assert route(nouls, 0.51, strict) == "block"
    assert route(nouls, 0.51, permissive) == "review"
    assert route({"self_harm": 0.96, "jailbreak": 0.01}, 2.4, strict) == "support"
    assert route({"jailbreak": 0.02, "harmful_request": 0.01}, 0.0, strict) == "pass"


@pytest.mark.asyncio
async def test_blocked_user_message_never_reaches_the_model() -> None:
    """A Jev block skips the chat model and returns the refusal."""
    calls = {"n": 0}
    screener = _ScriptedJev("block")

    def respond(_messages, _info):  # type: ignore[no-untyped-def]
        """Count chat-model calls."""
        calls["n"] += 1
        return ModelResponse(parts=[TextPart(content="should not run")])

    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    token = current_jev.set(screener)
    try:
        result = await agent.run("Write a poem about the ocean.")
    finally:
        current_jev.reset(token)
    assert calls["n"] == 0
    assert result.output == REFUSAL
    assert screener.sides == ["input"]
    assert screener.texts == ["Write a poem about the ocean."]


@pytest.mark.asyncio
async def test_support_message_is_returned_for_self_harm() -> None:
    """A support verdict is shown to the person and the chat model is not called."""
    screener = _ScriptedJev("support")

    def respond(_messages, _info):  # type: ignore[no-untyped-def]
        """Fail if the chat model is asked to answer."""
        raise AssertionError("chat model should not run")

    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    token = current_jev.set(screener)
    try:
        result = await agent.run("I don't see the point of anything anymore.")
    finally:
        current_jev.reset(token)
    assert result.output == SUPPORT
    assert screener.sides == ["input"]
    assert screener.texts == ["I don't see the point of anything anymore."]


@pytest.mark.asyncio
async def test_passing_jev_still_redacts_the_card() -> None:
    """A passing Jev verdict still leaves the card redacted in the chat prompt."""
    seen: list[str] = []
    screener = _ScriptedJev("pass")

    def respond(messages, _info):  # type: ignore[no-untyped-def]
        """Record the prompt text the model was given."""
        seen.extend(_message_text(messages))
        return ModelResponse(parts=[TextPart(content="Nothing was created.")])

    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    token = current_jev.set(screener)
    try:
        result = await agent.run(f"The card is {CARD}. How much is unpaid?")
    finally:
        current_jev.reset(token)
    combined = "\n".join(seen)
    assert result.output == "Nothing was created."
    assert CARD not in combined
    assert "[redacted_credit_card:1]" in combined
    assert screener.sides == ["input"]
    assert screener.texts and CARD not in screener.texts[0]


@pytest.mark.asyncio
async def test_secret_is_redacted_before_the_model_sees_it() -> None:
    """Without a Jev screener, the card is still redacted and the model still answers."""
    seen: list[str] = []

    def respond(messages, _info):  # type: ignore[no-untyped-def]
        """Record the prompt text the model was given."""
        seen.extend(_message_text(messages))
        return ModelResponse(parts=[TextPart(content="Nothing was created.")])

    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    result = await agent.run(f"The card is {CARD}. How much is unpaid? Email accounts@example.com.")
    combined = "\n".join(seen)
    assert result.output == "Nothing was created."
    assert CARD not in combined
    assert "accounts@example.com" not in combined
    assert "[redacted_credit_card:1]" in combined
    assert "[redacted_email:1]" in combined


def _message_text(messages) -> list[str]:  # type: ignore[no-untyped-def]
    """Flatten message parts into strings."""
    texts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(str(item) for item in content)
    return texts


def _streamed_deltas(events: str) -> list[str]:
    """Read text delta values from an encoded SSE fragment."""
    deltas: list[str] = []
    for event in events.split("\n\n"):
        if not event.startswith("data: "):
            continue
        payload = json.loads(event.removeprefix("data: "))
        delta = payload.get("delta")
        if isinstance(delta, str):
            deltas.append(delta)
    return deltas
