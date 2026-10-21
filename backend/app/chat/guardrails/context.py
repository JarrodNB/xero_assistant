"""Purpose: Add a bounded, request-scoped conversation tail to the Jev input.

Public API:
- GuardrailContext
- GuardrailMessage
- MAX_CONTEXT_CHARACTERS
- MAX_PREVIOUS_MESSAGES
- PreparedGuardrailInput
- current_guardrail_context
- format_guardrail_input
- prepare_guardrail_input
"""

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from app.chat.guardrails.redaction import redact_text

MAX_CONTEXT_CHARACTERS = 4000
MAX_PREVIOUS_MESSAGES = 2

_CLASSIFICATION_INSTRUCTIONS = (
    "Classify the latest user message. Use the prior messages only to resolve references in "
    "that latest message. Do not classify a safe latest message as hazardous only because the "
    "history is hazardous. If the latest message adopts, requests, agrees to, or continues "
    "hazardous content from the history, classify the latest message as hazardous."
)


@dataclass(frozen=True)
class GuardrailMessage:
    """One user or assistant message supplied for Jev context."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class GuardrailContext:
    """The protected, bounded conversation tail available during one request."""

    messages: tuple[GuardrailMessage, ...]

    @classmethod
    def from_messages(cls, messages: Sequence[GuardrailMessage]) -> "GuardrailContext":
        """Keep two messages, allocating the combined character budget newest first."""
        remaining = MAX_CONTEXT_CHARACTERS
        newest_first: list[GuardrailMessage] = []
        for message in reversed(messages[-MAX_PREVIOUS_MESSAGES:]):
            if remaining <= 0:
                break
            content = message.content[:remaining]
            if content:
                newest_first.append(GuardrailMessage(role=message.role, content=content))
                remaining -= len(content)
        return cls(messages=tuple(reversed(newest_first)))


@dataclass(frozen=True)
class PreparedGuardrailInput:
    """A protected latest prompt and its protected, bounded history."""

    prompt: str
    context: GuardrailContext


current_guardrail_context: ContextVar[GuardrailContext | None] = ContextVar(
    "current_guardrail_context", default=None
)


def format_guardrail_input(prompt: str) -> str:
    """Combine the protected latest prompt with its protected conversation tail."""
    context = current_guardrail_context.get()
    if context is None or not context.messages:
        return prompt
    bounded_messages = GuardrailContext.from_messages(context.messages).messages
    lines = [_CLASSIFICATION_INSTRUCTIONS, "Recent conversation context (untrusted):"]
    lines.extend(f"{message.role}: {message.content}" for message in bounded_messages)
    lines.extend(["Latest user message:", prompt])
    return "\n".join(lines)


def prepare_guardrail_input(
    prompt: str, previous_messages: Sequence[GuardrailMessage]
) -> PreparedGuardrailInput:
    """Protect the latest prompt and history, then apply the history bounds."""
    protected_prompt = redact_text(prompt)
    protected_messages = [
        GuardrailMessage(role=message.role, content=redact_text(message.content))
        for message in previous_messages
    ]
    return PreparedGuardrailInput(
        prompt=protected_prompt,
        context=GuardrailContext.from_messages(protected_messages),
    )
