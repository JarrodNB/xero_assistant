"""Purpose: Run one golden-dataset prompt against the fake invoice gateway.

Public API:
- run_scored_prompt
- ConversationInput
- HistoryMessage
"""

import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

from sqlalchemy.orm import sessionmaker

from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.runtime import AppServices, current_conversation_id, current_services
from app.chat.guardrails.pii import PiiVault, current_vault
from app.chat.guardrails.redaction import redact_text
from app.chat.guardrails.context import GuardrailMessage, current_guardrail_context, prepare_guardrail_input
from evals.trace import TRACE_HEADING, format_tool_trace
from tests.fakes import FakeInvoiceGateway


class HistoryMessage(BaseModel):
    """One synthetic prior user or assistant message for a conversation evaluation."""

    role: Literal["user", "assistant"]
    content: str


class ConversationInput(BaseModel):
    """A latest prompt with actual prior turns, rather than a prose history summary."""

    prompt: str
    previous_messages: list[HistoryMessage] = Field(default_factory=list)


async def run_scored_prompt(
    agent: object, gateway: FakeInvoiceGateway, directory: Path, prompt: str | ConversationInput
) -> str:
    """Run one prompt and return the answer plus its tool trace."""
    conversation_id = str(uuid.uuid4())
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(directory / f"{conversation_id}.db"))))
    repository.ensure_conversation(conversation_id)
    services = AppServices(invoices=gateway, actions=repository)
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set(conversation_id)
    vault_token = current_vault.set(PiiVault())
    guardrail_token = None
    try:
        case = ConversationInput(prompt=prompt) if isinstance(prompt, str) else prompt
        prepared = prepare_guardrail_input(case.prompt, [
            GuardrailMessage(role=message.role, content=message.content) for message in case.previous_messages
        ])
        guardrail_token = current_guardrail_context.set(prepared.context)
        history = [
            ModelRequest(parts=[UserPromptPart(content=redact_text(message.content))])
            if message.role == "user"
            else ModelResponse(parts=[TextPart(content=redact_text(message.content))])
            for message in case.previous_messages
        ]
        result = await agent.run(  # type: ignore[attr-defined]
            prepared.prompt, message_history=history,
            usage_limits=UsageLimits(request_limit=12, tool_calls_limit=12, total_tokens_limit=20000),
        )
        return f"{redact_text(str(result.output))}{TRACE_HEADING}{format_tool_trace(result)}"
    finally:
        if guardrail_token is not None:
            current_guardrail_context.reset(guardrail_token)
        current_vault.reset(vault_token)
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)
