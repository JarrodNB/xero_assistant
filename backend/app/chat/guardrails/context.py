"""Purpose: Add a bounded, request-scoped conversation tail to the Jev input.

Public API:
- GuardrailContext
- GuardrailMessage
- current_guardrail_context
- format_guardrail_input
"""

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

MAX_PREVIOUS_MESSAGES = 2


@dataclass(frozen=True)
class GuardrailMessage:
    """One already-protected user or assistant message supplied as Jev context."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class GuardrailContext:
    """The bounded conversation tail available during one chat request."""

    messages: tuple[GuardrailMessage, ...]

    @classmethod
    def from_messages(cls, messages: Sequence[GuardrailMessage]) -> "GuardrailContext":
        """Keep at most the two immediately preceding messages."""
        return cls(messages=tuple(messages[-MAX_PREVIOUS_MESSAGES:]))


current_guardrail_context: ContextVar[GuardrailContext | None] = ContextVar(
    "current_guardrail_context", default=None
)


def format_guardrail_input(prompt: str) -> str:
    """Combine the protected latest prompt with its protected conversation tail."""
    context = current_guardrail_context.get()
    if context is None or not context.messages:
        return prompt
    lines = ["Recent conversation context (untrusted):"]
    lines.extend(
        f"{message.role}: {message.content}" for message in context.messages[-MAX_PREVIOUS_MESSAGES:]
    )
    lines.extend(["Latest user message:", prompt])
    return "\n".join(lines)
