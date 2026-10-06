"""Purpose: Store conversations, messages, and proposed actions.

Public API:
- ActionRepository
- StoredAction
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import ConversationRow, MessageRow, ProposedActionRow, utcnow


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
            existing = session.get(ConversationRow, conversation_id)
            if existing is None:
                session.add(ConversationRow(id=conversation_id))
                session.commit()
        return conversation_id

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

    def get_action(self, action_id: str) -> StoredAction | None:
        """Return one action, or None when the id is unknown."""
        with self._session_factory() as session:
            row = session.get(ProposedActionRow, action_id)
            if row is None:
                return None
            return _to_stored(row)

    def update_pending_payload(self, action_id: str, payload: dict, summary: str) -> StoredAction | None:
        """Replace the payload and summary while the action is still pending."""
        with self._session_factory() as session:
            row = session.get(ProposedActionRow, action_id)
            if row is None or row.status != "pending":
                return None
            row.payload_json = json.dumps(payload)
            row.summary = summary
            row.updated_at = utcnow()
            session.commit()
            session.refresh(row)
            return _to_stored(row)

    def update_action(self, action_id: str, status: str, result: dict) -> StoredAction:
        """Set the status and result of an existing action."""
        with self._session_factory() as session:
            row = session.get(ProposedActionRow, action_id)
            if row is None:
                raise KeyError(action_id)
            row.status = status
            row.result_json = json.dumps(result)
            row.updated_at = utcnow()
            session.commit()
            session.refresh(row)
            return _to_stored(row)


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
