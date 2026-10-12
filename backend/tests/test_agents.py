"""Purpose: Check the orchestrator delegates reads and proposes writes itself.

Public API:
- test_create_flow_delegates_then_proposes
- test_invoices_agent_has_read_tools_only
- test_invoices_script_picks_each_read_tool
- test_invoice_question_reaches_the_gateway
- test_missing_reference_proposes_immediately
- test_orchestrator_receives_current_date
- test_orchestrator_tools_are_delegate_and_propose
- test_skip_proposes_without_delegating
- test_partial_optional_fields_are_preserved
- test_same_contact_follow_up_uses_actual_history
- test_scored_history_is_protected
- test_required_amount_still_needs_clarification
- test_contact_without_email_proposes
"""

import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.orm import sessionmaker

from app.chat.invoices_agent import INVOICE_READ_TOOLS, build_invoices_agent
from app.chat.orchestrator import build_chat_agent
from app.chat.guardrails.pii import current_vault
from app.chat.guardrails.context import current_guardrail_context
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.mcp_server.server import build_mcp_server
from app.runtime import AppServices, current_conversation_id, current_services
from evals.invoices.scripted import scripted_invoices_model
from evals.orchestrator.scripted import scripted_orchestrator_model
from evals.turn import ConversationInput, HistoryMessage, run_scored_prompt
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
async def test_orchestrator_receives_current_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each model run receives the current date for resolving relative dates."""
    from app.chat import prompt as prompt_module

    class OctoberTenth(prompt_module.date):
        """Return a stable date for the prompt regression test."""

        @classmethod
        def today(cls) -> "OctoberTenth":
            """Return October 10, 2026."""
            return cls(2026, 10, 10)

    seen: list[str] = []

    def respond(_messages, info):  # type: ignore[no-untyped-def]
        """Record system instructions and stop."""
        seen.append(info.instructions or "")
        return ModelResponse(parts=[TextPart(content="Nothing was created.")])

    monkeypatch.setattr(prompt_module, "date", OctoberTenth)
    agent = build_chat_agent(FunctionModel(respond), build_mcp_server())
    await agent.run("Create an invoice due tomorrow.")

    instructions = "\n".join(seen)
    assert "Today's date is 2026-10-10" in instructions
    assert "relative dates" in instructions


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
async def test_missing_reference_proposes_immediately(tmp_path: Path) -> None:
    """Missing optional fields do not prevent a proposal after contact lookup."""
    gateway = FakeInvoiceGateway()
    prompt = "Create an invoice for Bob's Construction for $55. I have not given a reference or a due date."
    result = await _run(tmp_path, prompt, gateway)
    assert "find_contacts" in gateway.read_calls
    assert _tool_names(result) == ["delegate_task", "propose_action"]
    assert gateway.write_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "expected", "omitted"),
    [
        ("Create an invoice for Bob's Construction for $55 for Labour. Reference PO-9.", {"reference": "PO-9"}, "due_date"),
        ("Create an invoice for Bob's Construction for $55 for Labour. Due date 2026-10-21.", {"due_date": "2026-10-21"}, "reference"),
    ],
)
async def test_partial_optional_fields_are_preserved(
    tmp_path: Path, prompt: str, expected: dict, omitted: str
) -> None:
    """A supplied optional field survives without requiring the other field."""
    result = await _run(tmp_path, prompt, FakeInvoiceGateway())
    calls = [
        part for message in result.new_messages() for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name == "propose_action"
    ]
    assert len(calls) == 1
    payload = json.loads(calls[0].args_as_dict()["payload_json"])
    assert all(payload[key] == value for key, value in expected.items())
    assert omitted not in payload
    assert "pending" in _tool_returns(result, "propose_action")[0]


@pytest.mark.asyncio
async def test_same_contact_follow_up_uses_actual_history(tmp_path: Path) -> None:
    """A required contact follow-up proposes the historical amount without another optional turn."""
    case = ConversationInput(prompt="Same contact as last.", previous_messages=[
        HistoryMessage(role="user", content="Create an invoice for Bob's Construction for $55 for Labour."),
        HistoryMessage(role="assistant", content="The confirmed invoice for Bob's Construction for $55 was created as INV-1001."),
        HistoryMessage(role="user", content="Create another invoice for $200 for consulting."),
        HistoryMessage(role="assistant", content="Which contact should I use? You can also provide a reference or due date."),
    ])
    output = await run_scored_prompt(
        build_chat_agent(scripted_orchestrator_model(), build_mcp_server()),
        FakeInvoiceGateway(), tmp_path, case,
    )
    assert output.count("call propose_action") == 1
    assert "pending" in output
    assert '\\"unit_amount\\": 200' in output
    assert "consulting" in output


@pytest.mark.asyncio
async def test_contact_without_email_proposes(tmp_path: Path) -> None:
    """A contact name alone produces one pending contact proposal without an email."""
    result = await _run(tmp_path, "Create a contact named Cedar Demo Supplies.", FakeInvoiceGateway())
    assert _tool_names(result) == ["propose_action"]
    calls = [
        part for message in result.new_messages() for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert calls[0].args_as_dict()["action_type"] == "create_contact"
    assert json.loads(calls[0].args_as_dict()["payload_json"]) == {"name": "Cedar Demo Supplies"}
    assert "pending" in _tool_returns(result, "propose_action")[0]


@pytest.mark.asyncio
async def test_scored_history_is_protected(tmp_path: Path) -> None:
    """Actual historical messages and latest prompts reach the model with one request vault."""
    seen: list[str] = []

    def respond(messages, _info):  # type: ignore[no-untyped-def]
        """Capture provider-facing history without returning its sensitive values."""
        seen.append(str(messages))
        return ModelResponse(parts=[TextPart(content="Nothing was created.")])

    case = ConversationInput(prompt="Use current@example.com.", previous_messages=[
        HistoryMessage(role="assistant", content="The prior email was prior@example.com and sk-abcdefghijklmnopqrstuvwxyz123456."),
    ])
    await run_scored_prompt(
        build_chat_agent(FunctionModel(respond), build_mcp_server()),
        FakeInvoiceGateway(), tmp_path, case,
    )
    assert seen
    text = " ".join(seen)
    assert "current@example.com" not in text
    assert "prior@example.com" not in text
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "[redacted_email:" in text
    assert current_vault.get() is None
    assert current_guardrail_context.get() is None


@pytest.mark.asyncio
async def test_required_amount_still_needs_clarification(tmp_path: Path) -> None:
    """An optional reference does not fill a missing required amount."""
    result = await _run(tmp_path, "Create an invoice for Bob's Construction for Labour. Reference PO-9.", FakeInvoiceGateway())
    assert "propose_action" not in _tool_names(result)
    assert "amount" in result.output


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
