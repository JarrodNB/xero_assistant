"""Purpose: SQLite tables for conversations, messages, proposed actions, and the Xero connection.

Public API:
- Base
- ConversationRow
- MessageRow
- ConversationSummaryRow
- ProposedActionRow
- XeroConnectionRow
- create_engine_for
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy base for application tables."""


def utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


class ConversationRow(Base):
    """One chat thread."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRow(Base):
    """One stored chat message."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationSummaryRow(Base):
    """The running summary of older messages in one thread."""

    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text)
    covered_message_count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class XeroConnectionRow(Base):
    """The one Demo Company authorisation for this server."""

    __tablename__ = "xero_connection"

    id: Mapped[int] = mapped_column(primary_key=True)
    refresh_token: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[str] = mapped_column(String)
    tenant_name: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposedActionRow(Base):
    """A write the model proposed and a person has not yet finished."""

    __tablename__ = "proposed_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    action_type: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def create_engine_for(database_path: str) -> Engine:
    """Open SQLite and create tables."""
    if database_path == ":memory:":
        url = "sqlite://"
    else:
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{database_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        """Turn on SQLite foreign key checks for this connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine
