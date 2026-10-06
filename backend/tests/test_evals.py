"""Purpose: Run the invoice evaluation dataset against the agent tools.

Public API:
- test_invoice_eval_cases
"""

import json
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.chat.agent import build_chat_agent
from app.chat.prompt import SYSTEM_PROMPT
from app.db.schema import create_engine_for
from app.db.repository import ActionRepository
from app.mcp_server.tools import build_mcp_server
from app.runtime import AppServices, current_conversation_id, current_services
from sqlalchemy.orm import sessionmaker

from tests.fakes import FakeInvoiceGateway

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "invoice_cases.json"


def _tool_returns(messages: list) -> list:
    """Collect tool results already present in the model message history."""
    returns = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if type(part).__name__ in {"ToolReturnPart", "BuiltinToolReturnPart"}:
                returns.append(part)
    return returns


@pytest.mark.asyncio
async def test_invoice_eval_cases(tmp_path) -> None:
    """Each case proposes or reads, and does not claim an invoice exists first."""
    assert "Do not say an invoice" in SYSTEM_PROMPT
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    for case in cases:
        fake = FakeInvoiceGateway()
        repository = ActionRepository(sessionmaker(bind=create_engine_for(str(tmp_path / f"{case['id']}.db"))))
        conversation_id = case["id"]
        repository.ensure_conversation(conversation_id)
        server = build_mcp_server()

        def respond(messages, _info, case=case):  # type: ignore[no-untyped-def]
            """Follow the dataset's tool steps, then answer without claiming a write."""
            completed = _tool_returns(messages)
            if len(completed) >= len(case["steps"]):
                return ModelResponse(parts=[TextPart(content=case["final_text"])])
            step = case["steps"][len(completed)]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=step["tool"],
                        args=step["args"],
                        tool_call_id=f"call-{len(completed)}",
                    )
                ]
            )

        agent: Agent = build_chat_agent(FunctionModel(respond), server)
        services = AppServices(invoices=fake, actions=repository)
        services_token = current_services.set(services)
        conversation_token = current_conversation_id.set(conversation_id)
        try:
            result = await agent.run(case["user"])
        finally:
            current_conversation_id.reset(conversation_token)
            current_services.reset(services_token)

        output = str(result.output)
        for phrase in case["forbid_phrases"]:
            assert phrase not in output.casefold()
        assert fake.write_calls == []
        if case.get("expected_action_type"):
            assert "pending" in output.casefold() or "confirm" in output.casefold()
            from sqlalchemy import select
            from app.db.schema import ProposedActionRow

            with repository._session_factory() as session:
                rows = session.scalars(select(ProposedActionRow)).all()
            assert len(rows) == 1
            assert rows[0].action_type == case["expected_action_type"]
            assert rows[0].status == "pending"
        else:
            assert "summarize_invoices" in fake.read_calls
