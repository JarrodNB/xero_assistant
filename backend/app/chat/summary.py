"""Purpose: Fold older chat messages into a stored summary and trim model history.

Public API:
- SUMMARY_MAX_CHARACTERS
- HistorySummary
- apply_history_summary
- current_history_summary
- limit_summary
- next_summary_slice
- summarize_with_model
- summary_prompt
- update_stored_summary
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace

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
from pydantic_ai.usage import UsageLimits
from app.config import Settings
from app.chat.execution import model_settings

from app.chat.guardrails.pii import current_vault
from app.chat.guardrails.redaction import redact_text
from app.db.repository import ActionRepository, StoredMessage

SUMMARY_LEAD = "Summary of the earlier conversation:\n"
SUMMARY_MAX_CHARACTERS = 2000

SUMMARY_INSTRUCTIONS = f"""
You update a running summary of one person's conversation with this assistant.
Summarize the whole conversation. Do not drop a topic because it is outside the subjects you have seen so far.

Keep names, amounts, dates, identifiers, skipped fields, decisions, and whether a proposal is pending, confirmed, or denied.
Do not claim anything was created, updated, or voided unless the transcript says it was executed.
Omit small talk. Do not invent facts. Do not repeat action ids.
When the transcript uses a token such as [redacted_email:1], copy that token unchanged.
Stay within {SUMMARY_MAX_CHARACTERS} characters. Drop the oldest small details first when the summary would exceed that.
""".strip()


@dataclass
class HistorySummary:
    """The summary and verbatim tail for one model request."""

    text: str
    every: int
    recent_stored: list[StoredMessage]
    degraded: bool = False
    server_owned: bool = False
    applied: bool = False


current_history_summary: ContextVar[HistorySummary | None] = ContextVar("current_history_summary", default=None)


def next_summary_slice(message_count: int, covered_count: int, every: int) -> tuple[int, int] | None:
    """Return the next stored-message range to fold, or None when no block is ready."""
    if every <= 0 or message_count <= 0:
        return None
    covered = min(max(covered_count, 0), message_count)
    if message_count - covered < every * 2:
        return None
    return covered, covered + every


def limit_summary(text: str, max_characters: int = SUMMARY_MAX_CHARACTERS) -> str:
    """Trim a summary to the character budget, preferring a sentence boundary."""
    cleaned = text.strip()
    if max_characters < 1:
        return ""
    if len(cleaned) <= max_characters:
        return cleaned
    window = cleaned[:max_characters]
    sentence_end = _last_sentence_end(window)
    if sentence_end >= max_characters // 2:
        return window[:sentence_end].rstrip()
    word_end = window.rfind(" ")
    if word_end > 0:
        return window[:word_end].rstrip()
    return window.rstrip()


def summary_prompt(previous: str, messages: list[StoredMessage]) -> str:
    """Build the redacted prompt for one summary update."""
    lines = [
        "Update the running summary using the earlier summary and the new messages.",
        f"Stay within {SUMMARY_MAX_CHARACTERS} characters.",
    ]
    if previous.strip():
        lines.append("Earlier summary:")
        lines.append(redact_text(previous))
    lines.append("Messages:")
    for message in messages:
        lines.append(f"{message.role}: {redact_text(message.content)}")
    return "\n".join(lines)


async def summarize_with_model(model: str | Model, prompt: str, settings: Settings | None = None) -> str:
    """Ask a tool-free model to rewrite the running summary."""
    agent = Agent(model, name="summary", instructions=SUMMARY_INSTRUCTIONS,
                  retries=settings.ai_validation_retries if settings else 1)
    result = await agent.run(prompt,
        model_settings=model_settings(settings, summary=True) if settings else {"max_tokens": 768, "timeout": 10},
        usage_limits=UsageLimits(request_limit=settings.summary_request_limit if settings else 2,
            total_tokens_limit=settings.summary_token_limit if settings else 4000, tool_calls_limit=0))
    output = result.output
    return output if isinstance(output, str) else str(output)


async def update_stored_summary(
    repository: ActionRepository,
    conversation_id: str,
    every: int,
    summarize: Callable[[str], Awaitable[str]],
    *, max_blocks: int = 1, recent_limit: int = 20, character_limit: int = 12000,
) -> HistorySummary:
    """Fold each ready block into the stored summary and return what the model should see."""
    messages = repository.list_messages(conversation_id)
    stored = repository.get_chat_summary(conversation_id)
    covered = stored.covered_message_count if stored else 0
    text = stored.summary if stored else ""
    degraded = False
    for _ in range(max_blocks):
        bounds = next_summary_slice(len(messages), covered, every)
        if bounds is None:
            break
        start, end = bounds
        try:
            updated = limit_summary((await summarize(summary_prompt(text, messages[start:end]))).strip())
        except Exception:
            degraded = True
            break
        vault = current_vault.get()
        if vault is not None and updated:
            updated = vault.restore_text(updated)
        if not updated:
            degraded = True
            break
        try:
            repository.save_chat_summary(conversation_id, updated, end)
        except Exception:
            degraded = True
            break
        text, covered = updated, end
    recent = messages[covered:][-recent_limit:]
    remaining = character_limit
    bounded: list[StoredMessage] = []
    for message in reversed(recent):
        if remaining <= 0:
            break
        content = message.content[:remaining]
        bounded.append(replace(message, content=content))
        remaining -= len(content)
    bounded.reverse()
    degraded = degraded or len(bounded) < len(messages[covered:]) or any(
        old.content != new.content for old, new in zip(recent[-len(bounded):], bounded))
    return HistorySummary(text=text, every=every, recent_stored=bounded, degraded=degraded, server_owned=True)


def apply_history_summary(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Replace covered history with the stored summary, leaving the recent tail verbatim."""
    state = current_history_summary.get()
    if state is None:
        return messages
    if state.server_owned and state.applied:
        return messages
    if state.server_owned:
        state.applied = True
        text = state.text or "No earlier summary; use the recent stored conversation."
        if state.degraded:
            text += "\nSome earlier context is unavailable. Ask for missing details; do not guess contacts, amounts, dates, or execution outcomes."
        return [_summary_message(text), *_stored_as_model_messages(state.recent_stored)]
    if _starts_with_summary(messages):
        return messages
    text = state.text
    if state.degraded:
        text += "\nSome earlier context is unavailable. Ask for missing details; do not guess contacts, amounts, dates, or execution outcomes."
    if not text.strip() and not state.degraded:
        return [_summary_message("No earlier summary; use the recent stored conversation."),
                *_stored_as_model_messages(state.recent_stored)]
    if len(messages) < len(state.recent_stored) or state.degraded:
        return [_summary_message(text), *_stored_as_model_messages(state.recent_stored)]
    kept = _keep_recent(messages, len(state.recent_stored))
    return [_summary_message(text), *kept]


def _last_sentence_end(text: str) -> int:
    """Return the index after the last sentence end, or -1 when the text has none."""
    end = -1
    for index, char in enumerate(text):
        if char not in ".!?":
            continue
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if char == "." and previous.isdigit() and following.isdigit():
            continue
        if following and not following.isspace():
            continue
        end = index + 1
    return end


def _for_model(text: str) -> str:
    """Protect stored text when this turn has a vault, and leave tests that have none unchanged."""
    if current_vault.get() is None:
        return text
    return redact_text(text)


def _summary_message(text: str) -> ModelRequest:
    """Build the one message that stands in for older turns."""
    return ModelRequest(parts=[UserPromptPart(content=f"{SUMMARY_LEAD}{_for_model(text)}")])


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
            converted.append(ModelResponse(parts=[TextPart(content=_for_model(message.content))]))
        else:
            converted.append(ModelRequest(parts=[UserPromptPart(content=_for_model(message.content))]))
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
