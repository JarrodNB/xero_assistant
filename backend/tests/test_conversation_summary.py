"""Purpose: Tests for folding older chat turns into a stored summary.

Public API:
- test_summary_slice_waits_for_a_full_block
- test_summary_runs_once_per_block_and_redacts_first
- test_summary_text_stays_within_the_character_budget
- test_stored_summary_is_capped_before_save
- test_chat_summary_round_trip
- test_history_trim_keeps_a_tool_call_with_its_result
- test_short_history_uses_the_stored_tail
- test_summary_already_applied_is_left_alone
"""

from datetime import datetime, timezone

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy.orm import sessionmaker

from app.chat.summary import (
    SUMMARY_INSTRUCTIONS,
    SUMMARY_MAX_CHARACTERS,
    HistorySummary,
    apply_history_summary,
    current_history_summary,
    limit_summary,
    next_summary_slice,
    summary_prompt,
    update_stored_summary,
)
from app.db.repository import ActionRepository, StoredMessage
from app.db.schema import create_engine_for
from tests.test_guardrails import CARD


def test_summary_slice_waits_for_a_full_block() -> None:
    """A block is folded only when another full window sits outside the recent tail."""
    assert next_summary_slice(19, 0, 10) is None
    assert next_summary_slice(20, 0, 10) == (0, 10)
    assert next_summary_slice(29, 10, 10) is None
    assert next_summary_slice(30, 10, 10) == (10, 20)
    assert next_summary_slice(40, 0, 0) is None


@pytest.mark.asyncio
async def test_summary_runs_once_per_block_and_redacts_first(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The summarizer sees redacted text and runs once per ready block."""
    repository = _repository(tmp_path)
    repository.ensure_conversation("thread")
    for index in range(20):
        role = "user" if index % 2 == 0 else "assistant"
        content = f"message {index}"
        if index == 3:
            content = f"Use card {CARD}"
        repository.add_message("thread", role, content)
    prompts: list[str] = []

    async def summarize(prompt: str) -> str:
        """Record the prompt and return a stand-in summary."""
        prompts.append(prompt)
        return f"summary {len(prompts)}"

    first = await update_stored_summary(repository, "thread", 10, summarize)
    assert first is not None
    assert len(prompts) == 1
    assert CARD not in prompts[0]
    assert "[redacted:credit_card]" in prompts[0]
    assert first.recent_stored[0].content == "message 10"
    stored = repository.get_chat_summary("thread")
    assert stored is not None
    assert stored.covered_message_count == 10
    assert stored.summary == "summary 1"

    for index in range(20, 25):
        repository.add_message("thread", "user" if index % 2 == 0 else "assistant", f"message {index}")
    second = await update_stored_summary(repository, "thread", 10, summarize)
    assert second is not None
    assert len(prompts) == 1
    assert len(second.recent_stored) == 15

    for index in range(25, 30):
        repository.add_message("thread", "user" if index % 2 == 0 else "assistant", f"message {index}")
    third = await update_stored_summary(repository, "thread", 10, summarize)
    assert third is not None
    assert len(prompts) == 2
    assert "summary 1" in prompts[1]
    assert third.recent_stored[0].content == "message 20"
    assert repository.get_chat_summary("thread").covered_message_count == 20  # type: ignore[union-attr]


def test_summary_text_stays_within_the_character_budget() -> None:
    """A short summary is kept, and a long one is cut on a sentence or a word."""
    assert str(SUMMARY_MAX_CHARACTERS) in SUMMARY_INSTRUCTIONS
    prompt = summary_prompt("", [StoredMessage("1", "thread", "user", "Invoice Ada", _now())])
    assert str(SUMMARY_MAX_CHARACTERS) in prompt
    assert limit_summary("Ada owes 55.50.") == "Ada owes 55.50."
    limited = limit_summary("Ada owes 55.50. " + ("Pending invoice detail. " * 200))
    assert len(limited) <= SUMMARY_MAX_CHARACTERS
    assert limited.startswith("Ada owes 55.50.")
    assert limited.endswith(".")
    word_cut = limit_summary("Start. " + ("word " * 1000), max_characters=80)
    assert len(word_cut) <= 80
    assert word_cut.endswith("word")


@pytest.mark.asyncio
async def test_stored_summary_is_capped_before_save(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The repository stores the trimmed summary, not the model's full reply."""
    repository = _repository(tmp_path)
    repository.ensure_conversation("thread")
    for index in range(20):
        repository.add_message("thread", "user" if index % 2 == 0 else "assistant", f"message {index}")

    async def summarize(_prompt: str) -> str:
        """Return a summary longer than the stored budget."""
        return "Ada owes 55.50. " + ("Pending invoice detail. " * 200)

    await update_stored_summary(repository, "thread", 10, summarize)
    stored = repository.get_chat_summary("thread")
    assert stored is not None
    assert len(stored.summary) <= SUMMARY_MAX_CHARACTERS
    assert stored.summary.startswith("Ada owes 55.50.")
    assert stored.covered_message_count == 10


def test_chat_summary_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A saved summary reloads with the count of messages it covers."""
    repository = _repository(tmp_path)
    repository.ensure_conversation("thread")
    repository.add_message("thread", "user", "Invoice Ada for 55")
    saved = repository.save_chat_summary("thread", "Ada owes 55.", 1)
    loaded = repository.get_chat_summary("thread")
    assert loaded is not None
    assert loaded.summary == saved.summary
    assert loaded.covered_message_count == 1
    messages = repository.list_messages("thread")
    assert [message.content for message in messages] == ["Invoice Ada for 55"]


def test_history_trim_keeps_a_tool_call_with_its_result() -> None:
    """A cut that would start on a tool return moves back to include the call."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content="old")]),
        ModelResponse(parts=[ToolCallPart(tool_name="find_contacts", args={"name": "Ada"}, tool_call_id="call-1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="find_contacts", content="found", tool_call_id="call-1")]),
        ModelRequest(parts=[UserPromptPart(content="recent question")]),
        ModelResponse(parts=[TextPart(content="recent answer")]),
    ]
    state = HistorySummary(text="Earlier, Ada was discussed.", every=10, recent_stored=_stored(3))
    token = current_history_summary.set(state)
    try:
        trimmed = apply_history_summary(messages)
    finally:
        current_history_summary.reset(token)
    texts = _visible_text(trimmed)
    assert texts[0].startswith("Summary of the earlier conversation:")
    assert "old" not in texts
    assert "recent question" in texts
    assert "recent answer" in texts
    call_ids = [
        part.tool_call_id
        for message in trimmed
        for part in getattr(message, "parts", [])
        if isinstance(part, (ToolCallPart, ToolReturnPart))
    ]
    assert call_ids == ["call-1", "call-1"]


def test_short_history_uses_the_stored_tail() -> None:
    """A refreshed client sends fewer messages, so the stored tail is restored."""
    recent = [
        StoredMessage("1", "thread", "user", "Invoice Ada for 55", _now()),
        StoredMessage("2", "thread", "assistant", "I proposed an invoice for Ada.", _now()),
    ]
    state = HistorySummary(text="Nothing older.", every=10, recent_stored=recent)
    incoming = [ModelRequest(parts=[UserPromptPart(content="new question")])]
    token = current_history_summary.set(state)
    try:
        trimmed = apply_history_summary(incoming)
    finally:
        current_history_summary.reset(token)
    assert _visible_text(trimmed) == [
        "Summary of the earlier conversation:\nNothing older.",
        "Invoice Ada for 55",
        "I proposed an invoice for Ada.",
    ]


def test_summary_already_applied_is_left_alone() -> None:
    """A later model request in the same turn does not rebuild the summary."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content="Summary of the earlier conversation:\nAda owes 55.")]),
        ModelResponse(parts=[ToolCallPart(tool_name="find_contacts", args={}, tool_call_id="call-2")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="find_contacts", content="found", tool_call_id="call-2")]),
    ]
    state = HistorySummary(text="Ada owes 55.", every=10, recent_stored=_stored(1))
    token = current_history_summary.set(state)
    try:
        trimmed = apply_history_summary(messages)
    finally:
        current_history_summary.reset(token)
    assert trimmed == messages


def _repository(tmp_path) -> ActionRepository:  # type: ignore[no-untyped-def]
    """Open a repository on a temporary SQLite file."""
    return ActionRepository(sessionmaker(bind=create_engine_for(str(tmp_path / "app.db"))))


def _stored(count: int) -> list[StoredMessage]:
    """Build placeholder stored messages so the trim keeps that many model messages."""
    return [StoredMessage(str(index), "thread", "user", f"kept {index}", _now()) for index in range(count)]


def _now() -> datetime:
    """Return a fixed timestamp for stored-message fixtures."""
    return datetime(2026, 10, 7, tzinfo=timezone.utc)


def _visible_text(messages: list[object]) -> list[str]:
    """Collect user and assistant text from model messages."""
    texts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str) and isinstance(part, (UserPromptPart, TextPart)):
                texts.append(content)
    return texts
