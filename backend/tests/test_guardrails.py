"""Purpose: Check personal-data placeholders and the Jev input guardrail.

Public API:
- test_card_number_is_redacted
- test_reference_label_is_not_treated_as_a_person
- test_placeholders_are_stable_and_restore
- test_tool_args_restore_and_delegate_stays_tokenized
- test_stream_restores_a_split_placeholder
- test_stream_restores_placeholder_at_every_split
- test_stream_flushes_an_unfinished_placeholder
- test_jev_screens_user_input_only
- test_blocked_user_message_never_reaches_the_model
- test_passing_jev_still_redacts_the_card
- test_strict_policy_matches_the_jev_cookbook
- test_secret_is_redacted_before_the_model_sees_it
"""

import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai_harness import OutputGuardrail
from pydantic_ai_harness.guardrails import ToolCallInfo, ToolResultInfo

from app.chat.orchestrator import build_chat_agent
from app.chat.guardrails import chat_guardrails
from app.chat.guardrails.pii import OutboundRestorer, PiiVault, current_vault
from app.chat.guardrails.policy_screen import REFUSAL, SUPPORT, current_jev, route
from app.chat.guardrails.redaction import redact_text, tool_result_guardrail
from app.mcp_server.server import build_mcp_server

CARD = "4111111111111111"


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
