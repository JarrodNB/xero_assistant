"""Purpose: Fold older chat messages into a stored summary and trim model history.

Public API:
- HistorySummary
- apply_history_summary
- current_history_summary
- next_summary_slice
- summarize_with_model
- summary_prompt
- update_stored_summary
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model

from app.chat.guardrails import redact_text
from app.db.repository import ActionRepository, StoredMessage

SUMMARY_LEAD = "Summary of the earlier conversation:\n"

SUMMARY_INSTRUCTIONS = """
You update a running summary of one person's conversation with this assistant.
Summarize the whole conversation. Do not drop a topic because it is outside the subjects you have seen so far.

Keep names, amounts, dates, identifiers, skipped fields, decisions, and whether a proposal is pending, confirmed, or denied.
Do not claim anything was created, updated, or voided unless the transcript says it was executed.
Omit small talk. Do not invent facts. Do not repeat action ids.
""".strip()


@dataclass
class HistorySummary:
    """The summary and verbatim tail for one model request."""

    text: str
    every: int
    recent_stored: list[StoredMessage]


current_history_summary: ContextVar[HistorySummary | None] = ContextVar("current_history_summary", default=None)


def next_summary_slice(message_count: int, covered_count: int, every: int) -> tuple[int, int] | None:
    """Return the next stored-message range to fold, or None when no block is ready."""
    if every <= 0 or message_count <= 0:
        return None
    covered = min(max(covered_count, 0), message_count)
    if message_count - covered < every * 2:
        return None
    return covered, covered + every


def summary_prompt(previous: str, messages: list[StoredMessage]) -> str:
    """Build the redacted prompt for one summary update."""
    lines = ["Update the running summary using the earlier summary and the new messages."]
    if previous.strip():
        lines.append("Earlier summary:")
        lines.append(redact_text(previous))
    lines.append("Messages:")
    for message in messages:
        lines.append(f"{message.role}: {redact_text(message.content)}")
    return "\n".join(lines)


async def summarize_with_model(model: str | Model, prompt: str) -> str:
    """Ask a tool-free model to rewrite the running summary."""
    agent = Agent(model, instructions=SUMMARY_INSTRUCTIONS)
    result = await agent.run(prompt)
    output = result.output
    return output if isinstance(output, str) else str(output)


async def update_stored_summary(
    repository: ActionRepository,
    conversation_id: str,
    every: int,
    summarize: Callable[[str], Awaitable[str]],
) -> HistorySummary | None:
    """Fold each ready block into the stored summary and return what the model should see."""
    if every <= 0:
        return None
    messages = repository.list_messages(conversation_id)
    stored = repository.get_chat_summary(conversation_id)
    covered = stored.covered_message_count if stored else 0
    text = stored.summary if stored else ""
    while True:
        bounds = next_summary_slice(len(messages), covered, every)
        if bounds is None:
            break
        start, end = bounds
        updated = (await summarize(summary_prompt(text, messages[start:end]))).strip()
        if not updated:
            break
        text = updated
        covered = end
        repository.save_chat_summary(conversation_id, text, covered)
    if not text.strip():
        return None
    return HistorySummary(text=text, every=every, recent_stored=messages[covered:])


def apply_history_summary(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Replace covered history with the stored summary, leaving the recent tail verbatim."""
    state = current_history_summary.get()
    if state is None or not state.text.strip():
        return messages
    if _starts_with_summary(messages):
        return messages
    if len(messages) < len(state.recent_stored):
        return [_summary_message(state.text), *_stored_as_model_messages(state.recent_stored)]
    kept = _keep_recent(messages, len(state.recent_stored))
    return [_summary_message(state.text), *kept]


def _summary_message(text: str) -> ModelRequest:
    """Build the one message that stands in for older turns."""
    return ModelRequest(parts=[UserPromptPart(content=f"{SUMMARY_LEAD}{text}")])


def _starts_with_summary(messages: list[ModelMessage]) -> bool:
    """Return whether this history was already trimmed earlier in the same turn."""
    if not messages or not isinstance(messages[0], ModelRequest):
        return False
    for part in messages[0].parts:
        if isinstance(part, UserPromptPart) and isinstance(part.content, str) and part.content.startswith(SUMMARY_LEAD):
            return True
    return False


def _stored_as_model_messages(messages: list[StoredMessage]) -> list[ModelMessage]:
    """Turn stored user and assistant text into model messages."""
    converted: list[ModelMessage] = []
    for message in messages:
        if message.role == "assistant":
            converted.append(ModelResponse(parts=[TextPart(content=message.content)]))
        else:
            converted.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
    return converted


def _keep_recent(messages: list[ModelMessage], keep: int) -> list[ModelMessage]:
    """Keep the latest messages, moving the cut earlier when it would split a tool pair."""
    if keep <= 0:
        return []
    if keep >= len(messages):
        return list(messages)
    start = _retreat_for_tool_pairs(messages, len(messages) - keep)
    return list(messages[start:])


def _retreat_for_tool_pairs(messages: list[ModelMessage], start: int) -> int:
    """Move the cut back until every kept tool return still has its call."""
    while start > 0:
        missing = _tool_return_ids(messages[start:]) - _tool_call_ids(messages[start:])
        if not missing:
            return start
        earlier = start
        for index in range(start - 1, -1, -1):
            if _tool_call_ids([messages[index]]) & missing:
                start = index
                break
        if start == earlier:
            return start
    return start


def _tool_call_ids(messages: list[ModelMessage]) -> set[str]:
    """Collect tool call ids from these messages."""
    found: set[str] = set()
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart) and part.tool_call_id:
                found.add(part.tool_call_id)
    return found


def _tool_return_ids(messages: list[ModelMessage]) -> set[str]:
    """Collect tool return ids from these messages."""
    found: set[str] = set()
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_call_id:
                found.add(part.tool_call_id)
    return found
