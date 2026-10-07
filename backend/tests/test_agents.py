"""Purpose: Check the orchestrator delegates reads and proposes writes itself.

Public API:
- test_create_flow_delegates_then_proposes
- test_invoices_agent_has_read_tools_only
- test_invoices_script_picks_each_read_tool
- test_invoice_question_reaches_the_gateway
- test_missing_reference_asks_once
- test_orchestrator_tools_are_delegate_and_propose
- test_skip_proposes_without_delegating
"""

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.orm import sessionmaker

from app.chat.invoices_agent import INVOICE_READ_TOOLS, build_invoices_agent
from app.chat.orchestrator import build_chat_agent
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.mcp_server.server import build_mcp_server
from app.runtime import AppServices, current_conversation_id, current_services
from evals.invoices.scripted import scripted_invoices_model
from evals.orchestrator.scripted import scripted_orchestrator_model
from tests.fakes import FakeInvoiceGateway


@pytest.mark.asyncio
async def test_invoices_agent_has_read_tools_only() -> None:
    """The invoices agent can look up contacts and invoices and cannot propose."""
    seen: dict[str, set[str]] = {}

    def respond(_messages, info):  # type: ignore[no-untyped-def]
        """Record the child tool names and stop."""
        seen["tools"] = {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[TextPart(content="No rows.")])

    agent = build_invoices_agent(FunctionModel(respond), build_mcp_server())
    await agent.run("List invoices")
    assert seen["tools"] == set(INVOICE_READ_TOOLS)
    assert "propose_action" not in seen["tools"]
    assert "delegate_task" not in seen["tools"]


@pytest.mark.asyncio
async def test_orchestrator_tools_are_delegate_and_propose() -> None:
    """The parent can delegate and propose, and it cannot call the read tools."""
    seen: dict[str, set[str]] = {}

    def respond(_messages, info):  # type: ignore[no-untyped-def]
        """Record the parent tool names and stop."""
        seen["tools"] = {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[TextPart(content="Nothing was created.")])

    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    await agent.run("How much is unpaid?")
    assert seen["tools"] == {"delegate_task", "propose_action"}


@pytest.mark.asyncio
async def test_invoices_script_picks_each_read_tool(tmp_path: Path) -> None:
    """The invoices stand-in calls the read tool named by each task."""
    prompts = (
        ("How much is currently unpaid?", "summarize_invoices"),
        ("Which invoices are overdue?", "find_invoices"),
        ("Does a contact named Bob's Construction exist?", "find_contacts"),
        ("Was revenue higher in February 2026 than in January 2026?", "compare_invoice_totals"),
        ("Load invoice INV-1001.", "get_invoice"),
    )
    gateway = FakeInvoiceGateway()
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(tmp_path / "conv-1.db"))))
    repository.ensure_conversation("conv-1")
    services = AppServices(invoices=gateway, actions=repository)
    agent = build_invoices_agent(scripted_invoices_model(), build_mcp_server())
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set("conv-1")
    try:
        for prompt, tool_name in prompts:
            result = await agent.run(prompt)
            names = _tool_names(result)
            assert names == [tool_name]
    finally:
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)


@pytest.mark.asyncio
async def test_invoice_question_reaches_the_gateway(tmp_path: Path) -> None:
    """An unpaid question delegates to invoices and summarizes on the fake gateway."""
    gateway = FakeInvoiceGateway()
    result = await _run(tmp_path, "How much is currently unpaid?", gateway)
    assert "summarize_invoices" in gateway.read_calls
    assert _tool_names(result) == ["delegate_task"]
    assert gateway.write_calls == []


@pytest.mark.asyncio
async def test_create_flow_delegates_then_proposes(tmp_path: Path) -> None:
    """A complete create request looks up the contact, then proposes the reference and due date."""
    gateway = FakeInvoiceGateway()
    prompt = "Send an invoice to Bob's Construction for $55. Reference PO-9. Due date 2026-10-21."
    result = await _run(tmp_path, prompt, gateway)
    assert "find_contacts" in gateway.read_calls
    assert _tool_names(result) == ["delegate_task", "propose_action"]
    proposed = _tool_returns(result, "propose_action")
    assert any("create_invoice" in item and "pending" in item and "PO-9" in item and "2026-10-21" in item for item in proposed)
    assert gateway.write_calls == []


@pytest.mark.asyncio
async def test_skip_proposes_without_delegating(tmp_path: Path) -> None:
    """Skip stores one invoice proposal and does not delegate that call."""
    gateway = FakeInvoiceGateway()
    prompt = "Earlier I asked for an invoice to Bob's Construction for $55. You asked for a reference and a due date. skip"
    result = await _run(tmp_path, prompt, gateway)
    assert _tool_names(result) == ["propose_action"]
    assert gateway.read_calls == []
    assert gateway.write_calls == []


@pytest.mark.asyncio
async def test_missing_reference_asks_once(tmp_path: Path) -> None:
    """A missing reference delegates the lookup and does not propose."""
    gateway = FakeInvoiceGateway()
    prompt = "Create an invoice for Bob's Construction for $55. I have not given a reference or a due date."
    result = await _run(tmp_path, prompt, gateway)
    assert "find_contacts" in gateway.read_calls
    assert "propose_action" not in _tool_names(result)
    assert "14 days" in str(result.output)
    assert gateway.write_calls == []


def _tool_names(result: object) -> list[str]:
    """Return parent tool names in call order."""
    names: list[str] = []
    for message in result.all_messages():  # type: ignore[attr-defined]
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                names.append(part.tool_name)
    return names


def _tool_returns(result: object, tool_name: str) -> list[str]:
    """Return the text of one tool's results."""
    found: list[str] = []
    for message in result.all_messages():  # type: ignore[attr-defined]
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                found.append(str(part.content))
    return found


async def _run(directory: Path, prompt: str, gateway: FakeInvoiceGateway):
    """Run one scripted orchestrator turn against the fake gateway."""
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(directory / "conv-1.db"))))
    repository.ensure_conversation("conv-1")
    services = AppServices(invoices=gateway, actions=repository)
    agent = build_chat_agent(scripted_orchestrator_model(), build_mcp_server())
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set("conv-1")
    try:
        return await agent.run(prompt)
    finally:
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)
