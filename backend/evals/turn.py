"""Purpose: Run one golden-dataset prompt against the fake invoice gateway.

Public API:
- run_scored_prompt
"""

import uuid
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.runtime import AppServices, current_conversation_id, current_services
from evals.trace import TRACE_HEADING, format_tool_trace
from tests.fakes import FakeInvoiceGateway


async def run_scored_prompt(agent: object, gateway: FakeInvoiceGateway, directory: Path, prompt: str) -> str:
    """Run one prompt and return the answer plus its tool trace."""
    conversation_id = str(uuid.uuid4())
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(directory / f"{conversation_id}.db"))))
    repository.ensure_conversation(conversation_id)
    services = AppServices(invoices=gateway, actions=repository)
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set(conversation_id)
    try:
        result = await agent.run(prompt)  # type: ignore[attr-defined]
    finally:
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)
    return f"{result.output}{TRACE_HEADING}{format_tool_trace(result)}"
