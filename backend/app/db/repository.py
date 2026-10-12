"""Purpose: Store conversations, messages, and proposed actions.

Public API:
- ActionRepository
- ConversationSummary
- StoredAction
- StoredChatSummary
- StoredMessage
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import ConversationRow, ConversationSummaryRow, MessageRow, ProposedActionRow, utcnow

_PREVIEW_LENGTH = 80
_NARRATION_PREFIXES = (
    "The user confirmed action ",
    "The user denied action ",
)


@dataclass
class StoredMessage:
    """One chat message loaded from SQLite."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


@dataclass
class StoredChatSummary:
    """The running summary of older messages in one thread."""

    conversation_id: str
    summary: str
    covered_message_count: int
    updated_at: datetime


@dataclass
class ConversationSummary:
    """A thread shown in the chat history list."""

    id: str
    updated_at: datetime
    preview: str


@dataclass
class StoredAction:
    """A proposed action loaded from SQLite."""

    id: str
    conversation_id: str
    action_type: str
    payload: dict
    summary: str
    status: str
    result: dict | None
    created_at: datetime
    updated_at: datetime


class ActionRepository:
    """Read and write chat state in SQLite."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Keep the session factory for short-lived transactions."""
        self._session_factory = session_factory

    def ensure_conversation(self, conversation_id: str) -> str:
        """Create the conversation when it does not already exist."""
        with self._session_factory() as session:
            session.execute(insert(ConversationRow).values(id=conversation_id).on_conflict_do_nothing(index_elements=["id"]))
            session.commit()
        return conversation_id

    def list_conversations(self) -> list[ConversationSummary]:
        """Return threads that have messages, newest activity first."""
        with self._session_factory() as session:
            conversations = session.scalars(select(ConversationRow)).all()
            summaries: list[ConversationSummary] = []
            for conversation in conversations:
                messages = session.scalars(
                    select(MessageRow)
                    .where(MessageRow.conversation_id == conversation.id)
                    .order_by(MessageRow.created_at, MessageRow.id)
                ).all()
                if not messages:
                    continue
                preview = ""
                for message in messages:
                    if message.role == "user" and not _is_narration(message.content):
                        preview = _preview(message.content)
                        break
                updated_at = max(message.created_at for message in messages)
                summaries.append(ConversationSummary(id=conversation.id, updated_at=updated_at, preview=preview))
        summaries.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return summaries

    def get_conversation(self, conversation_id: str) -> tuple[list[StoredMessage], list[StoredAction]] | None:
        """Return messages and proposed actions, or None when the thread is unknown."""
        with self._session_factory() as session:
            if session.get(ConversationRow, conversation_id) is None:
                return None
            messages = session.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.created_at, MessageRow.id)
            ).all()
            actions = session.scalars(
                select(ProposedActionRow)
                .where(ProposedActionRow.conversation_id == conversation_id)
                .order_by(ProposedActionRow.created_at, ProposedActionRow.id)
            ).all()
            return (
                [_to_message(row) for row in messages],
                [_to_stored(row) for row in actions],
            )

    def list_messages(self, conversation_id: str) -> list[StoredMessage]:
        """Return a conversation's messages in stored order."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.created_at, MessageRow.id)
            ).all()
            return [_to_message(row) for row in rows]

    def get_chat_summary(self, conversation_id: str) -> StoredChatSummary | None:
        """Return the running summary, or None when this thread has not been summarized."""
        with self._session_factory() as session:
            row = session.get(ConversationSummaryRow, conversation_id)
            if row is None:
                return None
            return _to_chat_summary(row)

    def save_chat_summary(self, conversation_id: str, summary: str, covered_message_count: int) -> StoredChatSummary:
        """Insert or replace the running summary for a conversation."""
        now = utcnow()
        with self._session_factory() as session:
            row = session.get(ConversationSummaryRow, conversation_id)
            if row is None:
                row = ConversationSummaryRow(
                    conversation_id=conversation_id,
                    summary=summary,
                    covered_message_count=covered_message_count,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.summary = summary
                row.covered_message_count = covered_message_count
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _to_chat_summary(row)

    def add_message(self, conversation_id: str, role: str, content: str) -> str:
        """Append a message to a conversation."""
        message_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                MessageRow(
                    id=message_id,
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                )
            )
            session.commit()
        return message_id

    def create_action(self, conversation_id: str, action_type: str, payload: dict, summary: str) -> StoredAction:
        """Insert a pending action and return it."""
        action_id = str(uuid.uuid4())
        now = utcnow()
        with self._session_factory() as session:
            session.add(
                ProposedActionRow(
                    id=action_id,
                    conversation_id=conversation_id,
                    action_type=action_type,
                    payload_json=json.dumps(payload),
                    summary=summary,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        stored = self.get_action(action_id)
        if stored is None:
            raise RuntimeError("Proposed action was not saved.")
        return stored

    def create_ui_action(self, request_id: str, action_type: str, payload: dict, summary: str) -> StoredAction:
        """Persist one editor write receipt, returning the original on duplicate submission."""
        action_id = f"ui-{request_id}"
        conversation_id = "ui-write-receipts"
        with self._session_factory() as session:
            session.execute(insert(ConversationRow).values(id=conversation_id).on_conflict_do_nothing(index_elements=["id"]))
            session.execute(insert(ProposedActionRow).values(
                id=action_id, conversation_id=conversation_id, action_type=action_type,
                payload_json=json.dumps(payload), summary=summary, status="pending",
            ).on_conflict_do_nothing(index_elements=["id"]))
            session.commit()
        stored = self.get_action(action_id)
        if stored is None:
            raise RuntimeError("Editor write receipt was not saved.")
        return stored

    def get_action(self, action_id: str) -> StoredAction | None:
        """Return one action, or None when the id is unknown."""
        with self._session_factory() as session:
            row = session.get(ProposedActionRow, action_id)
            if row is None:
                return None
            return _to_stored(row)

    def claim_action(self, action: StoredAction, payload: dict, summary: str) -> StoredAction | None:
        """Atomically freeze the confirmation payload and claim its pending write."""
        with self._session_factory() as session:
            changed = session.execute(
                update(ProposedActionRow)
                .where(
                    ProposedActionRow.id == action.id,
                    ProposedActionRow.status == "pending",
                    ProposedActionRow.updated_at == action.updated_at,
                )
                .values(payload_json=json.dumps(payload), summary=summary, status="executing", updated_at=utcnow())
            )
            session.commit()
            if changed.rowcount != 1:
                return None
        return self.get_action(action.id)

    def transition_action(self, action_id: str, expected_status: str, status: str, result: dict) -> StoredAction | None:
        """Record a result only when this action is still in the expected state."""
        with self._session_factory() as session:
            changed = session.execute(
                update(ProposedActionRow)
                .where(ProposedActionRow.id == action_id, ProposedActionRow.status == expected_status)
                .values(status=status, result_json=json.dumps(result), updated_at=utcnow())
            )
            session.commit()
            if changed.rowcount != 1:
                return None
        return self.get_action(action_id)

    def recover_stale_action(self, action_id: str, cutoff: datetime) -> None:
        """Quarantine an abandoned claim without replaying a potentially successful write."""
        with self._session_factory() as session:
            session.execute(
                update(ProposedActionRow)
                .where(
                    ProposedActionRow.id == action_id,
                    ProposedActionRow.status == "executing",
                    ProposedActionRow.updated_at < cutoff,
                )
                .values(status="unknown", updated_at=utcnow(), result_json=json.dumps({
                    "action_id": action_id,
                    "status": "unknown",
                    "what": "Execution outcome is unknown",
                    "why": "The server did not record a final result for this write.",
                    "retryable": False,
                    "next_step": "Check Xero before proposing another write; this action will not be replayed.",
                }))
            )
            session.commit()


def _is_narration(content: str) -> bool:
    """Return whether a user message is a confirm or deny note for the model."""
    text = content.strip()
    return text.startswith(_NARRATION_PREFIXES)


def _preview(content: str) -> str:
    """Shorten a user message for the history list."""
    compact = " ".join(content.split())
    return compact[:_PREVIEW_LENGTH]


def _to_chat_summary(row: ConversationSummaryRow) -> StoredChatSummary:
    """Map a table row into a stored chat summary."""
    return StoredChatSummary(
        conversation_id=row.conversation_id,
        summary=row.summary,
        covered_message_count=row.covered_message_count,
        updated_at=row.updated_at,
    )


def _to_message(row: MessageRow) -> StoredMessage:
    """Map a table row into a stored message."""
    return StoredMessage(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


def _to_stored(row: ProposedActionRow) -> StoredAction:
    """Map a table row into a stored action."""
    result = json.loads(row.result_json) if row.result_json else None
    return StoredAction(
        id=row.id,
        conversation_id=row.conversation_id,
        action_type=row.action_type,
        payload=json.loads(row.payload_json),
        summary=row.summary,
        status=row.status,
        result=result,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
